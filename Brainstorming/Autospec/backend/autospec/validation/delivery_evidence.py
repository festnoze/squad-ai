"""Supervisor-owned delivery evidence, never a producer's boolean receipt.

Cached installs are attestations, not invented process exit codes. Native
commands, immutable images and exact manifest/lock/recipe inputs are checked
independently. Missing evidence is a capability gap, not product success.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import asyncio
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path

from .support_adapter import AdapterUnavailable, Proof


REQUIRED_DOC_OBLIGATIONS=frozenset({"install","tests","coverage","e2e","launch","seed","migration","backup","restore"})


class NativeTimingUnavailable(AdapterUnavailable):
    """An admitted native operation has no usable diagnostic subclock.

    This never denotes a stale/contradictory source, receipt, recipe or image.
    A collector may retain the operation X and report PARTIAL/NOT_VERIFIED.
    """


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _image_id(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None


def delivery_build_checks(receipt: dict, source_root: Path, snapshot_hash: str,
                          *, image_lookup=None) -> list[dict]:
    """Verify V1 factory build receipts against source and fresh Docker inspect.

    ``image_lookup`` is the read-only Docker inspection port; production uses
    LinuxEnvironmentManager._image. Test doubles only validate this protocol,
    and are never evidence that the nominal application ran.
    """
    from ..orchestrator.validation_environment import LinuxEnvironmentManager, RECIPE_VERSION
    from ..orchestrator.isolated_validation import _node_command
    from ..agents.file_broker import ExecutionContext, FileBroker
    from .final_gate import source_snapshot

    source = Path(source_root).resolve()
    broker = FileBroker(ExecutionContext("delivery-evidence", source))
    rows = []
    def check(name, passed, observed):
        rows.append(dict(check=name, passed=bool(passed), observed=observed))
    if not isinstance(receipt, dict) or type(receipt.get("version")) is not int or receipt.get("version") != 1:
        raise AdapterUnavailable("typed factory delivery receipt V1 required")
    if receipt.get("snapshot_hash") != snapshot_hash or source_snapshot(source).digest != snapshot_hash:
        raise AdapterUnavailable("delivery receipt/source snapshot identity mismatch")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        raise AdapterUnavailable("actual delivery build status unavailable")
    check("native_build_status", receipt["status"] == "PASS", dict(status=receipt["status"], error=receipt.get("error")))
    # A failed native build may intentionally have no image or later receipts.
    if receipt["status"] == "FAIL":
        return rows
    if not _image_id(receipt.get("image_id")):
        raise AdapterUnavailable("immutable delivery image identity absent")
    if not isinstance(receipt.get("commands"), list) or not isinstance(receipt.get("locks_sha256"), dict):
        raise AdapterUnavailable("factory command/lock receipts absent")
    check("clean_install", all(receipt.get(k) is True for k in ("isolated", "no_host_dependencies", "manifest_only_install")),
          {k: receipt.get(k) for k in ("isolated", "no_host_dependencies", "manifest_only_install")})
    commands = {}
    for command in receipt["commands"]:
        kind = command.get("kind")
        if kind in commands or not isinstance(kind, str):
            raise AdapterUnavailable("ambiguous command receipt kind")
        commands[kind] = command
    ecology = "python" if broker.path("pyproject.toml").is_file() else "node" if broker.path("package.json").is_file() else None
    if ecology is None:
        raise AdapterUnavailable("supported source manifest absent")
    has_frontend = broker.path("frontend/package.json").is_file()
    expected = {"backend_install", "image_build"} | ({"frontend_install", "typecheck_frontend_build"} if has_frontend else set())
    if set(commands) != expected:
        raise AdapterUnavailable("exact install/typecheck/build command receipts required")
    if image_lookup is None:
        import tempfile
        manager = LinuxEnvironmentManager(Path(tempfile.gettempdir()).resolve() / "autospec-evidence-inspect")
        image_lookup = manager._image
    locks = {}
    jobs = [("backend_install", "", ecology, "runtime")]
    if has_frontend:
        jobs.append(("frontend_install", "frontend/", "node", "test"))
    for kind, relative, ecosystem, mode in jobs:
        command = commands[kind]
        manifest_name, lock_name = ("pyproject.toml", "uv.lock") if ecosystem == "python" else ("package.json", "package-lock.json")
        manifest, lock = broker.path(relative + manifest_name), broker.path(relative + lock_name)
        locks[relative + lock_name] = _sha(lock.read_bytes())
        inputs = command.get("attestation", {}).get("inputs", {})
        required_inputs = {"version", "ecosystem", "mode", "manifest", "lock", "toolchain_image", "platform", "supervisor_reporter", "toolchain_digest", "recipe_template_sha256"}
        if set(inputs) != required_inputs or not _image_id(inputs.get("toolchain_image")) or not re.fullmatch(r"[a-z0-9./:_-]+@sha256:[a-f0-9]{64}", inputs.get("toolchain_digest", "")) or not re.fullmatch(r"linux/[a-z0-9_]+", inputs.get("platform", "")):
            raise AdapterUnavailable("complete immutable dependency inputs required")
        fingerprint = _sha(json.dumps(inputs, sort_keys=True).encode())
        recipe = LinuxEnvironmentManager._recipe(inputs["toolchain_digest"], ecosystem, mode, fingerprint, manifest)
        template = LinuxEnvironmentManager._recipe(inputs["toolchain_digest"], ecosystem, mode, "FINGERPRINT", manifest)
        expected_inputs = dict(inputs, version=RECIPE_VERSION, ecosystem=ecosystem, mode=mode,
            manifest=_sha(manifest.read_bytes()), lock=_sha(lock.read_bytes()),
            recipe_template_sha256=_sha(template.encode()), supervisor_reporter="native")
        attestation = command["attestation"]
        if not _image_id(command.get("image_id")):
            raise AdapterUnavailable("immutable dependency image absent")
        check(kind + "_inputs", inputs == expected_inputs and command.get("environment_fingerprint") == fingerprint
              and attestation == dict(inputs=inputs, image=command["image_id"], recipe_sha256=_sha(recipe.encode())),
              dict(inputs=inputs, fingerprint=fingerprint, attestation=attestation))
        install = next(line[4:] for line in recipe.splitlines() if line.startswith(("RUN uv sync ", "RUN npm ci ")))
        if command.get("rc") is not None or command.get("argv") != shlex.split(install):
            raise AdapterUnavailable("install must be exact attestation, not fictional rc0")
        builder = command.get("builder", {})
        if builder.get("inputs") != inputs or builder.get("fingerprint") != fingerprint or builder.get("attestation") != attestation or builder.get("image_id") != command["image_id"]:
            raise AdapterUnavailable("builder/cache receipt is not bound to dependency inputs")
        if command.get("execution") == "attested-cache":
            if builder.get("status") != "cache_attested" or builder.get("rc") is not None or builder.get("argv") is not None:
                raise AdapterUnavailable("cache cannot claim executed builder")
        elif command.get("execution") == "attested-layer":
            argv = builder.get("argv")
            if not (isinstance(argv, list) and len(argv) == 9 and argv[1:] == ["build", "--pull=false", "--network=default", "--label", "autospec.environment="+fingerprint, "-t", "autospec/clean-env:"+fingerprint, "."] and builder.get("status") == "build_attested" and type(builder.get("rc")) is int):
                raise AdapterUnavailable("actual immutable layer builder receipt required")
            check(kind + "_builder", builder["rc"] == 0 and builder.get("recipe_sha256") == _sha(recipe.encode()),
                  dict(argv=argv, rc=builder["rc"], recipe_sha256=builder.get("recipe_sha256")))
        else:
            raise AdapterUnavailable("unknown dependency installation execution")
        actual = image_lookup(command["image_id"])
        check(kind + "_current_image", actual.get("Id") == command["image_id"] and actual.get("Config", {}).get("Labels", {}).get("autospec.environment") == fingerprint,
              dict(image_id=actual.get("Id"), environment_label=actual.get("Config", {}).get("Labels", {}).get("autospec.environment"), execution=command["execution"], rc=None))
    check("locks", receipt["locks_sha256"] == locks, dict(expected=locks, actual=receipt["locks_sha256"]))
    if has_frontend:
        command = commands["typecheck_frontend_build"]
        argv = _node_command(["/bin/sh", "-c", "node /opt/node_modules/typescript/bin/tsc -b --pretty false && exec node /opt/node_modules/vite/bin/vite.js build"], dist=True)
        if command.get("argv") != argv or command.get("components") != ["typecheck", "frontend_build"] or type(command.get("rc")) is not int or not broker.path("frontend/tsconfig.json").is_file():
            raise AdapterUnavailable("actual native tsc/Vite composite receipt required")
        dependency = commands["frontend_install"]
        check("typecheck_frontend_build", command["rc"] == 0 and command.get("isolated") is True and command.get("image_id") == dependency["image_id"] and command.get("environment_fingerprint") == dependency["environment_fingerprint"],
              dict(argv=argv, rc=command["rc"], components=command["components"]))
        if not isinstance(receipt.get("frontend_files"), dict) or not receipt["frontend_files"] or any(not p.startswith("frontend/dist/") or ".." in Path(p).parts or not re.fullmatch(r"[a-f0-9]{64}", digest) for p, digest in receipt["frontend_files"].items()):
            raise AdapterUnavailable("fresh frontend artifact identities absent")
    command = commands["image_build"]
    argv = command.get("argv")
    if not isinstance(argv, list) or len(argv) != 7 or argv[1:] != ["build", "--pull=false", "--network=none", "-t", receipt.get("image_tag"), "."] or type(command.get("rc")) is not int:
        raise AdapterUnavailable("actual confined final-image builder required")
    base = "autospec/clean-env:" + commands["backend_install"]["environment_fingerprint"]
    runtime=receipt.get("runtime_command")
    if (receipt.get("runtime_command_mode")!="explicit-factory" or not isinstance(runtime,list)
            or not 1<=len(runtime)<=200 or any(not isinstance(arg,str) or "\x00" in arg or len(arg)>4096 for arg in runtime)
            or runtime[0]!=("/opt/venv/bin/python" if ecology=="python" else "node")):
        raise AdapterUnavailable("explicit source-reviewed factory runtime argv required; legacy launcher is not acceptance")
    node_link="USER 0:0\nRUN ln -s /opt/node_modules /node_modules\n" if ecology=="node" else ""
    recipe = f'FROM {base}\nWORKDIR /app\nCOPY --chown=65532:65532 product/ /app/\n{node_link}ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1\nUSER 65532:65532\nENTRYPOINT []\nCMD {json.dumps(runtime)}\nLABEL autospec.snapshot={snapshot_hash}\n'
    check("image_builder", command["rc"] == 0 and command.get("isolated") is True and command.get("recipe_sha256") == _sha(recipe.encode()), dict(argv=argv, rc=command["rc"], recipe_sha256=command.get("recipe_sha256")))
    actual = image_lookup(receipt["image_id"])
    config=actual.get("Config",{})
    # Docker JSON may omit an actually empty ENTRYPOINT (Go templates expose
    # null). Fresh image inspection + exact recipe/Cmd still attest absence.
    check("baked_runtime_command",config.get("Cmd")==runtime and config.get("Entrypoint") in (None,[]),
          dict(expected=runtime,cmd=config.get("Cmd"),entrypoint=config.get("Entrypoint"),mode=receipt["runtime_command_mode"]))
    check("current_delivery_image", actual.get("Id") == receipt["image_id"] and actual.get("Config", {}).get("Labels", {}).get("autospec.snapshot") == snapshot_hash,
          dict(image_id=actual.get("Id"), snapshot_label=actual.get("Config", {}).get("Labels", {}).get("autospec.snapshot")))
    return rows


_PYTHON_AUDIT = '''import datetime,json,subprocess,time
argv=["/opt/auditor/bin/python","-I","-m","pip_audit","--no-deps","--disable-pip","--strict","--progress-spinner","off","--format","json","--requirement","/audit/requirements.txt"]
started=time.monotonic()
try:
 p=subprocess.run(argv,capture_output=True,text=True,timeout=240)
 result={"argv":argv,"return_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"seconds":time.monotonic()-started}
except Exception as e:
 result={"argv":argv,"return_code":None,"error":type(e).__name__,"seconds":time.monotonic()-started}
result.update(date=datetime.datetime.now(datetime.timezone.utc).isoformat(),tool="pip-audit==2.10.1")
open("/audit/result.json","w").write(json.dumps(result))
'''
_NODE_AUDIT = '''const fs=require("node:fs"),cp=require("node:child_process");
const argv=["audit","--json","--package-lock-only","--ignore-scripts","--userconfig=/dev/null","--globalconfig=/tmp/autospec-empty-global-npmrc","--registry=https://registry.npmjs.org"];
const start=process.hrtime.bigint();let result;
try {const p=cp.spawnSync("npm",argv,{encoding:"utf8",timeout:240000,maxBuffer:16000000});result={argv:["npm",...argv],return_code:p.status,stdout:p.stdout,stderr:p.stderr,error:p.error?.name};}
catch(e){result={argv:["npm",...argv],return_code:null,error:e.name};}
result.seconds=Number(process.hrtime.bigint()-start)/1e9;result.date=new Date().toISOString();result.tool="npm audit "+cp.spawnSync("npm",["--version"],{encoding:"utf8"}).stdout.trim();fs.writeFileSync("/audit/result.json",JSON.stringify(result));
'''


def _native_proof(root, name, value, snapshot_hash, contract_hash, *, checks, passed=True):
    from ..orchestrator.dependencies import atomic_json
    path=Path(root)/"delivery-evidence"/(name+"-"+uuid4().hex+".json")
    atomic_json(path,dict(snapshot_hash=snapshot_hash,contract_hash=contract_hash,value=value))
    return Proof("X",str(path),_sha(path.read_bytes()),snapshot_hash,contract_hash,tuple(checks),passed)


def _audit_findings(ecosystem, run, expected_packages):
    """Parse complete tool reports; missing collection cannot mean no findings."""
    if type(run.get("return_code")) is not int or run["return_code"] not in {0,1}:
        raise AdapterUnavailable("dependency auditor did not complete")
    report=json.loads(run["stdout"])
    findings=[]
    if ecosystem=="python":
        dependencies=report["dependencies"]
        if not isinstance(dependencies,list): raise AdapterUnavailable("pip-audit dependency collection absent")
        actual=[]
        for dep in dependencies:
            if not isinstance(dep.get("vulns"),list) or "skip_reason" in dep:
                raise AdapterUnavailable("pip-audit skipped a locked dependency")
            actual.append((dep["name"].lower().replace("_","-"),dep["version"]))
            for vuln in dep["vulns"]:
                if not isinstance(vuln.get("id"),str): raise AdapterUnavailable("advisory identity missing")
                findings.append(dict(id=vuln["id"],package=dep["name"],version=dep["version"],
                    severity="unknown",exploitable=None,arbitration=None,aliases=vuln.get("aliases",[]),
                    fix_versions=vuln.get("fix_versions",[])))
        if sorted(actual)!=sorted(expected_packages): raise AdapterUnavailable("audit did not cover exact registry lock inventory")
    else:
        if report.get("auditReportVersion")!=2 or not isinstance(report.get("vulnerabilities"),dict) or not isinstance(report.get("metadata",{}).get("dependencies"),dict) or "error" in report:
            raise AdapterUnavailable("npm audit complete lock report absent")
        for name,dep in report["vulnerabilities"].items():
            for vuln in dep.get("via",[]):
                if isinstance(vuln,str): continue  # A linked metavulnerability, not a distinct advisory.
                if not isinstance(vuln,dict) or type(vuln.get("source")) is not int:
                    raise AdapterUnavailable("npm advisory identity missing")
                findings.append(dict(id="npm:"+str(vuln["source"]),package=name,version=dep.get("range"),
                    severity=vuln.get("severity","unknown"),exploitable=None,arbitration=None,url=vuln.get("url")))
        # Never silently accept a report claiming vulnerability but no advisories.
        if report.get("metadata",{}).get("vulnerabilities",{}).get("total",0) and not findings:
            raise AdapterUnavailable("npm report lacks actual advisory details")
    if (run["return_code"]==0) != (not findings):
        raise AdapterUnavailable("auditor exit status contradicts raw findings")
    return findings


async def collect_dependency_audit(source_root, evidence_root, snapshot_hash, contract_hash,
                                   *, docker="docker", timeout=600, cache_root=None) -> dict:
    """Dated real pip-audit/npm audit in manifest-only Linux networking phases.

    No application source, scripts, host venv, npmrc, secrets or DB enter the
    builder. Only locked public package facts are sent to official registries.
    These known-advisory audits do not certify absence of malicious packages.
    Finding exploitability requires a separate exact-subject independent R.
    """
    from ..orchestrator.validation_environment import LinuxEnvironmentManager, admit_manifest
    from ..orchestrator.sandbox import _docker_call, _cleanup_container
    from ..agents.runner import _run_tracked
    from .final_gate import source_snapshot
    source,root=Path(source_root).resolve(),Path(evidence_root).absolute()
    if root.resolve()!=root or root.is_relative_to(source) or source_snapshot(source).digest!=snapshot_hash:
        raise AdapterUnavailable("audit requires exact frozen source and external evidence root")
    manager=LinuxEnvironmentManager(Path(cache_root) if cache_root else root/"audit-cache",docker=docker,timeout=timeout)
    scopes=[]
    if (source/"pyproject.toml").is_file(): scopes.append(("backend",source,"python"))
    elif (source/"package.json").is_file(): scopes.append(("backend",source,"node"))
    if (source/"frontend/package.json").is_file(): scopes.append(("frontend",source/"frontend","node"))
    if not scopes: raise AdapterUnavailable("supported locked audit scope absent")
    result=dict(status="AVAILABLE",date=datetime.now(timezone.utc).isoformat(),tool="factory manifest-only pip-audit/npm audit",
        report_valid=True,return_code=0,findings=[],artifacts=[],reports=[],limits=[
        "Advisory queries only; no package/application code executed during networking.",
        "All registry packages in Python lock (runtime+dev/all locked platforms); duplicate versions require explicit supported lock export.",
        "Finding severity/exploitability/arbitration must be source-reviewed; dev tooling is not presumed exploitable in production."])
    for scope,product,ecosystem in scopes:
        tag="autospec/dependency-audit:"+uuid4().hex;owner=uuid4().hex
        name="autospec-sandbox-"+uuid4().hex;image=None;observed={}
        try:
            manifest,lock=admit_manifest(product,ecosystem)
            manifest_bytes,lock_bytes=manifest.read_bytes(),lock.read_bytes()
            expected=[]
            with tempfile.TemporaryDirectory(prefix="autospec-audit-") as temporary:
                stage=Path(temporary)
                base=await asyncio.to_thread(manager._base,ecosystem)
                base_digest=base["RepoDigests"][0]
                if not re.fullmatch(r"[a-z0-9./:_-]+@sha256:[a-f0-9]{64}",base_digest): raise AdapterUnavailable("immutable audit toolchain digest absent")
                if ecosystem=="python":
                    packages=tomllib.loads(lock_bytes.decode())["package"]
                    by_name={}
                    for package in packages:
                        if package.get("source",{}).get("virtual")==".": continue
                        if package.get("source",{}).get("registry")!="https://pypi.org/simple":
                            raise AdapterUnavailable("audit supports only public PyPI registry lock facts")
                        key=package["name"].lower().replace("_","-");version=package["version"]
                        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*",key) or not re.fullmatch(r"[0-9A-Za-z.!+_-]+",version): raise AdapterUnavailable("invalid locked audit pin")
                        if key in by_name and by_name[key]!=version: raise AdapterUnavailable("multi-version lock needs explicit platform export")
                        by_name[key]=version
                    expected=sorted(by_name.items())
                    if not expected: raise AdapterUnavailable("no locked registry dependencies to audit")
                    (stage/"requirements.txt").write_text("".join(f"{name}=={version}\n" for name,version in expected),encoding="utf-8")
                    (stage/"runner.py").write_text(_PYTHON_AUDIT,encoding="utf-8")
                    recipe=f"FROM {base_digest}\nWORKDIR /audit\nRUN uv venv /opt/auditor && uv pip install --python /opt/auditor/bin/python --no-build --no-config pip-audit==2.10.1\nCOPY requirements.txt runner.py ./\nRUN /usr/local/bin/python -I runner.py\n"
                    reader=["/usr/local/bin/python","-I","-c","from pathlib import Path;print(Path('/audit/result.json').read_text())"]
                else:
                    (stage/"package.json").write_bytes(manifest_bytes);(stage/"package-lock.json").write_bytes(lock_bytes)
                    (stage/"runner.cjs").write_text(_NODE_AUDIT,encoding="utf-8")
                    recipe=f"FROM {base_digest}\nWORKDIR /audit\nCOPY package.json package-lock.json runner.cjs ./\nRUN node /audit/runner.cjs\n"
                    reader=["node","-e","process.stdout.write(require('node:fs').readFileSync('/audit/result.json','utf8'))"]
                recipe+=f"LABEL autospec.audit={owner}\nUSER 65532:65532\n"
                (stage/"Dockerfile").write_text(recipe,encoding="utf-8")
                argv=[docker,"build","--pull=false","--network=default","--no-cache","-t",tag,"."]
                rc,out,err=await asyncio.to_thread(_run_tracked,argv,"",str(stage),timeout)
                observed=dict(scope=scope,ecosystem=ecosystem,manifest_sha256=_sha(manifest_bytes),lock_sha256=_sha(lock_bytes),
                    builder_argv=argv,builder_return_code=rc,recipe_sha256=_sha(recipe.encode()),toolchain_image=base["Id"],toolchain_digest=base_digest,
                    declared_network="manifest-only registry advisory query; no product code",inputs=expected,
                    context_files={p.name:_sha(p.read_bytes()) for p in stage.iterdir()})
                if rc: raise AdapterUnavailable("audit image/tool preparation unavailable")
                image=await asyncio.to_thread(manager._image,tag)
                if not _image_id(image.get("Id")) or image.get("Config",{}).get("Labels",{}).get("autospec.audit")!=owner:
                    raise AdapterUnavailable("audit image ownership cannot be attested")
                readargv=[docker,"run","--rm","--name",name,"--label","autospec.run_id="+owner,"--label","autospec.kind=sandbox",
                    "--pull","never","--network","none","--read-only","--cap-drop","ALL","--security-opt","no-new-privileges=true",
                    "--user","65532:65532","--pids-limit","32","--memory","128m","--workdir","/tmp","--entrypoint",reader[0],image["Id"],*reader[1:]]
                read=await asyncio.to_thread(_docker_call,readargv,capture_output=True,text=True,timeout=30,check=False)
                if read.returncode or len(read.stdout)>16*1024*1024: raise AdapterUnavailable("audit raw result export unavailable")
                run=json.loads(read.stdout);observed.update(image_id=image["Id"],export_argv=readargv,export_return_code=read.returncode,run=run)
                findings=_audit_findings(ecosystem,run,expected)
                for finding in findings: finding["scope"]=scope
                result["findings"].extend(findings)
                if findings: result["return_code"]=1
                result["reports"].append(dict(scope=scope,tool=run["tool"],date=run["date"],return_code=run["return_code"],seconds=run["seconds"],
                    manifest_sha256=_sha(manifest_bytes),lock_sha256=_sha(lock_bytes),image_id=image["Id"]))
                if manifest.read_bytes()!=manifest_bytes or lock.read_bytes()!=lock_bytes: raise AdapterUnavailable("audit source drift")
        except Exception as exc:
            observed.update(unavailable=type(exc).__name__,reason=str(exc))
            result.update(status="UNAVAILABLE",report_valid=False,return_code=None)
            result["limits"].append(scope+": "+str(exc))
        finally:
            proof=_native_proof(root,"audit-raw",observed,snapshot_hash,contract_hash,checks=("OBS:audit_raw",),passed=True)
            result["artifacts"].append(asdict(proof))
            await asyncio.to_thread(_cleanup_container,docker,name,owner)
            if image is not None:
                actual=await asyncio.to_thread(manager._image,tag)
                if actual.get("Id")!=image["Id"] or actual.get("Config",{}).get("Labels",{}).get("autospec.audit")!=owner:
                    raise AdapterUnavailable("audit tag ownership changed; refusing cleanup")
                await asyncio.to_thread(_docker_call,[docker,"image","rm",tag],capture_output=True,text=True,timeout=15,check=False)
    if source_snapshot(source).digest!=snapshot_hash: raise AdapterUnavailable("source changed during dependency audit")
    return result


async def collect_manifest_audit(source,snapshot_hash,contract_hash,supervisor_root,**options):
    """Pre-review entrypoint: raw audit needs no delivery plan or R authority."""
    return await collect_dependency_audit(source,supervisor_root,snapshot_hash,contract_hash,**options)


def audit_review_subject(audit:dict) -> str:
    """Exact native raw receipts/finding inventory to be independently reviewed."""
    return _sha(json.dumps(audit,sort_keys=True,ensure_ascii=True).encode())


def apply_audit_review(audit:dict, review:Proof, *, evidence_root, snapshot_hash, contract_hash) -> dict:
    """Install GPT/local independent severity/exploitability arbitration, not R."""
    root=Path(evidence_root).resolve();subject=audit_review_subject(audit)
    if review.type!="R" or not review.passed or not Path(review.path).resolve().is_relative_to(root) or not review.intact(snapshot_hash=snapshot_hash,contract_hash=contract_hash) or "OPS-05:audit:"+subject not in review.checks:
        raise AdapterUnavailable("exact independent audit assessment absent")
    data=json.loads(Path(review.path).read_bytes())
    assessments=data.get("assessments")
    key=lambda f:(f["scope"],f["package"],f["id"])
    if not isinstance(assessments,list) or len({key(f) for f in assessments})!=len(assessments) or {key(f) for f in assessments}!={key(f) for f in audit["findings"]}:
        raise AdapterUnavailable("audit assessment must cover exact advisory inventory")
    mapping={key(f):f for f in assessments};result=dict(audit,findings=[])
    for finding in audit["findings"]:
        assessment=mapping[key(finding)]
        if assessment.get("severity") not in {"critical","high","moderate","low","info"} or type(assessment.get("exploitable")) is not bool or not isinstance(assessment.get("rationale"),str) or not assessment["rationale"].strip():
            raise AdapterUnavailable("severity/exploitability requires actual independent rationale")
        arbitration=assessment.get("arbitration")
        if arbitration is not None and (not isinstance(arbitration,dict) or not {"decision","owner","rationale","date"}<=arbitration.keys() or any(not isinstance(arbitration[k],str) or not arbitration[k].strip() for k in ("decision","owner","rationale","date"))):
            raise AdapterUnavailable("audit arbitration needs dated accountable decision")
        if arbitration is not None:
            try:
                date=datetime.fromisoformat(arbitration["date"].replace("Z","+00:00"))
                if date.tzinfo is None: raise ValueError("timezone absent")
            except ValueError as exc: raise AdapterUnavailable("audit arbitration date must be actual zoned ISO date") from exc
        result["findings"].append(dict(finding,severity=assessment["severity"],exploitable=assessment["exploitable"],arbitration=arbitration,rationale=assessment["rationale"]))
    result["assessment_review"]=asdict(review)
    result["raw_audit"]=audit
    return result


@dataclass(frozen=True)
class ReviewedDeliveryPlan:
    """Source-exact operational README facts, reviewed outside the product.

    The independent contract is NOT generated from this mapping. The review's
    JSON must include configuration_assessments keyed by exact source path,
    with source_sha256 and secrets_found (keys/locations, never secret values).
    """
    data: dict
    review: Proof

    @classmethod
    def from_dict(cls, value):
        data=dict(value)
        try: review=Proof(**data.pop("review"))
        except (TypeError,KeyError) as exc: raise AdapterUnavailable("reviewed delivery plan malformed") from exc
        return cls(data,review)

    @property
    def fingerprint(self):
        return _sha(json.dumps(self.data,sort_keys=True,ensure_ascii=True).encode())

    def validate(self, source_root, evidence_root, snapshot_hash, contract_hash,
                 *, required_obligations=None):
        from ..agents.file_broker import FileBroker,ExecutionContext
        from .final_gate import source_snapshot
        source,root=Path(source_root).resolve(),Path(evidence_root).resolve()
        if root.is_relative_to(source) or (self.data.get("snapshot_hash"),self.data.get("contract_hash"))!=(snapshot_hash,contract_hash) or source_snapshot(source).digest!=snapshot_hash:
            raise AdapterUnavailable("delivery plan source/contract identity mismatch")
        if not Path(self.review.path).resolve().is_relative_to(root) or self.review.type!="R" or not self.review.passed or not self.review.intact(snapshot_hash=snapshot_hash,contract_hash=contract_hash) or "PRODUCT:delivery:"+self.fingerprint not in self.review.checks:
            raise AdapterUnavailable("exact external delivery facts review absent")
        required={"version","snapshot_hash","contract_hash","readme","configuration","commands","migration_label","fixture_case","fixtures_fingerprint"}
        if set(self.data)!=required or self.data["version"]!=1:
            raise AdapterUnavailable("explicit delivery plan V1 schema required")
        broker=FileBroker(ExecutionContext("readme-delivery-review",source))
        files=[self.data["readme"],*self.data["configuration"]]
        if not self.data["configuration"] or len({f["path"] for f in files})!=len(files): raise AdapterUnavailable("distinct reviewed README/configuration files required")
        for file in files:
            path=broker.path(file["path"])
            if not path.is_file() or path.stat().st_size>1024*1024 or _sha(path.read_bytes())!=file["sha256"]:
                raise AdapterUnavailable("reviewed README/configuration source changed")
        text=broker.path(self.data["readme"]["path"]).read_text(encoding="utf-8")
        commands=self.data["commands"]
        if not isinstance(commands,list) or not commands or len(commands)>32 or len({c["label"] for c in commands})!=len(commands):
            raise AdapterUnavailable("explicit unique documented command mapping required")
        obligations=REQUIRED_DOC_OBLIGATIONS if required_obligations is None else set(required_obligations)
        if not obligations<={c.get("obligation") for c in commands}:
            raise AdapterUnavailable("documented source obligations absent: "+",".join(sorted(obligations-{c.get("obligation") for c in commands})))
        for command in commands:
            if command.get("execution") not in {"runtime","native_receipt","build_attestation","isolated_command","runtime_launch","fixture_provisioning"} or not isinstance(command.get("argv"),list) or not command["argv"] or any(not isinstance(x,str) or "\x00" in x for x in command["argv"]) or not isinstance(command.get("documented_text"),str) or not command["documented_text"] or command["documented_text"] not in text:
                raise AdapterUnavailable("documented command absent from reviewed README")
            if command["execution"]=="runtime" and (not isinstance(command.get("action"),str) or not isinstance(command.get("parameters"),dict)):
                raise AdapterUnavailable("explicit isolated runtime action/inputs required")
            if command["execution"]=="isolated_command" and (command.get("ecosystem") not in {"python","node"} or not isinstance(command.get("root"),str)):
                raise AdapterUnavailable("literal README CLI needs explicit suite root/ecosystem")
        if commands[0]["label"]!=self.data["migration_label"] or commands[0]["execution"]!="runtime" or commands[0].get("action")!="migrate_fresh":
            raise AdapterUnavailable("first documented command must migrate fresh validation DB before seed")
        if not isinstance(self.data["fixture_case"],str) or not self.data["fixture_case"] or not re.fullmatch(r"[a-f0-9]{64}",self.data["fixtures_fingerprint"]):
            raise AdapterUnavailable("explicit independently reviewed fixture case/fingerprint required")
        review_data=json.loads(Path(self.review.path).read_bytes())
        assessments=review_data.get("configuration_assessments")
        if not isinstance(assessments,dict) or set(assessments)!={f["path"] for f in self.data["configuration"]}:
            raise AdapterUnavailable("complete independent expurgated-configuration assessment required")
        for file in self.data["configuration"]:
            assessment=assessments[file["path"]]
            if assessment.get("source_sha256")!=file["sha256"] or not isinstance(assessment.get("secrets_found"),list):
                raise AdapterUnavailable("configuration assessment source identity absent")
        return assessments


def delivery_plan_schema():
    """Candidate facts schema for local GPT review; hashes attached by factory."""
    return dict(version=1,readme=dict(path="README.md",sha256="<source bytes SHA256>"),
        configuration=[dict(path="config.py",sha256="<source bytes SHA256>")],
        commands=[dict(label="migration",obligation="migration",documented_text="<literal command in README>",
            execution="runtime",argv=["/opt/venv/bin/python","main.py","migrate"],action="migrate_fresh",parameters={}),
            dict(label="install",obligation="install",documented_text="<literal locked install command>",execution="build_attestation",receipt_kind="backend_install",argv=["<exact factory recipe install argv>"]),
            dict(label="tests",obligation="tests",documented_text="pytest -q",execution="isolated_command",root=".",ecosystem="python",argv=["pytest","-q"]),
            dict(label="coverage",obligation="coverage",documented_text="pytest --cov",execution="isolated_command",root=".",ecosystem="python",argv=["pytest","--cov"]),
            dict(label="e2e",obligation="e2e",documented_text="<literal E2E CLI>",execution="isolated_command",root="frontend",ecosystem="node",argv=["<declared real browser CLI>"]),
            dict(label="launch",obligation="launch",documented_text="<literal product launcher>",execution="runtime_launch",argv=["/opt/venv/bin/python","main.py"]),
            dict(label="seed",obligation="seed",documented_text="<literal explicit seed command>",execution="fixture_provisioning",action="seed",argv=["/opt/venv/bin/python","main.py","seed"]),
            dict(label="backup",obligation="backup",documented_text="<literal backup command for controlled DB>",execution="runtime",action="backup",parameters={},argv=["<reviewed runtime backup CLI>"]),
            dict(label="restore",obligation="restore",documented_text="<literal restore command for controlled DB>",execution="runtime",action="restore",parameters={},argv=["<reviewed runtime restore CLI>"])],
        migration_label="migration",fixture_case="OPS-05",fixtures_fingerprint="<reviewed-fixtures fingerprint>",
        snapshot_hash="<source_snapshot.digest>",contract_hash="<immutable contract hash>")


def delivery_candidate_schema():
    """Strict proposer output: source facts only, hashes/review factory-attached."""
    text={"type":"string","minLength":1}
    argv={"type":"array","minItems":1,"items":text}
    command={"type":"object","additionalProperties":False,
        "required":["label","obligation","documented_text","execution","argv"],
        "properties":{"label":text,"obligation":{"type":"string","enum":sorted(REQUIRED_DOC_OBLIGATIONS)},
            "documented_text":text,"execution":{"type":"string","enum":["runtime","native_receipt","build_attestation","isolated_command","runtime_launch","fixture_provisioning"]},
            "argv":argv,"action":text,"parameters":{"type":"object"},"root":text,
            "ecosystem":{"type":"string","enum":["python","node"]},"receipt_kind":text,"receipt_name":text}}
    return {"type":"object","additionalProperties":False,"required":["readme","configuration","commands","migration_label","fixture_case"],
        "properties":{"readme":text,"configuration":{"type":"array","minItems":1,"uniqueItems":True,"items":text},
            "commands":{"type":"array","minItems":1,"maxItems":32,"items":command},"migration_label":text,"fixture_case":text}}


async def prepare_delivery_proposal(candidate,*,source_root,snapshot_hash,contract_hash,fixtures_fingerprint):
    """Readonly review subject; proposed facts never approve the independent oracle."""
    from ..agents.file_broker import FileBroker,ExecutionContext
    from .final_gate import source_snapshot
    source=Path(source_root).resolve()
    if set(candidate)!={"readme","configuration","commands","migration_label","fixture_case"} or source_snapshot(source).digest!=snapshot_hash or not re.fullmatch(r"[a-f0-9]{64}",fixtures_fingerprint):
        raise AdapterUnavailable("exact source/candidate/fixtures identity required")
    broker=FileBroker(ExecutionContext("delivery-proposal",source))
    def file(relative):
        path=broker.path(relative)
        if not path.is_file() or path.stat().st_size>1024*1024: raise AdapterUnavailable("bounded real README/configuration source required")
        return dict(path=relative,sha256=_sha(path.read_bytes()))
    readme=file(candidate["readme"]);configuration=[file(p) for p in candidate["configuration"]]
    text=broker.path(readme["path"]).read_text(encoding="utf-8")
    commands=candidate["commands"]
    if not isinstance(commands,list) or not commands or not REQUIRED_DOC_OBLIGATIONS<={c.get("obligation") for c in commands}:
        raise AdapterUnavailable("complete source README command obligation mapping required")
    allowed=set(delivery_candidate_schema()["properties"]["commands"]["items"]["properties"])
    required={"label","obligation","documented_text","execution","argv"}
    for c in commands:
        if not required<=set(c)<=allowed or not isinstance(c.get("documented_text"),str) or not c["documented_text"] or c["documented_text"] not in text or not isinstance(c.get("argv"),list) or not c["argv"] or any(not isinstance(x,str) or "\x00" in x for x in c["argv"]):
            raise AdapterUnavailable("literal source README command facts absent/malformed")
    data=dict(version=1,snapshot_hash=snapshot_hash,contract_hash=contract_hash,readme=readme,configuration=configuration,
        commands=commands,migration_label=candidate["migration_label"],fixture_case=candidate["fixture_case"],fixtures_fingerprint=fixtures_fingerprint)
    digest=_sha(json.dumps(data,sort_keys=True,ensure_ascii=True).encode())
    return dict(status="AWAITING_INDEPENDENT_REVIEW",plan=data,fingerprint=digest,
        required_review_checks=["PRODUCT:delivery:"+digest,"OPS-05:README","OPS-05:configuration"],
        configuration_review_inputs={c["path"]:dict(source_sha256=c["sha256"],secrets_found="independent reviewer must inspect; do not fill a default empty list") for c in configuration},
        limits=["Facts mapping only, no README command executed and no acceptance proof issued.","Audit is collected before review independently through collect_manifest_audit."])


class NativeDeliveryCollector:
    """Execute reviewed README actions in a fresh owned runtime and publish X.

    Call before preparing any fixture in this context. Other native suites and
    coverage/E2E/backup receipts must cite real X bytes; missing steps stay NV.
    This collector cannot issue independent R or run any product command host.
    """
    def __init__(self, plan:ReviewedDeliveryPlan, *, source_root,evidence_root,snapshot_hash,contract_hash,
                 required_obligations=None):
        self.plan,self.source,self.root=plan,Path(source_root).resolve(),Path(evidence_root).resolve()
        self.snapshot,self.contract=snapshot_hash,contract_hash
        # Only a trusted independent contract/test may narrow this; it is not
        # accepted in producer bindings or the external plan's JSON.
        self.required_obligations=required_obligations

    def _proof(self, value):
        proof=value if isinstance(value,Proof) else Proof(**value)
        if proof.type!="X" or not Path(proof.path).resolve().is_relative_to(self.root) or not proof.intact(snapshot_hash=self.snapshot,contract_hash=self.contract):
            raise AdapterUnavailable("actual external native command artifact required")
        return proof

    async def collect(self,harness,*,build_receipt=None,native_receipts=None,audit=None):
        from .coordinator import SupervisorEvidenceStore
        assessments=self.plan.validate(self.source,self.root,self.snapshot,self.contract,required_obligations=self.required_obligations)
        if harness.instrumented or harness._command_receipts or harness.bindings.fixture_fingerprint!=self.plan.data["fixtures_fingerprint"]:
            raise AdapterUnavailable("README validation requires fresh direct runtime and exact reviewed fixtures")
        native_receipts={} if native_receipts is None else native_receipts
        source_proofs=[];commands=[];before=None;fixture=False;limits=[]
        for command in self.plan.data["commands"]:
            row=dict(label=command["label"],argv=command["argv"],documented_text=command["documented_text"],execution=command["execution"])
            if command["execution"]=="runtime":
                binding=harness.bindings.commands.get(command["action"])
                if binding is None or list(binding.argv)!=command["argv"]: raise AdapterUnavailable("README argv differs from reviewed product command binding")
                result=await harness.command(command["action"],**command["parameters"])
                row["return_code"]=result["exit_code"]
                source_proofs.append(_native_proof(self.root,"readme-command",dict(row,parameters_sha256=_sha(json.dumps(command["parameters"],sort_keys=True).encode())),
                    self.snapshot,self.contract,checks=("OPS-05:README:"+row["label"],),passed=row["return_code"]==0))
                if command["label"]==self.plan.data["migration_label"]:
                    before=(await harness.observe("business_counts"))["users"]
                    if row["return_code"]==0 and before==0:
                        await harness.adapter.prepare_case(self.plan.data["fixture_case"])
                        fixture=True
            elif command["execution"]=="isolated_command":
                from ..orchestrator.isolated_validation import IsolatedValidator
                command_root=(self.source/command["root"]).resolve()
                if not command_root.is_relative_to(self.source): raise AdapterUnavailable("README command root escaped frozen source")
                validator=IsolatedValidator(self.root/"readme-linux-cache")
                rc,out,err,environment=await asyncio.to_thread(validator.run_captured,command_root,command["ecosystem"],command["argv"],mode="test")
                row.update(return_code=rc,isolated=True,mode="test",source_root=command["root"],environment_fingerprint=environment.fingerprint,image_id=environment.image,
                    stdout_sha256=_sha(out.encode()),stderr_sha256=_sha(err.encode()),output="withheld: source command output may contain credentials")
                source_proofs.append(_native_proof(self.root,"readme-isolated-command",row,self.snapshot,self.contract,checks=("OPS-05:README:"+row["label"],),passed=rc==0))
            elif command["execution"]=="runtime_launch":
                if command["argv"]!=list(harness.bindings.runtime_command) or command["argv"]!=harness.runtime.command:
                    raise AdapterUnavailable("README launch argv differs from actual isolated runtime")
                config=await asyncio.to_thread(harness.runtime.inspect_configuration)
                row.update(return_code=None,execution="observed-runtime",passed=config["running"] is True,container_id=config["container_id"],image_id=config["image_id"])
                source_proofs.append(_native_proof(self.root,"readme-launch",row,self.snapshot,self.contract,checks=("OPS-05:README:"+row["label"],),passed=row["passed"]))
            elif command["execution"]=="fixture_provisioning":
                binding=harness.bindings.commands.get(command.get("action"))
                matches=[r for r in harness._command_receipts if r["command"]==command.get("action")]
                if not fixture or binding is None or list(binding.argv)!=command["argv"] or not matches:
                    raise AdapterUnavailable("README explicit seed argv was not executed from reviewed fixture inputs")
                row.update(return_code=matches[-1]["exit_code"],fixtures_fingerprint=self.plan.data["fixtures_fingerprint"],inputs="independently reviewed credentials, never injected sessions")
                source_proofs.append(_native_proof(self.root,"readme-seed",row,self.snapshot,self.contract,checks=("OPS-05:README:"+row["label"],),passed=row["return_code"]==0))
            elif command["execution"]=="build_attestation":
                if build_receipt is None: raise AdapterUnavailable("actual README installation build receipt absent")
                predicates=await asyncio.to_thread(delivery_build_checks,build_receipt,self.source,self.snapshot)
                if not predicates or not all(p["passed"] for p in predicates):
                    row.update(return_code=None,execution="failed-build",passed=False)
                else:
                    receipt=next((c for c in build_receipt["commands"] if c["kind"]==command.get("receipt_kind")),None)
                    if receipt is None or not receipt["kind"].endswith("_install") or receipt["argv"]!=command["argv"]:
                        raise AdapterUnavailable("README install command not attested by actual manifest recipe")
                    row.update(return_code=None,execution=receipt["execution"],attestation=receipt["attestation"],environment_fingerprint=receipt["environment_fingerprint"],passed=True)
                source_proofs.append(_native_proof(self.root,"readme-install",dict(row,build_receipt=build_receipt),self.snapshot,self.contract,
                    checks=("OPS-05:README:"+row["label"],),passed=row.get("passed") is True))
            else:
                receipt=native_receipts.get(command.get("receipt_name"))
                if not isinstance(receipt,dict) or receipt.get("argv")!=command["argv"] or type(receipt.get("return_code")) is not int or not receipt.get("proofs"):
                    raise AdapterUnavailable("documented native test/coverage/E2E/backup execution unavailable")
                proofs=[self._proof(p) for p in receipt["proofs"]]
                # Raw execution receipt must itself contain the exact command
                # and rc, not just a boolean or unrelated screenshot.
                exact=False
                for proof in proofs:
                    payload=json.loads(Path(proof.path).read_bytes())
                    value=payload.get("value",payload)
                    candidates=value.get("commands",[value]) if isinstance(value,dict) else []
                    exact|=any(c.get("argv")==command["argv"] and c.get("return_code",c.get("rc"))==receipt["return_code"] for c in candidates)
                if not exact: raise AdapterUnavailable("native raw receipt does not contain exact documented command/rc")
                row["return_code"]=receipt["return_code"];source_proofs.extend(proofs)
            commands.append(row)
        if audit is None:
            audit=await collect_dependency_audit(self.source,self.root,self.snapshot,self.contract)
        if "assessment_review" in audit:
            reviewed=apply_audit_review(audit["raw_audit"],Proof(**audit["assessment_review"]),evidence_root=self.root,snapshot_hash=self.snapshot,contract_hash=self.contract)
            if reviewed!=audit: raise AdapterUnavailable("audit findings changed after independent assessment")
        for proof in audit.get("artifacts",[]): source_proofs.append(self._proof(proof))
        configuration=[dict(path=file["path"],source_sha256=file["sha256"],secrets_found=assessments[file["path"]]["secrets_found"]) for file in self.plan.data["configuration"]]
        value=dict(readme=self.plan.data["readme"],documented_commands=commands,configuration=configuration,
            fixtures_explicit=fixture,accounts_before_fixture=before,fixtures_fingerprint=self.plan.data["fixtures_fingerprint"],audit=audit,
            review=asdict(self.plan.review),limits=limits,scope="source-reviewed README mapping; actual isolated commands and native receipts; no full acceptance claim",
            obligations_scope=sorted(REQUIRED_DOC_OBLIGATIONS if self.required_obligations is None else self.required_obligations))
        own=_native_proof(self.root,"docs-audit",value,self.snapshot,self.contract,checks=("OPS-05:docs_audit",))
        source_proofs.append(own)
        store=SupervisorEvidenceStore(self.root,self.snapshot,self.contract)
        await store.record_native_observation("docs_audit",value,source_proofs=source_proofs)
        return value


class NativeTimingRecorder:
    """Measure supervisor actions, not estimated or reconstructed timestamps.

    A phase must cite obtained native X/V artifacts via proof_provider(result).
    Timer wrappers are trusted factory calls; never pass a producer host script.
    Durations are diagnostic, never reasons to delete source scenarios.
    """
    def __init__(self,*,evidence_root,snapshot_hash,contract_hash,docker="docker"):
        import threading
        self.root,self.snapshot,self.contract=Path(evidence_root).resolve(),snapshot_hash,contract_hash
        self.docker=docker;self.phases=[]
        self.lock=threading.Lock()
        self._ingested=set()

    def _record(self,phase,started,elapsed,proofs):
        if not proofs: raise AdapterUnavailable("measured phase has no native operation artifacts")
        for proof in proofs:
            if proof.type not in {"X","V"} or not Path(proof.path).resolve().is_relative_to(self.root) or not proof.intact(snapshot_hash=self.snapshot,contract_hash=self.contract):
                raise AdapterUnavailable("measured operation evidence stale/outside supervisor")
        value=dict(phase=phase,started_at=started,ended_at=datetime.now(timezone.utc).isoformat(),seconds=elapsed,source_proofs=[asdict(p) for p in proofs])
        proof=_native_proof(self.root,"timing",value,self.snapshot,self.contract,checks=("OPS-06:"+phase,))
        with self.lock: self.phases.append((value,proof))

    def measure_sync(self,phase,operation,proof_provider):
        """Same native measurement for run_suite/build inside asyncio.to_thread."""
        import time
        if phase not in {"install","tests","browser","build","docker"}: raise AdapterUnavailable("unknown measured phase")
        started=datetime.now(timezone.utc).isoformat();tick=time.monotonic()
        result=operation();elapsed=time.monotonic()-tick
        self._record(phase,started,elapsed,proof_provider(result))
        return result

    def ingest(self,phase,timing,source_proof:Proof):
        """Accept exact split native execution clocks, never narrative values.

        The intact raw .execution.json must contain this exact timing object in
        timing (tests/build) or environment_preparation (install). Thus the
        installation duration is not double-counted as test time.
        """
        import math
        if phase not in {"install","tests","browser","build","docker"} or not isinstance(timing,dict) or timing.get("phase")!=phase:
            raise AdapterUnavailable("exact named native timing required")
        if source_proof.type!="X" or not Path(source_proof.path).resolve().is_relative_to(self.root) or not source_proof.intact(snapshot_hash=self.snapshot,contract_hash=self.contract):
            raise AdapterUnavailable("native timing receipt stale/outside supervisor")
        payload=json.loads(Path(source_proof.path).read_bytes())
        value=payload.get("value",payload)
        value=value.get("execution_receipt",value)
        if timing not in [value.get("timing"),value.get("environment_preparation")]:
            raise AdapterUnavailable("ingested clock differs from actual native execution receipt")
        seconds=timing.get("seconds")
        if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:
            raise AdapterUnavailable("invalid monotonic measured seconds")
        try:
            start=datetime.fromisoformat(timing["started_at"].replace("Z","+00:00"));end=datetime.fromisoformat(timing["ended_at"].replace("Z","+00:00"))
            if start.tzinfo is None or end.tzinfo is None or end<start: raise ValueError("invalid wall clock bounds")
        except (ValueError,KeyError,TypeError) as exc: raise AdapterUnavailable("native zoned clock bounds absent") from exc
        if not _image_id(value.get("image_id")) or not re.fullmatch(r"[a-f0-9]{64}",value.get("environment_fingerprint","")):
            raise AdapterUnavailable("timing is not tied to an actual isolated environment")
        row=dict(timing,source_proofs=[asdict(source_proof)],scope="native split-clock receipt, not total operation estimate")
        key=("execution",_sha(json.dumps(value,sort_keys=True,ensure_ascii=True).encode()),phase)
        with self.lock:
            if key in self._ingested: raise AdapterUnavailable("native execution clock already ingested")
            proof=_native_proof(self.root,"timing",row,self.snapshot,self.contract,checks=("OPS-06:"+phase,))
            self.phases.append((row,proof));self._ingested.add(key)
        return proof

    def ingest_delivery(self,receipt,source_proof:Proof,*,source_root):
        """Retain exact native build subclocks once, without measuring the total.

        Fresh source/image/manifest/lock/recipe admission is required. The two
        install clocks measure environment preparation, including cache checks;
        they do not invent uv/npm executions. Frontend build and final Docker
        build clocks are separate, not the enclosing build_delivery_image call.
        A frontend receipt contributes four clocks; a backend-only one, two.
        Do not additionally measure_sync('build', build_delivery_image, ...).
        """
        import math
        from ..agents.file_broker import ExecutionContext,FileBroker
        if not isinstance(source_proof,Proof) or source_proof.type!="X" or source_proof.passed is not True or not source_proof.intact(snapshot_hash=self.snapshot,contract_hash=self.contract):
            raise AdapterUnavailable("intact native delivery receipt required")
        path=Path(source_proof.path).absolute()
        if path.resolve()!=path or not path.is_relative_to(self.root):
            raise AdapterUnavailable("native delivery receipt outside unaliased supervisor root")
        FileBroker(ExecutionContext("delivery-clock-proof",self.root)).path(path.relative_to(self.root).as_posix())
        payload=json.loads(path.read_bytes());actual=payload.get("value",payload)
        if actual!=receipt: raise AdapterUnavailable("delivery clocks differ from exact native raw receipt")
        checks=delivery_build_checks(receipt,Path(source_root),self.snapshot)
        if not checks or any(row.get("passed") is not True for row in checks):
            raise AdapterUnavailable("native delivery source/image/recipe admission failed")
        commands={c["kind"]:c for c in receipt["commands"]}
        backend=receipt.get("backend_dependency")
        if backend!=commands["backend_install"]["builder"]:
            raise AdapterUnavailable("backend preparation clock differs from admitted builder")
        jobs=[("backend_dependency.timing","install",backend,commands["backend_install"])]
        if "frontend_install" in commands:
            frontend=receipt.get("frontend_build")
            if not isinstance(frontend,dict) or frontend.get("dependency")!=commands["frontend_install"]["builder"] or {k:v for k,v in frontend.items() if k!="dependency"}!=commands["typecheck_frontend_build"]:
                raise AdapterUnavailable("frontend preparation/build clocks differ from admitted commands")
            jobs.extend([
                ("frontend_build.dependency.timing","install",frontend["dependency"],commands["frontend_install"]),
                ("frontend_build.timing","build",frontend,commands["typecheck_frontend_build"])])
        jobs.append(("commands.image_build.timing","docker",commands["image_build"],commands["image_build"]))
        digest=_sha(json.dumps(receipt,sort_keys=True,ensure_ascii=True).encode());pending=[]
        for native_path,phase,container,command in jobs:
            clock=container.get("timing")
            if not isinstance(clock,dict) or clock.get("phase")!=phase:
                raise NativeTimingUnavailable("exact native delivery subclock absent: "+native_path)
            seconds=clock.get("seconds")
            if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:
                raise NativeTimingUnavailable("invalid measured delivery seconds")
            try:
                start=datetime.fromisoformat(clock["started_at"].replace("Z","+00:00"));end=datetime.fromisoformat(clock["ended_at"].replace("Z","+00:00"))
                if start.tzinfo is None or end.tzinfo is None or end<start: raise ValueError("invalid clock bounds")
            except (ValueError,KeyError,TypeError) as exc:
                raise NativeTimingUnavailable("native zoned delivery clock bounds absent") from exc
            row=dict(clock,native_clock_path=native_path,native_kind=command["kind"],
                image_id=receipt["image_id"] if phase=="docker" else command["image_id"],
                environment_fingerprint=commands["backend_install"]["environment_fingerprint"] if phase=="docker" else command["environment_fingerprint"],
                execution=command.get("execution","observed-command"),argv=command["argv"],return_code=command["rc"],
                source_proofs=[asdict(source_proof)],scope="exact native delivery subclock; cache/layer preparation is not a new install rc; no enclosing total included")
            pending.append((("delivery",digest,native_path),row))
        # All clocks are validated before publication: a bad fourth clock must
        # not leave three apparently complete phases behind.
        with self.lock:
            if any(key in self._ingested for key,_ in pending):
                raise AdapterUnavailable("native delivery subclock already ingested")
            proofs=[_native_proof(self.root,"timing",row,self.snapshot,self.contract,checks=("OPS-06:"+row["phase"],)) for _,row in pending]
            self.phases.extend((row,proof) for (_,row),proof in zip(pending,proofs))
            self._ingested.update(key for key,_ in pending)
        return proofs

    async def measure(self,phase,operation,proof_provider):
        import time
        if phase not in {"install","tests","browser","build","docker"}: raise AdapterUnavailable("unknown measured phase")
        started=datetime.now(timezone.utc).isoformat();tick=time.monotonic()
        result=await operation()
        elapsed=time.monotonic()-tick
        proofs=proof_provider(result)
        if hasattr(proofs,"__await__"): proofs=await proofs
        self._record(phase,started,elapsed,proofs)
        return result

    async def publish(self,*,llm_cost=None,llm_cost_proof:Proof|None=None):
        import platform
        import os
        from ..orchestrator.sandbox import _docker_call
        from .coordinator import SupervisorEvidenceStore
        required={"install","tests","browser","build","docker"}
        if {p[0]["phase"] for p in self.phases}!=required:
            raise AdapterUnavailable("all actual diagnostic phases required, none estimated")
        run=await asyncio.to_thread(_docker_call,[self.docker,"version","--format","{{json .Server}}"],capture_output=True,text=True,timeout=15,check=False)
        if run.returncode: raise AdapterUnavailable("identified Docker server unavailable")
        server=json.loads(run.stdout)
        if not server.get("Version") or not server.get("Os") or not server.get("Arch"): raise AdapterUnavailable("actual Docker machine identity incomplete")
        value=dict(machine=dict(os=platform.platform(),cpu=dict(processor=platform.processor() or "unreported",architecture=platform.machine(),logical_processors=os.cpu_count()),python=platform.python_version(),docker=server),
            seconds={phase:sum(row["seconds"] for row,_ in self.phases if row["phase"]==phase) for phase in sorted(required)},
            phases=[row for row,_ in self.phases],scope="monotonic measured factory phases; machine identities are observed; no deadline-based scenario removal")
        proofs=[p for _,p in self.phases]
        if llm_cost is not None:
            if llm_cost_proof is None or llm_cost_proof.type!="X" or not Path(llm_cost_proof.path).resolve().is_relative_to(self.root) or not llm_cost_proof.intact(snapshot_hash=self.snapshot,contract_hash=self.contract):
                raise AdapterUnavailable("LLM estimate may appear only with actual recorded cost artifact")
            raw=json.loads(Path(llm_cost_proof.path).read_bytes())
            if raw.get("value",raw).get("llm_cost")!=llm_cost: raise AdapterUnavailable("reported LLM cost differs from recorded artifact")
            value.update(llm_cost=llm_cost,llm_cost_reported=True);proofs.append(llm_cost_proof)
        proof=_native_proof(self.root,"execution-timings",value,self.snapshot,self.contract,checks=("OPS-06:machine_phases",))
        await SupervisorEvidenceStore(self.root,self.snapshot,self.contract).record_native_observation("execution_timings",value,source_proofs=[*proofs,proof])
        return value
