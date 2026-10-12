"""Exact concurrent USD ledgers and actual controlled offline CLI processes."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time

import pytest

from autospec.agents.runner import ClaudeCliRunner, active_budget_usd
from autospec.orchestrator import budget_reservations as module
from autospec.orchestrator.budget_reservations import BudgetReservations, BudgetReservationError, ProviderBudgetProof


def proof(root, **changes):
    path = root / 'provider-proof.json'
    data = {'version': 1, 'provider': 'controlled-offline-cli', 'currency': 'USD', 'bound_kind': 'hard_usd',
        'whole_logical_call': True, 'all_billable_costs': True, 'enforced_before_overshoot': True,
        'exact_usd_transport': 'active_budget_usd', 'reviewed_by': 'factory-test-source-review', **changes}
    path.write_text(json.dumps(data, sort_keys=True))
    return ProviderBudgetProof(data['provider'], path, hashlib.sha256(path.read_bytes()).hexdigest())


def ledger(tmp_path, **options):
    return BudgetReservations(1, enabled=True, journal=tmp_path/'budget.json', budget_id='project-test', **options)


def test_default_off_and_enabled_requires_durable_external_identity(tmp_path):
    capability = proof(tmp_path)
    with pytest.raises(BudgetReservationError, match='DISABLED'):
        BudgetReservations(1).acquire('call', .1, capability)
    with pytest.raises(BudgetReservationError, match='DURABILITY_REQUIRED'):
        BudgetReservations(1, enabled=True)
    with pytest.raises(BudgetReservationError, match='UNSAFE_LEDGER'):
        BudgetReservations(1, enabled=True, journal=tmp_path/'budget.json', budget_id='p', producer_root=tmp_path)


@pytest.mark.parametrize('changes', [
    {'bound_kind': 'estimated_usd'}, {'enforced_before_overshoot': False},
    {'whole_logical_call': False}, {'all_billable_costs': False}, {'exact_usd_transport': 'float_rounded'},
])
def test_cli_flag_or_token_cap_is_not_a_hard_whole_call_proof(tmp_path, changes):
    pool = ledger(tmp_path)
    with pytest.raises(BudgetReservationError, match='PROVIDER_UNBOUNDED'):
        pool.acquire('call', .1, proof(tmp_path, **changes))
    assert pool.snapshot()['reserved_usd'] == '0'
    with pytest.raises(BudgetReservationError, match='TOKEN_UNBOUNDED'):
        pool.acquire('call', .1, proof(tmp_path), token_cap=100)


def test_receipt_tampering_and_inexact_transport_refuse_before_admission(tmp_path):
    capability = proof(tmp_path)
    pool = ledger(tmp_path)
    capability.evidence_path.write_text('{}')
    with pytest.raises(BudgetReservationError, match='PROVIDER_UNBOUNDED'):
        pool.acquire('changed', .1, capability)
    with pytest.raises(BudgetReservationError, match='INEXACT_ENVELOPE'):
        pool.acquire('precision', '0.1000000000000000001', proof(tmp_path))
    assert pool.snapshot()['reserved_usd'] == '0'


def test_atomic_thread_reservations_never_allocate_same_balance_twice(tmp_path):
    pool, capability = ledger(tmp_path), proof(tmp_path)
    def acquire(index):
        try:
            return pool.acquire(str(index), .1, capability)
        except BudgetReservationError as error:
            assert error.code == 'BUDGET_RESERVED'
            return None
    with ThreadPoolExecutor(max_workers=20) as workers:
        results = list(workers.map(acquire, range(50)))
    admitted = [reservation for reservation in results if reservation]
    assert len(admitted) == 10
    snapshot = pool.snapshot()
    assert Decimal(snapshot['recorded_usd']) + Decimal(snapshot['reserved_usd']) == 1
    for reservation in admitted:
        pool.cancel(reservation, cost_usd=.03, complete=True)
    assert Decimal(pool.snapshot()['recorded_usd']) == Decimal('.30')
    assert pool.snapshot()['reserved_usd'] == '0'


def test_unknown_partial_cancel_late_result_and_duplicate_receipt(tmp_path):
    pool, capability = ledger(tmp_path), proof(tmp_path)
    reservation = pool.acquire('once', .6, capability)
    pool.envelope(reservation)
    unknown = pool.cancel(reservation, cost_usd=.2)
    assert Decimal(unknown['recorded_usd']) == Decimal('.2')
    assert Decimal(unknown['reserved_usd']) == Decimal('.4') and unknown['unreported_calls'] == 1
    with pytest.raises(BudgetReservationError, match='COST_UNREPORTED'):
        pool.acquire('new', .1, capability)
    result = pool.reconcile(reservation, .3)
    assert Decimal(result['recorded_usd']) == Decimal('.3') and result['reserved_usd'] == '0'
    pool.reconcile(reservation, .3)
    pool.cancel(reservation)  # final known cost cannot become unknown/free
    assert Decimal(pool.snapshot()['recorded_usd']) == Decimal('.3')
    with pytest.raises(BudgetReservationError, match='DUPLICATE_CALL'):
        pool.acquire('once', .1, capability)


def test_restart_keeps_unknown_inflight_and_every_charged_amount(tmp_path):
    pool, capability = ledger(tmp_path), proof(tmp_path)
    completed = pool.acquire('done', .3, capability); pool.reconcile(completed, .2)
    pending = pool.acquire('inflight', .4, capability); pool.envelope(pending)
    restored = ledger(tmp_path)
    state = restored.snapshot()
    assert Decimal(state['recorded_usd']) == Decimal('.2') and Decimal(state['reserved_usd']) == Decimal('.4')
    assert state['unreported_calls'] == 1
    with pytest.raises(BudgetReservationError, match='COST_UNREPORTED'):
        restored.acquire('retry', .1, capability)
    restored.reconcile(pending, .25)
    assert Decimal(restored.snapshot()['recorded_usd']) == Decimal('.45')


def test_cap_lowered_inflight_preserves_envelopes_and_blocks_next_admissions(tmp_path):
    pool, capability = ledger(tmp_path), proof(tmp_path)
    first, second = pool.acquire('one', .4, capability), pool.acquire('two', .4, capability)
    state = pool.update_cap(.5)
    assert Decimal(state['cap_debt_usd']) == Decimal('.3')
    assert pool.envelope(first).usd_limit == '0.4' and pool.envelope(second).usd_limit == '0.4'
    with pytest.raises(BudgetReservationError, match='CAP_DEBT'):
        pool.acquire('three', .1, capability)
    pool.reconcile(first, .1)
    with pytest.raises(BudgetReservationError, match='CAP_CHANGED_IN_FLIGHT'):
        pool.acquire('still-active', .01, capability)
    pool.reconcile(second, .1)
    assert Decimal(pool.snapshot()['available_usd']) == Decimal('.3')
    pool.acquire('now-safe', .3, capability)


def test_overshoot_conflicting_final_cost_and_tiny_charges_never_disappear(tmp_path):
    pool, capability = ledger(tmp_path), proof(tmp_path)
    reservation = pool.acquire('violating-provider', .4, capability)
    state = pool.reconcile(reservation, .6)
    assert Decimal(state['overshoot_usd']) == Decimal('.2') and Decimal(state['recorded_usd']) == Decimal('.6')
    pool.reconcile(reservation, .1)
    assert Decimal(pool.snapshot()['recorded_usd']) == Decimal('.6')
    with pytest.raises(BudgetReservationError, match='PROVIDER_BOUND_BREACH'):
        pool.acquire('must-not-run', .1, capability)
    tiny = tmp_path/'tiny'; tiny.mkdir()
    pool = ledger(tiny)
    base = pool.acquire('base', .5, proof(tiny)); pool.reconcile(base, .5)
    tail = pool.acquire('tail', .1, proof(tiny)); pool.reconcile(tail, '5e-324')
    assert Decimal(pool.snapshot()['recorded_usd']) > Decimal('.5')


def test_single_dispatch_context_restores_and_invalid_usage_blocks(tmp_path):
    pool, capability = ledger(tmp_path), proof(tmp_path)
    reservation = pool.acquire('single', .2, capability)
    envelope = pool.envelope(reservation)
    with envelope.bind():
        assert active_budget_usd.get() == .2
    assert active_budget_usd.get() is None
    with pytest.raises(BudgetReservationError, match='DUPLICATE_DISPATCH'):
        with envelope.bind(): pass
    with pytest.raises(BudgetReservationError, match='INACTIVE_RESERVATION'):
        pool.envelope(reservation)
    with pytest.raises(BudgetReservationError, match='INVALID_USD'):
        pool.reconcile(reservation, 'NaN')
    assert pool.snapshot()['unreported_calls'] == 1


def test_failed_persistence_blocks_admission_without_reloading_older_totals(tmp_path, monkeypatch):
    pool, capability = ledger(tmp_path), proof(tmp_path)
    reservation = pool.acquire('paid', .4, capability)
    def fail(*args): raise OSError('disk write failed')
    monkeypatch.setattr(module, 'atomic_json', fail)
    with pytest.raises(OSError): pool.reconcile(reservation, .5)
    assert Decimal(pool.snapshot()['recorded_usd']) == Decimal('.5')
    assert 'STORAGE_FAILED' in pool.snapshot()['blocked_reasons']
    with pytest.raises(BudgetReservationError, match='STORAGE_FAILED'):
        pool.acquire('no-new-call', .1, capability)


@pytest.mark.asyncio
async def test_two_real_offline_cli_processes_receive_exact_parallel_envelopes(tmp_path, monkeypatch):
    """Real trusted local processes, NO Claude/API/model invocation at all."""
    from autospec.agents import runner as runner_module
    pool, capability = ledger(tmp_path), proof(tmp_path)
    script = tmp_path/'controlled_cli.py'
    markers = tmp_path/'markers'; markers.mkdir()
    script.write_text('''import json,sys,time
from decimal import Decimal
from pathlib import Path
root=Path(sys.argv[1]); call=sys.argv[2]; args=sys.argv[3:]
cap=args[args.index('--max-budget-usd')+1]
assert '--tools' in args and args[args.index('--tools')+1]==''
prompt=sys.stdin.read()
(root/(call+'.started')).write_text(json.dumps({'cap':cap,'started':time.monotonic()}))
deadline=time.monotonic()+15
while len(list(root.glob('*.started')))<2:
 if time.monotonic()>deadline: raise RuntimeError('two processes did not overlap')
 time.sleep(.01)
cost=min(Decimal('0.20'),Decimal(cap))
print(json.dumps({'result':json.dumps({'cap':cap,'call':call}), 'total_cost_usd':float(cost),
 'usage':{'input_tokens':10,'output_tokens':10}}))
''')
    original = runner_module._run_tracked
    def offline_cli(argv, prompt, cwd, timeout):
        # Keep real capped native-owned execution but substitute the source-
        # reviewed factory CLI. No native Claude executable can ever launch.
        return original([sys.executable, str(script), str(markers), prompt.splitlines()[-1], *argv[1:]], prompt, cwd, timeout)
    monkeypatch.setattr(runner_module, '_run_tracked', offline_cli)
    monkeypatch.setattr(runner_module, '_ensure_claude_isolation', lambda: None)
    first, second = pool.acquire('first', .4, capability), pool.acquire('second', .4, capability)
    with pytest.raises(BudgetReservationError, match='BUDGET_RESERVED'):
        pool.acquire('third', .3, capability)
    async def call(reservation):
        envelope = pool.envelope(reservation)
        try:
            with envelope.bind():
                result = await ClaudeCliRunner().arun(reservation.call_id, 'controlled offline fixture')
            assert result.usage_reported
            pool.reconcile(reservation, result.cost_usd)
            return json.loads(result.text)
        except BaseException:
            pool.cancel(reservation)
            raise
    outputs = await asyncio.wait_for(asyncio.gather(call(first), call(second)), timeout=25)
    assert outputs == [{'cap':'0.4','call':'first'}, {'cap':'0.4','call':'second'}]
    events = [json.loads(path.read_text()) for path in markers.glob('*.started')]
    assert len(events)==2 and all(event['cap']=='0.4' for event in events)
    state = pool.snapshot()
    assert Decimal(state['recorded_usd']) == Decimal('.4') and state['reserved_usd'] == '0'
    assert not state['blocked_reasons'] and active_budget_usd.get() is None
