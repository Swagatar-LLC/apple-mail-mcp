"""Tests for export-path sanitization (SEC-05: ../ in mailbox name).

`export_emails` confines `save_directory` to $HOME, but the mailbox name is also
appended to build the export directory ({save_dir}/{mailbox}_export). The
mailbox name is attacker-influenced and was only AppleScript-escaped, which
leaves "/" and ".." intact — so a mailbox of "../../evil" could place the export
outside the validated directory. The fix sanitizes the path segment separately.
"""

import os
import unittest
from unittest.mock import patch

from apple_mail_mcp.tools import analytics
from apple_mail_mcp.tools.analytics import _safe_path_segment


class SafePathSegmentTests(unittest.TestCase):
    def test_strips_parent_traversal(self):
        self.assertNotIn("..", _safe_path_segment("../../evil"))
        self.assertNotIn("/", _safe_path_segment("../../evil"))

    def test_strips_absolute_path(self):
        seg = _safe_path_segment("/etc/passwd")
        self.assertEqual(seg, "passwd")

    def test_dot_only_names_become_safe_default(self):
        self.assertEqual(_safe_path_segment(".."), "mailbox")
        self.assertEqual(_safe_path_segment("..."), "mailbox")
        self.assertEqual(_safe_path_segment(""), "mailbox")

    def test_normal_name_preserved(self):
        self.assertEqual(_safe_path_segment("INBOX"), "INBOX")
        self.assertEqual(_safe_path_segment("Sent Messages"), "Sent_Messages")

    def test_segment_never_escapes_join(self):
        home = os.path.realpath(os.path.expanduser("~"))
        for hostile in ["../../evil", "/etc/passwd", "..", "a/b/../../c"]:
            seg = _safe_path_segment(hostile)
            full = os.path.realpath(os.path.join(home, f"{seg}_export"))
            self.assertTrue(
                full == os.path.join(home, f"{seg}_export")
                and (full == home or full.startswith(home + os.sep)),
                msg=f"{hostile!r} -> {seg!r} escaped {home}",
            )


class ExportEmailsPathTests(unittest.TestCase):
    def test_traversal_mailbox_exports_inside_save_directory(self):
        home = os.path.realpath(os.path.expanduser("~"))
        captured = {}

        def fake_run_applescript(script, *args, **kwargs):
            captured["script"] = script
            return "ok"

        with patch.object(analytics, "run_applescript", side_effect=fake_run_applescript):
            # export_emails is wrapped by @inject_preferences; call the underlying fn.
            fn = analytics.export_emails
            fn = getattr(fn, "__wrapped__", fn)
            result = fn(
                account="Gmail",
                scope="entire_mailbox",
                mailbox="../../evil",
                save_directory="~",
                format="txt",
                max_emails=1,
            )

        self.assertNotIn("Error", result if isinstance(result, str) else "")
        script = captured["script"]
        # The export dir line must not contain a traversal sequence.
        self.assertIn("evil_export", script)
        self.assertNotIn("../../evil_export", script)
        self.assertNotIn("..", script.split("_export")[0].rsplit("exportDir", 1)[-1])
        # And the literal directory written stays under $HOME.
        self.assertIn(f'"{home}/evil_export"', script)


if __name__ == "__main__":
    unittest.main()
