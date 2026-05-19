"""In-memory store for VoucherDraft instances.

Thread-safe via asyncio.Lock.  All mutations go through this store so that
callers never hold a reference to the internal dict directly.

Only homologación drafts are supported at this stage.
"""

import asyncio
from datetime import datetime, timezone

from arca_mcp.invoicing.models import DraftStatus, VoucherDraft


class DraftNotFoundError(Exception):
    """Raised when a draft_id does not exist in the store."""

    def __init__(self, draft_id: str) -> None:
        super().__init__(f"Draft not found: {draft_id}")
        self.draft_id = draft_id


class InvalidStatusTransitionError(Exception):
    """Raised when a requested status transition is not allowed."""

    def __init__(
        self, draft_id: str, current: DraftStatus, requested: DraftStatus
    ) -> None:
        super().__init__(
            f"Cannot transition draft {draft_id} from {current} to {requested}."
        )
        self.draft_id = draft_id
        self.current = current
        self.requested = requested


# Allowed forward transitions.
_ALLOWED_TRANSITIONS: dict[DraftStatus, set[DraftStatus]] = {
    DraftStatus.PENDING: {DraftStatus.VALIDATED, DraftStatus.REJECTED},
    DraftStatus.VALIDATED: {DraftStatus.CONFIRMED, DraftStatus.REJECTED},
    DraftStatus.CONFIRMED: set(),
    DraftStatus.REJECTED: set(),
}


class DraftStore:
    """Async-safe in-memory store for VoucherDraft objects.

    Usage::

        store = DraftStore()
        draft = await store.create(my_draft)
        retrieved = await store.get(draft.draft_id)
        updated = await store.update_status(draft.draft_id, DraftStatus.VALIDATED)
    """

    def __init__(self) -> None:
        self._store: dict[str, VoucherDraft] = {}
        self._lock = asyncio.Lock()

    async def create(self, draft: VoucherDraft) -> VoucherDraft:
        """Persist a new draft in the store and return it.

        Raises:
            ValueError: if a draft with the same draft_id already exists.
        """
        async with self._lock:
            if draft.draft_id in self._store:
                raise ValueError(
                    f"Draft with id '{draft.draft_id}' already exists."
                )
            self._store[draft.draft_id] = draft
            return draft

    async def get(self, draft_id: str) -> VoucherDraft | None:
        """Return the draft for *draft_id*, or None if not found."""
        async with self._lock:
            return self._store.get(draft_id)

    async def update_status(
        self, draft_id: str, new_status: DraftStatus
    ) -> VoucherDraft:
        """Transition *draft_id* to *new_status* and return the updated draft.

        Raises:
            DraftNotFoundError: if the draft does not exist.
            InvalidStatusTransitionError: if the transition is not allowed.
        """
        async with self._lock:
            draft = self._store.get(draft_id)
            if draft is None:
                raise DraftNotFoundError(draft_id)

            allowed = _ALLOWED_TRANSITIONS[draft.status]
            if new_status not in allowed:
                raise InvalidStatusTransitionError(draft_id, draft.status, new_status)

            updated = draft.model_copy(
                update={
                    "status": new_status,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._store[draft_id] = updated
            return updated

    async def clear(self) -> None:
        """Remove all drafts from the store (useful for tests)."""
        async with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
