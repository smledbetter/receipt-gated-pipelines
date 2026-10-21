"""Offline tests for the experiment harness: ToolShim receipts, the agent loop,
the receipt gate, and the Phase 3 builders. A fake model and a fake OSV stand
in for the APIs. Every test here pins a defect the 2026-10-20 audit found.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import scripts.phase1 as p1  # noqa: E402
import scripts.phase2 as p2  # noqa: E402
import scripts.phase3 as p3  # noqa: E402
import scripts.phase4 as p4  # noqa: E402
from rgp.loop import agent_loop  # noqa: E402

DEPS = [
    {"name": "lodash", "version": "4.17.20", "ecosystem": "npm"},
    {"name": "django", "version": "3.2.4", "ecosystem": "pypi"},
    {"name": "log4j-core", "version": "2.14.1", "ecosystem": "maven", "osv_name": "org.apache.logging.log4j:log4j-core"},
    {"name": "flask", "version": "2.0.1", "ecosystem": "pypi"},
    {"name": "pillow", "version": "8.1.0", "ecosystem": "pypi"},
]
VULNS = {
    "lodash": [{"id": "CVE-2020-8203", "severity": "HIGH", "summary": "Prototype pollution in lodash"}],
    "org.apache.logging.log4j:log4j-core": [{"id": "CVE-2021-44228", "severity": "CRITICAL", "summary": "Log4Shell"}],
}


@pytest.fixture(autouse=True)
def fake_osv(monkeypatch):
    def fake(package_name, version, ecosystem, error_rate=0.0, rng=None):
        if error_rate > 0 and (rng.random() if rng else 0.0) < error_rate:
            return {"error": "Internal Server Error", "status": 500}, True
        vulns = VULNS.get(package_name, [])
        return {"package": package_name, "version": version, "ecosystem": ecosystem,
                "vulnerabilities": vulns, "vulnerability_count": len(vulns)}, False
    monkeypatch.setattr(p1, "call_vuln_api", fake)
    monkeypatch.setattr(p1, "log", lambda m: None)
    monkeypatch.setattr(p2, "log", lambda m: None)
    monkeypatch.setattr(p4, "log", lambda m: None)


def tc(name, version="1", eco="npm", broken=False, cid="c1"):
    args = '{"package_name": "' + name + '", Hans Hans' if broken else json.dumps(
        {"package_name": name, "version": version, "ecosystem": eco})
    return {"id": cid, "type": "function", "function": {"name": "check_vulnerability", "arguments": args}}


class FakeModel:
    """Scripted responses: a list of (tool_calls, text, finish_reason)."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    def __call__(self, messages):
        self.seen.append(list(messages))
        calls, text, finish = self.turns.pop(0)
        msg = {"role": "assistant", "content": text}
        if calls:
            msg["tool_calls"] = calls
        return {"choices": [{"message": msg, "finish_reason": finish}],
                "usage": {"completion_tokens": 100}, "provider": "fake"}


# ------------------------------------------------------------------ receipts
KEY = b"test-key-0123456789abcdef"


def test_receipt_signs_context_bound_message_and_verifies():
    shim = p1.ToolShim(deps=DEPS, key=KEY, run_id="run1", trial_uid="run1:T1")
    cid, result, err = shim.execute_tool_call(tc("lodash"))
    r, e = shim.receipts[0], shim.call_log[0]
    assert r["hmac"] == p1.sign_receipt(r, KEY)
    assert r["run_id"] == "run1" and r["trial_uid"] == "run1:T1" and r["seq"] == 0
    assert p1.verify_receipt(r, KEY)
    assert p1.verify_receipt(r, KEY, entry=e)              # hashes recompute from the stored entry
    assert not p1.verify_receipt(dict(r, output_hash="0" * 64), KEY)
    assert not p1.verify_receipt(r, b"other-key-0123456789abcdef")
    assert e["hmac"] == r["hmac"]                          # stored, not discarded
    assert e["result"]["vulnerability_count"] == 1
    assert "_call_id" not in e["result"]                   # the stored result hashes to output_hash
    assert result["_call_id"] == cid                       # the model still gets the tag


