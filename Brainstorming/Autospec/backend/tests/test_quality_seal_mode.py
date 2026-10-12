"""Author's mechanical regression tests, NOT independent product review R."""
import hashlib
from dataclasses import asdict

import pytest

from autospec.orchestrator.dependencies import atomic_json
from autospec.validation.coordinator import SupervisorEvidenceStore, _quality_seal
from autospec.validation.final_gate import source_snapshot
from autospec.validation.quality_contracts import NativeSuiteSpec, native_quality_plan_hash
from autospec.validation.support_adapter import AdapterUnavailable, Proof


@pytest.mark.parametrize('problem', [None,'missing_mode','unknown_mode','nonstring_mode','changed_mode','missing_mode_review'])
def test_reviewed_supervisor_browser_plan_seal_preserves_its_exact_mode(tmp_path, problem):
    source = tmp_path/'source'
    source.mkdir()
    (source/'service.py').write_text('# inert fixture; no host import\n')
    snapshot = source_snapshot(source).digest
    supervisor = tmp_path/'supervisor'
    supervisor.mkdir()
    contract = 'c'*64
    mapping = supervisor/'mapping.json'
    atomic_json(mapping, {'scope': 'mechanical fixture only'})
    suite = NativeSuiteSpec('backend', '.', 'python', ('service.py',), ('services',))
    digest = native_quality_plan_hash((suite,), mapping, e2e_mode='supervisor_browser')
    plan = supervisor/'quality-plan.json'
    payload = dict(snapshot_hash=snapshot, contract_hash=contract, mapping_path=str(mapping),
        mapping_sha256=hashlib.sha256(mapping.read_bytes()).hexdigest(), suites=[asdict(suite)],
        source_inventory={'backend': {'service.py': hashlib.sha256((source/'service.py').read_bytes()).hexdigest()}},
        mutation=None, e2e_mode='supervisor_browser', plan_hash=digest)
    if problem=='missing_mode': payload.pop('e2e_mode')
    elif problem=='unknown_mode': payload['e2e_mode']='borrowed_native'
    elif problem=='nonstring_mode': payload['e2e_mode']={'mode':'supervisor_browser'}
    elif problem=='changed_mode': payload['e2e_mode']='native'
    atomic_json(plan, payload)
    review_path = supervisor/'mechanical-review.json'
    atomic_json(review_path, {'scope': 'mechanical fixture only; no product acceptance'})
    tags = ('QUALITY:plan:'+digest,) + (() if problem=='missing_mode_review' else ('QUALITY:e2e:supervisor_browser',))
    review = Proof('R', str(review_path), hashlib.sha256(review_path.read_bytes()).hexdigest(), snapshot, contract, tags)
    seal = dict(path=str(plan), sha256=hashlib.sha256(plan.read_bytes()).hexdigest(), review=asdict(review))
    if problem is None:
        assert _quality_seal(SupervisorEvidenceStore(supervisor, snapshot, contract), seal, source) == review
    else:
        with pytest.raises(AdapterUnavailable):
            _quality_seal(SupervisorEvidenceStore(supervisor, snapshot, contract), seal, source)
