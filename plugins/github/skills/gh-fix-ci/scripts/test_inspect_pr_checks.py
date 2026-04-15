#!/usr/bin/env python3
"""Fixture tests for statusCheckRollup normalization in inspect_pr_checks.py."""
from __future__ import annotations

import pytest

from inspect_pr_checks import (
    _normalize_rollup_entry,
    is_failing,
    normalize_field,
    extract_run_id,
    extract_job_id,
)

# ---------------------------------------------------------------------------
# Fixtures: raw statusCheckRollup entries as returned by
# `gh pr view --json statusCheckRollup`
# ---------------------------------------------------------------------------

CHECKRUN_SUCCESS = {
    "__typename": "CheckRun",
    "name": "build (ubuntu-latest)",
    "status": "COMPLETED",
    "conclusion": "SUCCESS",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/12345678901/job/98765432101",
    "startedAt": "2026-04-15T10:00:00Z",
    "completedAt": "2026-04-15T10:05:00Z",
}

CHECKRUN_FAILURE = {
    "__typename": "CheckRun",
    "name": "test (ubuntu-latest, python-3.12)",
    "status": "COMPLETED",
    "conclusion": "FAILURE",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/12345678902/job/98765432102",
    "startedAt": "2026-04-15T10:00:00Z",
    "completedAt": "2026-04-15T10:03:00Z",
}

CHECKRUN_CANCELLED = {
    "__typename": "CheckRun",
    "name": "deploy",
    "status": "COMPLETED",
    "conclusion": "CANCELLED",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/12345678903/job/98765432103",
    "startedAt": "2026-04-15T10:00:00Z",
    "completedAt": "2026-04-15T10:01:00Z",
}

CHECKRUN_TIMED_OUT = {
    "__typename": "CheckRun",
    "name": "integration-tests",
    "status": "COMPLETED",
    "conclusion": "TIMED_OUT",
    "detailsUrl": "https://github.com/owner/repo/actions/runs/12345678904/job/98765432104",
    "startedAt": "2026-04-15T10:00:00Z",
    "completedAt": "2026-04-15T11:00:00Z",
}

CHECKRUN_IN_PROGRESS = {
    "__typename": "CheckRun",
    "name": "lint",
    "status": "IN_PROGRESS",
    "conclusion": None,
    "detailsUrl": "https://github.com/owner/repo/actions/runs/12345678905/job/98765432105",
    "startedAt": "2026-04-15T10:00:00Z",
    "completedAt": None,
}

CHECKRUN_NO_URL = {
    "__typename": "CheckRun",
    "name": "external-check",
    "status": "COMPLETED",
    "conclusion": "FAILURE",
    "detailsUrl": "",
    "startedAt": "2026-04-15T10:00:00Z",
    "completedAt": "2026-04-15T10:02:00Z",
}

CHECKRUN_EXTERNAL_URL = {
    "__typename": "CheckRun",
    "name": "codecov/patch",
    "status": "COMPLETED",
    "conclusion": "FAILURE",
    "detailsUrl": "https://app.codecov.io/gh/owner/repo/pull/42",
    "startedAt": "2026-04-15T10:00:00Z",
    "completedAt": "2026-04-15T10:01:00Z",
}

STATUS_CONTEXT_SUCCESS = {
    "__typename": "StatusContext",
    "context": "ci/circleci: build",
    "state": "SUCCESS",
    "targetUrl": "https://circleci.com/gh/owner/repo/12345",
    "createdAt": "2026-04-15T10:00:00Z",
}

STATUS_CONTEXT_FAILURE = {
    "__typename": "StatusContext",
    "context": "ci/circleci: test",
    "state": "FAILURE",
    "targetUrl": "https://circleci.com/gh/owner/repo/12346",
    "createdAt": "2026-04-15T10:00:00Z",
}

STATUS_CONTEXT_NO_URL = {
    "__typename": "StatusContext",
    "context": "license/cla",
    "state": "PENDING",
    "targetUrl": None,
    "createdAt": "2026-04-15T10:00:00Z",
}

CHECKRUN_NULL_FIELDS = {
    "__typename": "CheckRun",
    "name": "minimal-check",
    "status": None,
    "conclusion": None,
    "detailsUrl": None,
    "startedAt": None,
    "completedAt": None,
}


