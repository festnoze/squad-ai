"""Trusted REM-03 probe. Never imported from or executed inside product source.

The supervisor imports an explicit backend root under -I. Only the constant
smoke fixture is product code, and Pipeline runs it exclusively in NETNONE.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def durable(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".pending")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


# This is an owned local inference stand-in, NOT the paid Claude executable.
# Its barrier is emitted only after the real pipe has delivered the prompt.
LOCAL_CLI = r'''
import hashlib,json,os,sys,time
from pathlib import Path
root=Path(sys.argv[1]); payload=sys.stdin.read()
assert payload == 'REM03_LOCAL_ONLY_PROMPT'
value={'operation':'provider','cli_pid':os.getpid(),'cli_parent_pid':os.getppid(),'factory_pid':int(sys.argv[2]),
       'prompt_sha256':hashlib.sha256(payload.encode()).hexdigest(),'entered_at':time.time()}
with (root/'barrier.pending').open('w',encoding='utf-8') as stream:
 json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
os.replace(root/'barrier.pending',root/'barrier.json')
deadline=time.monotonic()+180
while not (root/'release').exists():
 if time.monotonic()>deadline:raise TimeoutError('probe release was not received')
 time.sleep(.02)
print('LOCAL_OWNED_RECEIPT')
'''


async def main(backend: Path, root: Path, operation: str, action: str) -> None:
    sys.path.insert(0, str(backend))
    from autospec import storage
    from autospec.config import settings
    from autospec.models import BuildStage, PipelinePhase, ProjectState, StoryStatus, Task, UserStory
    from autospec.agents.runner import AgentError, AgentResult, _run_tracked
    from autospec.orchestrator import pipeline as module

    settings.workspace_root = root / "workspace"
    settings.fake_agents = False
    settings.smoke_run = True
    settings.smoke_cli_help = False
    settings.smoke_run_timeout_s = 90
    settings.product_profile = "cli"
    settings.orphan_sweep_on_boot = False
    settings.skills_enabled = False
    settings.concurrent_budget_reservations = False
    settings.post_merge_canary = True
    settings.canary_batch_enabled = True

    class LocalCliRunner:
        async def arun(self, prompt, system_prompt, **kwargs):
            rc, out, err = await asyncio.to_thread(_run_tracked,
                [sys.executable, "-I", "-S", "-c", LOCAL_CLI, str(root), str(os.getpid())], prompt, None, 170)
            assert rc == 0, (out, err)
            assert out.strip() == "LOCAL_OWNED_RECEIPT"
            return AgentResult(out, cost_usd=0, input_tokens=1, output_tokens=1, usage_reported=True)

    class ForbiddenRunner:
        async def arun(self, *args, **kwargs):
            durable(root / "forbidden-call.json", {"operation": operation})
            raise AssertionError("Recovery must not start inference automatically")

    def flush(pipeline):
        pipeline._sync()
        module._PERSIST_EXECUTOR.submit(lambda: None).result(timeout=10)
        loaded = storage.load_state(pipeline.state.id)
        assert loaded is not None
        assert loaded.generation_checkpoint == pipeline.state.generation_checkpoint

    async def git(pipeline, *args):
        rc, output = await pipeline._agit(storage.workspace_dir("operation"), *args)
        assert rc == 0, (args, output)
        return output.strip()

    if action in {"interrupt", "nominal"}:
        status = {"provider": StoryStatus.IN_PROGRESS, "merge": StoryStatus.GREEN, "smoke": StoryStatus.DONE}[operation]
        stage = {"provider": BuildStage.IMPLEMENTING, "merge": BuildStage.MERGING, "smoke": BuildStage.DONE}[operation]
        task = Task(id="T1", story_id="US1", title="Owned probe", status=status,
                    current_stage=stage, attempts=1)
        story = UserStory(id="US1", epic_id="E1", title="Owned probe", status=status, tasks=[task])
        phase = PipelinePhase.GOVERN if operation == "smoke" else PipelinePhase.BUILD
        pipeline = module.Pipeline(ProjectState(id="operation", name="REM03", goal="Inert factory lifecycle probe",
            phase=phase, stories=[story], budget_usd=1, running=True, paused=True,
            resume_at=time.time()+3600), LocalCliRunner())
        ws = storage.workspace_dir("operation")
        ws.mkdir(parents=True, exist_ok=True)
        if operation == "merge":
            await git(pipeline, "init", "-b", "main")
            await git(pipeline, "config", "user.name", "Autospec REM03 owned fixture")
            await git(pipeline, "config", "user.email", "rem03@localhost.invalid")
            (ws / "payload.txt").write_bytes(b"base\n")
            await git(pipeline, "add", "payload.txt")
            await git(pipeline, "commit", "-m", "owned base")
            await git(pipeline, "checkout", "-b", "work/item")
            (ws / "payload.txt").write_bytes(b"real branch contribution\n")
            await git(pipeline, "add", "payload.txt")
            await git(pipeline, "commit", "-m", "owned contribution")
            branch = await git(pipeline, "rev-parse", "HEAD")
            await git(pipeline, "checkout", "main")
            base = await git(pipeline, "rev-parse", "HEAD")
            original_note = pipeline._anote_merge_sha

            async def after_real_merge(repo, wid):
                parents = (await git(pipeline, "rev-list", "--parents", "-n", "1", "HEAD")).split()
                assert parents[1:] == [base, branch]
                assert (ws / "payload.txt").read_bytes() == b"real branch contribution\n"
                durable(root / "barrier.json", {"operation": "merge", "factory_pid": os.getpid(),
                    "checkpoint_run_id": pipeline.state.generation_checkpoint["run_id"],
                    "merge_commit": parents[0], "parents": parents[1:],
                    "lock_owner": pipeline._merge_lock.owner, "entered_at": time.time(),
                    "boundary": "real Git merge returned; transaction final note not yet called"})
                deadline = time.monotonic() + 180
                while not (root / "release").exists():
                    if time.monotonic() > deadline:
                        raise TimeoutError("merge transaction probe was not released")
                    await asyncio.sleep(.02)
                await original_note(repo, wid)

            pipeline._anote_merge_sha = after_real_merge
        flush(pipeline)
        if operation == "provider":
            await pipeline._tracked.arun("REM03_LOCAL_ONLY_PROMPT", "LOCAL_OWNED_TEST_RUNNER")
        elif operation == "merge":
            assert await pipeline._amerge_work_item(ws, "work/item", "T1") == (True, [])
        else:
            from autospec.orchestrator import sandbox
            original_builder = sandbox.docker_run_cmd

            def record_actual_command(*args, **kwargs):
                argv = original_builder(*args, **kwargs)
                if args[0] == ["/opt/venv/bin/python", "main.py"]:
                    durable(root / "docker-dispatch.json", {"operation": "smoke", "argv": argv,
                        "owner": kwargs["run_id"], "name": kwargs["container_name"],
                        "factory_pid": os.getpid(), "entered_at": time.time()})
                return argv

            sandbox.docker_run_cmd = record_actual_command
            assert await pipeline._asmoke_phase(), pipeline.state.error
        flush(pipeline)
        durable(root / "completed.json", {"operation": operation,
            "usage": pipeline.state.usage.model_dump(), "checkpoint": pipeline.state.generation_checkpoint})
    elif action == "recover":
        from autospec.api import server
        server.pipelines = {}
        server._runner = ForbiddenRunner()
        assert server.recover_projects() == ["operation"]
        pipeline = server.pipelines["operation"]
        module._PERSIST_EXECUTOR.submit(lambda: None).result(timeout=10)
        state = storage.load_state("operation")
        assert state is not None
        assert state.phase == PipelinePhase.STOPPED
        assert state.generation_checkpoint["status"] == "interrupted"
        assert state.resume_at == 0 and not state.running and not state.paused
        assert not state.delivery_ready and pipeline._task is None and pipeline._resume_timer is None
        assert not (root / "forbidden-call.json").exists()
        durable(root / "recovered.json", {"operation": operation, "state": state.model_dump(mode="json"),
            "background_task": None, "automatic_provider_calls": 0})
        if operation == "provider":
            assert state.usage.unreported_calls == 1
            assert state.usage.agent_calls == 0
            try:
                await pipeline._tracked.arun("REM03_LOCAL_ONLY_PROMPT", "LOCAL_OWNED_TEST_RUNNER")
            except AgentError as exc:
                assert exc.code == "COST_UNREPORTED"
                durable(root / "resumed.json", {"operation": operation, "blocked_code": exc.code,
                    "reason": "Unknown interrupted receipt cannot be treated as free or re-spent"})
            else:
                raise AssertionError("Interrupted inference must fail closed before dispatch")
        else:
            assert state.usage.unreported_calls == 0
            old_run = state.generation_checkpoint["run_id"]
            pipeline.state.phase = PipelinePhase.GOVERN if operation == "smoke" else PipelinePhase.BUILD
            flush(pipeline)
            assert pipeline.state.generation_checkpoint["previous_run_id"] == old_run
            assert pipeline.state.generation_checkpoint["run_id"] != old_run
            if operation == "merge":
                old_head = await git(pipeline, "rev-parse", "HEAD")
                assert await pipeline._amerge_work_item(storage.workspace_dir("operation"), "work/item", "T1") == (True, [])
                assert await git(pipeline, "rev-parse", "HEAD") == old_head
                proof = {"merge_commit": old_head, "same_branch_replay_did_not_duplicate_commit": True}
            else:
                assert await pipeline._asmoke_phase(), pipeline.state.error
                proof = {"same_source_smoke_returned": True, "delivery_ready": pipeline.state.delivery_ready}
            flush(pipeline)
            durable(root / "resumed.json", {"operation": operation, **proof,
                "checkpoint": pipeline.state.generation_checkpoint})
    else:
        raise ValueError("unknown action")
    module._PERSIST_EXECUTOR.shutdown(wait=True)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3], sys.argv[4]))
