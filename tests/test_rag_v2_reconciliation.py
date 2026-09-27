from uuid import UUID

from src.qdrant_index import QdrantVectorIndex


class FakePoint:
    def __init__(self, point_id: str):
        self.id = point_id


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    def collection_exists(self, _name):
        return True

    def scroll(self, **_kwargs):
        page = self.pages[self.calls]
        self.calls += 1
        return page


def test_qdrant_point_ids_are_collected_across_scroll_pages() -> None:
    first = "00000000-0000-0000-0000-000000000001"
    second = "00000000-0000-0000-0000-000000000002"
    client = FakeClient(
        [
            ([FakePoint(first)], second),
            ([FakePoint(second)], None),
        ]
    )

    ids = QdrantVectorIndex(client=client).list_point_ids()

    assert ids == {UUID(first), UUID(second)}
    assert client.calls == 2
