import copy
import importlib.util
import io
import json
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "jira_resolve_csd.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("jira_resolve_csd", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeJiraAPI:
    def __init__(self):
        self.calls = []
        self.issues = {
            "CSD-10001": {"status": "New", "status_category": "new", "resolution": None},
            "CSD-10002": {
                "status": "InProgress",
                "status_category": "indeterminate",
                "resolution": None,
            },
            "CSD-10003": {
                "status": "RESOLVED",
                "status_category": "done",
                "resolution": "Done",
            },
            "CSD-10004": {"status": "New", "status_category": "new", "resolution": None},
        }
        self.transition_overrides = {
            "CSD-10004": [
                {
                    "id": "811",
                    "name": "Reject",
                    "to": {"name": "Rejected", "statusCategory": {"key": "done"}},
                }
            ]
        }

    def issue_payload(self, issue_key):
        issue = self.issues[issue_key]
        resolution = None
        if issue["resolution"] is not None:
            resolution = {"name": issue["resolution"]}
        return {
            "key": issue_key,
            "fields": {
                "versions": [
                    {
                        "id": "43913",
                        "name": "4.5.2",
                    }
                ],
                "status": {
                    "name": issue["status"],
                    "statusCategory": {"key": issue["status_category"]},
                },
                "resolution": resolution,
            },
        }

    def transitions_for_issue(self, issue_key):
        if issue_key in self.transition_overrides:
            return copy.deepcopy(self.transition_overrides[issue_key])

        issue = self.issues[issue_key]
        if issue["status"] == "New":
            return [
                {
                    "id": "4",
                    "name": "Start Progress",
                    "to": {"name": "InProgress", "statusCategory": {"key": "indeterminate"}},
                },
                {
                    "id": "811",
                    "name": "Reject",
                    "to": {"name": "Rejected", "statusCategory": {"key": "done"}},
                },
            ]
        if issue["status"] == "InProgress":
            return [
                {
                    "id": "5",
                    "name": "Resolve Issue",
                    "to": {"name": "RESOLVED", "statusCategory": {"key": "done"}},
                }
            ]
        return []

    def __call__(self, method, path_or_url, **kwargs):
        self.calls.append(
            {
                "method": method,
                "path_or_url": path_or_url,
                "kwargs": kwargs,
            }
        )

        parts = [part for part in path_or_url.strip("/").split("/") if part]
        if len(parts) < 4 or parts[:3] != ["rest", "api", "2"] or parts[3] != "issue":
            raise AssertionError(f"Unexpected Jira path: {path_or_url}")

        issue_key = parts[4]
        if method == "GET" and len(parts) == 5:
            return self.issue_payload(issue_key)

        if len(parts) == 6 and parts[5] == "transitions":
            if method == "GET":
                return {"transitions": self.transitions_for_issue(issue_key)}
            if method == "POST":
                transition_id = kwargs["json_body"]["transition"]["id"]
                if transition_id == "4":
                    self.issues[issue_key]["status"] = "InProgress"
                    self.issues[issue_key]["status_category"] = "indeterminate"
                    return None
                if transition_id == "5":
                    self.issues[issue_key]["status"] = "RESOLVED"
                    self.issues[issue_key]["status_category"] = "done"
                    self.issues[issue_key]["resolution"] = "Done"
                    return None
                raise AssertionError(f"Unexpected transition id: {transition_id}")

        raise AssertionError(f"Unexpected Jira call: {method} {path_or_url}")


class JiraResolveCsdTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_normalize_issue_input_accepts_key_and_browse_url(self):
        self.assertEqual(
            self.module.normalize_issue_input("CSD-77806"),
            "CSD-77806",
        )
        self.assertEqual(
            self.module.normalize_issue_input(
                "https://jira.agoralab.co/browse/CSD-77806"
            ),
            "CSD-77806",
        )

    def test_normalize_issue_input_rejects_invalid_value(self):
        with self.assertRaisesRegex(ValueError, "Invalid CSD issue input"):
            self.module.normalize_issue_input("https://jira.agoralab.co/browse/ABC-1")

    def test_find_transition_by_name_returns_match(self):
        transition = self.module.find_transition_by_name(
            {
                "transitions": [
                    {
                        "id": "5",
                        "name": "Resolve Issue",
                        "to": {"name": "RESOLVED"},
                    }
                ]
            },
            "Resolve Issue",
            "CSD-10001",
        )

        self.assertEqual(transition["id"], "5")

    def test_find_transition_by_name_raises_clear_error(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "CSD-10001.*Resolve Issue.*Reject, Close",
        ):
            self.module.find_transition_by_name(
                {
                    "transitions": [
                        {"id": "811", "name": "Reject"},
                        {"id": "812", "name": "Close"},
                    ]
                },
                "Resolve Issue",
                "CSD-10001",
            )

    def test_main_dry_run_plans_actions_for_mixed_statuses(self):
        stdout = io.StringIO()
        fake_request = FakeJiraAPI()

        result = self.module.main(
            argv=[
                "https://jira.agoralab.co/browse/CSD-10001",
                "CSD-10002",
                "CSD-10003",
            ],
            request_func=fake_request,
            stdout=stdout,
        )

        self.assertEqual(
            [item["key"] for item in result],
            ["CSD-10001", "CSD-10002", "CSD-10003"],
        )
        self.assertEqual(result[0]["actions"], ["Start Progress", "Resolve Issue"])
        self.assertEqual(result[0]["result"], "resolved")
        self.assertEqual(result[0]["status"], "RESOLVED")
        self.assertEqual(result[0]["resolution"], "Done")
        self.assertEqual(result[1]["actions"], ["Resolve Issue"])
        self.assertEqual(result[1]["result"], "resolved")
        self.assertEqual(result[2]["actions"], [])
        self.assertEqual(result[2]["result"], "skipped")
        self.assertTrue(all(item["dry_run"] for item in result))
        self.assertIn('"url": "https://jira.agoralab.co/browse/CSD-10001"', stdout.getvalue())

    def test_main_resolve_processes_batch_and_continues_on_error(self):
        stdout = io.StringIO()
        fake_request = FakeJiraAPI()

        result = self.module.main(
            argv=["CSD-10001", "CSD-10002", "CSD-10003", "CSD-10004", "--resolve"],
            request_func=fake_request,
            stdout=stdout,
        )

        self.assertEqual([item["key"] for item in result], ["CSD-10001", "CSD-10002", "CSD-10003", "CSD-10004"])
        self.assertEqual(result[0]["result"], "resolved")
        self.assertEqual(result[0]["actions"], ["Start Progress", "Resolve Issue"])
        self.assertEqual(result[0]["status"], "RESOLVED")
        self.assertEqual(result[0]["resolution"], "Done")
        self.assertEqual(result[1]["result"], "resolved")
        self.assertEqual(result[1]["actions"], ["Resolve Issue"])
        self.assertEqual(result[2]["result"], "skipped")
        self.assertEqual(result[2]["status"], "RESOLVED")
        self.assertEqual(result[2]["resolution"], "Done")
        self.assertEqual(result[3]["result"], "error")
        self.assertEqual(result[3]["actions"], ["Start Progress", "Resolve Issue"])
        self.assertIn("Start Progress", result[3]["error"])
        self.assertIn("Reject", result[3]["error"])
        self.assertTrue(all(not item["dry_run"] for item in result))
        self.assertIn('"result": "error"', stdout.getvalue())

        transition_posts = [
            call
            for call in fake_request.calls
            if call["method"] == "POST" and call["path_or_url"].endswith("/transitions")
        ]
        self.assertEqual(
            transition_posts[0]["kwargs"]["json_body"],
            {
                "transition": {"id": "4"},
                "fields": {"customfield_13903": {"id": "12611"}},
            },
        )
        self.assertEqual(
            transition_posts[1]["kwargs"]["json_body"],
            {
                "transition": {"id": "5"},
                "fields": {
                    "resolution": {"id": "13000"},
                    "customfield_16704": {"id": "15003"},
                    "customfield_16901": "Enough information to troubleshoot",
                    "customfield_18000": [{"id": "16203"}],
                    "customfield_14600": [{"id": "13500"}],
                    "customfield_12404": "1",
                    "customfield_12107": {"id": "11227"},
                    "customfield_13701": "Resolved during close-csd skill verification and test issue cleanup.",
                    "customfield_13704": ["N/A"],
                    "customfield_13703": "Smoke check the Jira workflow only.",
                    "customfield_11708": "Issue was created for skill validation and is being resolved after the workflow check.",
                    "customfield_12100": {
                        "id": "11202",
                        "child": {"id": "11271"},
                    },
                    "fixVersions": [{"id": "43913"}],
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
