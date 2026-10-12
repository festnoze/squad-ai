"""Independent adversarial join replay: native supervisor/trusted fixture only."""
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest

from autospec.contracts import import_contract
from autospec.validation.business_contracts import BusinessContractVerifier
from autospec.validation.coordinator import SupervisorEvidenceStore, _current_rows
from autospec.validation.evidence_join import publish_backend_receipt, publish_browser_receipts, join_rechecked_native
from autospec.validation.support_adapter import AdapterUnavailable, Proof
from tests.support_contract_fixture import SQLiteSupportSubject


@pytest.fixture
def contract():
    root = Path('C:/Users/e.millerioux/.codex/worktrees/autospec-remediation-integration/squad-ai/Brainstorming/Autospec/docs/validation/support-client')
    return import_contract((root/'01_specification.md').read_text(encoding='utf-8'),
        (root/'02_requirements_verification.md').read_text(encoding='utf-8'), reviewed_by='independent fixture test')


async def native(tmp_path, contract, rid='FUN-02'):
    subject = SQLiteSupportSubject(tmp_path, contract)
    store = SupervisorEvidenceStore(tmp_path, subject.snapshot, contract.contract_hash)
    subject.adapter._ports['proofs'] = store.proofs
    row = await recheck(subject, contract, rid)
    return subject, store, row


async def recheck(subject, contract, rid='FUN-02'):
    report = await BusinessContractVerifier(subject.adapter, contract).verify(subject.snapshot, ids=[rid])
    row, = _current_rows(report, {rid}, subject.snapshot, contract.contract_hash)
    return row


def ui_row(tmp_path, store, *, rid='FUN-02', tag='ui_clear', passed=True):
    checks = [{'check': rid+':'+tag, 'passed': passed, 'observed': passed, 'expected': True}]
    path = tmp_path/(rid+'-'+tag+'.json')
    path.write_text(json.dumps(dict(id=rid,snapshot_hash=store.snapshot,contract_hash=store.contract,checks=checks)))
    proof = Proof('X',str(path),hashlib.sha256(path.read_bytes()).hexdigest(),store.snapshot,
        store.contract,(rid+':'+tag,),passed)
    return dict(id=rid, status='PASS' if passed else 'FAIL', native_complete=False,
        snapshot_hash=store.snapshot,contract_hash=store.contract,proofs=[asdict(proof)],observed=checks,limits=[])


async def test_fresh_complete_native_replay_consumes_exact_ui_tag_and_retains_both_proofs(tmp_path, contract):
    subject,store,previous = await native(tmp_path,contract)
    try:
        assert previous['status']=='NOT_VERIFIED' and previous['native_complete'] is True
        assert await publish_backend_receipt(store,previous) is True
        browser = ui_row(tmp_path,store)
        await publish_browser_receipts(store,[browser])
        current = await recheck(subject,contract)
        joined = join_rechecked_native(previous,current,browser)
        assert joined['status']=='PASS'
        xs=[Proof(**p) for p in joined['proofs'] if p['type']=='X']
        assert all(p.intact(snapshot_hash=store.snapshot,contract_hash=store.contract) for p in xs)
        native_paths={p['path'] for row in (previous,current) for p in row['proofs'] if p['type']=='X' and 'FUN-02:scope' in p['checks']}
        assert len(native_paths)==2
    finally: await subject.adapter.close()


@pytest.mark.parametrize('damage',['missing','tampered','wrong_snapshot','wrong_contract','mismatched_observed','false_completion'])
async def test_backend_marker_needs_current_exact_native_artifact(tmp_path,contract,damage):
    subject,store,row=await native(tmp_path,contract)
    try:
        if damage=='missing': row['proofs']=[]
        elif damage=='tampered': Path(row['proofs'][0]['path']).write_text('changed')
        elif damage=='wrong_snapshot': row['proofs'][0]['snapshot_hash']='b'*64
        elif damage=='wrong_contract': row['proofs'][0]['contract_hash']='c'*64
        elif damage=='mismatched_observed': row['observed']=row['observed'][:-1]
        else: row['native_complete']=False
        try: obtained=await publish_backend_receipt(store,row)
        except AdapterUnavailable: obtained=False
        assert obtained is False
        assert not any('FUN-02:backend' in p.checks for p in await store.proofs('FUN-02'))
    finally: await subject.adapter.close()


@pytest.mark.parametrize('tag',['missing_clears_previous_detail','ui_clear_typo'])
async def test_nonexact_browser_alias_cannot_satisfy_ui_check(tmp_path,contract,tag):
    subject,store,previous=await native(tmp_path,contract)
    try:
        await publish_backend_receipt(store,previous)
        browser=ui_row(tmp_path,store,tag=tag)
        await publish_browser_receipts(store,[browser])
        current = await recheck(subject,contract)
        assert join_rechecked_native(previous,current,browser)['status']=='NOT_VERIFIED'
    finally: await subject.adapter.close()


