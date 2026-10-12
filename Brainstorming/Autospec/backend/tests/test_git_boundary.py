"""No hostile hook/filter is executed: refusal is tested before dispatch."""
import os

import pytest

from autospec.orchestrator.git_boundary import GitConfigurationRefused,git_invocation,run_git


@pytest.mark.parametrize("config",['[include]\npath = ../private',
    '[includeIf "gitdir:*"]\npath = elsewhere','[filter "example"]\nclean = untrusted',
    '[merge "example"]\ndriver = untrusted','[diff "example"]\ntextconv = untrusted',
    '[core]\nfsmonitor = untrusted','[core]\nhooksPath = elsewhere',
    '[alias]\naction = !untrusted','[commit]\ngpgsign = true'])
def test_executable_brownfield_configuration_refused_without_git_dispatch(tmp_path,config,monkeypatch):
    (tmp_path/".git").mkdir();(tmp_path/".git/config").write_text(config)
    from autospec.agents import runner
    monkeypatch.setattr(runner,"_run_tracked",lambda *a:pytest.fail("unsafe config must not reach process"))
    with pytest.raises(GitConfigurationRefused):run_git(tmp_path,["status","--porcelain"])


def test_invocation_removes_config_credentials_pager_and_process_hooks(tmp_path,monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT","1");monkeypatch.setenv("GIT_CONFIG_KEY_0","filter.example.clean")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0","untrusted");monkeypatch.setenv("GIT_SSH_COMMAND","untrusted")
    argv,env=git_invocation(tmp_path,["add","-A"])
    assert "core.fsmonitor=false" in argv and any(a.startswith("core.hooksPath=") for a in argv)
    assert "GIT_CONFIG_COUNT" not in env and "GIT_CONFIG_KEY_0" not in env and "GIT_SSH_COMMAND" not in env
    assert env["GIT_CONFIG_NOSYSTEM"]=="1" and env["GIT_CONFIG_GLOBAL"]==os.devnull
    assert f"--git-dir={tmp_path}/.git".replace("/",os.sep) in [a.replace("/",os.sep) for a in argv]


@pytest.mark.parametrize("command",["fetch","push","clone","credential","custom-alias"])
def test_remote_and_external_git_operations_not_admitted(tmp_path,command):
    with pytest.raises(GitConfigurationRefused):git_invocation(tmp_path,[command])


@pytest.mark.parametrize("args", [["clean","-xffd"],["clean","-fd","../parent"],["clean","-ffdx"]])
def test_rollback_cleanup_cannot_expand_beyond_local_nonignored_files(tmp_path,args):
    with pytest.raises(GitConfigurationRefused): git_invocation(tmp_path,args)


@pytest.mark.parametrize("failure", ["reset", "clean"])
async def test_refused_rollback_never_reports_success(tmp_path,monkeypatch,failure):
    from autospec.agents.runner import FakeRunner
    from autospec.models import ProjectState
    from autospec.orchestrator.pipeline import Pipeline
    pipeline=Pipeline(ProjectState(id="rollback-refusal",name="fixture",goal="offline"),FakeRunner())
    async def owned(ws): return True
    calls=[]
    async def git(ws,*args):
        calls.append(args)
        return (1,"refused") if args[0]==failure else (0,"")
    monkeypatch.setattr(pipeline,"_ahas_workspace_git",owned)
    monkeypatch.setattr(pipeline,"_agit",git)
    with pytest.raises(ValueError,match="rollback incomplet"):
        await pipeline._areset_workspace(tmp_path,"HEAD")
    assert len(calls)==(1 if failure=="reset" else 2)


def test_native_owned_git_repo_worktree_merge_and_no_parent_adoption(tmp_path):
    parent=tmp_path/"parent";parent.mkdir()
    assert run_git(parent,["init"])[0]==0
    product=parent/"product";product.mkdir()
    assert run_git(product,["init"])[0]==0
    assert run_git(product,["config","user.email","fixture@example.invalid"])[0]==0
    assert run_git(product,["config","user.name","Factory fixture"])[0]==0
    (product/"main.py").write_text("# data, not executed\n")
    assert run_git(product,["add","-A"])[0]==0
    assert run_git(product,["commit","-m","fixture"])[0]==0
    owned=tmp_path/"linked"
    assert run_git(product,["worktree","add","-b","fixture-branch",str(owned),"HEAD"])[0]==0
    assert run_git(owned,["rev-parse","--show-toplevel"])[1].strip().replace("\\","/")==str(owned).replace("\\","/")
    (owned/"main.py").write_text("# changed data, not executed\n")
    assert run_git(owned,["add","-A"])[0]==0
    assert run_git(owned,["commit","-m","linked fixture"])[0]==0
    assert run_git(product,["merge","--no-ff","-m","merge fixture","fixture-branch"])[0]==0
    code,base=run_git(product,["merge-base","HEAD","fixture-branch"])
    assert code==0 and len(base.strip())==40
    assert run_git(product,["revert","-m","1","--no-edit","HEAD"])[0]==0
    assert (product/"main.py").read_text()=="# data, not executed\n"
    assert run_git(product,["status","--porcelain"])[1].strip()==""
    assert run_git(parent,["rev-parse","HEAD"])[0]!=0  # parent HEAD still unborn


