"""The npm audit gate is load-bearing security infrastructure (T-13): it
decides whether a high/critical advisory blocks the build or is suppressed by
a documented, expiring allowlist. Tested like code. Loaded from scripts/."""

import importlib.util
import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "npm_audit_gate", Path(__file__).parents[2] / "scripts" / "npm_audit_gate.py"
)
assert _SPEC and _SPEC.loader
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)

_GHSA = "GHSA-qwww-vcr4-c8h2"


def _audit(
    severity: str = "high", url: str = f"https://github.com/advisories/{_GHSA}"
) -> dict[str, Any]:
    """A minimal npm-audit --json shape with one advisory on react-router."""
    return {
        "vulnerabilities": {
            "react-router": {
                "severity": severity,
                "via": [
                    {"source": 1, "name": "react-router", "url": url, "severity": severity},
                    "react-router-dom",  # a transitive-dep string, not an advisory
                ],
            }
        }
    }


class TestAdvisoryExtraction:
    def test_extracts_high_advisory_by_ghsa(self) -> None:
        adv = gate._advisories(_audit("high"))
        assert set(adv) == {_GHSA}
        assert adv[_GHSA]["severity"] == "high"
        assert adv[_GHSA]["package"] == "react-router"

    def test_ignores_low_and_moderate(self) -> None:
        assert gate._advisories(_audit("moderate")) == {}
        assert gate._advisories(_audit("low")) == {}

    def test_critical_is_blocking(self) -> None:
        assert set(gate._advisories(_audit("critical"))) == {_GHSA}

    def test_string_via_entries_are_not_advisories(self) -> None:
        audit = {"vulnerabilities": {"x": {"severity": "high", "via": ["just-a-dep-name"]}}}
        assert gate._advisories(audit) == {}

    def test_empty_audit(self) -> None:
        assert gate._advisories({}) == {}
        assert gate._advisories({"vulnerabilities": {}}) == {}

    def test_unmappable_high_advisory_blocks(self) -> None:
        # A high/critical advisory with no GHSA url must NOT be silently dropped
        # (fail closed): it gets a synthetic UNMAPPED id so it can't be
        # allowlisted and it blocks.
        adv = gate._advisories(_audit("high", url="https://npmjs.com/advisories/1234"))
        assert len(adv) == 1
        (gid,) = adv
        assert gid.startswith("UNMAPPED:")


class TestAuditInfraFailsClosed:
    """A failed/errored `npm audit` (registry or network outage) must fail
    CLOSED, not be read as 'no vulnerabilities found'."""

    def _fake_proc(self, stdout: str, returncode: int = 1, stderr: str = "") -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    def test_error_json_raises(self, monkeypatch: Any, tmp_path: Path) -> None:
        payload = json.dumps({"error": {"code": "ENETUNREACH", "summary": "network down"}})
        monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: self._fake_proc(payload))
        with pytest.raises(SystemExit):
            gate._run_npm_audit(tmp_path)

    def test_missing_vulnerabilities_key_raises(self, monkeypatch: Any, tmp_path: Path) -> None:
        monkeypatch.setattr(
            gate.subprocess, "run", lambda *a, **k: self._fake_proc(json.dumps({"metadata": {}}))
        )
        with pytest.raises(SystemExit):
            gate._run_npm_audit(tmp_path)

    def test_empty_stdout_raises(self, monkeypatch: Any, tmp_path: Path) -> None:
        monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: self._fake_proc(""))
        with pytest.raises(SystemExit):
            gate._run_npm_audit(tmp_path)

    def test_clean_audit_with_empty_vulns_passes_through(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        # exit 0, has vulnerabilities key (empty) → valid, returns data
        proc = self._fake_proc(json.dumps({"vulnerabilities": {}, "metadata": {}}), returncode=0)
        monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: proc)
        assert gate._run_npm_audit(tmp_path) == {"vulnerabilities": {}, "metadata": {}}


