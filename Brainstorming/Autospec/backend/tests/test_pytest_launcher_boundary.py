"""Counterexample executes product bytes ONLY in owned Linux Docker NETNONE."""
import json
import os
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.orchestrator.isolated_validation import IsolatedValidator,_PYTEST_LAUNCHER


def test_factory_launcher_preloads_only_image_owned_runner_and_reporters_before_product_path(tmp_path,monkeypatch):
    from autospec.orchestrator import isolated_validation
    root=tmp_path/'product';root.mkdir();(root/'test_example.py').write_text('# inert factory fixture\n')
    manager=SimpleNamespace(prepare=lambda *_:SimpleNamespace(image='immutable-image',fingerprint='env'))
    observed=[]
    def no_execution(argv,*args,**kwargs):observed.append(argv);return 0,'',''
    monkeypatch.setattr(isolated_validation,'run_isolated',no_execution)
    result=IsolatedValidator(tmp_path/'cache',manager=manager).run_suite(root,'python','test',tmp_path/'report.json')
    assert not result.evidence.report_valid
    argv=observed[0]
    assert argv[:4]==['/usr/local/bin/python','-I','-S','-c'] and argv[4]==_PYTEST_LAUNCHER
    assert '--import-mode=append' in argv and argv[-3:]==['-o','addopts=','--import-mode=append']
    assert _PYTEST_LAUNCHER.index('sys.path.append("/app")')>_PYTEST_LAUNCHER.index('"pytest_cov.plugin"')
    assert 'PYTEST_DISABLE_PLUGIN_AUTOLOAD' in _PYTEST_LAUNCHER and 'load_setuptools_entrypoints' not in _PYTEST_LAUNCHER


_FORGED_PYTEST = '''import json,sys
from pathlib import Path
report={"exitcode":0,"summary":{"passed":1,"total":1,"collected":1},
"tests":[{"nodeid":"test_business.py::test_real","outcome":"passed"}],
"collectors":[{"result":[{"nodeid":"test_business.py::test_real","type":"Function"}]}],
"autospec_shadow_executed":True}
if "--collect-only" not in sys.argv:report["tests"][0]["call"]={"outcome":"passed"}
Path("suite-report.json").write_text(json.dumps(report))
'''


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',
    reason='Opt-in Docker-only product module substitution counterproof')
