"""Academy qualification gate for Gold Elevate Pool (Master Prompt v4.0 §7, Spec v4.1 §1.2).

Rule: a member needs THREE NEW, completed Academy videos for the applicable cycle.
- Only videos the member has actually finished count (backend-recorded watch progress).
- A video already consumed by an earlier qualification batch can never be reused (v4 §7.3).
- Pure function: the caller supplies the watched ids and the already-used ids.
"""
from __future__ import annotations

ACADEMY_NEW_VIDEOS_REQUIRED = 3


def academy_qualification(watched_video_ids: set[str], used_video_ids: set[str]) -> dict:
    available_new = sorted(v for v in watched_video_ids if v not in used_video_ids)
    completed = len(available_new)
    required = ACADEMY_NEW_VIDEOS_REQUIRED
    return {
        "qualified": completed >= required,
        "new_videos_completed": min(completed, required),
        "new_videos_required": required,
        "remaining": max(0, required - completed),
        # The batch that would be consumed on issuance/qualification (deterministic order).
        "batch_candidate": available_new[:required] if completed >= required else [],
    }
