"""Offline source-R consumption and execution-owned join metadata regressions."""
import hashlib
from pathlib import Path

import pytest

from autospec.contracts import import_contract
from autospec.validation.architecture_contracts import ArchitectureContractVerifier, ARCHITECTURE_CHECKS
from autospec.validation.business_contracts import BusinessContractVerifier
from autospec.validation.support_adapter import AdapterUnavailable, Proof
from tests.support_contract_fixture import SQLiteSupportSubject


@pytest.fixture
def contract():
    root = Path(__file__).resolve().parents[2] / 'docs/validation/support-client'
    return import_contract((root / '01_specification.md').read_text(encoding='utf-8'),
        (root / '02_requirements_verification.md').read_text(encoding='utf-8'),
        reviewed_by='independent fixture test')


@pytest.mark.parametrize('rid', ['ARC-01', 'ARC-09'])
@pytest.mark.parametrize('mode,expected', [('valid','PASS'), ('absent','NOT_VERIFIED'),
    ('tampered','NOT_VERIFIED'), ('partial','NOT_VERIFIED'), ('negative','FAIL')])
async def test_r_only_architecture_consumes_exact_intact_reviews(tmp_path, contract, rid, mode, expected):
    subject = SQLiteSupportSubject(tmp_path, contract)
    path = tmp_path / 'independent-review.json'
    path.write_text('independent source review', encoding='utf-8')
    names = ARCHITECTURE_CHECKS[rid]
    tags = tuple(rid + ':' + name for name in (names[:-1] if mode == 'partial' else names))
    proof = Proof('R', str(path), hashlib.sha256(path.read_bytes()).hexdigest(),
        subject.snapshot, contract.contract_hash, tags, mode != 'negative')
    if mode == 'tampered': path.write_text('changed review', encoding='utf-8')
    async def supplied(requirement): return [] if mode == 'absent' else [proof]
    subject.adapter._ports['proofs'] = supplied
    try:
        report = await ArchitectureContractVerifier(subject.adapter, contract).verify(subject.snapshot, ids=[rid])
        row, = report['requirements']
        assert row['id'] == rid
        assert row['status'] == expected, row
        assert row['observed'] == []  # R never manufactures native execution.
        if mode == 'valid':
            assert not row['limits']
            assert {p['type'] for p in row['proofs']} == {'R'}
    finally:
        await subject.adapter.close()


@pytest.mark.parametrize('ids', ['FUN-01', [], ['FUN-01', 'FUN-01'], ['ARC-01'], ['FUN-01', 1]])
async def test_selector_rejects_ambiguous_unknown_or_duplicate_ids_before_execution(tmp_path, contract, ids):
    subject = SQLiteSupportSubject(tmp_path, contract)
    async def forbidden(): raise AssertionError('selector must reject before identity/native ports')
    subject.adapter._ports['snapshot'] = forbidden
    with pytest.raises(ValueError, match='unique supported'):
        await BusinessContractVerifier(subject.adapter, contract).verify(subject.snapshot, ids=ids)
    await subject.adapter.close()


async def test_selected_native_complete_without_ui_or_review_approval(tmp_path, contract):
    subject = SQLiteSupportSubject(tmp_path, contract)
    try:
        report = await BusinessContractVerifier(subject.adapter, contract).verify(subject.snapshot,
            ids=['FUN-02', 'FUN-01'])
        assert [r['id'] for r in report['requirements']] == ['FUN-02', 'FUN-01']
        first, second = report['requirements']
        assert first['native_complete'] is True and first['status'] == 'NOT_VERIFIED'
        assert any('ui_clear' in reason for reason in first['limits'])
        assert second['native_complete'] is True and second['status'] == 'PASS'
    finally:
        await subject.adapter.close()


async def test_supplied_green_native_proof_cannot_fill_unexecuted_subprobe(tmp_path, contract):
    subject = SQLiteSupportSubject(tmp_path, contract)
    path = tmp_path / 'supplied.json'; path.write_text('not execution')
    proof = Proof('X', str(path), hashlib.sha256(path.read_bytes()).hexdigest(), subject.snapshot,
        contract.contract_hash, ('FUN-01:creation', 'FUN-01:roles', 'FUN-01:bounds'))
    async def supplied(rid): return [proof]
    async def absent(*args, **kwargs): raise AdapterUnavailable('native prepare unavailable')
    subject.adapter._ports['proofs'] = supplied
    subject.adapter._ports['prepare'] = absent
    try:
        row, = (await BusinessContractVerifier(subject.adapter, contract).verify(subject.snapshot,
            ids=['FUN-01']))['requirements']
        assert row['native_complete'] is False
        assert row['status'] == 'NOT_VERIFIED'
        assert any('native execution absent' in reason for reason in row['limits'])
    finally:
        await subject.adapter.close()


async def test_failed_native_assertions_remain_failed_even_when_complete(tmp_path, contract):
    subject = SQLiteSupportSubject(tmp_path, contract, 'agent_creation')
    try:
        row, = (await BusinessContractVerifier(subject.adapter, contract).verify(subject.snapshot,
            ids=['FUN-01']))['requirements']
        assert row['native_complete'] is True  # complete does not mean passing.
        assert row['status'] == 'FAIL'
        assert any(not e['passed'] for e in row['observed'])
        assert any(p['type'] == 'X' and p['passed'] is False for p in row['proofs'])
    finally:
        await subject.adapter.close()


async def test_identity_mismatch_cannot_be_native_complete(tmp_path, contract):
    subject = SQLiteSupportSubject(tmp_path, contract)
    try:
        row, = (await BusinessContractVerifier(subject.adapter, contract).verify('b' * 64,
            ids=['FUN-01']))['requirements']
        assert row['native_complete'] is False and row['status'] == 'NOT_VERIFIED'
        assert not row['observed']
    finally:
        await subject.adapter.close()


async def test_two_passes_keep_both_native_artifacts_intact(tmp_path, contract):
    subject = SQLiteSupportSubject(tmp_path, contract)
    try:
        verifier = BusinessContractVerifier(subject.adapter, contract)
        first, = (await verifier.verify(subject.snapshot, ids=['FUN-01']))['requirements']
        second, = (await verifier.verify(subject.snapshot, ids=['FUN-01']))['requirements']
        assert first['status'] == second['status'] == 'PASS'
        x1, = [Proof(**p) for p in first['proofs'] if p['type'] == 'X']
        x2, = [Proof(**p) for p in second['proofs'] if p['type'] == 'X']
        assert x1.path != x2.path
        for proof in (x1, x2):
            assert proof.intact(snapshot_hash=subject.snapshot, contract_hash=contract.contract_hash)
    finally:
        await subject.adapter.close()
