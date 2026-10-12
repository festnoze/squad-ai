"""Hermetic local Git bookkeeping; product configuration cannot execute tools.

This is not a general Git client: no remote operation is supported. Unsafe
brownfield configuration is refused, never overwritten or silently adopted.
"""
from __future__ import annotations

import os
import json
import re
import tempfile
from pathlib import Path


class GitConfigurationRefused(ValueError):
    pass


_REDIRECT = {"GIT_DIR","GIT_WORK_TREE","GIT_COMMON_DIR","GIT_INDEX_FILE",
             "GIT_OBJECT_DIRECTORY","GIT_ALTERNATE_OBJECT_DIRECTORIES"}
_COMMANDS = {"init","config","rev-parse","add","commit","rm","log","show","diff",
             "status","worktree","branch","merge","rebase","reset","checkout",
             "restore","ls-files","rev-list","check-ignore","ls-tree","cat-file","clean",
             "merge-base","revert"}
_SAFE_SECTIONS = {"core","user","remote","branch","init","safe","extensions"}
_CORE = {"repositoryformatversion","filemode","bare","logallrefupdates","symlinks",
         "ignorecase","autocrlf","eol","precomposeunicode","worktree","sharedrepository",
         "sparsecheckout","sparsecheckoutcone"}


def _regular(path):
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part.lstat(),"st_file_attributes",0)&0x400:
            raise GitConfigurationRefused("Git metadata link/reparse refused")
    if path.is_file() and path.stat().st_nlink!=1:
        raise GitConfigurationRefused("Git metadata hardlink refused")


def _metadata(root):
    marker=root/".git"
    if not marker.exists(): return []
    _regular(marker)
    if marker.is_dir(): directories=[marker]
    else:
        if marker.stat().st_size>8192: raise GitConfigurationRefused("Git marker exceeds bound")
        text=marker.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir: "): raise GitConfigurationRefused("Git marker invalid")
        candidate=Path(text[8:]);candidate=candidate if candidate.is_absolute() else root/candidate
        _regular(candidate)
        metadata=candidate.resolve();backlink=metadata/"gitdir"
        if not backlink.is_file(): raise GitConfigurationRefused("Linked Git metadata has no owned backlink")
        _regular(backlink)
        target=Path(backlink.read_text(encoding="utf-8").strip())
        if not target.is_absolute():target=metadata/target
        if target.resolve()!=marker.resolve():raise GitConfigurationRefused("Git backlink differs")
        directories=[metadata]
        common=metadata/"commondir"
        if common.exists():
            _regular(common)
            value=Path(common.read_text(encoding="utf-8").strip())
            candidate=value if value.is_absolute() else metadata/value
            _regular(candidate)
            directories.append(candidate.resolve())
    return directories


def _validate_config(path,*,expected_workspace=None):
    if not path.exists():return
    _regular(path)
    if not path.is_file() or path.stat().st_size>128_000:
        raise GitConfigurationRefused("Git config exceeds bound or is not regular")
    text=path.read_text(encoding="utf-8")
    if "\x00" in text:raise GitConfigurationRefused("Git config contains NUL")
    section=""
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith(("#",";")):continue
        if line.startswith("["):
            match=re.fullmatch(r'\[([A-Za-z0-9-]+)(?:\s+"[^"\r\n]*")?\]',line)
            if not match or match[1].casefold() not in _SAFE_SECTIONS:
                raise GitConfigurationRefused("Git executable/include/custom config refused")
            section=match[1].casefold();continue
        key=re.match(r"([A-Za-z][A-Za-z0-9-]*)\s*(?:=|\s|$)",line)
        if not section or not key or (section=="core" and key[1].casefold() not in _CORE):
            raise GitConfigurationRefused("Git unsupported core/config entry refused")
        if section=="extensions" and key[1].casefold() not in {"objectformat","worktreeconfig"}:
            raise GitConfigurationRefused("Git extension unsupported")
        if section=="core" and key[1].casefold()=="worktree" and expected_workspace is not None:
            value=line[key.end():].strip()
            if value.startswith('"'):
                try:value=json.loads(value)
                except ValueError as exc:raise GitConfigurationRefused("Git worktree path invalid") from exc
            if not isinstance(value,str) or not value:raise GitConfigurationRefused("Git worktree path absent")
            target=Path(value)
            if not target.is_absolute():target=path.parent/target
            if target.resolve()!=expected_workspace.resolve():raise GitConfigurationRefused("Git local worktree redirected")