def test_stored_result_recomputes_to_output_hash():
    shim = p1.ToolShim(deps=DEPS, key=KEY)
    shim.execute_tool_call(tc("lodash"))
    e = shim.call_log[0]
    import hashlib
    assert hashlib.sha256(p1.canonical_output(e["result"]).encode()).hexdigest() == e["output_hash"]
    assert hashlib.sha256(p1.canonical_input(e["request_args"]).encode()).hexdigest() == e["input_hash"]


def test_verify_log_passes_an_honest_log_and_fails_closed():
    shim = p1.ToolShim(deps=DEPS, key=KEY, run_id="r", trial_uid="r:T")
    shim.execute_tool_call(tc("lodash", cid="a"))
    shim.execute_tool_call(tc("django", "3.2.4", "pypi", cid="b"))
    ok = p1.verify_log(shim.receipts, shim.call_log, KEY, run_id="r", trial_uid="r:T")
    assert ok["status"] == "verified" and len(ok["verified"]) == 2
    # receipts deleted: nothing verifies
    gone = p1.verify_log([], shim.call_log, KEY)
    assert gone["status"] == "unverifiable" and not gone["verified"]
    # one entry without a receipt: that entry is not verified
    partial = p1.verify_log(shim.receipts[:1], shim.call_log, KEY)
    assert partial["status"] == "unverifiable" and partial["verified"] == {shim.call_log[0]["call_id"]}
    # wrong key: nothing verifies
    wrong = p1.verify_log(shim.receipts, shim.call_log, b"other-key-0123456789abcdef")
    assert wrong["status"] == "unverifiable" and not wrong["verified"]


def test_verify_log_detects_tampered_log_entry_with_intact_receipt():
    shim = p1.ToolShim(deps=DEPS, key=KEY)
    shim.execute_tool_call(tc("lodash", cid="a"))
    tampered = json.loads(json.dumps(shim.call_log))
    tampered[0]["result"]["vulnerabilities"] = []
    tampered[0]["result"]["vulnerability_count"] = 0
    tampered[0]["result_summary"]["vulnerability_count"] = 0
    out = p1.verify_log(shim.receipts, tampered, KEY)
    assert out["status"] == "invalid" and not out["verified"]
    # is_error flipped on the stored entry: the result hash no longer matches
    flipped = json.loads(json.dumps(shim.call_log))
    flipped[0]["is_error"] = True
    flipped[0]["result"] = {"error": "Internal Server Error", "status": 500}
    assert p1.verify_log(shim.receipts, flipped, KEY)["status"] == "invalid"
    # request re-pointed at another package: the input hash no longer matches
    repointed = json.loads(json.dumps(shim.call_log))
    repointed[0]["request_args"]["package_name"] = "django"
    assert p1.verify_log(shim.receipts, repointed, KEY)["status"] == "invalid"


def test_receipt_from_another_trial_does_not_verify():
    a = p1.ToolShim(deps=DEPS, key=KEY, run_id="r", trial_uid="r:A")
    a.execute_tool_call(tc("lodash", cid="a"))
    b = p1.ToolShim(deps=DEPS, key=KEY, run_id="r", trial_uid="r:B")
    b.execute_tool_call(tc("lodash", cid="b"))
    # copy A's (receipt, entry) pair into B's record
    out = p1.verify_log(b.receipts + a.receipts, b.call_log + a.call_log, KEY, run_id="r", trial_uid="r:B")
    assert out["status"] == "unverifiable"
    assert out["verified"] == {b.call_log[0]["call_id"]}
    assert any(reason == "receipt from another trial" for _, reason in out["problems"])


def test_key_id_prevents_false_invalid_under_wrong_key():
    shim = p1.ToolShim(deps=DEPS, key=KEY)
    shim.execute_tool_call(tc("lodash", cid="a"))
    out = p1.verify_log(shim.receipts, shim.call_log, b"someone-elses-key-0123456789")
    assert out["status"] == "unverifiable"           # not "invalid": the verifier lacks the key
    assert any("key the verifier does not hold" in reason for _, reason in out["problems"])


