import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "jira_request.py"


def load_module():
    spec = importlib.util.spec_from_file_location("jira_request", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload, status=200, content_type="application/json"):
        self._payload = payload
        self.status = status
        self.reason = "OK" if status < 400 else "Bad Request"
        self._content_type = content_type

    def read(self):
        if self._payload is None:
            return b""
        return json.dumps(self._payload).encode("utf-8")

    def getheader(self, name, default=None):
        if name.lower() == "content-type":
            return self._content_type
        return default


class FakeConnection:
    def __init__(self, host, timeout=None, response=None):
        self.host = host
        self.timeout = timeout
        self.response = response or FakeResponse({})
        self.request_method = None
        self.request_target = None
        self.headers = []
        self.sent_body = b""
        self.closed = False

    def putrequest(self, method, target):
        self.request_method = method
        self.request_target = target

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self):
        return None

    def send(self, data):
        self.sent_body += data

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class JiraRequestTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def write_env(self, content):
        tmpdir = tempfile.TemporaryDirectory()
        env_path = Path(tmpdir.name) / ".env"
        env_path.write_text(content, encoding="utf-8")
        self.addCleanup(tmpdir.cleanup)
        return env_path

    def test_request_jira_json_posts_json_with_exact_access_token_header(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )
        response = FakeResponse(
            {
                "id": "10001",
                "key": "CSD-10001",
                "self": "https://jira.agoralab.co/rest/api/2/issue/10001",
            }
        )
        captured = {}

        def fake_connection_factory(host, timeout):
            connection = FakeConnection(host, timeout=timeout, response=response)
            captured["connection"] = connection
            return connection

        payload = self.module.request_jira_json(
            "POST",
            "/rest/api/2/issue",
            json_body={"fields": {"summary": "Example summary"}},
            env_path=env_path,
            token_fetcher=lambda _: "token-123",
            connection_factory=fake_connection_factory,
        )

        connection = captured["connection"]
        headers = dict(connection.headers)

        self.assertEqual(payload["key"], "CSD-10001")
        self.assertEqual(connection.request_method, "POST")
        self.assertEqual(connection.request_target, "/rest/api/2/issue")
        self.assertEqual(connection.timeout, 30)
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["accessToken"], "token-123")
        self.assertNotIn("Accesstoken", headers)
        self.assertEqual(
            headers["Authorization"],
            "Basic "
            + base64.b64encode(b"user@example.com:pass-123").decode("ascii"),
        )
        self.assertEqual(
            json.loads(connection.sent_body.decode("utf-8")),
            {"fields": {"summary": "Example summary"}},
        )
        self.assertTrue(connection.closed)

    def test_request_jira_json_allows_empty_success_body_when_json_not_expected(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "jira_user=user@example.com",
                    "jira_pwd=pass-123",
                ]
            )
        )
        response = FakeResponse(None, status=204)
        captured = {}

        def fake_connection_factory(host, timeout):
            connection = FakeConnection(host, timeout=timeout, response=response)
            captured["connection"] = connection
            return connection

        payload = self.module.request_jira_json(
            "PUT",
            "/rest/api/2/issue/CSD-10001/assignee",
            json_body={"name": "xieziling@agora.io"},
            env_path=env_path,
            token_fetcher=lambda _: "token-123",
            connection_factory=fake_connection_factory,
            expect_json=False,
        )

        connection = captured["connection"]

        self.assertIsNone(payload)
        self.assertEqual(connection.request_method, "PUT")
        self.assertEqual(connection.request_target, "/rest/api/2/issue/CSD-10001/assignee")
        self.assertEqual(
            json.loads(connection.sent_body.decode("utf-8")),
            {"name": "xieziling@agora.io"},
        )
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
