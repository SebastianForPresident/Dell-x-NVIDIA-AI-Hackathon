"""One canonical MongoDB configuration and authoritative business service."""

from functools import lru_cache

from investigations import InvestigationService
from persistence import MongoStore


@lru_cache(maxsize=1)
def get_service():
    return InvestigationService(MongoStore.from_env())
