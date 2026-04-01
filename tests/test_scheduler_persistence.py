"""Tests for PersistedJob model and Store job persistence."""

import pytest

from crazypumpkin.framework.models import JobStatus, PersistedJob
from crazypumpkin.framework.store import Store


class TestPersistedJobModel:
    def test_default_values(self):
        job = PersistedJob()
        assert job.job_id  # auto-generated
        assert job.name == ""
        assert job.status == JobStatus.PENDING
        assert job.attempt == 0
        assert job.max_retries == 3
        assert job.payload == {}
        assert job.error == ""
        assert job.created_at
        assert job.updated_at

    def test_custom_creation(self):
        job = PersistedJob(
            job_id="j1",
            name="build-widget",
            status=JobStatus.RUNNING,
            attempt=1,
            max_retries=5,
            payload={"task_id": "t1"},
            error="",
        )
        assert job.job_id == "j1"
        assert job.name == "build-widget"
        assert job.status == JobStatus.RUNNING
        assert job.max_retries == 5
        assert job.payload == {"task_id": "t1"}

    def test_job_status_values(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.SUCCEEDED.value == "succeeded"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.DEAD_LETTER.value == "dead_letter"


class TestJobStoreRoundTrip:
    def test_save_and_get(self):
        store = Store()
        job = PersistedJob(job_id="j1", name="test-job")
        store.save_job(job)
        assert store.get_job("j1") is job

    def test_get_missing_returns_none(self):
        store = Store()
        assert store.get_job("nonexistent") is None

    def test_list_all_jobs(self):
        store = Store()
        store.save_job(PersistedJob(job_id="j1", name="a"))
        store.save_job(PersistedJob(job_id="j2", name="b"))
        jobs = store.list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_filter_by_status(self):
        store = Store()
        store.save_job(PersistedJob(job_id="j1", status=JobStatus.PENDING))
        store.save_job(PersistedJob(job_id="j2", status=JobStatus.FAILED))
        store.save_job(PersistedJob(job_id="j3", status=JobStatus.PENDING))
        pending = store.list_jobs(status=JobStatus.PENDING)
        assert len(pending) == 2
        assert all(j.status == JobStatus.PENDING for j in pending)

    def test_update_job(self):
        store = Store()
        job = PersistedJob(job_id="j1", name="test")
        store.save_job(job)
        old_updated = job.updated_at

        job.status = JobStatus.RUNNING
        store.update_job(job)
        loaded = store.get_job("j1")
        assert loaded.status == JobStatus.RUNNING
        assert loaded.updated_at >= old_updated

    def test_save_overwrite(self):
        store = Store()
        store.save_job(PersistedJob(job_id="j1", name="first"))
        store.save_job(PersistedJob(job_id="j1", name="second"))
        assert store.get_job("j1").name == "second"
