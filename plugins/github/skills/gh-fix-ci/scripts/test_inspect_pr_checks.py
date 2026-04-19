#!/usr/bin/env python3
"""Fixture tests for inspect_pr_checks.py statusCheckRollup normalization.

Covers the normalization seam: statusCheckRollup CheckRun nodes (uppercase
GraphQL values) must map correctly into the internal check shape consumed
by is_failing() and analyze_check().

Acceptance criteria (PORAA-1208):
  - successful CheckRun: classified as non-failing
  - failing CheckRun: classified as failing, detailsUrl preserved
  - non-Actions / missing-URL CheckRun: handled gracefully
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inspect_pr_checks import (
    FAILURE_CONCLUSIONS,
    FAILURE_STATES,
    analyze_check,
    extract_job_id,
    extract_run_id,
    is_failing,
    normalize_field,
)

# ---------------------------------------------------------------------------
# Fixtures: statusCheckRollup CheckRun node shapes
# ---------------------------------------------------------------------------

SUCCESSFUL_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "build (ubuntu-latest)",
    "conclusion": "SUCCESS",
    "status": "COMPLETED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/9876543210/job/12345678901",
}

FAILING_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "test (python-3.12)",
    "conclusion": "FAILURE",
    "status": "COMPLETED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/9876543210/job/99999999999",
}

CANCELLED_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "deploy-preview",
    "conclusion": "CANCELLED",
    "status": "COMPLETED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/9876543210/job/11111111111",
}

TIMED_OUT_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "integration-tests",
    "conclusion": "TIMED_OUT",
    "status": "COMPLETED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/5555555555/job/22222222222",
}

ACTION_REQUIRED_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "codeql-analysis",
    "conclusion": "ACTION_REQUIRED",
    "status": "COMPLETED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/7777777777/job/33333333333",
}

NEUTRAL_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "optional-lint",
    "conclusion": "NEUTRAL",
    "status": "COMPLETED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/4444444444/job/55555555555",
}

SKIPPED_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "conditional-job",
    "conclusion": "SKIPPED",
    "status": "COMPLETED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/4444444444/job/66666666666",
}

IN_PROGRESS_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "slow-build",
    "conclusion": None,
    "status": "IN_PROGRESS",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/8888888888/job/77777777777",
}

EXTERNAL_CHECK_NO_ACTIONS_URL = {
    "__typename": "CheckRun",
    "name": "codecov/project",
    "conclusion": "FAILURE",
    "status": "COMPLETED",
    "detailsUrl": "https://codecov.io/gh/owner/repo/pull/42",
}

MISSING_URL_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "status-check",
    "conclusion": "FAILURE",
    "status": "COMPLETED",
    "detailsUrl": "",
}

NULL_URL_CHECKRUN = {
    "__typename": "CheckRun",
    "name": "webhook-check",
    "conclusion": "SUCCESS",
    "status": "COMPLETED",
    "detailsUrl": None,
}

# Old-style gh pr checks --json shape (lowercase, uses "state" not "status")
LEGACY_FAILING_CHECK = {
    "name": "tests",
    "state": "failure",
    "conclusion": "failure",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/1111111111/job/2222222222",
}

# Fallback shape with bucket/link fields
FALLBACK_FAILING_CHECK = {
    "name": "ci-check",
    "state": "fail",
    "bucket": "fail",
    "link": "https://github.com/owner/repo/actions/runs/3333333333/job/4444444444",
}


class TestNormalizeField(unittest.TestCase):

    def test_uppercase_to_lowercase(self):
        self.assertEqual(normalize_field("SUCCESS"), "success")
        self.assertEqual(normalize_field("FAILURE"), "failure")
        self.assertEqual(normalize_field("COMPLETED"), "completed")
        self.assertEqual(normalize_field("IN_PROGRESS"), "in_progress")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_field("  FAILURE  "), "failure")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_field(None), "")

    def test_passthrough_lowercase(self):
        self.assertEqual(normalize_field("failure"), "failure")
        self.assertEqual(normalize_field("success"), "success")


class TestIsFailingWithStatusCheckRollup(unittest.TestCase):

    def test_successful_checkrun_not_failing(self):
        self.assertFalse(is_failing(SUCCESSFUL_CHECKRUN))

    def test_failing_checkrun_detected(self):
        self.assertTrue(is_failing(FAILING_CHECKRUN))

    def test_cancelled_checkrun_detected(self):
        self.assertTrue(is_failing(CANCELLED_CHECKRUN))

    def test_timed_out_checkrun_detected(self):
        self.assertTrue(is_failing(TIMED_OUT_CHECKRUN))

    def test_action_required_checkrun_detected(self):
        self.assertTrue(is_failing(ACTION_REQUIRED_CHECKRUN))

    def test_neutral_checkrun_not_failing(self):
        self.assertFalse(is_failing(NEUTRAL_CHECKRUN))

    def test_skipped_checkrun_not_failing(self):
        self.assertFalse(is_failing(SKIPPED_CHECKRUN))

    def test_in_progress_checkrun_not_failing(self):
        self.assertFalse(is_failing(IN_PROGRESS_CHECKRUN))

    def test_external_failing_check_detected(self):
        self.assertTrue(is_failing(EXTERNAL_CHECK_NO_ACTIONS_URL))

    def test_missing_url_failing_check_detected(self):
        self.assertTrue(is_failing(MISSING_URL_CHECKRUN))

    def test_null_url_success_not_failing(self):
        self.assertFalse(is_failing(NULL_URL_CHECKRUN))

    def test_legacy_lowercase_failing(self):
        self.assertTrue(is_failing(LEGACY_FAILING_CHECK))

    def test_fallback_bucket_failing(self):
        self.assertTrue(is_failing(FALLBACK_FAILING_CHECK))


class TestExtractRunAndJobId(unittest.TestCase):

    def test_actions_url_extracts_run_id(self):
        url = "https://github.com/owner/repo/actions/runs/9876543210/job/12345678901"
        self.assertEqual(extract_run_id(url), "9876543210")

    def test_actions_url_extracts_job_id(self):
        url = "https://github.com/owner/repo/actions/runs/9876543210/job/12345678901"
        self.assertEqual(extract_job_id(url), "12345678901")

    def test_non_actions_url_returns_none(self):
        url = "https://codecov.io/gh/owner/repo/pull/42"
        self.assertIsNone(extract_run_id(url))
        self.assertIsNone(extract_job_id(url))

    def test_empty_url_returns_none(self):
        self.assertIsNone(extract_run_id(""))
        self.assertIsNone(extract_job_id(""))

    def test_none_url_returns_none(self):
        self.assertIsNone(extract_run_id(None))
        self.assertIsNone(extract_job_id(None))

    def test_run_only_url_no_job(self):
        url = "https://github.com/owner/repo/actions/runs/9876543210"
        self.assertEqual(extract_run_id(url), "9876543210")
        self.assertIsNone(extract_job_id(url))


class TestAnalyzeCheckNormalization(unittest.TestCase):
    """Test that analyze_check() can consume statusCheckRollup nodes.

    We mock fetch_run_metadata and fetch_check_log to isolate the
    normalization layer from network I/O.
    """

    @patch("inspect_pr_checks.fetch_check_log", return_value=("log output", "", "ok"))
    @patch("inspect_pr_checks.fetch_run_metadata", return_value={"conclusion": "failure"})
    def test_failing_checkrun_preserves_details_url(self, _meta, _log):
        result = analyze_check(FAILING_CHECKRUN, repo_root=Path("."), max_lines=10, context=5)
        self.assertEqual(result["detailsUrl"], FAILING_CHECKRUN["detailsUrl"])
        self.assertEqual(result["name"], "test (python-3.12)")
        self.assertEqual(result["runId"], "9876543210")
        self.assertEqual(result["jobId"], "99999999999")
        self.assertEqual(result["status"], "ok")

    @patch("inspect_pr_checks.fetch_check_log", return_value=("log output", "", "ok"))
    @patch("inspect_pr_checks.fetch_run_metadata", return_value={"conclusion": "success"})
    def test_successful_checkrun_preserves_details_url(self, _meta, _log):
        result = analyze_check(SUCCESSFUL_CHECKRUN, repo_root=Path("."), max_lines=10, context=5)
        self.assertEqual(result["detailsUrl"], SUCCESSFUL_CHECKRUN["detailsUrl"])
        self.assertEqual(result["name"], "build (ubuntu-latest)")
        self.assertIsNotNone(result["runId"])

    def test_external_check_marked_external(self):
        result = analyze_check(
            EXTERNAL_CHECK_NO_ACTIONS_URL, repo_root=Path("."), max_lines=10, context=5
        )
        self.assertEqual(result["status"], "external")
        self.assertEqual(result["detailsUrl"], EXTERNAL_CHECK_NO_ACTIONS_URL["detailsUrl"])
        self.assertIn("No GitHub Actions run id", result.get("note", ""))

    def test_missing_url_marked_external(self):
        result = analyze_check(MISSING_URL_CHECKRUN, repo_root=Path("."), max_lines=10, context=5)
        self.assertEqual(result["status"], "external")
        self.assertEqual(result["detailsUrl"], "")
        self.assertIsNone(result["runId"])

    def test_null_url_marked_external(self):
        result = analyze_check(NULL_URL_CHECKRUN, repo_root=Path("."), max_lines=10, context=5)
        self.assertEqual(result["status"], "external")
        self.assertEqual(result["detailsUrl"], "")
        self.assertIsNone(result["runId"])

    @patch("inspect_pr_checks.fetch_check_log", return_value=("log", "", "ok"))
    @patch("inspect_pr_checks.fetch_run_metadata", return_value=None)
    def test_fallback_link_field_used(self, _meta, _log):
        result = analyze_check(FALLBACK_FAILING_CHECK, repo_root=Path("."), max_lines=10, context=5)
        self.assertEqual(
            result["detailsUrl"],
            "https://github.com/owner/repo/actions/runs/3333333333/job/4444444444",
        )
        self.assertEqual(result["runId"], "3333333333")
        self.assertEqual(result["jobId"], "4444444444")


class TestFailureClassificationCompleteness(unittest.TestCase):
    """Verify the normalization maps uppercase GraphQL values into the
    sets that is_failing() checks against."""

    def test_all_failure_conclusions_recognized_uppercase(self):
        for conclusion in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"):
            normalized = normalize_field(conclusion)
            self.assertIn(
                normalized,
                FAILURE_CONCLUSIONS,
                f"Uppercase conclusion {conclusion!r} normalized to {normalized!r} "
                f"not in FAILURE_CONCLUSIONS",
            )

    def test_non_failure_conclusions_excluded(self):
        for conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED", "STALE"):
            normalized = normalize_field(conclusion)
            self.assertNotIn(
                normalized,
                FAILURE_CONCLUSIONS,
                f"Non-failure conclusion {conclusion!r} should not be in FAILURE_CONCLUSIONS",
            )

    def test_all_failure_states_recognized_uppercase(self):
        for state in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"):
            normalized = normalize_field(state)
            self.assertIn(
                normalized,
                FAILURE_STATES,
                f"Uppercase state {state!r} normalized to {normalized!r} "
                f"not in FAILURE_STATES",
            )


if __name__ == "__main__":
    unittest.main()
