"""Trusted supervisor probe: actual Windows/HTTP, intercepted creation, no LLM.

No product imports or host execution. Only Autospec's trusted factory starts.
The parent create_once boundary is replaced by a deliberate exception after
live ownership admission, so not even one project POST can be sent.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys


class ProbeComplete(Exception):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--expected-commit",required=True)
    parser.add_argument("--campaign",required=True)
    parser.add_argument("--port",type=int,default=8131)
    args = parser.parse_args()
    root = args.root.resolve()
    spec = importlib.util.spec_from_file_location("native_campaign_probe",root/"tools/support_benchmark_campaign.py")
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    campaign = c.WORKSPACE/args.campaign
    env = c.environment(os.environ,campaign,args.port)
    receipt = c.preflight(root,campaign,args.port,args.expected_commit,env)
    campaign.mkdir(exist_ok=False)
    (campaign/"projects").mkdir()
    processes, interpreters, requests, attempts = [], [], [], []
    popen, member, http = c.subprocess.Popen, c.job_member_identity, c.http
    class OwnedPopen(popen):
        # Keep class semantics for asyncio.windows_utils.Popen's cold import.
        # No fake process: the exact native Popen/handles remain underneath.
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            processes.append(self)
    def owned_member(*a,**kw):
        actual = member(*a,**kw)
        actual.assert_alive()
        interpreters.append(actual)
        return actual
    def health_only(method,url,body=None):
        assert method=="GET" and url==f"http://127.0.0.1:{args.port}/api/health", "Non-health RPC forbidden by this probe"
        requests.append(dict(method=method,path="/api/health"))
        return http(method,url,body)
    def intercept_creation(*a,**kw):
        assert len(interpreters)==1 and interpreters[0].handle
        interpreters[0].assert_alive()
        attempts.append("intercepted before POST; no project and no inference")
        raise ProbeComplete()
    c.subprocess.Popen, c.job_member_identity = OwnedPopen, owned_member
    c.http, c.create_once = health_only, intercept_creation
    completed = False
    try:
        try:
            c.supervise(root,campaign,args.port,env,receipt)
        except ProbeComplete:
            completed = True
    finally:
        c.subprocess.Popen, c.job_member_identity, c.http = popen, member, http
        event_path=campaign/"supervisor.jsonl"
        events=[json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
        result=dict(scope="trusted actual supervisor with intercepted creation; NOT a generation",
            factory_commit=receipt["factory_commit"],auth=receipt["auth"],checked_at=receipt["checked_at"],
            source_hashes=receipt["source_hashes"],docker_os=receipt["docker_os"],port=args.port,
            admitted_before_interception=completed,health_requests=requests,intercepted_attempts=attempts,
            owned_process_count=len(processes),process_return_codes=[p.poll() for p in processes],
            retained_interpreter_count=len(interpreters),retained_handles_closed=all(p.handle is None for p in interpreters),
            events=events,project_created=(campaign/"creation-attempt.json").exists(),
            generated_project_files=list((campaign/"projects").iterdir()))
        (campaign/"native-probe.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        assert completed and len(processes)==len(interpreters)==len(attempts)==1
        assert all(p.poll() is not None for p in processes)
        assert result["retained_handles_closed"]
        assert not result["project_created"] and not result["generated_project_files"]
        assert {"FACTORY_OWNED","INTERPRETER_OWNED","SUPERVISOR_STOPPED"}<={e["event"] for e in events}
        assert "OWNED_CLEANUP_ERROR" not in {e["event"] for e in events}
        try:
            with socket.create_connection(("127.0.0.1",args.port),timeout=.5):
                raise AssertionError("Owned test server still listening after cleanup")
        except OSError:
            result["owned_port_closed"] = True
        (campaign/"native-probe.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps({k:result[k] for k in ("factory_commit","auth","admitted_before_interception",
            "owned_process_count","process_return_codes","retained_handles_closed","project_created","owned_port_closed")}))


if __name__=="__main__":
    main()