# ---------------------------------------------------------------------------
# Tests: _normalize_rollup_entry produces the expected internal shape
# ---------------------------------------------------------------------------

INTERNAL_KEYS = {"name", "state", "conclusion", "detailsUrl", "startedAt", "completedAt"}


class TestNormalizeRollupEntry:
    def test_checkrun_success_shape(self):
        result = _normalize_rollup_entry(CHECKRUN_SUCCESS)
        assert set(result.keys()) == INTERNAL_KEYS
        assert result["name"] == "build (ubuntu-latest)"
        assert result["state"] == "COMPLETED"
        assert result["conclusion"] == "SUCCESS"
        assert result["detailsUrl"] == CHECKRUN_SUCCESS["detailsUrl"]
        assert result["startedAt"] == "2026-04-15T10:00:00Z"
        assert result["completedAt"] == "2026-04-15T10:05:00Z"

    def test_checkrun_failure_shape(self):
        result = _normalize_rollup_entry(CHECKRUN_FAILURE)
        assert set(result.keys()) == INTERNAL_KEYS
        assert result["name"] == "test (ubuntu-latest, python-3.12)"
        assert result["conclusion"] == "FAILURE"
        assert result["detailsUrl"] == CHECKRUN_FAILURE["detailsUrl"]

    def test_checkrun_cancelled_shape(self):
        result = _normalize_rollup_entry(CHECKRUN_CANCELLED)
        assert result["conclusion"] == "CANCELLED"

    def test_checkrun_timed_out_shape(self):
        result = _normalize_rollup_entry(CHECKRUN_TIMED_OUT)
        assert result["conclusion"] == "TIMED_OUT"

    def test_checkrun_in_progress_shape(self):
        result = _normalize_rollup_entry(CHECKRUN_IN_PROGRESS)
        assert set(result.keys()) == INTERNAL_KEYS
        assert result["state"] == "IN_PROGRESS"
        assert result["conclusion"] == ""
        assert result["completedAt"] == ""

    def test_checkrun_no_url(self):
        result = _normalize_rollup_entry(CHECKRUN_NO_URL)
        assert result["detailsUrl"] == ""

    def test_checkrun_external_url_preserved(self):
        result = _normalize_rollup_entry(CHECKRUN_EXTERNAL_URL)
        assert result["detailsUrl"] == "https://app.codecov.io/gh/owner/repo/pull/42"

    def test_checkrun_null_fields_produce_empty_strings(self):
        result = _normalize_rollup_entry(CHECKRUN_NULL_FIELDS)
        assert set(result.keys()) == INTERNAL_KEYS
        for key in INTERNAL_KEYS:
            assert isinstance(result[key], str), f"{key} should be str, got {type(result[key])}"

    def test_status_context_success_shape(self):
        result = _normalize_rollup_entry(STATUS_CONTEXT_SUCCESS)
        assert set(result.keys()) == INTERNAL_KEYS
        assert result["name"] == "ci/circleci: build"
        assert result["state"] == "SUCCESS"
        assert result["conclusion"] == "SUCCESS"
        assert result["detailsUrl"] == "https://circleci.com/gh/owner/repo/12345"

    def test_status_context_failure_shape(self):
        result = _normalize_rollup_entry(STATUS_CONTEXT_FAILURE)
        assert result["name"] == "ci/circleci: test"
        assert result["state"] == "FAILURE"
        assert result["conclusion"] == "FAILURE"

    def test_status_context_no_url(self):
        result = _normalize_rollup_entry(STATUS_CONTEXT_NO_URL)
        assert result["detailsUrl"] == ""
        assert result["completedAt"] == ""

    def test_unknown_typename_treated_as_checkrun(self):
        entry = {
            "__typename": "SomeNewType",
            "name": "new-check",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "detailsUrl": "https://example.com",
            "startedAt": "2026-04-15T10:00:00Z",
            "completedAt": "2026-04-15T10:01:00Z",
        }
        result = _normalize_rollup_entry(entry)
        assert result["name"] == "new-check"
        assert result["detailsUrl"] == "https://example.com"

    def test_missing_typename_treated_as_checkrun(self):
        entry = {
            "name": "bare-check",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/999/job/111",
        }
        result = _normalize_rollup_entry(entry)
        assert result["name"] == "bare-check"
        assert result["conclusion"] == "FAILURE"


