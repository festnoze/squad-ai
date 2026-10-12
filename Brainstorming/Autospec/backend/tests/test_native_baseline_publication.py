"""Offline baseline publication mechanics; source strings are never executed."""
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.orchestrator import pipeline_validation as boundary
from autospec.orchestrator.dependencies import atomic_json
from autospec.orchestrator.test_integrity import SuiteEvidence, capture_baseline, save_baseline
from autospec.agents.file_broker import IsolationViolation


def setup(tmp_path,monkeypatch, *, logical_prefix=''):
    root=tmp_path/'source';root.mkdir()
    checker=root/'test_required.py';checker.write_text('# original independently sealed checker\n')
    supervisor=tmp_path/'supervisor'
    arguments=dict(owner='retry-owner',project_root=root,docker='docker',timeout=30,logical_prefix=logical_prefix)
    evidence=SuiteEvidence({'test_required.py::required':'passed'},1,0)
    class Port:
        def __init__(self,*args,**kwargs):pass
        def collect_python(self,*args):return tuple(evidence.outcomes),SimpleNamespace(evidence=evidence,output='offline collection port',source_fingerprint='c'*64)
        def run_suite(self,*args,**kwargs):return SimpleNamespace(evidence=evidence,output='offline suite port',fingerprint='a'*64,image='sha256:'+'b'*64,source_fingerprint='c'*64)
    monkeypatch.setattr(boundary,'IsolatedValidator',Port)
    old_digest=hashlib.sha256(checker.read_bytes()).hexdigest()
    atomic_json(supervisor/'protected-test-files.json',{'files':{(logical_prefix+'/' if logical_prefix else '')+checker.name:old_digest}})
    baseline_path=supervisor/'native-baselines'/(hashlib.sha256(b'retry-owner:python').hexdigest()[:24]+'.json')
    return root,checker,supervisor,arguments,old_digest,baseline_path


@pytest.mark.parametrize('prefix',['','backend'])
def test_refused_baseline_is_not_published_and_retry_cannot_be_green(tmp_path,monkeypatch,prefix):
    root,checker,supervisor,args,old_digest,baseline_path=setup(tmp_path,monkeypatch,logical_prefix=prefix)
    checker.write_text('# weakened checker with same reported ID\n')
    before=(supervisor/'protected-test-files.json').read_bytes()
    for _ in range(3):
        ok,output,_=boundary.run_native(root,'python',supervisor,**args)
        assert not ok and 'CRITICAL_TEST_CHANGED_UNREVIEWED' in output
        assert not baseline_path.exists()
        assert (supervisor/'protected-test-files.json').read_bytes()==before


def test_existing_poisoned_baseline_remains_refused_on_every_retry(tmp_path,monkeypatch):
    root,checker,supervisor,args,_,baseline_path=setup(tmp_path,monkeypatch)
    checker.write_text('# previously poisoned candidate\n')
    save_baseline(capture_baseline(root,[checker.name],['test_required.py::required']),baseline_path,root)
    for _ in range(2):
        ok,output,_=boundary.run_native(root,'python',supervisor,**args)
        assert not ok and 'CRITICAL_TEST_CHANGED_UNREVIEWED' in output


def test_existing_baseline_without_protection_is_unavailable_not_auto_approved(tmp_path,monkeypatch):
    root,checker,supervisor,args,_,baseline_path=setup(tmp_path,monkeypatch)
    save_baseline(capture_baseline(root,[checker.name],['test_required.py::required']),baseline_path,root)
    (supervisor/'protected-test-files.json').unlink()
    ok,output,_=boundary.run_native(root,'python',supervisor,**args)
    assert not ok and 'CRITICAL_TEST_BASELINE_UNPUBLISHED' in output
    assert not (supervisor/'protected-test-files.json').exists()


def test_failed_atomic_baseline_save_preserves_protection_and_safe_retry(tmp_path,monkeypatch):
    root,checker,supervisor,args,old_digest,baseline_path=setup(tmp_path,monkeypatch)
    original=boundary.save_baseline
    def interrupted(*args):raise OSError('offline interrupted baseline publication')
    monkeypatch.setattr(boundary,'save_baseline',interrupted)
    with pytest.raises(OSError):boundary.run_native(root,'python',supervisor,**args)
    assert not baseline_path.exists()
    assert json.loads((supervisor/'protected-test-files.json').read_bytes())['files'][checker.name]==old_digest
    monkeypatch.setattr(boundary,'save_baseline',original)
    assert boundary.run_native(root,'python',supervisor,**args)[0]
    checker.write_text('# change after accepted baseline\n')
    assert not boundary.run_native(root,'python',supervisor,**args)[0]


