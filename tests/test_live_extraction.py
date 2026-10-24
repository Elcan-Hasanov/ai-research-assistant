"""A live check of the contract the extraction tests assume of the provider.

Every other test replaces the provider: FakeLLMClient above the client, a
recorded body below it. This one sends the production extraction request, for
the article the response-variability measurement used, to the real gateway
once, and checks only what production relies on. A red result means the
provider side changed, or a rare real event happened; the comment on each
assertion says where to look.

It is billed, so it runs only when asked for: pytest --live -m live.
It needs no database.
"""

import pytest

from app.core.config import get_settings
from app.core.llm import CompletionStop, create_llm_client
from app.generation.extraction import parse_paper_facts
from app.services.generation_service import extraction_request
from tests.conftest import load_recording

pytestmark = pytest.mark.live


async def test_the_provider_answers_extraction_as_our_doubles_assume():
    # The direct path never reports a cost, and nothing is deployed on it yet:
    # its live check is added when something is.
    if not get_settings().llm_base_url:
        pytest.skip("checks the gateway path; LLM_BASE_URL is not set")

    # The measured article: the expectations below were measured on it.
    article = load_recording("extract_paper_facts.v1")["article"]
    request = extraction_request(article)

    client = create_llm_client()
    try:
        completion = await client.complete(**request.to_completion_kwargs())
    finally:
        await client.aclose()

    # First, because the schema guarantee below holds only for an answer that
    # completed. Red: run it again; if it repeats, look at the model, the
    # prompt and the provider. Production would be answering 500 or 422.
    assert completion.stop == CompletionStop.COMPLETED

    # Raises if the answer does not fit PaperFacts. Red: look for a markdown
    # fence in the text and at which provider served the call; a provider
    # without structured outputs ignores output_config.
    parse_paper_facts(completion.text)

    # Red: the gateway moved or dropped the cost, and production is storing it
    # as unknown without a word. Record a new response and see where it went.
    assert completion.reported_cost_usd is not None
    assert completion.reported_cost_usd > 0

    # Red: the gateway stopped reporting token counts, which the attempt
    # records store.
    assert completion.input_tokens > 0
    assert completion.output_tokens > 0