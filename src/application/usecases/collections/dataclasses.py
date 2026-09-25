import attrs


@attrs.frozen
class CollectionData:
    collection_id: int
    name: str