@pytest.mark.parametrize("args",[
    ["merge-base","--octopus","HEAD","branch"],["merge-base","--all","HEAD"],
    ["merge-base","HEAD","../../foreign"],["merge-base","HEAD","HEAD^{tree}"],
    ["merge-base","HEAD","branch","extra"],
    ["revert","--no-edit","HEAD"],["revert","-m","2","--no-edit","HEAD"],
    ["revert","-m","1","--no-edit","branch"],["revert","-m","1","--no-edit","HEAD~1"],
    ["revert","-m","1","--no-edit","--all"],["revert","--continue"],
    ["revert","--abort","extra"]])
def test_new_local_commands_cannot_expand_factory_shapes(tmp_path,monkeypatch,args):
    from autospec.agents import runner
    monkeypatch.setattr(runner,"_run_tracked",lambda *a:pytest.fail("invalid argv must never dispatch"))
    with pytest.raises(GitConfigurationRefused):run_git(tmp_path,args)


def test_symbolic_revert_is_pinned_to_observed_commit_before_mutation(tmp_path,monkeypatch):
    from autospec.agents import runner
    calls=[];commit="a"*40
    def tracked(argv,*args):
        calls.append(argv)
        return (0,commit+"\n","") if argv[-3:]==["rev-parse","--verify","HEAD^{commit}"] else (0,"","")
    monkeypatch.setattr(runner,"_run_tracked",tracked)
    assert run_git(tmp_path,["revert","-m","1","--no-edit","HEAD"])[0]==0
    assert calls[-1][-5:]==["revert","-m","1","--no-edit",commit]


@pytest.mark.parametrize("relative",["refs/heads","objects/pack","logs/refs/heads"])
def test_metadata_descendant_alias_refused_before_git_dispatch(tmp_path,monkeypatch,relative):
    from autospec.agents import runner
    import subprocess
    product=tmp_path/"product";metadata=product/".git";metadata.mkdir(parents=True)
    foreign=tmp_path/"foreign-owned-fixture";foreign.mkdir();sentinel=foreign/"sentinel";sentinel.write_bytes(b"unchanged")
    alias=metadata/relative;alias.parent.mkdir(parents=True,exist_ok=True)
    assert alias.parent.resolve().is_relative_to(tmp_path.resolve()) and foreign.resolve().is_relative_to(tmp_path.resolve())
    if os.name=="nt":
        # Create only an owned test junction; no Git command ever traverses it.
        result=subprocess.run(["cmd","/c","mklink","/J",str(alias),str(foreign)],capture_output=True,text=True)
        assert result.returncode==0,(result.stdout,result.stderr)
    else:alias.symlink_to(foreign,target_is_directory=True)
    monkeypatch.setattr(runner,"_run_tracked",lambda *a:pytest.fail("metadata alias must never reach Git"))
    try:
        with pytest.raises(GitConfigurationRefused,match="descendant link/reparse"):
            run_git(product,["commit","-m","never-dispatched"])
        assert sentinel.read_bytes()==b"unchanged" and sorted(p.name for p in foreign.iterdir())==["sentinel"]
    finally:
        if os.name=="nt":alias.rmdir()  # remove the junction only, never its target
        else:alias.unlink()


def test_git_metadata_hardlink_refused_before_subprocess(tmp_path,monkeypatch):
    from autospec.agents import runner
    refs=tmp_path/"product/.git/refs/heads";refs.mkdir(parents=True)
    foreign=tmp_path/"foreign-ref-fixture";foreign.write_bytes(b"a"*40+b"\n")
    os.link(foreign,refs/"main")
    monkeypatch.setattr(runner,"_run_tracked",lambda *a:pytest.fail("hardlink must never reach Git"))
    with pytest.raises(GitConfigurationRefused,match="descendant hardlink"):
        run_git(tmp_path/"product",["reset","--hard","HEAD"])
    assert foreign.read_bytes()==b"a"*40+b"\n"
