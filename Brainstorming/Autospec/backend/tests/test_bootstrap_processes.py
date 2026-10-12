"""Legacy bootstrap APIs have no host fallback.
Real Windows Jobs/descendant proofs live in test_owned_execution/test_runner_processes;
real isolated product runtime proof in test_linux_validation.
"""
import asyncio
import sys
import time
import pytest
from autospec.orchestrator import bootstrap

async def test_legacy_spawn_is_unavailable_without_creating_a_process(tmp_path):
    marker=tmp_path/'must-not-exist'
    with pytest.raises(bootstrap.BootstrapFailure,match='ISOLATION_UNAVAILABLE'):
        await bootstrap._spawn([sys.executable,'-c',f'open({str(marker)!r},"w").write("host")'],tmp_path,{})
    assert not marker.exists()

async def test_legacy_command_never_runs_host_product(tmp_path):
    marker=tmp_path/'must-not-exist'
    with pytest.raises(bootstrap.BootstrapFailure,match='ISOLATION_UNAVAILABLE'):
        await bootstrap._command([sys.executable,'-c',f'open({str(marker)!r},"w").write("host")'],tmp_path,{},time.monotonic()+2,None)
    assert not marker.exists()

async def test_cancelled_preflight_cannot_launch_another_command(tmp_path):
    cancel=asyncio.Event();cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await bootstrap._command([sys.executable,'-c','print("no")'],tmp_path,{},time.monotonic()+5,cancel)
