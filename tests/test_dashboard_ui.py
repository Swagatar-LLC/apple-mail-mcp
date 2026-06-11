"""Tests for the inbox dashboard UI resource (SEC-01: <script> breakout XSS).

The dashboard injects ``accountsData`` / ``recentEmails`` into an inline
``<script>`` block. Those values carry attacker-controlled email metadata
(any incoming email's subject/sender), so the serialization must neutralize the
``</script>`` byte sequence that would otherwise terminate the script element at
HTML-parse time and inject arbitrary markup into the MCP-UI webview.
"""

import json
import unittest

from ui import create_inbox_dashboard_ui
from ui.dashboard import _safe_inline_json


# A subject crafted to break out of the inline <script> JSON blob.
BREAKOUT = "</script><img src=x onerror=alert(1)>"
# U+2028 / U+2029: valid JSON, but a raw newline inside a JS string literal.
LINE_SEP = " "
PARA_SEP = " "


def _dashboard_html(accounts, emails):
    """Return the rendered htmlString for a dashboard resource."""
    return create_inbox_dashboard_ui(accounts, emails).resource.text


class SafeInlineJsonTests(unittest.TestCase):
    def test_neutralizes_script_breakout(self):
        out = _safe_inline_json([{"subject": BREAKOUT}])
        # The literal closing tag must not survive ...
        self.assertNotIn("</script>", out)
        self.assertNotIn("</", out)
        # ... but the escaped form is present and JS-equivalent.
        self.assertIn("<\\/script>", out)

    def test_neutralizes_line_and_paragraph_separators(self):
        out = _safe_inline_json([{"subject": f"a{LINE_SEP}b{PARA_SEP}c"}])
        self.assertNotIn(LINE_SEP, out)
        self.assertNotIn(PARA_SEP, out)
        self.assertIn("\\u2028", out)
        self.assertIn("\\u2029", out)

    def test_remains_parseable_after_unescaping(self):
        # Reversing the parse-time-only escapes must yield the original data,
        # i.e. we did not corrupt the payload, only made it HTML-safe.
        out = _safe_inline_json([{"subject": BREAKOUT, "sender": "a b"}])
        restored = (
            out.replace("<\\/", "</")
            .replace("\\u2028", LINE_SEP)
            .replace("\\u2029", PARA_SEP)
        )
        data = json.loads(restored)
        self.assertEqual(data[0]["subject"], BREAKOUT)
        self.assertEqual(data[0]["sender"], "a b")


class DashboardBreakoutTests(unittest.TestCase):
    def test_email_subject_cannot_break_out_of_script(self):
        html = _dashboard_html(
            {"Gmail": 1},
            [{
                "subject": BREAKOUT,
                "sender": "attacker@example.com",
                "date": "2026-06-11",
                "is_read": False,
            }],
        )
        # The crafted closing tag must never appear literally in the output.
        self.assertNotIn("</script><img", html)
        # The escaped, inert form is what actually lands in the document.
        self.assertIn("<\\/script>", html)

    def test_account_name_cannot_break_out_of_script(self):
        html = _dashboard_html({BREAKOUT: 3}, [])
        self.assertNotIn("</script><img", html)
        self.assertIn("<\\/script>", html)

    def test_benign_data_still_injected(self):
        html = _dashboard_html(
            {"Work": 5},
            [{
                "subject": "Quarterly report",
                "sender": "boss@example.com",
                "date": "2026-06-11",
                "is_read": True,
            }],
        )
        self.assertIn("const accountsData =", html)
        self.assertIn("const recentEmails =", html)
        self.assertIn("Quarterly report", html)
        self.assertIn("Work", html)


class CdnPinningTests(unittest.TestCase):
    """SEC-03: the dashboard must not load an unpinned, no-SRI CDN script."""

    def test_no_executable_unpinned_cdn_script_tag(self):
        # The dead @latest reference must not be loaded by an actual <script src>
        # tag. (It may still be named in an explanatory HTML comment.)
        import re

        html = _dashboard_html({"Gmail": 1}, [])
        tags = re.findall(r"<script\b[^>]*\bsrc=[^>]*>", html, re.IGNORECASE)
        self.assertFalse(
            [t for t in tags if "mcp-apps-sdk" in t],
            msg="dead mcp-apps-sdk CDN script is still loaded by a <script src> tag",
        )

    def test_any_cdn_script_is_pinned_with_sri(self):
        # If a CDN <script src="https://..."> is ever (re)introduced, it must be
        # version-pinned (no @latest) and carry a Subresource Integrity hash.
        import re

        html = _dashboard_html({"Gmail": 1}, [])
        for tag in re.findall(r"<script\b[^>]*\bsrc=[^>]*>", html, re.IGNORECASE):
            if "https://" in tag:
                self.assertNotIn("@latest", tag)
                self.assertIn("integrity=", tag)


if __name__ == "__main__":
    unittest.main()
