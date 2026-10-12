"""Linux validation safety and opt-in real Python/React/runtime proofs."""
import json
import os
from pathlib import Path
import shutil
import urllib.request
from types import SimpleNamespace

import pytest

from autospec.agents.file_broker import IsolationViolation
from autospec.orchestrator.validation_environment import (LinuxEnvironmentManager, snapshot_product, admit_manifest)
from autospec.orchestrator.isolated_validation import IsolatedValidator, RuntimeSession


def test_filtered_snapshot_never_exposes_factory_metadata_or_credentials(tmp_path):
    root = tmp_path / "product"
    root.mkdir()
    for name in ("autospec-state.json", ".env", ".autospec-bootstrap.json", "acceptance-contract.json", "build-monitor.jsonl"):
        (root / name).write_text("secret")
    for name in (".claude", ".autospec", ".venv", "node_modules", ".git"):
        (root / name).mkdir()
        (root / name / "secret").write_text("secret")
    (root / "main.py").write_text("print('product')")
    stage = snapshot_product(root, tmp_path / "stage")
    assert [p.name for p in stage.iterdir()] == ["main.py"]


def test_snapshot_rejects_hardlinked_source(tmp_path):
    root = tmp_path / "product"
    root.mkdir()
    (tmp_path / "outside").write_text("secret")
    os.link(tmp_path / "outside", root / "main.py")
    with pytest.raises(IsolationViolation):
        snapshot_product(root, tmp_path / "stage")