# ---------------------------------------------------------------------------
# Tests: is_failing correctly classifies normalized rollup output
# ---------------------------------------------------------------------------

class TestIsFailingWithNormalized:
    def test_successful_checkrun_not_failing(self):
        check = _normalize_rollup_entry(CHECKRUN_SUCCESS)
        assert not is_failing(check)

    def test_failed_checkrun_is_failing(self):
        check = _normalize_rollup_entry(CHECKRUN_FAILURE)
        assert is_failing(check)

    def test_cancelled_checkrun_is_failing(self):
        check = _normalize_rollup_entry(CHECKRUN_CANCELLED)
        assert is_failing(check)

    def test_timed_out_checkrun_is_failing(self):
        check = _normalize_rollup_entry(CHECKRUN_TIMED_OUT)
        assert is_failing(check)

    def test_in_progress_checkrun_not_failing(self):
        check = _normalize_rollup_entry(CHECKRUN_IN_PROGRESS)
        assert not is_failing(check)

    def test_successful_status_context_not_failing(self):
        check = _normalize_rollup_entry(STATUS_CONTEXT_SUCCESS)
        assert not is_failing(check)

    def test_failed_status_context_is_failing(self):
        check = _normalize_rollup_entry(STATUS_CONTEXT_FAILURE)
        assert is_failing(check)

    def test_no_url_failure_still_detected(self):
        check = _normalize_rollup_entry(CHECKRUN_NO_URL)
        assert is_failing(check)

    def test_external_url_failure_still_detected(self):
        check = _normalize_rollup_entry(CHECKRUN_EXTERNAL_URL)
        assert is_failing(check)


# ---------------------------------------------------------------------------
# Tests: normalized output feeds analyze_check structure correctly
# (no network calls — just verify the dict shape is consumable)
# ---------------------------------------------------------------------------

class TestAnalyzeCheckInputShape:
    def test_detailsUrl_available_for_run_id_extraction(self):
        check = _normalize_rollup_entry(CHECKRUN_FAILURE)
        url = check.get("detailsUrl") or check.get("link") or ""
        assert url != ""
        run_id = extract_run_id(url)
        assert run_id == "12345678902"
        job_id = extract_job_id(url)
        assert job_id == "98765432102"

    def test_external_url_yields_no_run_id(self):
        check = _normalize_rollup_entry(CHECKRUN_EXTERNAL_URL)
        url = check.get("detailsUrl") or check.get("link") or ""
        run_id = extract_run_id(url)
        assert run_id is None

    def test_empty_url_yields_no_run_id(self):
        check = _normalize_rollup_entry(CHECKRUN_NO_URL)
        url = check.get("detailsUrl") or check.get("link") or ""
        run_id = extract_run_id(url)
        assert run_id is None

    def test_status_context_url_yields_no_run_id(self):
        check = _normalize_rollup_entry(STATUS_CONTEXT_FAILURE)
        url = check.get("detailsUrl") or check.get("link") or ""
        run_id = extract_run_id(url)
        assert run_id is None

    def test_name_field_always_present(self):
        for fixture in [
            CHECKRUN_SUCCESS,
            CHECKRUN_FAILURE,
            CHECKRUN_NO_URL,
            STATUS_CONTEXT_SUCCESS,
            STATUS_CONTEXT_NO_URL,
            CHECKRUN_NULL_FIELDS,
        ]:
            check = _normalize_rollup_entry(fixture)
            assert "name" in check
            assert isinstance(check["name"], str)


# ---------------------------------------------------------------------------
# Tests: normalize_field lowercases GraphQL enum values correctly
# ---------------------------------------------------------------------------

class TestNormalizeFieldWithGraphQLEnums:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("SUCCESS", "success"),
            ("FAILURE", "failure"),
            ("CANCELLED", "cancelled"),
            ("TIMED_OUT", "timed_out"),
            ("ACTION_REQUIRED", "action_required"),
            ("COMPLETED", "completed"),
            ("IN_PROGRESS", "in_progress"),
            ("  FAILURE  ", "failure"),
            (None, ""),
        ],
    )
    def test_graphql_enum_normalization(self, raw, expected):
        assert normalize_field(raw) == expected