def git_invocation(workspace,args):
    root=Path(workspace).absolute()
    if any(os.environ.get(k) for k in _REDIRECT):raise GitConfigurationRefused("Git environment redirect refused")
    if not args or args[0] not in _COMMANDS or any(not isinstance(a,str) or "\x00" in a for a in args):
        raise GitConfigurationRefused("Only bounded local Git bookkeeping is allowed")
    if args[0] == "clean" and list(args) != ["clean", "-fd"]:
        raise GitConfigurationRefused("Only the factory local non-ignored rollback cleanup is admitted")
    if args[0] == "merge-base":
        def local_ref(value):
            return (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,199}",value) is not None
                and ".." not in value and not value.endswith(("/",".lock"))
                and all(part not in {"","."} for part in value.split("/")))
        if len(args)!=3 or not all(local_ref(ref) for ref in args[1:]):
            raise GitConfigurationRefused("Only two explicit local merge-base refs are admitted")
    if args[0] == "revert":
        abort=list(args)==["revert","--abort"]
        commit=(len(args)==5 and list(args[1:4])==["-m","1","--no-edit"]
            and (args[4]=="HEAD" or re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}",args[4]) is not None))
        if not (abort or commit):
            raise GitConfigurationRefused("Only the factory no-edit merge-commit revert or abort is admitted")
    metadata_dirs=_metadata(root)
    for metadata in metadata_dirs:
        for name in ("config","config.worktree"):
            _validate_config(metadata/name,expected_workspace=root if (root/".git").is_dir() or name=="config.worktree" else None)
    # A factory-owned empty hooks directory, never a path inside product data.
    empty=Path(tempfile.gettempdir())/"autospec-disabled-git-hooks"
    empty.mkdir(exist_ok=True)
    _regular(empty)
    if any(empty.iterdir()):raise GitConfigurationRefused("Disabled hooks directory is not empty")
    env={k:v for k,v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1",GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,
        GIT_ATTR_NOSYSTEM="1",GIT_TERMINAL_PROMPT="0",GIT_PAGER="",GIT_EDITOR="",
        GIT_SEQUENCE_EDITOR="",GIT_LFS_SKIP_SMUDGE="1")
    gitdir=metadata_dirs[0] if metadata_dirs else root/".git"
    argv=["git","--no-pager",f"--git-dir={gitdir}",f"--work-tree={root}","-c",f"core.hooksPath={empty}","-c","core.fsmonitor=false",
        "-c",f"core.attributesFile={os.devnull}","-c","credential.helper=","-c","commit.gpgSign=false",
        "-c","tag.gpgSign=false","-c","protocol.ext.allow=never","-c","protocol.file.allow=never",*args]
    return argv,env


def run_git(workspace,args,*,timeout=120):
    """Owned Job/process group with bounded output and cleanup on timeout."""
    from ..agents.runner import _agent_environment,_run_tracked
    argv,env=git_invocation(workspace,args)
    token=_agent_environment.set(env)
    try:
        if list(args)==["revert","-m","1","--no-edit","HEAD"]:
            # The factory holds its merge lock. Pin its symbolic HEAD before
            # dispatch so the actual mutating argv names one immutable commit.
            rc,out,_=_run_tracked(argv[:-5]+["rev-parse","--verify","HEAD^{commit}"],"",str(workspace),timeout)
            commit=out.strip()
            if rc or re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}",commit) is None:
                raise GitConfigurationRefused("Current merge commit could not be identified")
            argv[-1]=commit
        rc,out,err=_run_tracked(argv,"",str(workspace),timeout)
        return rc,out+err
    finally:_agent_environment.reset(token)
