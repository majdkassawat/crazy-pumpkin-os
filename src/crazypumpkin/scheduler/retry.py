"""Retry logic for scheduler jobs — backoff calculation and failure handling."""

from __future__ import annotations

from crazypumpkin.framework.models import JobStatus, PersistedJob, _now


def calculate_backoff(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """Calculate exponential backoff delay in seconds.

    Returns ``min(base * 2**attempt, cap)``.  *attempt* is clamped to >= 0.
    """
    if attempt < 0:
        attempt = 0
    delay = base * (2 ** attempt)
    return min(delay, cap)


def handle_job_failure(job: PersistedJob, error: str) -> None:
    """Transition a job after a failure.

    Increments ``attempt``.  If ``attempt >= max_retries`` the job moves to
    DEAD_LETTER; otherwise it moves to FAILED (eligible for retry).
    """
    job.attempt += 1
    job.error = error
    job.updated_at = _now()

    if job.attempt >= job.max_retries:
        job.status = JobStatus.DEAD_LETTER
    else:
        job.status = JobStatus.FAILED


def complete_job(job: PersistedJob) -> None:
    """Mark a job as successfully completed."""
    job.status = JobStatus.SUCCEEDED
    job.error = ""
    job.updated_at = _now()
