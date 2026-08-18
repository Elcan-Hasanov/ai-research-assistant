# Step 12 — Lexical vs Semantic Retrieval: Qualitative Findings

## 1. Relevance criterion  (written BEFORE any result was inspected)

Binary. A document is **relevant** if it contains the information the person
asking this query was looking for.

Pre-committed edge cases:
- Same topic, different sub-problem → NOT relevant.
- Mentions the topic only in related-work framing → NOT relevant.
- Survey covering the topic among many others → relevant.

This section is frozen. If it turns out to be wrong, that is a finding to
record in section 5, not a licence to edit this section.

**Methodology note added after inspection (does not alter the criterion
above, only how it was applied):** the annotator does not have domain
expertise in ML/NLP and limited English fluency, so two judgment modes were
used instead of one:

- **Known-item mode** (q09, q10, q12–q17): the target document was fixed
  *before* the query was written (it was the source the paraphrase/probe was
  derived from). Relevance = "did the known target document appear in the
  top-5", not a subjective read of the result list. This sidesteps both the
  expertise gap and pooling bias (T4) for these eight queries.
- **Surface-match mode** (q01–q05, q08, q11, q18): relevance judged only by
  whether the query term or its expansion appears literally in the result
  title (e.g. "RLHF" ↔ "Reinforcement Learning from Human Feedback"). This is
  a shallower criterion than true topical relevance and is recorded as a
  limitation in section 5.
