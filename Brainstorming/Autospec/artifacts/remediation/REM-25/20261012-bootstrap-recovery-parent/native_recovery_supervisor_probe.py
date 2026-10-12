"""Native trusted factory/owned Job/metadata probe on a fictional incident copy.

No POST ever reaches the factory: /resume-build is intercepted BEFORE transport
and acknowledged only to drive the supervisor's real owned stop/finally path.
No product source exists in the fixture; no provider or generation is started.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--port", type=int, default=8132)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    fixture = Path(args.fixture).resolve()
    parent = Path("C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011").resolve()
    if fixture.parent != parent or not fixture.name.startswith("native-recovery-supervisor-"):
        raise RuntimeError("exact owned new fixture directory required")
    if fixture.exists():
        raise RuntimeError("fixture exists; preserve it and choose a fresh invocation")
    spec = importlib.util.spec_from_file_location("native_recovery_campaign", root / "tools/support_benchmark_campaign.py")
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    c.check_port(args.port)
    original = c.WORKSPACE / c.RECOVERY_CAMPAIGN
    original_snapshot = c.recovery_snapshot(root, original, c.RECOVERY_PROJECT)
    # Copy only the exact pre-bootstrap supervisor files inspected above.
    # This is a test-fixture copy, never a second project creation/generation.
    fixture.mkdir()
    for relative, sha in original_snapshot["files_sha256"].items():
        source = original / relative
        target = fixture / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
            raise RuntimeError("fixture copy identity mismatch")
    (fixture / "projects/.autospec-tmp").mkdir(exist_ok=True)
    copied = dict(original_snapshot)
    copied["state"] = json.loads((fixture / copied["state_path"]).read_bytes())
    runtime = c.reserve_recovery(fixture, copied, {"factory_commit": args.commit})
    env = c.environment(dict(__import__("os").environ), fixture, args.port)
    processes, handles, requests = [], [], []
    actual_popen = c.subprocess.Popen
    actual_member = c.job_member_identity
    actual_http = c.http

    class RecordedPopen(actual_popen):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            processes.append(self)

    def member(job, pid):
        result = actual_member(job, pid)
        handles.append(result)
        return result

    base = f"http://127.0.0.1:{args.port}"
    endpoint = base + "/api/projects/" + c.RECOVERY_PROJECT

    def guarded_request(method, url, body=None):
        requests.append({"method": method, "url": url})
        if method == "POST" and url == endpoint + "/resume-build":
            # NEVER send this POST. The synthetic ACK is scoped to this probe.
            (runtime / "stop-intent.json").write_bytes(c.canonical({
                "action": "stop", "project_id": c.RECOVERY_PROJECT,
            }))
            return {"ok": True}
        allowed = {( "GET", base + "/api/health"), ("GET", endpoint),
                   ("PUT", endpoint + "/language")}
        if (method, url) not in allowed or (method == "PUT" and body != {"language": "python"}):
            raise RuntimeError("probe forbids any other request")
        return actual_http(method, url, body)

    c.subprocess.Popen = RecordedPopen
    c.job_member_identity = member
    c.http = guarded_request
    error = None
    result = None
    try:
        result = c.supervise(root, fixture, args.port, env, {"factory_commit": args.commit},
                             runtime_dir=runtime, recovery=copied)
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
    finally:
        state = json.loads((fixture / copied["state_path"]).read_bytes())
        # Closing the owned Windows Job initiates child termination; observe the
        # listener for a bounded interval instead of assuming synchronous exit.
        shutdown_started = time.monotonic()
        port_closed = False
        while time.monotonic() - shutdown_started < 5.0:
            alive = socket.socket()
            alive.settimeout(0.2)
            try:
                port_closed = alive.connect_ex(("127.0.0.1", args.port)) != 0
            finally:
                alive.close()
            if port_closed:
                break
            time.sleep(0.05)
        shutdown_seconds = time.monotonic() - shutdown_started
        evidence = {
            "factory_commit": args.commit, "fixture": str(fixture), "runtime": str(runtime),
            "result": result, "error": error, "requests": requests,
            "real_post_count": 0,
            "intercepted_resume_count": sum(r["method"] == "POST" for r in requests),
            "resume_ack_synthetic": any(r["method"] == "POST" for r in requests),
            "processes": [{"pid": p.pid, "exit_code": p.poll()} for p in processes],
            "retained_handles": [{"identity": str(h), "closed": h.handle is None} for h in handles],
            "port_closed": port_closed, "port_shutdown_observation_seconds": shutdown_seconds,
            "usage": state["usage"], "budget_usd": state["budget_usd"],
            "project_id": state["id"], "oracle_hash": state["acceptance_contract_hash"],
            "technical_stack": state["technical_stack"],
            "original_runtime_intact": all((fixture / name).read_bytes() == (original / name).read_bytes()
                for name in ("factory.log", "factory-identity.json", "input.json", "preflight.json")),
            "original_campaign_intact": c.recovery_snapshot(root, original, c.RECOVERY_PROJECT) == original_snapshot,
            "scope": "Native factory GET/PUT metadata and owned Job/finally only; no actual resume/generation/product acceptance",
        }
        (fixture / "native-probe.json").write_bytes(c.canonical(evidence))
        print(json.dumps(evidence, indent=2))
    assert error is None, error
    assert result == 0 and len(processes) == len(handles) == 1
    assert all(p.poll() is not None for p in processes) and all(h.handle is None for h in handles)
    assert evidence["port_closed"] and evidence["original_runtime_intact"] and evidence["original_campaign_intact"]
    assert state["usage"] == copied["state"]["usage"] and state["budget_usd"] == 40
    assert state["technical_stack"] == {"backend": "python", "source": "explicit"}
    assert sum(r["method"] == "POST" for r in requests) == 1  # intercepted, not sent
    assert sum(r["method"] == "PUT" for r in requests) == 1


if __name__ == "__main__":
    main()
