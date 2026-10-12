"""Supervisor-only conservative QA write intent, outside every product root."""
from pathlib import Path
import json

from ..agents.file_broker import ExecutionContext,FileBroker,IsolationViolation
from .claims import canonical_path
from .dependencies import atomic_json,file_lock


def record_qa_write_intent(supervisor,paths):
    """Call only after supervisor role/claim admission, before batch mutation.

    This is intent, not fabricated byte evidence. Native collection seals real
    hashes later. Cross-process union prevents concurrent factory roots losing
    provenance; source agents have no filesystem access to this location.
    """
    control=Path(supervisor).absolute()
    if control.resolve()!=control:
        raise IsolationViolation("Canonical supervisor QA root required")
    control.mkdir(parents=True,exist_ok=True)
    broker=FileBroker(ExecutionContext("qa-provenance-journal",control))
    journal=broker.path("qa-authored-files.json")
    lock=broker.path("qa-authored-files.lock")
    with file_lock(lock):
        if journal.exists() and (not journal.is_file() or journal.stat().st_size>2_000_000):
            raise IsolationViolation("Invalid bounded supervisor QA journal")
        value=json.loads(journal.read_bytes()) if journal.is_file() else {"files":[]}
        existing=value.get("files") if isinstance(value,dict) else None
        if (not isinstance(value,dict) or set(value)!={"files"} or not isinstance(existing,list)
                or len(existing)>20_000 or any(not isinstance(p,str) for p in existing)
                or len(set(existing))!=len(existing)):
            raise IsolationViolation("Invalid supervisor QA provenance")
        logged=sorted(set(existing)|set(paths))
        if len(logged)>20_000 or any(not isinstance(p,str) or len(p)>1024 or canonical_path(p,windows=False)!=p for p in logged):
            raise IsolationViolation("Canonical bounded QA provenance required")
        atomic_json(journal,{"files":logged})
