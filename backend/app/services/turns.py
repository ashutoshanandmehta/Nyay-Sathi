"""Local turn coordination. Scope is supplied by the authenticated API only."""

import asyncio
from collections import defaultdict


class TurnCoordinator:
    def __init__(self):
        self._locks = defaultdict(asyncio.Lock)

    def lock_for(self, owner_id: str, case_id: str) -> asyncio.Lock:
        return self._locks[(owner_id, case_id)]
