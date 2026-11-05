"""Shared test helpers.

Every report now ends with the urgency question ("how urgent is this?"), which is asked LAST and is never guessed.
Tests about other behaviour either look past it (`blockers`, `asking`) or answer it the way a person would (`settle`).
"""
from backend.app.domain.issues import next_blocker
from backend.app.domain.schemas import IssueType


def blockers(draft):
    """Blocking issues other than the final urgency question."""
    return [i for i in draft.open_blockers() if i.type != IssueType.MISSING_URGENCY]


def asking(result):
    """The type of the open question, ignoring the final urgency question (None when only urgency is left)."""
    q = result.question
    return q.issue_type if q is not None and q.issue_type != IssueType.MISSING_URGENCY else None


def settle(p, sid, level="can_wait"):
    """Answer the urgency question if (and only if) it is the one that is open."""
    issue = next_blocker(p.store.draft(sid))
    if issue is not None and issue.type == IssueType.MISSING_URGENCY:
        p.choose(sid, issue.id, level)
    return p.store.draft(sid)


def review(p, sid, *args):
    """Review after answering the urgency question."""
    settle(p, sid)
    return p.review(sid, *args)
