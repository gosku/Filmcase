import attrs

from src.domain.recipes import operations as domain_operations
from src.domain.recipes.queries import CollectionNotFound as DomainCollectionNotFound


@attrs.frozen
class CollectionNotFound(Exception):
    """
    Raised when no collection with the given id exists.
    """

    collection_id: int


def delete_collection(*, collection_id: int) -> None:
    """
    Delete the collection with *collection_id*.

    :raises CollectionNotFound: If no collection with *collection_id* exists.
    """
    try:
        domain_operations.delete_collection(collection_id=collection_id)
    except DomainCollectionNotFound as exc:
        raise CollectionNotFound(collection_id=exc.collection_id)
