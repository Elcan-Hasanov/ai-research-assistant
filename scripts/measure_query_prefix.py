import argparse
import asyncio
import logging

import numpy as np

from app.core.config import get_settings
from app.core.database import create_script_pool
from app.core.embedding import EmbeddingModel, create_embedding_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

# BAAI's documented instruction prefix for bge-* retrieval queries.
# Applied to the QUERY side only — never to passages.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Deliberately mixed query shapes: exact terminology, acronyms, paraphrase,
# and purely conceptual phrasing. A prefix that matters should not matter
# uniformly across these.
DEFAULT_QUERIES = [
    "retrieval augmented generation",
    "RLHF",
    "how do transformers handle long context windows",
    "reducing hallucination in language models",
    "mixture of experts routing",
    "parameter efficient fine tuning",
    "what makes a good sentence embedding",
    "vector database approximate nearest neighbor search",
    "chain of thought prompting",
    "model distillation for smaller models",
]


async def fetch_corpus(model_name: str) -> tuple[list[str], list[str], np.ndarray]:
    """Load every stored vector for one model into memory.

    Inline SQL is deliberate: this is a lab-scope read that has no place on the
    API surface, and keeping it here avoids widening the repository contract
    for a throwaway measurement.
    """
    pool = await create_script_pool(min_size=1, max_size=2)
    try:
        rows = await pool.fetch(
            """
            SELECT a.arxiv_id, a.title, e.embedding
            FROM article_embeddings e
            JOIN articles a ON a.arxiv_id = e.arxiv_id
            WHERE e.model_name = $1
            ORDER BY a.arxiv_id;
            """,
            model_name,
        )
    finally:
        await pool.close()

    if not rows:
        return [], [], np.empty((0, 0), dtype=np.float32)

    ids = [row["arxiv_id"] for row in rows]
    titles = [row["title"] for row in rows]
    matrix = np.vstack(
    [np.asarray(row["embedding"].to_list(), dtype=np.float32) for row in rows]
    )
    return ids, titles, matrix


def report_corpus_facts(matrix: np.ndarray) -> None:
    norms = np.linalg.norm(matrix, axis=1)

    print("\n" + "=" * 68)
    print(f"CORPUS  (n = {matrix.shape[0]}, dim = {matrix.shape[1]})")
    print("=" * 68)
    print(f"  stored L2 norm  min : {norms.min():.6f}")
    print(f"  stored L2 norm  max : {norms.max():.6f}")

    if np.allclose(norms, 1.0, atol=1e-3):
        print("  -> Stored vectors ARE normalized. dot product == cosine similarity.")
    else:
        print("  -> Stored vectors are NOT normalized.")
        print("     STOP. The backfill did not normalize; every comparison below is invalid.")


def report_st_prompt_behavior(model: EmbeddingModel) -> bool:
    """Determine empirically whether encode_query() injects anything.

    Reaches into the private SentenceTransformer to obtain a raw, prompt-free
    encoding. Acceptable here precisely because this file is a measurement
    script and not part of the application; production code must not do this.
    """
    raw = model._model
    probe = "vector search"

    via_query = np.asarray(
        raw.encode_query(probe, normalize_embeddings=True, convert_to_numpy=True)
    )
    via_raw = np.asarray(
        raw.encode(probe, normalize_embeddings=True, convert_to_numpy=True)
    )
    identical = bool(np.allclose(via_query, via_raw, atol=1e-6))

    print("\n" + "=" * 68)
    print("SENTENCE-TRANSFORMERS PROMPT BEHAVIOUR")
    print("=" * 68)
    print(f"  model.prompts             : {raw.prompts}")
    print(f"  model.default_prompt_name : {raw.default_prompt_name}")
    print(f"  encode_query == encode    : {identical}")

    if identical:
        print("\n  -> encode_query() applies NO prefix. Option A == no instruction at all.")
    else:
        print("\n  -> encode_query() DOES apply a prefix. Manual injection would DOUBLE it.")
    return identical


def top_k(matrix: np.ndarray, vector: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    scores = matrix @ vector
    order = np.argsort(-scores, kind="stable")[:k]
    return order, scores[order]


def encode_pair(model: EmbeddingModel, query: str) -> tuple[np.ndarray, np.ndarray]:
    plain = np.asarray(model.encode_query(query), dtype=np.float32)
    prefixed = np.asarray(
        model.encode_query(BGE_QUERY_PREFIX + query), dtype=np.float32
    )
    return plain, prefixed


def compare_query(
    model: EmbeddingModel,
    matrix: np.ndarray,
    query: str,
    k: int,
) -> tuple[float, bool, float, np.ndarray, np.ndarray]:
    plain_vec, prefixed_vec = encode_pair(model, query)
    query_similarity = float(plain_vec @ prefixed_vec)

    plain_idx, _ = top_k(matrix, plain_vec, k)
    prefixed_idx, _ = top_k(matrix, prefixed_vec, k)

    overlap = len(set(plain_idx.tolist()) & set(prefixed_idx.tolist())) / k
    top1_same = bool(plain_idx[0] == prefixed_idx[0])
    return overlap, top1_same, query_similarity, plain_idx, prefixed_idx


def print_side_by_side(
    query: str, titles: list[str], plain_idx: np.ndarray, prefixed_idx: np.ndarray
) -> None:
    print(f"\n  QUERY: {query!r}")
    print(f"  {'NO PREFIX':<46} | {'WITH PREFIX':<46}")
    print("  " + "-" * 95)
    for left, right in zip(plain_idx[:5], prefixed_idx[:5]):
        print(f"  {titles[left][:44]:<46} | {titles[right][:44]:<46}")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure whether the BAAI query instruction prefix changes ranking."
    )
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--top-k", type=int, default=10, help="Ranking depth to compare")
    parser.add_argument(
        "--show", type=int, default=3, help="How many most-divergent queries to print in full"
    )
    args = parser.parse_args()

    settings = get_settings()
    model_name = args.model or settings.embedding_model_name

    model = create_embedding_model(model_name)
    report_st_prompt_behavior(model)

    ids, titles, matrix = await fetch_corpus(model_name)
    if not ids:
        logger.error(
            "No embeddings stored for model %r. Run scripts.backfill_embeddings first.",
            model_name,
        )
        return 1
    report_corpus_facts(matrix)

    k = min(args.top_k, len(ids))
    results = []
    for query in DEFAULT_QUERIES:
        results.append((query, *compare_query(model, matrix, query, k)))

    overlaps = [row[1] for row in results]
    top1_changes = sum(1 for row in results if not row[2])
    query_sims = [row[3] for row in results]

    print("\n" + "=" * 68)
    print(f"PREFIX IMPACT  (top-{k}, n_queries = {len(results)})")
    print("=" * 68)
    print(f"  mean overlap@{k}        : {np.mean(overlaps):.3f}")
    print(f"  min  overlap@{k}        : {np.min(overlaps):.3f}")
    print(f"  top-1 changed          : {top1_changes} / {len(results)}")
    print(f"  mean query-vector cos  : {np.mean(query_sims):.4f}")

    print("\n  Per query:")
    for query, overlap, top1_same, sim, _, _ in results:
        flag = " " if top1_same else "*"
        print(f"   {flag} overlap={overlap:.2f}  qcos={sim:.4f}  {query}")

    for query, _, _, _, plain_idx, prefixed_idx in sorted(results, key=lambda r: r[1])[: args.show]:
        print_side_by_side(query, titles, plain_idx, prefixed_idx)

    print("\n" + "=" * 68 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))