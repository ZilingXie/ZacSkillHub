import base64
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "jira_get.py"


def load_module():
    spec = importlib.util.spec_from_file_location("jira_get", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload, url, status=200, content_type="application/json"):
        self._payload = payload
        self._url = url
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def geturl(self):
        return self._url


class FakeConnection:
    def __init__(self, host, timeout=None, response=None):
        self.host = host
        self.timeout = timeout
        self.response = response or FakeResponse({}, "")
        self.request_method = None
        self.request_target = None
        self.headers = []
        self.closed = False

    def putrequest(self, method, target):
        self.request_method = method
        self.request_target = target

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self):
        return None

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class JiraGetTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def write_env(self, content):
        tmpdir = tempfile.TemporaryDirectory()
        env_path = Path(tmpdir.name) / ".env"
        env_path.write_text(content, encoding="utf-8")
        self.addCleanup(tmpdir.cleanup)
        return env_path

    def test_load_basic_auth_credentials_reads_jira_user_and_password(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )

        username, password = self.module.load_basic_auth_credentials(env_path)

        self.assertEqual(username, "user@example.com")
        self.assertEqual(password, "pass-123")

    def test_load_basic_auth_credentials_requires_both_values(self):
        env_path = self.write_env("jira_user=user@example.com")

        with self.assertRaisesRegex(ValueError, "jira_pwd"):
            self.module.load_basic_auth_credentials(env_path)

    def test_fetch_jira_json_sends_basic_auth_access_token_and_query(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )
        response = FakeResponse(
            {"key": "CSD-1"},
            "https://jira.agoralab.co/rest/api/2/search",
        )
        captured = {}

        def fake_connection_factory(host, timeout):
            connection = FakeConnection(host, timeout=timeout, response=response)
            captured["connection"] = connection
            return connection

        payload = self.module.fetch_jira_json(
            "/rest/api/2/search",
            query_params={
                "jql": 'project = CSD AND status = RESOLVED',
                "fields": "summary,assignee",
            },
            env_path=env_path,
            token_fetcher=lambda _: "token-123",
            connection_factory=fake_connection_factory,
        )

        connection = captured["connection"]
        parsed_url = urlparse(
            f"https://{connection.host}{connection.request_target}"
        )
        query = parse_qs(parsed_url.query)
        headers = dict(connection.headers)

        self.assertEqual(payload["key"], "CSD-1")
        self.assertEqual(parsed_url.path, "/rest/api/2/search")
        self.assertEqual(query["jql"], ["project = CSD AND status = RESOLVED"])
        self.assertEqual(query["fields"], ["summary,assignee"])
        self.assertEqual(connection.timeout, 30)
        self.assertEqual(connection.request_method, "GET")
        self.assertEqual(headers["accessToken"], "token-123")
        self.assertEqual(
            headers["Authorization"],
            "Basic "
            + base64.b64encode(b"user@example.com:pass-123").decode("ascii"),
        )
        self.assertIn(("accessToken", "token-123"), connection.headers)
        self.assertNotIn(("Accesstoken", "token-123"), connection.headers)
        self.assertTrue(connection.closed)

    def test_main_prints_pretty_json_response(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )
        stdout = io.StringIO()
        response = FakeResponse(
            {"key": "CSD-942266", "fields": {"summary": "Example issue"}},
            "https://jira.agoralab.co/rest/api/2/issue/942266",
        )

        payload = self.module.main(
            argv=["/rest/api/2/issue/942266"],
            env_path=env_path,
            token_fetcher=lambda _: "token-123",
            connection_factory=lambda host, timeout: FakeConnection(
                host,
                timeout=timeout,
                response=response,
            ),
            stdout=stdout,
        )

        self.assertEqual(payload["key"], "CSD-942266")
        self.assertIn('"key": "CSD-942266"', stdout.getvalue())
        self.assertIn('"summary": "Example issue"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