async def test_tampered_ui_artifact_cannot_publish_or_promote(tmp_path,contract):
    subject,store,previous=await native(tmp_path,contract)
    try:
        browser=ui_row(tmp_path,store)
        Path(browser['proofs'][0]['path']).write_text('tampered')
        with pytest.raises(AdapterUnavailable): await publish_browser_receipts(store,[browser])
        current = await recheck(subject,contract)
        assert join_rechecked_native(previous,current)['status']=='NOT_VERIFIED'
    finally: await subject.adapter.close()


async def test_failed_ui_stays_failed(tmp_path,contract):
    subject,store,previous=await native(tmp_path,contract)
    try:
        await publish_backend_receipt(store,previous)
        browser=ui_row(tmp_path,store,passed=False)
        await publish_browser_receipts(store,[browser])
        current = await recheck(subject,contract)
        assert current['status']=='FAIL'
        assert join_rechecked_native(previous,current,browser)['status']=='FAIL'
    finally: await subject.adapter.close()


@pytest.mark.parametrize('rid,tag,review', [('FUN-12','ui_refresh',False),
    ('FUN-06','ui_draft',False), ('FUN-06','ui_draft',True)])
async def test_other_exact_ui_aliases_do_not_replace_required_source_review(tmp_path,contract,rid,tag,review):
    subject,store,previous=await native(tmp_path,contract,rid)
    try:
        assert previous['native_complete'] is True
        await publish_backend_receipt(store,previous)
        browser=ui_row(tmp_path,store,rid=rid,tag=tag)
        await publish_browser_receipts(store,[browser])
        if review:
            path=tmp_path/'source-review.json';path.write_text('fixture source transaction review')
            proof=Proof('R',str(path),hashlib.sha256(path.read_bytes()).hexdigest(),store.snapshot,
                store.contract,(rid+':transactions',))
            index_path=tmp_path/'proofs.json'
            index=json.loads(index_path.read_text())
            index['proofs'].setdefault(rid,[]).append(asdict(proof))
            index_path.write_text(json.dumps(index))
        current=await recheck(subject,contract,rid)
        joined=join_rechecked_native(previous,current,browser)
        assert joined['status']==('NOT_VERIFIED' if rid=='FUN-06' and not review else 'PASS'),joined
        if rid=='FUN-06' and not review:
            assert any('transactions' in limit or 'evidence type R' in limit for limit in joined['limits'])
    finally: await subject.adapter.close()


@pytest.mark.parametrize('prior_status,prior_complete,current_status,current_complete,expected',[
    ('FAIL',True,'PASS',True,'FAIL'),('NOT_VERIFIED',False,'PASS',True,'NOT_VERIFIED'),
    ('NOT_VERIFIED',True,'PASS',False,'NOT_VERIFIED'),('NOT_VERIFIED',True,'FAIL',True,'FAIL')])
def test_join_cannot_erase_failure_or_incomplete_native_execution(prior_status,prior_complete,current_status,current_complete,expected):
    def row(status,complete): return dict(id='FUN-02',snapshot_hash='a'*64,contract_hash='b'*64,
        status=status,native_complete=complete,proofs=[],observed=[],limits=[])
    assert join_rechecked_native(row(prior_status,prior_complete),row(current_status,current_complete))['status']==expected


@pytest.mark.parametrize('field',['id','snapshot_hash','contract_hash'])
def test_join_refuses_cross_identity(field):
    previous=dict(id='FUN-02',snapshot_hash='a'*64,contract_hash='b'*64,status='NOT_VERIFIED',native_complete=True,
        proofs=[],observed=[],limits=[])
    current=copy.deepcopy(previous);current[field]='different'
    with pytest.raises(AdapterUnavailable): join_rechecked_native(previous,current)


async def test_arc_contribution_alone_never_replaces_full_architecture_verification(tmp_path,contract):
    subject=SQLiteSupportSubject(tmp_path,contract)
    from autospec.validation.architecture_contracts import ArchitectureContractVerifier
    store=SupervisorEvidenceStore(tmp_path,subject.snapshot,contract.contract_hash)
    subject.adapter._ports['proofs']=store.proofs
    contribution=ui_row(tmp_path,store,rid='ARC-06',tag='error_client')
    try:
        await publish_browser_receipts(store,[contribution])
        row,=(await ArchitectureContractVerifier(subject.adapter,contract).verify(subject.snapshot,ids=['ARC-06']))['requirements']
        assert row['status']!='PASS'  # fixture lacks source R and full conforming DTO/OpenAPI.
        assert any('ARC-06:public_dto' in limit or 'ARC-06:frontend_errors' in limit for limit in row['limits'])
        assert any(e['check']=='openapi' for e in row['observed'])
    finally: await subject.adapter.close()
