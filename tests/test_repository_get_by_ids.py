import pytest

from tests.factories import insert_article


pytestmark = pytest.mark.db

IDS = ["2601.00001", "2601.00002", "2601.00003", "2601.00004", "2601.00005"]


@pytest.fixture
async def seeded(db_conn):
    for index, arxiv_id in enumerate(IDS, start=1):
        await insert_article(db_conn, arxiv_id, title=f"Test Article {index}")
    return IDS


async def test_empty_input_returns_empty_list(repository, seeded):
    assert await repository.get_by_ids([]) == []


async def test_unknown_ids_are_silently_omitted(repository, seeded):
    assert await repository.get_by_ids(["9999.99999", "9999.99998"]) == []


async def test_mixture_of_known_and_unknown_returns_only_the_known(
    repository, seeded
):
    rows = await repository.get_by_ids([IDS[0], "9999.99999"])

    assert [row["arxiv_id"] for row in rows] == [IDS[0]]


async def test_repeated_ids_produce_one_row_each(repository, seeded):
    rows = await repository.get_by_ids([IDS[0], IDS[0], IDS[0]])

    assert len(rows) == 1
    assert rows[0]["arxiv_id"] == IDS[0]


async def test_result_is_a_set_of_rows_and_carries_no_order_guarantee(
    repository, seeded
):
    """Ensure callers do not rely on input order being preserved.

    The repository query has no ORDER BY, so result order is not part of the
    method's contract.
    """
    forward = await repository.get_by_ids(IDS)
    backward = await repository.get_by_ids(list(reversed(IDS)))

    assert {row["arxiv_id"] for row in forward} == set(IDS)
    assert {row["arxiv_id"] for row in backward} == set(IDS)


async def test_returns_only_the_narrow_column_set(repository, seeded):
    rows = await repository.get_by_ids([IDS[0]])

    assert set(rows[0].keys()) == {"arxiv_id", "title"}


async def test_rows_are_plain_dicts_not_asyncpg_records(repository, seeded):
    rows = await repository.get_by_ids([IDS[0]])

    assert type(rows[0]) is dict