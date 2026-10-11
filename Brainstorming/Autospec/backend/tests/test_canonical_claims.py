import asyncio
import os

import pytest

from autospec.orchestrator.arbitration import ClaimArbiter
from autospec.orchestrator.claims import ClaimError, canonical_claim, canonical_path, claims_conflict, file_in_scope


@pytest.mark.parametrize("path", ["../clock.py", "src/../errors.py", "/tmp/file.py", r"C:\project\a.py",
                                r"C:relative.py", r"\\server\share\a.py", "file.py:secret", "\x00bad"])
def test_absolute_traversal_drives_and_ads_refused(path):
    with pytest.raises(ClaimError):
        canonical_path(path, windows=True)


def test_platform_case_separators_and_future_globs(tmp_path):
    claim = canonical_claim(r".\Relais_Support\Future\**\*.PY", project_root=tmp_path,
                            owner="A", windows=True)
    assert claim.path == "relais_support/future/**/*.py"
    assert claim.stream_root == str(tmp_path.resolve())
    assert canonical_path("Pkg/File.py", windows=False) == "Pkg/File.py"
    assert canonical_path("Pkg/File.py", windows=True) == "pkg/file.py"
    assert file_in_scope("relais_support/future/a.py", [claim.path], project_root=tmp_path, owner="A", windows=True)
    assert file_in_scope("relais_support/future/sub/a.py", [claim.path], project_root=tmp_path, owner="A", windows=True)
    assert not file_in_scope("relais_support/other/a.py", [claim.path], project_root=tmp_path, owner="A", windows=True)
    assert not file_in_scope("src/sub/a.py", ["src/*.py"], project_root=tmp_path, owner="A")


def test_real_scaffold_root_and_wrong_synthetic_backend_prefix(tmp_path):
    canonical_claim("relais_support/db.py", project_root=tmp_path, owner="A", stream_root="",
                    incompatible_prefixes=["backend/relais_support"])
    with pytest.raises(ClaimError, match="layout"):
        canonical_claim("backend/relais_support/db.py", project_root=tmp_path, owner="A", stream_root="",
                        incompatible_prefixes=["backend/relais_support"])
    canonical_claim("frontend/src/auth/**", project_root=tmp_path, owner="F", stream_root="frontend")
    with pytest.raises(ClaimError, match="outside"):
        canonical_claim("src/auth/**", project_root=tmp_path, owner="F", stream_root="frontend")


def test_symlink_escape_is_refused_before_future_file_write(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "product"
    root.mkdir()
    try:
        (root / "escape").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable on {os.name}: {exc}")
    with pytest.raises(ClaimError, match="escapes"):
        canonical_claim("escape/future/*.py", project_root=root, owner="A")


def test_cross_stream_paths_and_read_claims(tmp_path):
    a = canonical_claim("errors.py", project_root=tmp_path, owner="A")
    b = canonical_claim("ERRORS.py", project_root=tmp_path, owner="B", windows=True)
    assert claims_conflict(a, b)
    a = canonical_claim("errors.py", project_root=tmp_path, owner="A", mode="read")
    b = canonical_claim("errors.py", project_root=tmp_path, owner="B", mode="read")
    assert not claims_conflict(a, b)


async def test_two_synchronized_expansions_have_only_one_writer_and_requeue(tmp_path):
    arbiter = ClaimArbiter(max_attempts=3)
    claim = lambda owner, path: canonical_claim(path, project_root=tmp_path, owner=owner)
    assert (await arbiter.reserve("A", [claim("A", "a.py")])).status == "granted"
    assert (await arbiter.reserve("B", [claim("B", "b.py")])).status == "granted"
    barrier = asyncio.Event()

    async def expand(owner):
        await barrier.wait()
        return await arbiter.reserve(owner, [claim(owner, "clock.py"), claim(owner, "errors.py")], expand=True)

    tasks = [asyncio.create_task(expand(owner)) for owner in ("A", "B")]
    barrier.set()
    decisions = await asyncio.gather(*tasks)
    assert sorted(d.status for d in decisions) == ["granted", "waiting_claim"]
    winner = next(d.owner for d in decisions if d.status == "granted")
    loser = next(d.owner for d in decisions if d.status == "waiting_claim")
    assert not await arbiter.owns_write(loser, claim(loser, "clock.py"))
    assert not await arbiter.authorize_write(loser, "clock.py", project_root=tmp_path)
    assert await arbiter.owns_write(winner, claim(winner, "clock.py"))
    assert await arbiter.authorize_write(winner, "clock.py", project_root=tmp_path)
    # Existing integrated work is not rolled back by arbitration/requeue.
    integrated = {"a.py": "A output", "b.py": "B output"}
    await arbiter.release(winner)
    assert (await arbiter.reserve(loser, [claim(loser, "clock.py")], expand=True)).status == "granted"
    assert integrated == {"a.py": "A output", "b.py": "B output"}


async def test_wait_cycle_replans_and_retries_are_bounded(tmp_path):
    arbiter = ClaimArbiter(max_attempts=2)
    c = lambda owner, path: canonical_claim(path, project_root=tmp_path, owner=owner)
    await arbiter.reserve("A", [c("A", "clock.py")])
    await arbiter.reserve("B", [c("B", "errors.py")])
    assert (await arbiter.reserve("A", [c("A", "errors.py")], expand=True)).status == "waiting_claim"
    decision = await arbiter.reserve("B", [c("B", "clock.py")], expand=True)
    assert decision.status == "replan" and "cycle" in decision.reason
    await arbiter.release("B")
    assert (await arbiter.reserve("A", [c("A", "errors.py")], expand=True)).status == "granted"
    assert (await arbiter.reserve("C", [c("C", "clock.py")])).status == "waiting_claim"
    decision = await arbiter.reserve("C", [c("C", "clock.py")])
    assert decision.status == "replan" and decision.attempt == 2
    assert "C" not in (await arbiter.snapshot())["active"]
    await arbiter.release("C")
    assert (await arbiter.reserve("C", [c("C", "clock.py")])).attempt == 3


async def test_claim_expansion_is_all_or_nothing(tmp_path):
    arbiter = ClaimArbiter()
    c = lambda owner, path: canonical_claim(path, project_root=tmp_path, owner=owner)
    await arbiter.reserve("A", [c("A", "errors.py")])
    await arbiter.reserve("B", [c("B", "b.py")])
    decision = await arbiter.reserve("B", [c("B", "free.py"), c("B", "errors.py")], expand=True)
    assert decision.status == "waiting_claim"
    assert not await arbiter.owns_write("B", c("B", "free.py"))
    assert (await arbiter.snapshot())["active"]["B"] == ["b.py"]
    assert not await arbiter.authorize_write("B", "b.py", project_root=tmp_path / "other-project")
    with pytest.raises(ClaimError, match="another workspace"):
        await arbiter.reserve("C", [canonical_claim("b.py", project_root=tmp_path / "other", owner="C")])
