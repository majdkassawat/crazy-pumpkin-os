"""Tests for scheduler retry logic — backoff, failure handling, completion."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.models import JobStatus, PersistedJob
from crazypumpkin.scheduler.retry import calculate_backoff, complete_job, handle_job_failure


class TestCalculateBackoff:
    def test_attempt_zero(self):
        assert calculate_backoff(0) == 1.0  # base * 2^0

    def test_mid_attempt(self):
        assert calculate_backoff(3) == 8.0  # 1.0 * 2^3

    def test_cap_reached(self):
        assert calculate_backoff(10, base=1.0, cap=60.0) == 60.0

    def test_negative_attempt_clamped(self):
        assert calculate_backoff(-5) == 1.0  # treated as attempt=0

    def test_custom_base(self):
        assert calculate_backoff(2, base=2.0) == 8.0  # 2.0 * 2^2

    def test_custom_cap(self):
        assert calculate_backoff(5, base=1.0, cap=10.0) == 10.0


class TestHandleJobFailure:
    def test_retry_when_under_max(self):
        job = PersistedJob(job_id="j1", max_retries=3, attempt=0)
        handle_job_failure(job, "timeout")
        assert job.attempt == 1
        assert job.status == JobStatus.FAILED
        assert job.error == "timeout"

    def test_dead_letter_when_max_reached(self):
        job = PersistedJob(job_id="j1", max_retries=2, attempt=1)
        handle_job_failure(job, "crash")
        assert job.attempt == 2
        assert job.status == JobStatus.DEAD_LETTER
        assert job.error == "crash"

    def test_dead_letter_when_already_over_max(self):
        job = PersistedJob(job_id="j1", max_retries=1, attempt=5)
        handle_job_failure(job, "oops")
        assert job.status == JobStatus.DEAD_LETTER

    def test_updates_timestamp(self):
        job = PersistedJob(job_id="j1", max_retries=5, attempt=0)
        old_ts = job.updated_at
        handle_job_failure(job, "err")
        assert job.updated_at >= old_ts


class TestCompleteJob:
    def test_sets_succeeded(self):
        job = PersistedJob(job_id="j1", status=JobStatus.RUNNING, error="old error")
        complete_job(job)
        assert job.status == JobStatus.SUCCEEDED
        assert job.error == ""

    def test_updates_timestamp(self):
        job = PersistedJob(job_id="j1", status=JobStatus.RUNNING)
        old_ts = job.updated_at
        complete_job(job)
        assert job.updated_at >= old_ts
