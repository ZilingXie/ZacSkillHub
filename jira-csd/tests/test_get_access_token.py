import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "get_access_token.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("get_access_token", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class GetAccessTokenTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def write_env(self, content):
        tmpdir = tempfile.TemporaryDirectory()
        env_path = Path(tmpdir.name) / ".env"
        env_path.write_text(content, encoding="utf-8")
        self.addCleanup(tmpdir.cleanup)
        return env_path

    def test_load_env_returns_required_credentials(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "JIRA_OAUTH_CLIENT_ID=client-id",
                    "JIRA_OAUTH_CLIENT_SECRET=client-secret",
                    "JIRA_OAUTH_USERNAME=user@example.com",
                    "JIRA_OAUTH_PASSWORD=pass-123",
                ]
            )
        )

        config = self.module.load_env(env_path)

        self.assertEqual(
            config,
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "username": "user@example.com",
                "password": "pass-123",
            },
        )

    def test_load_env_rejects_missing_required_credentials(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "JIRA_OAUTH_CLIENT_ID=client-id",
                    "JIRA_OAUTH_USERNAME=user@example.com",
                ]
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "JIRA_OAUTH_CLIENT_SECRET, JIRA_OAUTH_PASSWORD",
        ):
            self.module.load_env(env_path)

    def test_fetch_access_token_posts_form_urlencoded_payload(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = {
                key.lower(): value for key, value in request.header_items()
            }
            captured["body"] = parse_qs(request.data.decode("utf-8"))
            return FakeResponse({"access_token": "token-123"})

        token = self.module.fetch_access_token(
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "username": "user@example.com",
                "password": "pass-123",
            },
            urlopen=fake_urlopen,
        )

        self.assertEqual(token, "token-123")
        self.assertEqual(captured["url"], self.module.OAUTH_TOKEN_URL)
        self.assertEqual(captured["timeout"], 30)
        self.assertEqual(
            captured["headers"]["content-type"],
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(
            captured["body"],
            {
                "grant_type": ["password"],
                "client_id": ["client-id"],
                "client_secret": ["client-secret"],
                "username": ["user@example.com"],
                "password": ["pass-123"],
            },
        )

    def test_main_prints_only_the_access_token(self):
        env_path = self.write_env(
            "\n".join(
                [
                    "JIRA_OAUTH_CLIENT_ID=client-id",
                    "JIRA_OAUTH_CLIENT_SECRET=client-secret",
                    "JIRA_OAUTH_USERNAME=user@example.com",
                    "JIRA_OAUTH_PASSWORD=pass-123",
                ]
            )
        )
        stdout = io.StringIO()

        token = self.module.main(
            env_path=env_path,
            urlopen=lambda request, timeout: FakeResponse(
                {"access_token": "token-abc"}
            ),
            stdout=stdout,
        )

        self.assertEqual(token, "token-abc")
        self.assertEqual(stdout.getvalue(), "token-abc\n")


if __name__ == "__main__":
    unittest.main()