class TestAllowlistLoading:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert gate._load_allowlist(tmp_path / "nope.json") == []

    def test_empty_file_is_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text("   ")
        assert gate._load_allowlist(p) == []

    def test_valid_entries(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text(json.dumps([{"id": _GHSA, "reason": "SPA, no RSC", "expires": "2026-10-22"}]))
        assert gate._load_allowlist(p)[0]["id"] == _GHSA

    def test_missing_required_key_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text(json.dumps([{"id": _GHSA, "reason": "x"}]))  # no expires
        with pytest.raises(SystemExit):
            gate._load_allowlist(p)

    def test_non_list_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text(json.dumps({"id": _GHSA}))
        with pytest.raises(SystemExit):
            gate._load_allowlist(p)

    @pytest.mark.parametrize("reason", ["", "   ", None])
    def test_blank_reason_rejected(self, tmp_path: Path, reason: Any) -> None:
        # A blank/absent-text justification must NOT be accepted (Codex P2).
        p = tmp_path / "a.json"
        p.write_text(json.dumps([{"id": _GHSA, "reason": reason, "expires": "2026-10-22"}]))
        with pytest.raises(SystemExit):
            gate._load_allowlist(p)

    def test_blank_id_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text(json.dumps([{"id": "  ", "reason": "x", "expires": "2026-10-22"}]))
        with pytest.raises(SystemExit):
            gate._load_allowlist(p)

    @pytest.mark.parametrize("bad_id", ["UNMAPPED:1234", "CVE-2024-1234", "GHSA-short", "random"])
    def test_non_ghsa_id_rejected(self, tmp_path: Path, bad_id: str) -> None:
        # The fail-closed guarantee: a non-GHSA id (esp. a synthetic UNMAPPED
        # one) can NEVER be allowlisted, so unmappable advisories keep blocking.
        p = tmp_path / "a.json"
        p.write_text(json.dumps([{"id": bad_id, "reason": "x", "expires": "2026-10-22"}]))
        with pytest.raises(SystemExit):
            gate._load_allowlist(p)

    def test_unmappable_cannot_be_suppressed_end_to_end(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        # A high advisory with no GHSA url gets an UNMAPPED id; even with an
        # allowlist entry attempting that id, load rejects it -> the advisory
        # still blocks.
        audit = _audit("high", url="https://npmjs.com/advisories/1234")
        entry = {"id": "UNMAPPED:1234", "reason": "try to hide it", "expires": "2026-10-22"}
        allow_path = tmp_path / ".audit-allowlist.json"
        allow_path.write_text(json.dumps([entry]))
        with pytest.raises(SystemExit):  # rejected at load — cannot be suppressed
            gate._load_allowlist(allow_path)
        # and with an empty allowlist it blocks as expected
        assert _run_gate(monkeypatch, audit, [], "2026-07-24", tmp_path) == 1

    def test_bad_expires_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text(json.dumps([{"id": _GHSA, "reason": "x", "expires": "soon"}]))
        with pytest.raises(SystemExit):
            gate._load_allowlist(p)


def _run_gate(
    monkeypatch: Any,
    audit: dict[str, Any],
    allowlist: list[dict[str, Any]],
    today: str,
    tmp_path: Path,
) -> int:
    monkeypatch.setattr(gate, "_run_npm_audit", lambda _dir: audit)
    allow_path = tmp_path / ".audit-allowlist.json"
    allow_path.write_text(json.dumps(allowlist))
    argv = ["prog", "--dir", str(tmp_path), "--allowlist", str(allow_path), "--today", today]
    monkeypatch.setattr("sys.argv", argv)
    rc: int = gate.main()
    return rc


class TestGateDecision:
    _entry: ClassVar[dict[str, Any]] = {
        "id": _GHSA,
        "reason": "client-side SPA, no RSC",
        "expires": "2026-10-22",
    }

    def test_not_allowlisted_blocks(self, monkeypatch: Any, tmp_path: Path) -> None:
        assert _run_gate(monkeypatch, _audit("high"), [], "2026-07-24", tmp_path) == 1

    def test_allowlisted_and_unexpired_passes(self, monkeypatch: Any, tmp_path: Path) -> None:
        assert _run_gate(monkeypatch, _audit("high"), [self._entry], "2026-07-24", tmp_path) == 0

    def test_allowlisted_but_expired_blocks(self, monkeypatch: Any, tmp_path: Path) -> None:
        # one day past expiry -> blocks again (forced re-review)
        assert _run_gate(monkeypatch, _audit("high"), [self._entry], "2026-10-23", tmp_path) == 1

    def test_no_advisories_passes(self, monkeypatch: Any, tmp_path: Path) -> None:
        assert (
            _run_gate(monkeypatch, {"vulnerabilities": {}}, [self._entry], "2026-07-24", tmp_path)
            == 0
        )

    def test_stale_entry_warns_but_passes(
        self, monkeypatch: Any, tmp_path: Path, capsys: Any
    ) -> None:
        # advisory gone but entry remains -> not blocking, but flagged stale
        rc = _run_gate(monkeypatch, {"vulnerabilities": {}}, [self._entry], "2026-07-24", tmp_path)
        assert rc == 0
        assert "stale allowlist entry" in capsys.readouterr().out

    def test_expiry_boundary_last_valid_day_passes(self, monkeypatch: Any, tmp_path: Path) -> None:
        # today == expires is still valid (expires is inclusive)
        assert _run_gate(monkeypatch, _audit("high"), [self._entry], "2026-10-22", tmp_path) == 0