def test_qa_authored_helper_outside_patterns_is_immutable_but_nonqa_business_is_not(tmp_path,monkeypatch):
    root,checker,supervisor,args,_,_=setup(tmp_path,monkeypatch)
    (root/'checks').mkdir();helper=root/'checks/login_assertions.py';helper.write_text('# independently authored QA assertions\n')
    business=root/'business.py';business.write_text('# product implementation v1\n')
    atomic_json(supervisor/'qa-authored-files.json',{'files':['checks/login_assertions.py','future_helper.py']})
    assert boundary.run_native(root,'python',supervisor,**args)[0]
    protected=json.loads((supervisor/'protected-test-files.json').read_bytes())['files']
    assert 'checks/login_assertions.py' in protected and 'business.py' not in protected and 'future_helper.py' not in protected
    business.write_text('# legitimate product implementation v2\n')
    assert boundary.run_native(root,'python',supervisor,**args)[0]
    helper.write_text('# weakening QA assertion\n')
    for _ in range(2):
        ok,output,_=boundary.run_native(root,'python',supervisor,**args)
        assert not ok and 'CRITICAL_TEST_CHANGED_UNREVIEWED' in output


def test_qa_workspace_paths_filter_exact_frontend_logical_prefix(tmp_path,monkeypatch):
    root,_,supervisor,_,_,_=setup(tmp_path,monkeypatch)
    (root/'checks').mkdir();(root/'checks/ui.ts').write_text('// QA helper\n')
    atomic_json(supervisor/'qa-authored-files.json',{'files':['web/client/checks/ui.ts','backend/checks/auth.py','web/clients/not_this.ts']})
    assert boundary.read_qa_authored_files(supervisor,root,logical_prefix='web/client')==['checks/ui.ts']


@pytest.mark.parametrize('files',[['../escape.py'],['C:/outside.py'],['bad\\path.py'],['checks//auth.py'],['x.py','x.py'],[False]])
def test_malformed_qa_provenance_is_refused_before_admission(tmp_path,monkeypatch,files):
    root,_,supervisor,args,_,baseline=setup(tmp_path,monkeypatch)
    atomic_json(supervisor/'qa-authored-files.json',{'files':files})
    with pytest.raises((ValueError,IsolationViolation)):boundary.run_native(root,'python',supervisor,**args)
    assert not baseline.exists()


def test_producer_like_extra_role_or_hash_is_not_admitted_provenance(tmp_path,monkeypatch):
    root,_,supervisor,_,_,_=setup(tmp_path,monkeypatch)
    atomic_json(supervisor/'qa-authored-files.json',{'files':['test_required.py'],'role':'qa','sha256':'a'*64})
    with pytest.raises(ValueError):boundary.read_qa_authored_files(supervisor,root)


def test_qa_journal_and_helper_hardlinks_cannot_alias_independent_metadata(tmp_path,monkeypatch):
    root,_,supervisor,_,_,_=setup(tmp_path,monkeypatch)
    journal=supervisor/'qa-authored-files.json';atomic_json(journal,{'files':['helper.py']})
    helper=root/'helper.py';helper.write_text('# regular helper\n')
    os.link(helper,tmp_path/'helper_alias.py')
    with pytest.raises(IsolationViolation):boundary.read_qa_authored_files(supervisor,root)
    helper.unlink();helper.write_text('# replacement regular helper\n')
    os.link(journal,tmp_path/'journal_alias.json')
    with pytest.raises(IsolationViolation):boundary.read_qa_authored_files(supervisor,root)


def test_new_qa_helper_does_not_silently_extend_an_existing_owner_baseline(tmp_path,monkeypatch):
    root,_,supervisor,args,_,_=setup(tmp_path,monkeypatch)
    assert boundary.run_native(root,'python',supervisor,**args)[0]
    (root/'additional_helper.py').write_text('# new QA helper\n')
    atomic_json(supervisor/'qa-authored-files.json',{'files':['additional_helper.py']})
    ok,output,_=boundary.run_native(root,'python',supervisor,**args)
    assert not ok and 'CRITICAL_QA_SUPPORT_BASELINE_INCOMPLETE' in output


def test_concurrent_sealed_owner_ids_cannot_be_overwritten_by_inflight_capture(tmp_path,monkeypatch):
    root,checker,supervisor,args,_,baseline_path=setup(tmp_path,monkeypatch)
    original=boundary.capture_baseline
    saved=[]
    def other_worker(*args):
        candidate=original(*args)
        save_baseline(replace(candidate,expected_test_ids=candidate.expected_test_ids+('test_required.py::another_required',)),baseline_path,root)
        saved.append(baseline_path.read_bytes())
        return candidate
    monkeypatch.setattr(boundary,'capture_baseline',other_worker)
    ok,output,_=boundary.run_native(root,'python',supervisor,**args)
    assert not ok and 'CRITICAL_BASELINE_CHANGED_CONCURRENTLY' in output
    assert baseline_path.read_bytes()==saved[0]


def test_oversized_provenance_is_not_parsed_or_admitted(tmp_path,monkeypatch):
    root,_,supervisor,_,_,_=setup(tmp_path,monkeypatch)
    (supervisor/'qa-authored-files.json').write_bytes(b' '*2_000_001)
    with pytest.raises(ValueError,match='bounded QA provenance'):boundary.read_qa_authored_files(supervisor,root)