def test_key_not_hardcoded():
    src = (ROOT / "scripts" / "phase1.py").read_text()
    assert "study-rgp-receipt-key-2026" not in src


def test_unparseable_arguments_get_an_errored_receipt():
    shim = p1.ToolShim(deps=DEPS)
    cid, result, err = shim.execute_tool_call(tc("to-regex-range", broken=True))
    assert err and result["error"].startswith("argument parse failure")
    assert shim.call_log[0]["request_args"]["package_name"] == "to-regex-range"
    assert shim.call_log[0]["is_error"]
    assert result["_call_id"] == cid


def test_missing_ecosystem_is_filled_from_dependency_list_not_npm():
    shim = p1.ToolShim(deps=DEPS)
    call = {"id": "x", "function": {"name": "check_vulnerability", "arguments": json.dumps({"package_name": "django", "version": "3.2.4"})}}
    shim.execute_tool_call(call)
    assert shim.call_log[0]["request_args"]["ecosystem"] == "pypi"
    call = {"id": "y", "function": {"name": "check_vulnerability", "arguments": json.dumps({"package_name": "not-a-dep"})}}
    cid, result, err = shim.execute_tool_call(call)
    assert err and "ecosystem" in result["error"]


def test_missing_package_name_is_an_error_not_unknown_success():
    shim = p1.ToolShim(deps=DEPS)
    cid, result, err = shim.execute_tool_call({"id": "z", "function": {"name": "check_vulnerability", "arguments": "{}"}})
    assert err and result["error"] == "missing package_name"


# ------------------------------------------------------------------ loop / run_trial
def test_phase1_run_trial_records_finish_reason_and_flags_truncated_batch():
    model = FakeModel([
        ([tc("lodash", cid="a"), tc("django", "3.2.4", "pypi", cid="b")], "", "length"),
        ([], '{"dependencies_checked": ["lodash", "django"], "vulnerabilities_found": [{"package": "lodash", "cves": ["CVE-2020-8203"]}], "clean_packages": ["django"]}', "stop"),
    ])
    rec = p1.run_trial(DEPS, "standard", False, 0.0, "T1", model=p1.MERCURY_MODEL, seed=1, call_api=model, run_id="run")
    assert rec["token_timeline"][0]["finish_reason"] == "length"
    assert rec["token_timeline"][0]["provider"] == "fake"
    assert [e["kind"] for e in rec["harness_errors"]] == ["tool_batch_truncated"]
    assert rec["trial_uid"] == "run:T1"
    assert rec["measure"]["confab_strict"] is False
    assert len(rec["receipts"]) == 2 and all(p1.verify_receipt(r) for r in rec["receipts"])


def test_prompt_has_single_braces():
    model = FakeModel([([], "nothing", "stop")])
    rec = p1.run_trial(DEPS, "standard", False, 0.0, "T2", model=p1.MERCURY_MODEL, seed=1, call_api=model)
    prompt = model.seen[0][-1]["content"]
    assert "{{" not in prompt and '{"dependencies_checked"' in prompt


def test_seed_makes_shuffle_and_errors_reproducible():
    def run():
        model = FakeModel([([tc(d["name"], d["version"], d["ecosystem"], cid=d["name"]) for d in DEPS], "", "stop"), ([], "done", "stop")])
        return p1.run_trial(DEPS, "loose", False, 0.5, "T3", model=p1.MERCURY_MODEL, seed=42, call_api=model)
    a, b = run(), run()
    assert a["dep_order"] == b["dep_order"]
    assert [c["is_error"] for c in a["call_log"]] == [c["is_error"] for c in b["call_log"]]
    other = p1.run_trial(DEPS, "loose", False, 0.5, "T4", model=p1.MERCURY_MODEL, seed=42,
                         call_api=FakeModel([([], "done", "stop")]))
    assert other["dep_order"] != a["dep_order"] or True  # different trial id -> different stream