@pytest.mark.parametrize("manifest", [
    {"dependencies": {"x": "file:../outside"}},
    {"dependencies": {"x": "https://localhost/package.tgz"}},
    {"workspaces": ["../outside"]},
])
def test_local_url_workspace_dependencies_denied_before_docker(tmp_path, manifest):
    (tmp_path / "package.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="ISOLATION_UNAVAILABLE"):
        admit_manifest(tmp_path, "node", require_lock=False)


def test_clean_recipe_disables_hooks_builds_and_project_install(tmp_path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname="proof"\nversion="0.1.0"\n')
    recipe = LinuxEnvironmentManager._recipe("sha256:" + "a" * 64, "python", "test", "b" * 64, manifest)
    assert "--locked --no-build --no-install-project --no-config" in recipe
    assert "UV_PROJECT_ENVIRONMENT=/opt/venv" in recipe
    assert "COPY ." not in recipe
    assert "USER 65532:65532" in recipe
    assert '--python /usr/local/bin/python --target /opt/reporters --no-deps --no-build --no-config' in recipe
    assert 'uv pip install --python /opt/venv/bin/python' not in recipe
    node = LinuxEnvironmentManager._recipe("sha256:" + "a" * 64, "node", "test", "b" * 64, manifest)
    assert "--ignore-scripts" in node and "--userconfig=/dev/null" in node


def test_runtime_forbids_environment_secrets_and_external_db(tmp_path):
    with pytest.raises(RuntimeError):
        RuntimeSession(tmp_path, "image", ["python"], env={"ANTHROPIC_API_KEY": "secret"})
    with pytest.raises(RuntimeError):
        RuntimeSession(tmp_path, "image", ["python"], env={"DATABASE_URL": "postgres://host/private"})


@pytest.mark.parametrize('report',['not-json',None])
def test_suite_cannot_admit_missing_or_malformed_report(tmp_path,monkeypatch,report):
    from autospec.orchestrator import isolated_validation
    root=tmp_path/'source';root.mkdir();(root/'test.py').write_text('# trusted fixture')
    manager=SimpleNamespace(prepare=lambda *_:SimpleNamespace(image='attested',fingerprint='fingerprint'))
    def run(command,stage,*args,**kwargs):
        if report is not None: (stage/'suite-report.json').write_text(report)
        return 0,'exit zero is not evidence',''
    monkeypatch.setattr(isolated_validation,'run_isolated',run)
    result=IsolatedValidator(tmp_path/'cache',manager=manager).run_suite(root,'python','test',tmp_path/'evidence.json')
    assert result.evidence.exit_code==0 and not result.evidence.report_valid


def test_collection_refuses_incomplete_custom_items(tmp_path,monkeypatch):
    from autospec.orchestrator.isolated_validation import IsolatedSuiteResult
    from autospec.orchestrator.test_integrity import SuiteEvidence
    validator=IsolatedValidator(tmp_path/'cache')
    report=tmp_path/'report.json'
    def suite(*args,**kwargs):
        report.write_text(json.dumps({'collectors':[{'result':[{'nodeid':'custom::id','type':'UnknownItem'}]}]}))
        return IsolatedSuiteResult(SuiteEvidence({},1,0),'','fingerprint','image')
    monkeypatch.setattr(validator,'run_suite',suite)
    with pytest.raises(RuntimeError,match='Incomplete/unsupported'):
        validator.collect_python(tmp_path/'product',report)


def test_coverage_requires_full_source_inventory_and_ignores_foreign_totals(tmp_path):
    from autospec.orchestrator.isolated_validation import _coverage_inventory,_admit_source_coverage
    (tmp_path/'business.py').write_text('value=1\n')
    (tmp_path/'critical.py').write_text('def security():return False\n')
    (tmp_path/'test_business.py').write_text('assert True\n')
    inventory=_coverage_inventory(tmp_path,'.')
    assert set(inventory)=={'business.py','critical.py'}
    environment=SimpleNamespace(fingerprint='env',image='image')
    covered={'summary':{'covered_lines':1,'num_statements':1,'missing_lines':0,'num_branches':0,'covered_branches':0}}
    missing={'summary':{'covered_lines':0,'num_statements':1,'missing_lines':1,'num_branches':0,'covered_branches':0}}
    with pytest.raises(ValueError,match='omitted'):
        _admit_source_coverage({'files':{'business.py':covered}},inventory,'.','source',environment)
    result=_admit_source_coverage({'files':{'business.py':covered,'critical.py':missing,'test_business.py':covered},
        'totals':{'percent_covered':100000}},inventory,'.','source',environment)
    assert result['totals']['percent_covered']==50
    assert set(result['files'])==set(inventory) and result['autospec_inventory']['files']==inventory


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION") != "1", reason="Opt-in real Linux Docker dependency/network proof")
def test_real_python_locked_suite_and_net_none_runtime(tmp_path):
    product = tmp_path / "product"
    product.mkdir()
    (product / "pyproject.toml").write_text('[project]\nname="isolated-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=["fastapi==0.136.3","uvicorn==0.49.0","pytest==9.0.3","httpx==0.28.1"]\n')
    (product / "main.py").write_text('import os,sqlite3\nfrom fastapi import FastAPI\nimport uvicorn\na=FastAPI()\n@a.get("/api/health")\ndef health():\n c=sqlite3.connect("/tmp/runtime.db"); value=c.execute("select 1").fetchone()[0]; c.close(); return {"value":value,"secret":os.environ.get("ANTHROPIC_API_KEY"),"uid":os.getuid()}\nuvicorn.run(a,host="0.0.0.0",port=8000)\n')
    (product / "test_nominal.py").write_text('import os,socket\ndef test_isolated():\n assert os.getuid()==65532\n assert "ANTHROPIC_API_KEY" not in os.environ\n assert not os.path.exists("/var/run/docker.sock")\n s=socket.socket();s.settimeout(.2)\n try: s.connect(("1.1.1.1",443))\n except OSError: pass\n else: assert False,"network escaped"\n')
    validator = IsolatedValidator(tmp_path / "cache", timeout=300)
    validator.manager.ensure_lock(product, "python")
    result = validator.run_suite(product, "python", "test", tmp_path / "report.json")
    assert result.evidence.exit_code == 0, result.output
    assert result.evidence.outcomes == {"test_nominal.py::test_isolated": "passed"}
    assert result.fingerprint and result.image.startswith("sha256:")
    first = validator.manager.prepare(product, "python", "test")
    assert first.image == result.image
    stage = snapshot_product(product, tmp_path / "runtime-stage")
    import time
    with RuntimeSession(stage, first.image, ["/opt/venv/bin/python", "main.py"]) as runtime:
        deadline=time.monotonic()+15
        while True:
            try:
                body=json.load(urllib.request.urlopen(runtime.origin+"/api/health",timeout=3))
                break
            except OSError:
                if time.monotonic()>deadline: raise AssertionError(runtime.logs())
                time.sleep(.1)
        assert body == {"value":1,"secret":None,"uid":65532}
        identifier=runtime.identifier
        port=runtime.host_port
    import socket
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1",port)) != 0
    from autospec.orchestrator.sandbox import _docker_call
    result = _docker_call(["docker", "container", "inspect",identifier],capture_output=True,text=True,timeout=10)
    assert result.returncode != 0


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION") != "1", reason="Opt-in real Python/React/API/SQLite/Chromium foundation")
@pytest.mark.asyncio
async def test_real_fullstack_foundation_and_runtime_recovery(tmp_path, monkeypatch):
    from autospec.orchestrator import bootstrap, workspace
    root=tmp_path/'product';root.mkdir()
    state=SimpleNamespace(id='linux-foundation',name='Linux proof',streams=[],brownfield_path='',product_profile='api',
        backend_language=SimpleNamespace(value='python'),technical_stack={'backend':'python','framework':'fastapi','frontend':'react','database':'sqlite','kind':'fullstack'})
    monkeypatch.setattr(workspace,'workspace_dir',lambda _:root)
    # The driver uses the factory's installed Playwright, never product deps.
    factory=Path(os.environ.get('AUTOSPEC_TEST_FACTORY_ROOT','C:/Dev/squad-ai/Brainstorming/Autospec'))
    monkeypatch.setattr(bootstrap,'PROJECT_DIR',factory)
    workspace.scaffold(state,streams_enabled=False,ui_tests_enabled=False)
    result=await bootstrap.verify(state,root,timeout_s=600)
    assert result.ok,result.detail
    assert 'Chromium' in result.detail and 'SELECT 1 OK' in result.detail
    assert (root/'uv.lock').exists() and (root/'frontend/package-lock.json').exists()
    assert not (root/'.venv').exists() and not (root/'frontend/node_modules').exists()
    assert not (root/'.autospec/bootstrap.db').exists()
    # Recovery is cache/image based, no host venv resurrection or source reset.
    source=(root/'main.py').read_bytes();lock=(root/'uv.lock').read_bytes()
    recovered=await bootstrap.verify_runtime(state,root,timeout_s=90,repair_dependencies=True)
    assert recovered.ok,recovered.detail
    assert (root/'main.py').read_bytes()==source and (root/'uv.lock').read_bytes()==lock
    # Vite transpilation alone would accept this. The independent tsc gate must
    # reject it before any dist export or browser success is claimed.
    frontend=root/'frontend'
    (frontend/'src/TypeBroken.ts').write_text('export const wrong: string = 123;\n')
    validator=IsolatedValidator(tmp_path/'typecheck-cache')
    rc,output,dist,_=validator.build_frontend(frontend)
    try:
        assert rc!=0 and 'TS2322' in output,output
        assert not (dist/'dist').exists()
    finally:
        shutil.rmtree(dist)


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION") != "1", reason="Opt-in real manifest-only dependency coordinator Linux resolver")
@pytest.mark.parametrize('ecosystem',['python','node'])
def test_real_dependency_resolver_exports_only_manifest_lock(tmp_path,ecosystem):
    from autospec.orchestrator.validation_environment import dependency_resolver
    if ecosystem=='python':
        (tmp_path/'pyproject.toml').write_text('[project]\nname="deps-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
        command=['uv','add','--no-sync','--no-build','httpx==0.28.1']
        expected={'pyproject.toml','uv.lock','source.py','.env'}
    else:
        (tmp_path/'package.json').write_text(json.dumps({'name':'deps-proof','version':'1.0.0','scripts':{'preinstall':'node -e "process.exit(97)"','postinstall':'node -e "process.exit(98)"'}}))
        command=['npm','install','--package-lock-only','--ignore-scripts','--save-prod','react@18.3.1']
        expected={'package.json','package-lock.json','source.py','.env'}
    (tmp_path/'source.py').write_text('raise RuntimeError("MUST NEVER EXECUTE")')
    (tmp_path/'.env').write_text('SECRET=must-not-enter-builder')
    result=dependency_resolver(command,cwd=tmp_path,env={'ANTHROPIC_API_KEY':'must-not-inherit'})
    assert result.returncode==0,result.stdout+result.stderr
    assert {p.name for p in tmp_path.iterdir()}==expected
    assert (tmp_path/'source.py').read_text()=='raise RuntimeError("MUST NEVER EXECUTE")'


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION") != "1", reason="Opt-in real pytest collection and branch coverage in Linux")
def test_real_pytest_collection_and_coverage_are_structured(tmp_path):
    root=tmp_path/'product';root.mkdir()
    (root/'pyproject.toml').write_text('[project]\nname="coverage-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=["pytest==9.0.3"]\n')
    (root/'business.py').write_text('def choose(value):\n if value:\n  return 1\n return 0\n')
    (root/'test_business.py').write_text('import pytest\nfrom business import choose\n@pytest.mark.parametrize("value",[True,False])\ndef test_choose(value):\n assert choose(value)==int(value)\n')
    (root/'.coveragerc').write_text('[run]\nomit=business.py\n')
    (root/'pytest.ini').write_text('[pytest]\naddopts=--no-cov --json-report-file=forged.json\n')
    validator=IsolatedValidator(tmp_path/'cache')
    validator.manager.ensure_lock(root,'python')
    ids,collected=validator.collect_python(root,tmp_path/'collection.json')
    assert ids==('test_business.py::test_choose[False]','test_business.py::test_choose[True]')
    assert collected.evidence.collected==2 and collected.evidence.executed==0
    result=validator.run_suite(root,'python','test',tmp_path/'suite.json',coveragepath=tmp_path/'coverage.json',coverage_source='business')
    assert result.evidence.report_valid and result.evidence.exit_code==0,result.output
    assert result.evidence.outcomes=={identifier:'passed' for identifier in ids}
    assert result.coverage['totals']['num_statements']==4
    assert result.coverage['totals']['covered_lines']==4
    assert result.coverage['totals']['num_branches']==2
    assert result.coverage['totals']['covered_branches']==2
    assert json.loads((tmp_path/'coverage.json').read_text())==result.coverage
    assert result.source_fingerprint==collected.source_fingerprint
    assert result.coverage['autospec_inventory']['files'].keys()=={'business.py'}
