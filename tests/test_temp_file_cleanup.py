"""Regression tests for temp-file cleanup on error (SEC-04).

compose.py writes email HTML/body to a NamedTemporaryFile and reads it back from
inside the AppleScript via `cat`. The in-script `rm -f` only runs if the script
runs to completion, so on an osascript error or timeout the temp file — which
contains the (possibly sensitive) email body — would be orphaned in /var/folders.

Each osascript call is wrapped in a Python try/finally that os.unlink()s the temp
path. These tests lock that behavior in: the temp file is removed even when the
subprocess raises (timeout) or returns a non-zero error.
"""

import glob
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from apple_mail_mcp.tools import compose as compose_tools


def _temp_files_before():
    """Snapshot the mail_* temp files currently in the temp dir."""
    tmp = tempfile.gettempdir()
    return set(glob.glob(os.path.join(tmp, "mail_*")))


def _new_temp_files(before):
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "mail_*"))) - before


class HtmlSendCleanupTests(unittest.TestCase):
    def test_temp_file_removed_on_timeout(self):
        before = _temp_files_before()

        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="osascript", timeout=30)

        with patch.object(compose_tools.subprocess, "run", side_effect=boom):
            result = compose_tools._send_html_email(
                account="Gmail",
                to="a@example.com",
                subject="Secret subject",
                body_plain="secret body",
                body_html="<p>secret body</p>",
            )

        self.assertIn("timed out", result.lower())
        self.assertEqual(_new_temp_files(before), set(),
                         "HTML temp file orphaned after timeout")

    def test_temp_file_removed_on_error_return(self):
        before = _temp_files_before()

        class FakeResult:
            returncode = 1
            stdout = b""
            stderr = b"osascript: execution error"

        with patch.object(compose_tools.subprocess, "run", return_value=FakeResult()):
            compose_tools._send_html_email(
                account="Gmail",
                to="a@example.com",
                subject="Secret subject",
                body_plain="secret body",
                body_html="<p>secret body</p>",
            )

        self.assertEqual(_new_temp_files(before), set(),
                         "HTML temp file orphaned after error return")


if __name__ == "__main__":
    unittest.main()