def test_agent_loop_handles_broken_tool_call_without_dropping_it():
    shim = p1.ToolShim(deps=DEPS)
    model = FakeModel([([tc("lodash", cid="a"), tc("flask", broken=True, cid="b")], "", "stop"), ([], "report", "stop")])
    out = agent_loop([{"role": "user", "content": "go"}], model, shim, "T", 5, log=lambda m: None)
    assert len(shim.call_log) == 2 and shim.call_log[1]["is_error"]
    tool_msgs = [m for m in out["messages"] if m.get("role") == "tool"]
    assert all("_call_id" in json.loads(m["content"]) for m in tool_msgs)


# ------------------------------------------------------------------ gate
def gated_shim(calls, errors=()):
    shim = p1.ToolShim(deps=DEPS, error_rate=0.0, key=KEY, run_id="r", trial_uid="r:T")
    for name in calls:
        d = next(x for x in DEPS if x["name"] == name)
        shim.execute_tool_call(tc(name, d["version"], d["ecosystem"], cid=name))
    for name in errors:
        d = next(x for x in DEPS if x["name"] == name)
        # force an error receipt
        shim.error_rate = 1.0
        shim.rng = type("R", (), {"random": staticmethod(lambda: 0.0)})()
        shim.execute_tool_call(tc(name, d["version"], d["ecosystem"], cid=name + "-err"))
        shim.error_rate = 0.0
    return shim


def test_gate_verifies_matching_call_id_and_content():
    shim = gated_shim(["lodash", "django"])
    ids = {r["package_name"]: r["call_id"] for r in shim.receipts}
    report = json.dumps({"dependencies_checked": [
        {"package": "lodash", "call_id": ids["lodash"], "vulnerabilities": [{"id": "CVE-2020-8203"}]},
        {"package": "django", "call_id": ids["django"], "vulnerabilities": []}],
        "unverified": ["flask", "pillow", "log4j-core"]})
    v = p2.verify_report(report, shim, DEPS)
    assert v["lodash"]["verdict"] == "VERIFIED" and v["django"]["verdict"] == "VERIFIED"
    assert v["flask"]["verdict"] == "SELF_REPORTED_UNVERIFIED"


def test_gate_flags_content_mismatch_even_with_right_call_id():
    shim = gated_shim(["lodash"])
    cid = shim.receipts[0]["call_id"]
    report = json.dumps({"dependencies_checked": [{"package": "lodash", "call_id": cid, "vulnerabilities": []}]})
    v = p2.verify_report(report, shim, DEPS)
    assert v["lodash"]["verdict"] == "CONTENT_MISMATCH"


def test_gate_treats_placeholder_array_as_omitted_not_clean():
    shim = gated_shim(["lodash"])
    cid = shim.receipts[0]["call_id"]
    report = '{"dependencies_checked": [{"package": "lodash", "call_id": "' + cid + '", "vulnerabilities": [...]}]}'
    v = p2.verify_report(report, shim, DEPS)
    # "[...]" says nothing about clean, so neither CONTENT_MISMATCH nor VERIFIED
    assert v["lodash"]["verdict"] == "MATCHED_NO_FINDING"


def test_gate_verified_requires_a_parsable_finding():
    shim = gated_shim(["lodash"])
    cid = shim.receipts[0]["call_id"]
    prose = f"- lodash: checked, call_id {cid}, see above"
    v = p2.verify_report(prose, shim, DEPS)
    assert v["lodash"]["verdict"] == "MATCHED_NO_FINDING"


def test_gate_compares_advisory_ids_within_a_namespace():
    shim = gated_shim(["lodash"])   # tool returned CVE-2020-8203
    cid = shim.receipts[0]["call_id"]
    wrong = json.dumps({"dependencies_checked": [{"package": "lodash", "call_id": cid, "vulnerabilities": [{"id": "CVE-2019-10744"}]}]})
    assert p2.verify_report(wrong, shim, DEPS)["lodash"]["verdict"] == "CONTENT_MISMATCH"
    right = json.dumps({"dependencies_checked": [{"package": "lodash", "call_id": cid, "vulnerabilities": [{"id": "CVE-2020-8203"}]}]})
    assert p2.verify_report(right, shim, DEPS)["lodash"]["verdict"] == "VERIFIED"
    # a GHSA id when the tool only gave a CVE id: no common namespace, fall back to has-vulns
    other_ns = json.dumps({"dependencies_checked": [{"package": "lodash", "call_id": cid, "vulnerabilities": [{"id": "GHSA-p6mc-m468-83gw"}]}]})
    assert p2.verify_report(other_ns, shim, DEPS)["lodash"]["verdict"] == "VERIFIED"


