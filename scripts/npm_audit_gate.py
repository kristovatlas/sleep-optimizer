#!/usr/bin/env python3
"""npm audit gate with a documented, expiring per-advisory allowlist (T-13).

Plain ``npm audit`` has no way to suppress a single advisory, so a genuinely
non-applicable high/critical finding would wedge every PR. This wrapper runs
the same lockfile-only, production-only audit and fails on any high/critical
advisory that is NOT on an explicit allowlist. Each allowlist entry carries a
written reason and an expiry date: an expired entry is treated as NOT
allowlisted (it blocks again), forcing periodic re-review instead of a
forever-suppression. Stdlib only -- no new dependency to audit.

CI usage (from repo root):  python3 scripts/npm_audit_gate.py --dir frontend
Allowlist: ``<dir>/.audit-allowlist.json`` -- a list of
``{"id": "GHSA-xxxx", "reason": "...", "expires": "YYYY-MM-DD"}``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

_GHSA = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}", re.IGNORECASE)
_BLOCKING = {"high", "critical"}


def _run_npm_audit(dir_: Path) -> dict[str, Any]:
    """Run the production, lockfile-only audit and return parsed JSON.

    npm audit exits non-zero when vulnerabilities exist; that is expected --
    we read stdout regardless and only fail on our own allowlist decision.
    """
    proc = subprocess.run(
        ["npm", "audit", "--package-lock-only", "--omit=dev", "--json"],
        cwd=dir_,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        raise SystemExit(
            f"npm audit produced no JSON output (exit {proc.returncode}; "
            f"stderr: {proc.stderr.strip()})"
        )
    try:
        data: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"could not parse npm audit JSON: {exc}") from exc
    # Fail CLOSED if the audit itself did not complete (registry/network error):
    # a successful audit always has a "vulnerabilities" key (possibly empty); an
    # errored one emits {"error": {...}} with a non-zero exit and no
    # vulnerabilities. Treating that as "no vulns found" would silently pass a
    # PR during an advisory-DB outage (a normal audit-with-vulns also exits
    # non-zero, but it HAS "vulnerabilities" — so we key on the data, not the
    # exit code).
    if "error" in data or "vulnerabilities" not in data:
        raise SystemExit(
            f"npm audit did not complete (exit {proc.returncode}): "
            f"{data.get('error', 'no vulnerabilities key in output')}"
        )
    return data


def _advisories(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract blocking (high/critical) advisories, keyed by GHSA id."""
    found: dict[str, dict[str, Any]] = {}
    for pkg, node in (audit.get("vulnerabilities") or {}).items():
        for via in node.get("via", []):
            if not isinstance(via, dict):
                continue  # a plain string == a transitive dep name, not an advisory
            sev = str(via.get("severity", "")).lower()
            if sev not in _BLOCKING:
                continue
            # Fail CLOSED on an advisory we cannot map to a GHSA id: it can't be
            # allowlisted (entries are keyed by GHSA), so give it a synthetic
            # UNMAPPED id and let it block + be reported, rather than dropping it.
            match = _GHSA.search(str(via.get("url", "")))
            gid = (
                match.group(0)
                if match
                else f"UNMAPPED:{via.get('source') or via.get('url') or pkg}"
            )
            found.setdefault(
                gid,
                {
                    "id": gid,
                    "severity": sev,
                    "package": via.get("name", pkg),
                    "url": via.get("url") or "(no advisory url)",
                },
            )
    return found


def _load_allowlist(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text().strip()
    if not text:
        return []  # empty file == no allowlist
    data = json.loads(text)
    if not isinstance(data, list):
        raise SystemExit(f"{path}: allowlist must be a JSON list")
    for entry in data:
        if not isinstance(entry, dict) or not {"id", "reason", "expires"} <= set(entry):
            raise SystemExit(f"{path}: each entry needs id, reason, expires -- got {entry}")
        # ids MUST be real GHSA ids. This is what keeps the fail-closed
        # guarantee honest: an advisory with no GHSA url is keyed UNMAPPED:<..>
        # in _advisories, and because that is not a GHSA id it can never be
        # placed on the allowlist -- so unmappable advisories always block
        # (Codex P2). Also blocks blank/non-string ids.
        if not (isinstance(entry["id"], str) and _GHSA.fullmatch(entry["id"])):
            raise SystemExit(
                f"{path}: entry 'id' must be a GHSA id (GHSA-xxxx-xxxx-xxxx) -- got {entry}"
            )
        # A blank reason would suppress an advisory with no written justification,
        # defeating the point of the allowlist (Codex P2). Require real text.
        if not (isinstance(entry["reason"], str) and entry["reason"].strip()):
            raise SystemExit(
                f"{path}: entry 'reason' must be a non-empty written justification -- got {entry}"
            )
        try:
            dt.date.fromisoformat(str(entry["expires"]))
        except ValueError as exc:
            raise SystemExit(f"{path}: entry 'expires' must be YYYY-MM-DD -- got {entry}") from exc
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="frontend")
    ap.add_argument("--allowlist", default=None)
    ap.add_argument("--today", default=None, help="override today (YYYY-MM-DD) for tests")
    args = ap.parse_args()

    dir_ = Path(args.dir)
    allow_path = Path(args.allowlist) if args.allowlist else dir_ / ".audit-allowlist.json"
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    advisories = _advisories(_run_npm_audit(dir_))
    allow = {e["id"]: e for e in _load_allowlist(allow_path)}

    blocking: list[str] = []
    for gid, adv in sorted(advisories.items()):
        entry = allow.get(gid)
        head = f"{gid} [{adv['severity']}] {adv['package']}"
        if entry is None:
            blocking.append(f"  x {head} -- {adv['url']}")
            continue
        if today > dt.date.fromisoformat(entry["expires"]):
            blocking.append(f"  x {head} -- allowlist entry EXPIRED {entry['expires']}; re-review")
        else:
            print(f"  suppressed {head} until {entry['expires']}: {entry['reason']}")

    # Stale allowlist entries (advisory no longer present) -- warn, don't block.
    for gid in allow:
        if gid not in advisories:
            print(f"  stale allowlist entry {gid}: advisory no longer reported -- safe to remove")

    if blocking:
        print(
            f"\nnpm-audit-gate: FAIL -- {len(blocking)} un-allowlisted high/critical advisory(ies):"
        )
        print("\n".join(blocking))
        return 1
    print(f"\nnpm-audit-gate: PASS -- no un-allowlisted high/critical advisories ({dir_}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
