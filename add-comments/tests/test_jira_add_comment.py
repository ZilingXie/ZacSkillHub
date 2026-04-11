import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "jira_add_comment.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("jira_add_comment", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class JiraAddCommentTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.module = load_module()

    def make_file(self, relative_path: str, content, *, binary: bool = False) -> Path:
        path = Path(self.tmpdir.name) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def test_normalize_issue_input_accepts_key_and_browse_url(self):
        self.assertEqual(
            self.module.normalize_issue_input("CSD-77810"),
            "CSD-77810",
        )
        self.assertEqual(
            self.module.normalize_issue_input(
                "https://jira.agoralab.co/browse/CSD-77810"
            ),
            "CSD-77810",
        )

    def test_collect_attachment_infos_rejects_duplicate_basenames(self):
        first = self.make_file("one/screen.png", b"\x89PNG\r\n\x1a\n", binary=True)
        second = self.make_file("two/screen.png", b"\x89PNG\r\n\x1a\n", binary=True)

        with self.assertRaisesRegex(ValueError, "Duplicate attachment basename"):
            self.module.collect_attachment_infos([str(first), str(second)])

    def test_build_comment_body_replaces_placeholders_and_appends_other_files(self):
        screen = self.make_file("screen.png", b"\x89PNG\r\n\x1a\n", binary=True)
        extra = self.make_file("extra.jpg", b"\xff\xd8\xff", binary=True)
        log_file = self.make_file("agora.log", "log contents")
        attachments = self.module.collect_attachment_infos(
            [str(screen), str(extra), str(log_file)]
        )

        final_body, inlined_images = self.module.build_comment_body(
            "Investigation update\n{{image:screen.png}}",
            attachments,
        )

        self.assertIn("!screen.png!", final_body)
        self.assertIn("!extra.jpg!", final_body)
        self.assertIn("Attached files: agora.log", final_body)
        self.assertEqual(inlined_images, ["screen.png", "extra.jpg"])

    def test_build_comment_body_rejects_missing_or_non_image_placeholders(self):
        log_file = self.make_file("agora.log", "log contents")
        attachments = self.module.collect_attachment_infos([str(log_file)])

        with self.assertRaisesRegex(ValueError, "Placeholder image not found"):
            self.module.build_comment_body("{{image:screen.png}}", attachments)

        with self.assertRaisesRegex(ValueError, "is not an image attachment"):
            self.module.build_comment_body("{{image:agora.log}}", attachments)

    def test_main_requires_exactly_one_body_source(self):
        body_file = self.make_file("comment.txt", "hello")

        with self.assertRaisesRegex(ValueError, "--body or --body-file"):
            self.module.main(argv=["CSD-10001"])

        with self.assertRaisesRegex(ValueError, "Choose exactly one of --body or --body-file"):
            self.module.main(
                argv=[
                    "CSD-10001",
                    "--body",
                    "hello",
                    "--body-file",
                    str(body_file),
                ]
            )

    def test_main_dry_run_prints_comment_plan_without_touching_jira(self):
        image = self.make_file("screen.png", b"\x89PNG\r\n\x1a\n", binary=True)
        log_file = self.make_file("agora.log", "log contents")
        stdout = io.StringIO()

        result = self.module.main(
            argv=[
                "CSD-10001",
                "--body",
                "Investigation update {{image:screen.png}}",
                "--file",
                str(image),
                "--file",
                str(log_file),
            ],
            stdout=stdout,
            upload_attachments_func=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("dry-run should not upload")
            ),
            create_comment_func=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("dry-run should not add comment")
            ),
        )

        self.assertEqual(result["key"], "CSD-10001")
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["attachments"], ["screen.png", "agora.log"])
        self.assertEqual(result["inlined_images"], ["screen.png"])
        self.assertIn("!screen.png!", result["comment_body"])
        self.assertIn("Attached files: agora.log", result["comment_body"])
        self.assertIn("Dry run only.", stdout.getvalue())
        self.assertIn('"issue_url": "https://jira.agoralab.co/browse/CSD-10001"', stdout.getvalue())

    def test_main_add_uploads_attachments_before_comment_and_returns_links(self):
        image = self.make_file("screen.png", b"\x89PNG\r\n\x1a\n", binary=True)
        log_file = self.make_file("agora.log", "log contents")
        calls = []

        def fake_upload(issue_key, file_paths, **kwargs):
            calls.append(("upload", issue_key, [Path(path).name for path in file_paths]))
            return [
                {"filename": "screen.png"},
                {"filename": "agora.log"},
            ]

        def fake_comment(issue_key, body, **kwargs):
            calls.append(("comment", issue_key, body))
            return {"id": "20001"}

        result = self.module.main(
            argv=[
                "CSD-10001",
                "--body",
                "Investigation update {{image:screen.png}}",
                "--file",
                str(image),
                "--file",
                str(log_file),
                "--add",
            ],
            upload_attachments_func=fake_upload,
            create_comment_func=fake_comment,
            stdout=io.StringIO(),
        )

        self.assertEqual(
            calls,
            [
                ("upload", "CSD-10001", ["screen.png", "agora.log"]),
                ("comment", "CSD-10001", "Investigation update !screen.png!\n\nAttached files: agora.log"),
            ],
        )
        self.assertEqual(result["comment_id"], "20001")
        self.assertEqual(
            result["issue_url"],
            "https://jira.agoralab.co/browse/CSD-10001",
        )
        self.assertEqual(
            result["comment_url"],
            "https://jira.agoralab.co/browse/CSD-10001?focusedCommentId=20001#comment-20001",
        )

    def test_main_reports_uploaded_files_when_comment_creation_fails(self):
        log_file = self.make_file("agora.log", "log contents")

        def fake_upload(issue_key, file_paths, **kwargs):
            return [{"filename": Path(file_paths[0]).name}]

        def fake_comment(issue_key, body, **kwargs):
            raise RuntimeError("comment failed")

        with self.assertRaisesRegex(
            RuntimeError,
            "Uploaded attachments to https://jira.agoralab.co/browse/CSD-10001 but failed to add comment.*agora.log",
        ):
            self.module.main(
                argv=[
                    "CSD-10001",
                    "--body",
                    "Investigation update",
                    "--file",
                    str(log_file),
                    "--add",
                ],
                upload_attachments_func=fake_upload,
                create_comment_func=fake_comment,
                stdout=io.StringIO(),
            )


if __name__ == "__main__":
    unittest.main()