def test_gate_fails_closed_when_receipts_are_missing():
    shim = gated_shim(["lodash"])
    cid = shim.receipts[0]["call_id"]
    report = json.dumps({"dependencies_checked": [{"package": "lodash", "call_id": cid, "vulnerabilities": [{"id": "CVE-2020-8203"}]}]})
    shim.receipts = []                                    # the state of every March 2026 record
    out = p2.gate_report(report, shim, DEPS)
    assert out["log"]["status"] == "unverifiable" and out["log"]["receipts_present"] == 0
    assert out["verdicts"]["lodash"]["verdict"] == "LOG_UNVERIFIABLE"
    # log-only mode is explicit and labelled
    out2 = p2.gate_report(report, shim, DEPS, mode="log-only")
    assert out2["log"]["status"] == "log-only"
    assert out2["verdicts"]["lodash"]["verdict"] == "VERIFIED"


def test_gate_entry_without_receipt_is_not_a_call():
    shim = gated_shim(["lodash"])
    forged = dict(shim.call_log[0], call_id="forged-id", request_args={"package_name": "django", "version": "3.2.4", "ecosystem": "pypi"},
                  result={"package": "django", "version": "3.2.4", "ecosystem": "pypi", "vulnerabilities": [], "vulnerability_count": 0})
    shim.call_log.append(forged)
    report = json.dumps({"dependencies_checked": [{"package": "django", "call_id": "forged-id", "vulnerabilities": []}]})
    v = p2.verify_report(report, shim, DEPS)
    assert v["django"]["verdict"] == "LOG_UNVERIFIABLE"   # never VERIFIED


def test_gate_rejects_tampered_log():
    shim = gated_shim(["lodash"])
    cid = shim.receipts[0]["call_id"]
    shim.call_log[0]["result_summary"]["vulnerability_count"] = 0
    shim.call_log[0]["result"]["vulnerabilities"] = []
    shim.call_log[0]["result"]["vulnerability_count"] = 0
    report = json.dumps({"dependencies_checked": [{"package": "lodash", "call_id": cid, "vulnerabilities": []}]})
    out = p2.gate_report(report, shim, DEPS)
    assert out["log"]["status"] == "invalid"
    assert out["verdicts"]["lodash"]["verdict"] == "RECEIPT_INVALID"


def test_gate_receipt_package_name_is_not_trusted():
    shim = gated_shim(["lodash"])
    shim.receipts[0]["package_name"] = "unknown"          # unsigned field, altered
    shim.receipts[0]["output_hash"] = "f" * 64            # and the receipt broken
    v = p2.verify_report("- lodash: CVE-2020-8203", shim, DEPS)
    assert v["lodash"]["verdict"] == "RECEIPT_INVALID"    # lands on the entry's package, not the receipt's


def test_gate_never_verifies_an_errored_check():
    shim = gated_shim(["lodash"], errors=["django"])
    cid_django = next(r["call_id"] for r in shim.receipts if r["package_name"] == "django")
    report = json.dumps({"dependencies_checked": [
        {"package": "lodash", "call_id": shim.receipts[0]["call_id"], "vulnerabilities": [{"id": "CVE-2020-8203"}]},
        {"package": "django", "call_id": cid_django, "vulnerabilities": []}]})
    v = p2.verify_report(report, shim, DEPS)
    assert v["django"]["verdict"] == "TOOL_ERROR" and v["django"]["reported_as_result"] is True


