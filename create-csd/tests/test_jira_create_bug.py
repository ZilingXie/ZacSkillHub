import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "jira_create_bug.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("jira_create_bug", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class JiraCreateBugTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def write_env(self, content):
        tmpdir = tempfile.TemporaryDirectory()
        env_path = Path(tmpdir.name) / ".env"
        env_path.write_text(content, encoding="utf-8")
        self.addCleanup(tmpdir.cleanup)
        return env_path

    def test_build_issue_payload_applies_template_prefix_and_generated_vid(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )
        now = datetime(2026, 4, 11, 18, 45, 7)

        payload = self.module.build_issue_payload(
            summary="create path smoke test",
            description=None,
            env_path=env_path,
            now=now,
        )

        fields = payload["fields"]
        self.assertEqual(
            fields["summary"],
            "[TEST][CSD] create path smoke test",
        )
        self.assertEqual(fields["reporter"], {"name": "user@example.com"})
        self.assertEqual(fields["project"], {"key": "CSD"})
        self.assertEqual(fields["issuetype"], {"id": "10004"})
        self.assertEqual(fields["components"], [{"id": "25502"}])
        self.assertEqual(fields["priority"], {"id": "2"})
        self.assertEqual(fields["versions"], [{"id": "43913"}])
        self.assertEqual(fields["customfield_11621"], {"id": "11265"})
        self.assertEqual(fields["customfield_12110"], {"id": "11261"})
        self.assertEqual(fields["customfield_18003"], {"id": "16209"})
        self.assertEqual(fields["customfield_12600"], "TEST-CSD-20260411-184507")
        self.assertIn("test issue", fields["description"].lower())

    def test_main_dry_run_prints_url_payload_and_create_hint(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )
        stdout = io.StringIO()

        payload = self.module.main(
            argv=["--summary", "create path smoke test"],
            env_path=env_path,
            now_provider=lambda: datetime(2026, 4, 11, 18, 45, 7),
            request_func=lambda *args, **kwargs: self.fail(
                "dry-run should not send the request"
            ),
            stdout=stdout,
        )

        self.assertEqual(
            payload["fields"]["summary"],
            "[TEST][CSD] create path smoke test",
        )
        self.assertIn(
            "POST https://jira.agoralab.co/rest/api/2/issue",
            stdout.getvalue(),
        )
        self.assertIn('"customfield_12600": "TEST-CSD-20260411-184507"', stdout.getvalue())
        self.assertIn("assign the new issue to xieziling@agora.io", stdout.getvalue())
        self.assertIn("Start Progress", stdout.getvalue())
        self.assertIn("https://jira.agoralab.co/browse/<new-key>", stdout.getvalue())
        self.assertIn("--create", stdout.getvalue())

    def test_find_transition_by_name_returns_match(self):
        transition = self.module.find_transition_by_name(
            {
                "transitions": [
                    {
                        "id": "4",
                        "name": "Start Progress",
                        "to": {"name": "InProgress"},
                    }
                ]
            },
            "Start Progress",
            "CSD-10001",
        )

        self.assertEqual(transition["id"], "4")
        self.assertEqual(transition["to"]["name"], "InProgress")

    def test_find_transition_by_name_raises_clear_error(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "CSD-10001.*Start Progress.*Reject, Close",
        ):
            self.module.find_transition_by_name(
                {
                    "transitions": [
                        {"id": "811", "name": "Reject"},
                        {"id": "812", "name": "Close"},
                    ]
                },
                "Start Progress",
                "CSD-10001",
            )

    def test_main_create_posts_and_prints_result(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )
        stdout = io.StringIO()
        captured = []

        def fake_request(method, path_or_url, **kwargs):
            captured.append(
                {
                    "method": method,
                    "path_or_url": path_or_url,
                    "kwargs": kwargs,
                }
            )
            if len(captured) == 1:
                return {
                    "id": "10001",
                    "key": "CSD-10001",
                    "self": "https://jira.agoralab.co/rest/api/2/issue/10001",
                    "extra": "ignored",
                }
            if len(captured) == 2:
                return None
            if len(captured) == 3:
                return {
                    "transitions": [
                        {
                            "id": "4",
                            "name": "Start Progress",
                            "to": {"name": "InProgress"},
                        }
                    ]
                }
            if len(captured) == 4:
                return None
            self.fail(
                "create flow should only send create + assignee + transitions lookup + transition requests"
            )

        result = self.module.main(
            argv=["--summary", "create path smoke test", "--create"],
            env_path=env_path,
            now_provider=lambda: datetime(2026, 4, 11, 18, 45, 7),
            request_func=fake_request,
            stdout=stdout,
        )

        self.assertEqual(len(captured), 4)
        self.assertEqual(captured[0]["method"], "POST")
        self.assertEqual(captured[0]["path_or_url"], "/rest/api/2/issue")
        self.assertEqual(
            captured[0]["kwargs"]["json_body"]["fields"]["summary"],
            "[TEST][CSD] create path smoke test",
        )
        self.assertEqual(captured[1]["method"], "PUT")
        self.assertEqual(
            captured[1]["path_or_url"],
            "/rest/api/2/issue/CSD-10001/assignee",
        )
        self.assertEqual(
            captured[1]["kwargs"]["json_body"],
            {"name": "xieziling@agora.io"},
        )
        self.assertFalse(captured[1]["kwargs"]["expect_json"])
        self.assertEqual(captured[2]["method"], "GET")
        self.assertEqual(
            captured[2]["path_or_url"],
            "/rest/api/2/issue/CSD-10001/transitions",
        )
        self.assertEqual(captured[3]["method"], "POST")
        self.assertEqual(
            captured[3]["path_or_url"],
            "/rest/api/2/issue/CSD-10001/transitions",
        )
        self.assertEqual(
            captured[3]["kwargs"]["json_body"],
            {
                "transition": {"id": "4"},
                "fields": {"customfield_13903": {"id": "12611"}},
            },
        )
        self.assertFalse(captured[3]["kwargs"]["expect_json"])
        self.assertEqual(
            result,
            {
                "id": "10001",
                "key": "CSD-10001",
                "self": "https://jira.agoralab.co/rest/api/2/issue/10001",
                "assignee": "xieziling@agora.io",
                "status": "InProgress",
                "url": "https://jira.agoralab.co/browse/CSD-10001",
            },
        )
        self.assertIn('"key": "CSD-10001"', stdout.getvalue())
        self.assertIn('"assignee": "xieziling@agora.io"', stdout.getvalue())
        self.assertIn('"status": "InProgress"', stdout.getvalue())
        self.assertIn('"url": "https://jira.agoralab.co/browse/CSD-10001"', stdout.getvalue())
        self.assertNotIn("ignored", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
