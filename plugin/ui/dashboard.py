"""
Apple Mail MCP Dashboard UI Module

Provides functions to create UI resources for the inbox dashboard.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any

from mcp_ui_server import create_ui_resource


def _safe_inline_json(data: Any) -> str:
    """Serialize ``data`` as JSON safe to embed inside an inline ``<script>``.

    ``json.dumps`` escapes quotes and backslashes but NOT the byte sequence
    ``</``. An HTML parser terminates a ``<script>`` element at the first literal
    ``</script>`` regardless of JavaScript string context, so an attacker-
    controlled email subject/sender of e.g. ``</script><img src=x onerror=...>``
    would break out of the data block at parse time (SEC-01).

    The data here is fully attacker-controlled: any incoming email's subject and
    sender flow unsanitized into the inbox dashboard. Neutralize the breakout
    sequences plus the two line/paragraph separators that are valid JSON but
    illegal in a JS string literal (U+2028/U+2029).
    """
    serialized = json.dumps(data, ensure_ascii=False)
    return (
        serialized.replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def create_inbox_dashboard_ui(
    accounts_data: Dict[str, int],
    recent_emails: List[Dict[str, Any]]
) -> Any:
    """
    Create a UI resource for the Apple Mail inbox dashboard.

    Args:
        accounts_data: Dictionary mapping account names to unread email counts.
                      Example: {"Gmail": 5, "Work": 12, "Personal": 3}
        recent_emails: List of recent email dictionaries with keys:
                      - subject: Email subject line
                      - sender: Sender name/email
                      - date: Date string
                      - is_read: Boolean indicating read status
                      - account: (optional) Account name
                      - preview: (optional) Email preview text

    Returns:
        UIResource with uri "ui://apple-mail/inbox-dashboard"
    """
    # Get the template file path
    template_path = Path(__file__).parent / "templates" / "dashboard.html"

    # Read the HTML template
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # Serialize the data for injection into the template. Both blobs carry
    # attacker-controlled email metadata and land inside an inline <script>,
    # so they must be neutralized against </script> parse-time breakout (SEC-01).
    accounts_json = _safe_inline_json(accounts_data)
    emails_json = _safe_inline_json(recent_emails)

    # Inject data into the template
    html_content = template_content.replace(
        "/* ACCOUNTS_DATA_PLACEHOLDER */",
        f"const accountsData = {accounts_json};"
    ).replace(
        "/* EMAILS_DATA_PLACEHOLDER */",
        f"const recentEmails = {emails_json};"
    )

    # Create and return the UI resource
    return create_ui_resource({
        "uri": "ui://apple-mail/inbox-dashboard",
        "content": {
            "type": "rawHtml",
            "htmlString": html_content
        },
        "encoding": "text"
    })
