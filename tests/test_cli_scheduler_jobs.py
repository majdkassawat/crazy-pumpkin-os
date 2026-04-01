"""Tests for CLI `jobs` and `retry-job` commands."""

import pytest
from click.testing import CliRunner

from crazypumpkin.cli import cli
from crazypumpkin.framework.models import JobStatus, PersistedJob
from crazypumpkin.framework.store import Store


@pytest.fixture()
def store_with_jobs():
    store = Store()
    store.save_job(PersistedJob(job_id="j1", name="build-alpha", status=JobStatus.PENDING))
    store.save_job(PersistedJob(job_id="j2", name="deploy-beta", status=JobStatus.FAILED, attempt=1, max_retries=3))
    store.save_job(PersistedJob(job_id="j3", name="test-gamma", status=JobStatus.SUCCEEDED))
    return store


class TestJobsCommand:
    def test_lists_all_jobs(self, store_with_jobs):
        runner = CliRunner()
        result = runner.invoke(cli, ["jobs"], obj=store_with_jobs)
        assert result.exit_code == 0
        assert "j1" in result.output
        assert "j2" in result.output
        assert "j3" in result.output

    def test_no_jobs_message(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["jobs"], obj=Store())
        assert result.exit_code == 0
        assert "No jobs found." in result.output

    def test_filter_by_status(self, store_with_jobs):
        runner = CliRunner()
        result = runner.invoke(cli, ["jobs", "--status", "failed"], obj=store_with_jobs)
        assert result.exit_code == 0
        assert "j2" in result.output
        assert "j1" not in result.output


class TestRetryJobCommand:
    def test_retry_failed_job(self, store_with_jobs):
        runner = CliRunner()
        result = runner.invoke(cli, ["retry-job", "j2"], obj=store_with_jobs)
        assert result.exit_code == 0
        assert "queued for retry" in result.output
        assert store_with_jobs.get_job("j2").status == JobStatus.PENDING

    def test_retry_nonexistent_job(self, store_with_jobs):
        runner = CliRunner()
        result = runner.invoke(cli, ["retry-job", "bad-id"], obj=store_with_jobs)
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_retry_non_failed_job(self, store_with_jobs):
        runner = CliRunner()
        result = runner.invoke(cli, ["retry-job", "j1"], obj=store_with_jobs)
        assert result.exit_code != 0
        assert "not retryable" in result.output
