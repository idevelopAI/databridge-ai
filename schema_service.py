from functools import lru_cache

from database import get_schema_metadata as inspect_schema_metadata
from privacy_policy import filter_schema_by_policy


@lru_cache(maxsize=1)
def get_schema_metadata() -> list[dict]:
    return filter_schema_by_policy(inspect_schema_metadata())


def clear_schema_cache() -> None:
    get_schema_metadata.cache_clear()