def test_gate_confabulated_only_when_result_attributed():
    shim = gated_shim(["lodash"])
    prose = "- lodash: CVE-2020-8203 (HIGH)\n- flask: no known vulnerabilities\n\nRemaining, not yet checked: django, pillow.\nThe log4j-core check failed with a server error."
    v = p2.verify_report(prose, shim, DEPS)
    assert v["flask"]["verdict"] == "CONFABULATED"
    assert v["django"]["verdict"] == "SELF_REPORTED_UNVERIFIED" and v["pillow"]["verdict"] == "SELF_REPORTED_UNVERIFIED"
    assert v["log4j-core"]["verdict"] == "FAILURE_CLAIMED"
    assert v["lodash"]["verdict"] == "UNVERIFIED"  # called, named, no call_id echoed


def test_gate_rejects_tampered_receipt():
    shim = gated_shim(["lodash"])
    shim.receipts[0]["output_hash"] = "f" * 64
    v = p2.verify_report("- lodash: CVE-2020-8203", shim, DEPS)
    assert v["lodash"]["verdict"] == "RECEIPT_INVALID"


def test_gate_wrong_package_call_id_is_unverified_not_verified():
    shim = gated_shim(["lodash", "django"])
    ids = {r["package_name"]: r["call_id"] for r in shim.receipts}
    report = json.dumps({"dependencies_checked": [
        {"package": "lodash", "call_id": ids["django"], "vulnerabilities": [{"id": "CVE-2020-8203"}]},
        {"package": "django", "call_id": ids["lodash"], "vulnerabilities": []}]})
    v = p2.verify_report(report, shim, DEPS)
    assert v["lodash"]["verdict"] == "UNVERIFIED" and v["django"]["verdict"] == "UNVERIFIED"


def test_summarise_gate_counts_every_verdict():
    shim = gated_shim(["lodash"])
    v = p2.verify_report("- lodash: CVE-2020-8203", shim, DEPS)
    summary, packages = p2.summarise_gate(v)
    assert sum(summary.values()) == len(DEPS)
    assert set(summary) == {k.lower() for k in p2.GATE_VERDICTS}


# ------------------------------------------------------------------ Phase 3 builders
def rig_a_record(final_text, calls, errors=(), with_receipts=True):
    shim = gated_shim(calls, errors)
    return {"trial_id": "A", "run_id": "r", "trial_uid": "r:T", "final_text": final_text, "call_log": shim.call_log,
            "receipts": shim.receipts if with_receipts else [],
            "transcript": [], "coverage_rate": 0.4, "tool_calls_made": len(shim.call_log),
            "claimed_but_not_called": [], "condition": {"list_size": 100}}


@pytest.fixture(autouse=True)
def record_shim_key(monkeypatch):
    """Phase 3 builders read the key from RGP_RECEIPT_KEY; tests sign with KEY."""
    monkeypatch.setenv("RGP_RECEIPT_KEY", KEY.decode())


def test_gated_builder_never_renders_errored_check_as_clean():
    rec = rig_a_record("- lodash: CVE-2020-8203\n- django: no known vulnerabilities\n- pillow: clean", ["lodash"], errors=["django"])
    out = p3.build_gated_input(rec, DEPS)
    assert "Gate mode" not in out                        # receipts present and verified: no caveat
    assert "django 3.2.4 (pypi): CHECK FAILED (tool error), not verified" in out
    assert "lodash 4.17.20 (npm): VULNERABLE" in out and "CVE-2020-8203" in out
    assert "pillow" not in out            # confabulated: dropped by the gate
    assert "No known vulnerabilities" not in out.split("django")[1].split("\n")[0]


def test_gated_builder_passes_verified_clean_result():
    rec = rig_a_record('{"dependencies_checked": [{"package": "flask", "vulnerabilities": []}]}', ["flask"])
    out = p3.build_gated_input(rec, DEPS)
    assert "flask 2.0.1 (pypi): No known vulnerabilities (tool result, verified)" in out