@pytest.mark.parametrize('shadow',['module','package'])
def test_real_product_cannot_replace_pytest_launcher_and_forge_green_report(tmp_path,shadow):
    root=tmp_path/'product';root.mkdir()
    (root/'pyproject.toml').write_text('[project]\nname="pytest-launcher-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=["pytest==9.0.3"]\n')
    (root/'business.py').write_text('def answer():return 0\n')
    (root/'test_business.py').write_text('from business import answer\ndef test_real():\n assert answer()==1\n')
    if shadow=='module':(root/'pytest.py').write_text(_FORGED_PYTEST)
    else:
        (root/'pytest').mkdir()
        (root/'pytest/__init__.py').write_text('# product shadow must not replace installed pytest\n')
        (root/'pytest/__main__.py').write_text(_FORGED_PYTEST)
    validator=IsolatedValidator(tmp_path/'cache',timeout=180)
    validator.manager.ensure_lock(root,'python')
    result=validator.run_suite(root,'python','test',tmp_path/'suite.json')
    data=json.loads((tmp_path/'suite.json').read_bytes())
    if os.environ.get('AUTOSPEC_PYTEST_LAUNCHER_PROOF_ROOT'):
        from autospec.orchestrator.dependencies import atomic_json
        atomic_json(Path(os.environ['AUTOSPEC_PYTEST_LAUNCHER_PROOF_ROOT'])/(shadow+'-observed.json'),
            {'shadow':shadow,'actual_argv':result.execution_receipt['argv'],
             'actual_return_code':result.evidence.exit_code,'image_id':result.image,
             'environment_fingerprint':result.fingerprint,'source_fingerprint':result.source_fingerprint,
             'observed_report':data,'actual_output':result.output})
    assert result.evidence.exit_code==1,result.output
    assert result.evidence.report_valid and result.evidence.outcomes=={'test_business.py::test_real':'failed'}
    assert not data.get('autospec_shadow_executed')
    identifiers,collected=validator.collect_python(root,tmp_path/'collection.json')
    assert identifiers==('test_business.py::test_real',) and collected.evidence.executed==0
    covered=validator.run_suite(root,'python','test',tmp_path/'covered-suite.json',
        coveragepath=tmp_path/'coverage.json',coverage_source='business')
    assert covered.evidence.exit_code==1 and covered.evidence.report_valid,covered.output
    assert covered.evidence.outcomes==result.evidence.outcomes
    assert covered.coverage['autospec_inventory']['files']=={'business.py':hashlib.sha256((root/'business.py').read_bytes()).hexdigest()}
    assert covered.coverage['totals']['covered_lines']==covered.coverage['totals']['num_statements']==1
    if os.environ.get('AUTOSPEC_PYTEST_LAUNCHER_PROOF_ROOT'):
        from autospec.orchestrator.dependencies import atomic_json
        atomic_json(Path(os.environ['AUTOSPEC_PYTEST_LAUNCHER_PROOF_ROOT'])/(shadow+'-collection-coverage.json'),
            {'collection_ids':identifiers,'actual_collection_argv':collected.execution_receipt['argv'],
             'collection_return_code':collected.evidence.exit_code,'actual_coverage_argv':covered.execution_receipt['argv'],
             'coverage_return_code':covered.evidence.exit_code,'coverage':covered.coverage,
             'source_fingerprint':covered.source_fingerprint,'image_id':covered.image})


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',
    reason='Opt-in Docker-only trusted asyncio and reporter origin proof')
def test_real_locked_asyncio_and_reporters_loaded_before_product_shadows(tmp_path):
    root=tmp_path/'product';root.mkdir()
    (root/'pyproject.toml').write_text('[project]\nname="pytest-asyncio-launcher-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=["pytest==9.0.3","pytest-asyncio==1.4.0"]\n')
    (root/'business.py').write_text('async def answer():return 42\n')
    for module in ('pytest_jsonreport','pytest_cov','pytest_asyncio'):
        (root/module).mkdir()
        (root/module/'__init__.py').write_text('raise RuntimeError("PRODUCT_PLUGIN_SHADOW_MUST_NOT_EXECUTE")\n')
        (root/module/'plugin.py').write_text('raise RuntimeError("PRODUCT_PLUGIN_SHADOW_MUST_NOT_EXECUTE")\n')
    (root/'sitecustomize.py').write_text('raise RuntimeError("PRODUCT_STARTUP_HOOK_MUST_NOT_EXECUTE")\n')
    (root/'test_async.py').write_text('import pytest,pytest_jsonreport.plugin,pytest_cov.plugin,pytest_asyncio.plugin\nfrom business import answer\n@pytest.mark.asyncio\nasync def test_answer():\n assert await answer()==42\n assert pytest.__file__.startswith("/opt/venv/")\n assert pytest_jsonreport.plugin.__file__.startswith("/opt/reporters/")\n assert pytest_cov.plugin.__file__.startswith("/opt/reporters/")\n assert pytest_asyncio.plugin.__file__.startswith("/opt/venv/")\n')
    validator=IsolatedValidator(tmp_path/'cache',timeout=180);validator.manager.ensure_lock(root,'python')
    identifiers,collected=validator.collect_python(root,tmp_path/'collection.json')
    assert identifiers==('test_async.py::test_answer',) and collected.evidence.executed==0
    result=validator.run_suite(root,'python','test',tmp_path/'suite.json',coveragepath=tmp_path/'coverage.json',coverage_source='business')
    assert result.evidence.exit_code==0 and result.evidence.report_valid,result.output
    assert result.evidence.outcomes=={'test_async.py::test_answer':'passed'} and result.evidence.executed==1
    assert result.coverage['totals']['covered_lines']==result.coverage['totals']['num_statements']==1