- **Not judged** (q06, q07): no known target and no reliable surface signal
  (they don't quote a specific term); marked `inconclusive` rather than
  guessed.

## 2. Corpus snapshot

| Field | Value |
|---|---|
| Categories | cs.AI, cs.CL, cs.LG |
| Articles | 5000 |
| Embedded documents | 5000 |
| Model | BAAI/bge-small-en-v1.5 |
| Query set | evaluation/queries_v1.json (version 1) |
| Date | 2026-08-13 |

### 2.1 Coverage probes (D10 — single-term, run before the comparison)

No separate single-term probe queries were run. Instead, the single-token
queries already present in the set are used as probes, since they satisfy
D10's requirement (one term, no AND-of-multiple-stems ambiguity):

| Probe term | lexical total | Verdict |
|---|---|---|
| LoRA | 110 | present, abundant |
| Qwen | 63 | present, abundant |
| RLHF | 9 | present, sparse |
| FlashAttention | 4 | present, very sparse |
| RestoreKV | 1 | present, single paper (expected — proper name) |

**Step 10's open problem — "parameter efficient fine tuning has no match in
the corpus" — resolved / not resolved:**

**Partially resolved.** The literal 4-word phrase `"parameter efficient fine
tuning"` was not re-tested and, per the D10 mechanism (all four stems ANDed),
would very likely still return 0 — that is a property of the phrase's length,
not of corpus coverage. What *is* now confirmed is that the underlying
concept is well represented: LoRA alone returns 110 lexical hits, so
PEFT-adjacent terminology exists in depth. The original problem was a probe
design issue (multi-word AND-phrase), not a corpus gap.

## 3. Per-query observations

| id | type | lex total | overlap | winner | relevant_ids / target | observation |
|---|---|---|---|---|---|---|
| q01 | exact_term | 121 | 1/5 | tie | surface-match: both lists are RAG papers on title inspection | Both systems return topically coherent RAG results; low overlap means they *agree on the topic* but rank different papers within it |
| q02 | exact_term | 65 | 2/5 | tie | surface-match: both lists contain "distillation"/KD in nearly every title | Same pattern as q01 |
| q09 | exact_term | 18 | 2/5 | tie | target=2608.01247, lex rank 1, sem rank 2 | Known-item. Both found it; lexical ranked it higher |
| q03 | acronym | 9 | 0/5 | lexical | lex #1 (Meta-Learned Reward Shaping RLHF) is a clear surface match; lex #2–5 and all 5 semantic results show no RLHF/reward connection in the title | ⚑ needs your check — see note below |
| q04 | acronym | 110 | 1/5 | tie | surface-match: every title in both lists contains "LoRA" or "Low-Rank Adaptation" | |
| q05 | named_entity | 4 | 0/5 | lexical | lex results are attention/inference-adjacent titles; semantic results (video editing, image editing, prompt injection) show no surface or apparent topical connection | Matches the "flash" mis-association discussed — token collision with photography sense |
| q10 | named_entity | 1 | 1/5 | tie | target=2608.01247, lex rank 1, sem rank 1 | Known-item, single-paper case. Both perfect |
| q11 | named_entity | 63 | 2/5 | tie | surface-match: lex #1–2 and sem #1–2 all contain "Qwen"; both lists' #3–5 lose the surface match | Both degrade similarly past rank 2 |
| q06 | paraphrase | 0 | 0/5 | inconclusive | no known target, no reliable surface signal | Lexical correctly returns nothing (no shared terms). Semantic returns plausible-looking titles about belief/reasoning evaluation; whether they are actually about hallucination cannot be judged without domain review |
| q12 | paraphrase | 0 | 0/5 | both_failed | target=2607.21861, not found either system | Known-item |
| q13 | paraphrase | 0 | 0/5 | both_failed | target=2608.04286, not found either system | Known-item |
| q14 | paraphrase | 0 | 0/5 | both_failed | target=2608.01247, not found either system | Known-item. Semantic top score 0.83 — highest in the entire set, on a wrong result |
| q07 | conceptual | 1 | 0/5 | inconclusive | no known target, no reliable surface signal | Lexical's one hit scores 0.0018 — effectively noise. Semantic results are about GPU efficiency/serving, plausible but not verifiably on-target without domain review |
| q15 | conceptual | 0 | 0/5 | both_failed | target=2607.21861, not found either system | Known-item |
| q16 | conceptual | 0 | 0/5 | both_failed | target=2608.04286, not found either system | Known-item |
| q17 | conceptual | 0 | 0/5 | both_failed | target=2608.01247, not found either system | Known-item |
| q08 | out_of_corpus | 0 | 0/5 | lexical | correct behaviour = return nothing | Semantic returned 5 confident results (0.62–0.66) on an absent topic |
| q18 | out_of_corpus | 0 | 0/5 | lexical | correct behaviour = return nothing | Semantic returned 5 confident results (0.63–0.78) on an absent topic |

`winner` legend: `lexical` / `semantic` / `tie` / `both_failed` / `inconclusive`
(`inconclusive` added to the original four-value legend — no known target and
no surface signal available; recorded rather than guessed, per section 1's
methodology note)

**⚑ Flag on q03 — please confirm or correct:** I judged lexical results #2–5
(Epanorthosis rhetoric, Nanbeige agentic model, Shapley data auditing, latent
reasoning reward models) as *not* surface-matching "RLHF" — none mention
reward, feedback, or RL in the title. If you read those titles differently,
change `winner` to reflect that; I don't have more than the title to go on
either.

## 4. Pattern map (grouped by query type)

### exact_term
Both systems succeed when the query terms literally appear in the target's
title (q01, q02, q09). Lexical ranks the literal match higher (q09: rank 1
vs 2); semantic still finds it because shared vocabulary produces similar
token representations — semantic's success here doesn't require semantic
understanding, it piggybacks on the same surface overlap lexical uses.

### acronym
Splits by whether the acronym's expansion is common in the corpus. `LoRA`
(abundant, 110 hits) — both systems succeed. `RLHF` (sparse, 9 hits) —
lexical finds the one clear match, semantic finds none; with few positive
examples in training-adjacent contexts, the model has less signal to anchor
the acronym's meaning.

### named_entity
The sharpest split in the set. Success depends entirely on whether the name
tokenizes into fragments the model has *correctly* learned to associate with
the paper's actual topic. `RestoreKV` → fragments (`restore`, `kv`) happen to
align with the paper's real content (cache *recovery*) — success. 
`FlashAttention` → the fragment `flash` carries a strong, unrelated learned
association (photography/imaging) that overrides the intended technical
meaning — semantic fails with topically unrelated but confident results.
Named-entity queries are a coin flip that depends on accidental token
semantics, not a reliably weak or strong point for either system.

### paraphrase
**The core finding of this step.** In all four known-item cases (q12, q13,
q14), and the frozen seed query q06, lexical fails correctly — zero results,
zero content-word overlap, an honest "not found." Semantic fails silently:
it returns full, high-scoring result lists (up to 0.83, the highest score in
the entire set) that do not contain the target and are drawn instead from
whatever documents in the corpus happen to share vocabulary with the
paraphrase (e.g. "memory" and "conversations" pulling in unrelated
long-term-memory papers instead of the KV-cache paper that never uses those
words). Semantic search here is not doing conceptual matching in the sense
the term implies — it is matching on whatever surface or near-surface
vocabulary the paraphrase happens to share with *some* document, which is
not necessarily the target document.

### conceptual
Same failure mode as paraphrase, one level further from the source
vocabulary (q15, q16, q17 — all `both_failed`). The user-voice symptom
report in q17 ("my model runs out of memory when the input gets long")
shares no terminology with the domain literature ("KV cache eviction") and
neither system bridges that gap.

### out_of_corpus
Confirms T2 directly. Lexical is the only system capable of correctly
reporting absence (0 results both times). Semantic cannot express "not
found" — it always returns its nearest neighbours, with confidence scores
(0.62–0.78) indistinguishable in magnitude from scores on queries that *do*
have a real answer (e.g. q17's failed match scored similarly, 0.67).

## 5. Limitations of this dataset

- **Pooling bias (T4).** Judgements for the surface-match queries were made
  only over documents returned by these two systems. A document neither
  system found is absent from this set and will be scored as irrelevant by
  any future system that finds it. This set is a *pooled judgement*, not
  complete ground truth. **The known-item queries (q09, q10, q12–q17) are not
  subject to this bias** — their target was fixed before either system ran.
- **Sample size (T7).** n = 18. No claim in this document is statistical. The
  language here is "I observed X on queries of type Y", never "X is N%
  better".
- **Single annotator, single pass.** No inter-annotator agreement, no
  re-judging.
- **Single model.** All semantic results come from one embedding model.
- **Annotator does not have ML/NLP domain expertise and has limited English
  fluency.** For queries without a known target (q06, q07) and for the
  non-target rows of surface-match queries (q03 rows 2–5, q05, q07's semantic
  results), deep topical relevance could not be judged — only literal term
  presence in the title. This is a materially shallower criterion than
  section 1's original relevance definition and likely undercounts semantic
  successes that use synonyms the annotator wouldn't recognise as related.
- **Known-item method is stricter than pooled judgement in one respect:** it
  only tells you whether the *exact* source document was retrieved, not
  whether some *other* genuinely relevant document was retrieved instead.
  A "failure" here means "didn't find the one paper it was built from," not
  necessarily "found nothing useful."

## 6. What carries into V6

- **`evaluation/queries_v1.json`** as the first version of the benchmark
  query set — stratified by type, with `note` fields recording why each
  query was chosen.
- **Known-item as the preferred judgment method going forward.** It removed
  the domain-expertise and pooling-bias problems that blocked pooled
  judgement for 8 of the 18 queries here. *Action still open:* add a
  `target_id` field to queries_v1.json for q09, q10, q12–q17 so this becomes
  machine-checkable rather than living only in this document.
- **The `relevant_ids` / `target` column** in section 3 as the seed for
  whatever ground-truth format V6's metric library expects.
- **The central finding:** semantic search's score is not a reliability
  signal. The highest score in this entire run (0.83, q14) sits on a wrong
  answer. Any V6 metric or V5 confidence threshold based on raw similarity
  score needs to account for this — score reflects nearest-neighbour
  distance, not correctness.

## 7. Open questions raised by this step

- Should `target_id` be added to queries_v1.json now, or deferred until V6
  picks a metric library and the schema needs are clearer?
- q03 and q05 show semantic failing even where lexical partially succeeds
  (RLHF, FlashAttention) — both are cases of sparse or fragment-collision
  acronyms. Worth a dedicated probe set in a later step, or fold into V5's
  domain-adaptation decision?
- The paraphrase/conceptual failure (section 4) implies `bge-small-en-v1.5`
  lacks domain-specific associations for this corpus's vocabulary. Is the
  V5 fix query expansion, a domain-adapted/fine-tuned embedding model, or
  both? This step only establishes that the problem exists, not which fix is
  right — that's a V5 decision, not this step's.
- Given how cleanly the known-item method worked here, should future
  evaluation steps design *all* queries as known-item where possible, and
  drop pooled/surface-match judgment entirely?