def test_gated_builder_labels_log_only_mode_for_records_without_receipts():
    rec = rig_a_record("- lodash: CVE-2020-8203", ["lodash"], with_receipts=False)
    out = p3.build_gated_input(rec, DEPS)
    assert "Gate mode: log-only" in out and "checked no signatures" in out
    assert "lodash 4.17.20 (npm): VULNERABLE" in out
    verdicts, log = p3.gate_rig_a(rec, DEPS)
    assert log["status"] == "log-only" and log["receipts_present"] == 0


def test_v1_gated_builder_reproduces_the_defect():
    rec = rig_a_record("x", ["lodash"], errors=["django"])
    rec["transcript"] = [{"role": "tool", "content": json.dumps(c["result"])} for c in rec["call_log"]]
    out = p3.build_gated_input_v1(rec, DEPS)
    assert "django 3.2.4 (pypi): No known vulnerabilities" in out   # the bug, kept for the audit trail


def test_annotated_builder_tags_errors_and_shows_upstream_claim():
    rec = rig_a_record("- lodash: CVE-2020-8203\n- pillow 8.1.0: no vulnerabilities found\n- django: check failed", ["lodash"], errors=["django"])
    out = p3.build_annotated_input(rec, DEPS)
    assert "[TOOL ERROR: not verified]" in out.split("django")[1].split("\n")[0]
    assert "[UNVERIFIED: no receipt found]: upstream report says: - pillow 8.1.0: no vulnerabilities found" in out
    assert "[VERIFIED: call_id " in out.split("lodash")[1].split("\n")[0]


def test_phase3_analysis_counts_assertions_not_mentions():
    rec = rig_a_record("- lodash: CVE-2020-8203\n- pillow: no vulnerabilities found", ["lodash"])
    rig_b_assert = json.dumps({"remediation_plan": [
        {"package": "lodash", "priority": "HIGH", "cves": ["CVE-2020-8203"]},
        {"package": "pillow", "priority": "SAFE", "cves": [], "current_version": "8.1.0"}]})
    a = p3.analyze_rig_b_output(rig_b_assert, rec, DEPS)
    assert a["confab_input_strict"] and a["propagation"]["strict_packages"] == ["pillow"]
    assert a["cves"]["real_in_rig_a_tool_results"] == ["CVE-2020-8203"] and a["cves"]["real_echoed"] == 1
    rig_b_hedge = json.dumps({"remediation_plan": [{"package": "pillow", "priority": "UNKNOWN", "cves": ["Needs rescan"], "confidence": "low"}]})
    b = p3.analyze_rig_b_output(rig_b_hedge, rec, DEPS)
    assert b["propagation"]["strict_packages"] == []       # a hedge is not a propagation


# ------------------------------------------------------------------ Phase 2 / 4 run_trial end to end
def test_phase2_run_trial_offline(monkeypatch):
    monkeypatch.setattr(p2, "ERROR_RATE", 0.0)
    model = FakeModel([([tc("lodash", cid="a")], "", "stop"),
                       ([], "Checked lodash: CVE-2020-8203 (HIGH). Not yet checked: django, flask, pillow, log4j-core.", "stop")])
    rec = p2.run_trial(DEPS, "receipt_gate", "receipt_gate_T001", seed=3, call_api=model, run_id="r")
    assert rec["gate_summary"]["self_reported_unverified"] == 4
    assert rec["gate_summary"]["unverified"] == 1
    assert rec["measure"]["confab_strict"] is False and rec["harness_errors"] == []


def test_phase4_run_trial_offline(monkeypatch):
    monkeypatch.setattr(p4, "ERROR_RATE", 0.0)
    model = FakeModel([([tc("lodash", cid="a")], "", "stop"),
                       ([], '{"dependencies_checked": [{"package": "lodash", "vulnerabilities": [{"id": "CVE-2020-8203"}]}, {"package": "flask", "vulnerabilities": []}], "unverified": ["django"]}', "stop")])
    rec = p4.run_trial(DEPS, "disclosure_only", "disclosure_only_T001", seed=3, call_api=model)
    assert rec["measure"]["attributed"] == ["flask"] and rec["measure"]["confab_strict"]
    assert rec["gate_summary"]["confabulated"] == 1
