# AGENTS.md

Guidance for human and AI contributors working in this repository.

## 1. What this is

`apple-mail-mcp` is a **FastMCP stdio server** that gives an AI assistant ~27 tools over the
local macOS **Mail.app**: read, search, compose/reply/forward, organize, bulk operations,
analytics, and export. There is no database, no backend, and **no network egress** in the
server — every operation builds an AppleScript string and shells out to `osascript`, then
parses the text result.

This repo is **`Swagatar-LLC/apple-mail-mcp`**, an internal fork of
[`patrickfreyer/apple-mail-mcp`](https://github.com/patrickfreyer/apple-mail-mcp) maintained
for **security hardening** (mirrors our `Swagatar-LLC/email-mcp` pattern). Keep diffs minimal
and upstream-friendly so we can contribute fixes back and pull updates cleanly.

- `origin`   → `Swagatar-LLC/apple-mail-mcp` (our fork)
- `upstream` → `patrickfreyer/apple-mail-mcp` (sync from here)

## 2. Quick reference

```bash
# Tests need the package on the path (it lives under plugin/, not installed for tests).
PYTHONPATH=plugin python -m pytest -q        # full suite (82 tests, ~1s, no Mail.app needed)
python scripts/check_versions.py             # version-drift guard (must pass)
```

Local setup:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r plugin/requirements.txt pytest
```

CI (`.github/workflows/ci.yml`) runs the test matrix (Python 3.10–3.13) + the version-drift
guard on every PR, plus a non-blocking `pip-audit` dependency scan. **All required checks must
be green before a PR merges.**

## 3. Architecture

```
plugin/apple_mail_mcp/
├── __main__.py          # CLI entry: --read-only flag, PPID orphan-watcher, mcp.run()
├── server.py            # FastMCP instance + USER_PREFERENCES + READ_ONLY flag
├── constants.py         # SKIP_FOLDERS, localized inbox-name table
├── core.py              # THE security + execution core (see §4)
└── tools/               # one module per capability group, each registers @mcp.tool fns
    ├── inbox.py         # read:   inbox overview / listing / unread counts
    ├── search.py        # read:   multi-account + content search
    ├── compose.py       # write:  compose / reply / forward (ASObjC clipboard HTML paste)
    ├── manage.py        # write:  move / flag / trash / drafts / attachments
    ├── analytics.py     # mixed:  statistics, export, dashboard data
    └── smart_inbox.py   # read:   newsletter / triage heuristics
plugin/ui/               # MCP-UI inbox dashboard (rawHtml resource) — untrusted-render surface
plugin/skills/           # SHIPPED product skill (see §6)
scripts/check_versions.py# fails if the 5 version strings drift apart
tests/                   # pytest unit tests; subprocess/osascript is mocked
```

Packaging targets: PyPI wheel (`pyproject.toml`), `.mcpb` desktop bundle
(`apple-mail-mcpb/manifest.json` + `plugin/start_mcp.sh`), MCP registry (`server.json`), and
Claude plugin (`.claude-plugin/`).

## 4. The security boundary — read before touching tools

Everything that reaches Mail goes through **`core.run_applescript()`**, the single `osascript`
choke-point. The defense against AppleScript/shell injection is:

1. **`core.escape_applescript(value)`** — every user/LLM-controlled **string** MUST pass through
   this (or a stricter whitelist) before being interpolated into an AppleScript source string.
   Builders in `core.py` (`build_mailbox_ref`, `contains_any_condition`, `build_filter_condition`)
   already do this; reuse them rather than hand-rolling f-strings.
2. **`core.normalize_message_ids()`** — message IDs are validated digits-only.
3. **FastMCP/Pydantic type coercion** — `int`-typed params are guaranteed numeric at interpolation.
4. **`do shell script`** must use AppleScript `quoted form of` or a random `tempfile` path —
   never raw interpolation.

**Rule:** if you add a tool argument that becomes part of an AppleScript or shell string, route
it through `escape_applescript()`/a whitelist and add a test asserting an injection payload
(e.g. `"` , `</script>`, `$(...)`, `\n`) is neutralized. Untrusted input also includes the
**content of processed emails** (subject/sender/body), not just tool args.

The MCP-UI dashboard (`plugin/ui/`) renders email metadata; treat it as a sink for stored/
indirect injection (data originates from arbitrary incoming mail).

## 5. Conventions

### Branches & PRs (our operating procedure)
- **All work happens on a branch and lands via PR.** No direct commits to `main`.
- Branch names: `feat/...`, `fix/...`, `chore/...`, `security/...`.
- Open the PR, ensure **CI is green**, then a human reviews/merges. Security PRs are reviewed by
  a human before merge — do not self-merge security changes.
- Keep PRs focused and upstream-friendly (one concern per PR).

### Commits — Conventional Commits
`type(scope): description` — types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`,
`ci`, `chore`, `revert`. Co-author trailers on agent-authored commits:

```
Co-Authored-By: Craft Agent <agents-noreply@craft.do>
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

### Python style
- Target **Python 3.10+**; keep the 3.10–3.13 matrix green.
- Type-hint public functions; write module/function docstrings (match the existing density in
  `core.py`).
- Prefer the shared AppleScript builders in `core.py` over inline f-strings.
- No new runtime dependencies without a clear need — this server is intentionally near-stdlib
  (only `fastmcp`, plus `mcp-ui-server` for the dashboard).

### Versioning — keep 5 files in sync
A release version appears in **five** places, enforced by `scripts/check_versions.py`:
`apple-mail-mcpb/manifest.json`, `pyproject.toml`, `server.json` (×2: `#version` and
`packages[0].version`), and `plugin/apple_mail_mcp/__init__.py`. Bump all five together or CI
fails.

### Tests
- Co-located in `tests/`, `pytest`, `unittest.mock` for `subprocess`/`osascript` (no real
  Mail.app in CI). New behavior needs a test; new escaping/injection defenses need an
  adversarial test.

## 6. Skills (shipped product skill)

This repo **ships** an end-user skill at `plugin/skills/email-management/` (loaded by the host
when the MCP is installed). It has valid frontmatter (`name`, `description`) and documents
inbox-triage / inbox-zero / folder-organization workflows. When you add or rename a tool,
update this skill's tool inventory (`SKILL.md` §"Available MCP Tools") so it stays accurate.
Treat it as product surface, not contributor docs — contributor guidance lives in this file.

## 7. Hard rules

1. Never weaken the `escape_applescript()` boundary or interpolate untrusted strings directly.
2. Never add network egress to the server without an explicit decision recorded in the PR.
3. Never commit secrets; there are none today (`gitleaks`-clean) — keep it that way.
4. Keep changes minimal and upstream-mergeable; we want to contribute fixes back.
5. CI green is a merge gate, not a suggestion.
