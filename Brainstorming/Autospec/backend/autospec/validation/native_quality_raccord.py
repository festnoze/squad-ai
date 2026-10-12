"""Consume sealed external plans and publish obtained native X observations.

No producer command/provider/reviewer is invoked. Experimental authorization
mutations use their independently approved exact-copy operational profiles.
Collection is not acceptance: red measurements stay red; unavailable ports NV.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..agents.file_broker import ExecutionContext, FileBroker
from ..config import settings
from ..orchestrator.dependencies import atomic_json
from ..orchestrator.isolated_validation import IsolatedValidator
from . import coordinator
from .final_gate import source_snapshot
from .quality_contracts import NativeQualityCollector, QUALITY_IDS
from .review_plans import load_reviewed_quality_plan
from .support_adapter import AdapterUnavailable, Proof


_OBSERVATIONS = {'native_suites': ('TST-01',), 'requirement_test_mapping': ('TST-02',),
    'coverage': ('TST-03',), 'real_sqlite_test_environment': ('TST-04',),
    'browser_e2e': ('TST-05',), 'authorization_mutation': ('TST-06',)}
_SEC09 = {'nominal_login_alice', 'nominal_login_bob', 'idor_no_db_effect',
    'permissions_before_idempotency_replay', 'list_no_foreign_ticket', 'scoped_list_total', 'scoped_dashboard_total'} | {
    'idor_' + method + endpoint for method, endpoint in [('GET','ticket'),('PATCH','ticket'),('GET','messages'),('GET','history')]} | {
    'idor_indistinguishable_' + method + endpoint for method, endpoint in [('GET','ticket'),('PATCH','ticket'),('GET','messages'),('GET','history')]}
_SEC10 = {'nominal_login_alice','nominal_login_agent2','staff_internal_note_created',
    'internal_absent_ticket','internal_absent_messages','internal_absent_history',
    'internal_filtered_before_pagination','no_internal_message_dto','internal_not_searchable'}
_FUN06 = {'patch_race','distinct_connections','close_wins','message_wins'}


def _owned_json(path, root):
    """Read only bounded, regular, unaliased supervisor artifacts."""
    root, path = Path(root).absolute(), Path(path).absolute()
    if not path.is_relative_to(root):
        raise AdapterUnavailable('native artifact is outside the supervisor root')
    try:
        path = FileBroker(ExecutionContext('native-quality-artifact', root)).path(path.relative_to(root).as_posix())
        if not path.is_file() or path.stat().st_size > 16_000_000:
            raise ValueError('bounded regular native artifact required')
        return json.loads(path.read_bytes())
    except (OSError, ValueError, RuntimeError) as exc:
        raise AdapterUnavailable('bounded native artifact unavailable') from exc


def _native_proof(path, store, checks):
    _owned_json(path, store.root)
    return Proof('X', str(path), hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                 store.snapshot, store.contract, tuple(checks), True,
                 'actual obtained measurement; not an acceptance verdict')


class _ReceiptValidator:
    """Retain provider-observed argv/rc, never reconstruct a likely command."""
    def __init__(self, validator, store, output, timing_recorder=None):
        self.validator, self.store, self.output = validator, store, output
        self.timing_recorder = timing_recorder
        self.receipts, self.timings, self.limits = {}, [], []

    def run_suite(self, root, ecosystem, mode, reportpath, **options):
        result = self.validator.run_suite(root, ecosystem, mode, reportpath, **options)
        receipt = getattr(result, 'execution_receipt', None)
        sidecar = Path(reportpath).with_suffix('.execution.json')
        try:
            raw = _owned_json(sidecar, self.store.root)
            if (not isinstance(receipt, dict) or raw != receipt or
                not isinstance(raw.get('argv'), list) or not raw['argv'] or
                any(not isinstance(arg, str) or '\x00' in arg for arg in raw['argv']) or
                type(raw.get('return_code')) is not int or
                raw['return_code'] != result.evidence.exit_code or
                raw.get('image_id') != result.image or
                raw.get('source_fingerprint') != result.source_fingerprint or
                raw.get('environment_fingerprint') != result.fingerprint):
                raise AdapterUnavailable('observed command/return code identity differs')
            name = Path(reportpath).name.split('-', 1)[0]
            # Bind the exact sidecar to the overall source/contract identity.
            path = self.output/(name+'-execution-receipt-'+uuid4().hex+'.json')
            atomic_json(path, dict(raw, snapshot_hash=self.store.snapshot, contract_hash=self.store.contract))
            proof = _native_proof(path, self.store, ('TST-01:'+name+':execution',))
            self.receipts[name] = dict(argv=raw['argv'], return_code=raw['return_code'], proofs=[asdict(proof)])
            if options.get('coveragepath') is not None:
                self.receipts[name+'_coverage'] = self.receipts[name]
            for field, phase in [('timing', 'tests'), ('environment_preparation', 'install')]:
                clock = raw.get(field)
                if (not isinstance(clock, dict) or clock.get('phase') != phase or
                    type(clock.get('seconds')) not in {int, float} or not math.isfinite(clock['seconds']) or clock['seconds'] < 0 or
                    not isinstance(clock.get('started_at'), str) or not isinstance(clock.get('ended_at'), str)):
                    self.limits.append(name+': actual '+phase+' timing unavailable')
                else:
                    self.timings.append(dict(clock, proofs=[asdict(proof)]))
                    if self.timing_recorder is not None:
                        self.timing_recorder.ingest(phase,clock,proof)
        except AdapterUnavailable as exc:
            self.limits.append(Path(reportpath).name+': '+str(exc))
        return result


class _IdentityAdapter:
    def __init__(self, contract, source, store):
        self.contract, self.source, self.store = contract, source, store
        self.evidence_root = store.root
    async def snapshot_hash(self): return source_snapshot(self.source).digest
    async def contract_hash(self): return self.contract.contract_hash
    async def proofs(self, rid): return await self.store.proofs(rid)


def _experimental_row(rid, observed, proofs, *, snapshot, contract, evidence_root, required):
    """Only complete executed observations and matching native X define verdict.

    RFAIL/source-review text, row.status and incomplete assertions cannot kill a
    mutant or make nominal green. No acceptance PASS is returned here.
    """
    if (not isinstance(observed,list) or not observed or
        any(not isinstance(row,dict) or type(row.get('passed')) is not bool or
            not isinstance(row.get('check'),str) or not row['check'] for row in observed) or
        not required <= {row.get('check') for row in observed}):
        raise AdapterUnavailable('complete native experimental checks absent: '+rid)
    expected = all(row['passed'] for row in observed)
    native = []
    for raw in proofs:
        try: proof = raw if isinstance(raw,Proof) else Proof(**raw)
        except (TypeError, ValueError) as exc: raise AdapterUnavailable('experimental proof malformed') from exc
        if proof.type != 'X': continue
        data = _owned_json(proof.path, evidence_root)
        if (type(proof.passed) is not bool or
            (data.get('snapshot_hash'),data.get('contract_hash')) != (snapshot,contract) or
            not proof.intact(snapshot_hash=snapshot,contract_hash=contract) or
            not {rid+':'+row['check'] for row in observed} <= set(proof.checks)):
            raise AdapterUnavailable('experimental X identity/scope unavailable: '+rid)
        if proof.passed is expected:
            actual = data.get('observed', data.get('checks'))
            if actual == json.loads(json.dumps(observed)):
                native.append(proof)
    if not native:
        raise AdapterUnavailable('native X does not attest these experimental observations: '+rid)
    return dict(id=rid, status='EXPERIMENTAL', runtime_status='PASS' if expected else 'FAIL',
        snapshot_hash=snapshot,contract_hash=contract,observed=observed,
        proofs=[asdict(p) for p in native],limits=[],
        scope='complete executed mutation experiment only; never requirement acceptance')


async def _mutation_runtime(contract, source, snapshot, control):
    """SEC09/10 and FUN06 only, on a fresh exact owned instrumented Linux DB."""
    from .security_contracts import SecurityVerifier, _Case
    from .business_contracts import BusinessContractVerifier, BUSINESS_CHECKS
    context, _ = coordinator._context(contract,source,snapshot,control,instrumented=True,phase='quality-mutation')
    rows = {}
    async with context as harness:
        verifier = SecurityVerifier(contract,harness.adapter)
        verifier.snapshot = snapshot
        await verifier._identity()
        for rid, required in [('SEC-09',_SEC09),('SEC-10',_SEC10)]:
            case = _Case(verifier,rid); verifier._active_case = case
            manifest = await harness.adapter.prepare_case(rid)
            verifier._secrets.update(account.password for account in manifest.accounts.values())
            await getattr(verifier,'_sec'+rid[-2:])(case)
            await verifier._identity()
            path = Path(harness.adapter.evidence_root)/(rid+'-experiment-'+uuid4().hex+'.json')
            atomic_json(path,dict(id=rid,snapshot_hash=snapshot,contract_hash=contract.contract_hash,
                                 checks=case.checks,reproduction=case.reproduction,scope='EXPERIMENTAL'))
            proof = Proof('X',str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,
                contract.contract_hash,tuple(rid+':'+row['check'] for row in case.checks),all(row['passed'] for row in case.checks))
            rows[rid] = _experimental_row(rid,case.checks,[proof],snapshot=snapshot,contract=contract.contract_hash,
                                          evidence_root=control,required=required)
        class ExperimentalBusiness(BusinessContractVerifier):
            checks = {'FUN-06': BUSINESS_CHECKS['FUN-06']}
        report = await ExperimentalBusiness(harness.adapter,contract).verify(snapshot)
        result = report['requirements'][0]
        rows['FUN-06'] = _experimental_row('FUN-06',result['observed'],result['proofs'],snapshot=snapshot,
            contract=contract.contract_hash,evidence_root=control,required=_FUN06)
    return rows


def _mutation_callback(contract, source, snapshot, control, plan):
    async def probe(root, identity, oracle):
        root = Path(root).resolve()
        if oracle != contract.contract_hash or source_snapshot(root).digest != identity:
            raise AdapterUnavailable('experimental source/oracle identity differs')
        if identity == snapshot and root == source:
            target = control
        elif (identity == plan['mutant_snapshot_hash'] and root != source and
              plan['mutant_supervisor_root'] is not None):
            target = Path(plan['mutant_supervisor_root']).resolve()
            if target != control/'mutation-profiles'/identity:
                raise AdapterUnavailable('experimental operational profile is not the sealed exact mutant')
        else:
            raise AdapterUnavailable('no reviewed runtime profile for this experimental copy')
        return await _mutation_runtime(contract,root,identity,target)
    return probe


class _BrowserRun:
    def __init__(self, contract, source, snapshot, control, timings, timing_recorder=None):
        self.contract,self.source,self.snapshot,self.control = contract,source,snapshot,control
        self.timings = timings
        self.timing_recorder = timing_recorder
    async def verify_e2e(self, snapshot, *, mode, scenario_ids):
        if snapshot != self.snapshot:
            raise AdapterUnavailable('native browser snapshot changed')
        context, store = coordinator._context(self.contract,self.source,snapshot,self.control,phase='quality-browser')
        async with context as harness:
            tick, started = time.monotonic(), datetime.now(timezone.utc).isoformat()
            async def execute():
                return await coordinator._execute_e2e(self.contract,harness,store,snapshot,
                    modes=(mode,),scenario_ids=scenario_ids)
            if self.timing_recorder is None:
                runs = await execute()
            else:
                runs = await self.timing_recorder.measure('browser',execute,
                    lambda rows:[Proof(**p) for row in rows for p in row.get('proofs',[]) if p.get('type') in {'X','V'}])
            self.timings.append(dict(phase='browser',seconds=time.monotonic()-tick,started_at=started,
                ended_at=datetime.now(timezone.utc).isoformat(),scope='actual Playwright API verification; no CLI argv claimed',
                proofs=[p for row in runs for p in row.get('proofs',[]) if p.get('type') in {'X','V'}]))
        return dict(snapshot_hash=snapshot,contract_hash=self.contract.contract_hash,scenarios=runs)


async def _publish_collection(collector, store, output_root):
    published = []
    for name, rids in _OBSERVATIONS.items():
        if name in collector.errors or name not in collector.records:
            continue  # absence remains unavailable, never an empty success observation
        value = await collector.observe(name)
        path = output_root/(name+'.json')
        atomic_json(path,dict(name=name,value=value,snapshot_hash=store.snapshot,contract_hash=store.contract,
            scope='obtained native measurement; not an acceptance verdict'))
        proof = Proof('X',str(path),hashlib.sha256(path.read_bytes()).hexdigest(),store.snapshot,store.contract,
            ('OBS:'+name,)+tuple(rid+':native_collection' for rid in rids),True,
            'obtained native measurement; failed values preserved')
        await store.record_native_observation(name,value,source_proofs=[proof])
        for rid in rids: await store.publish_native_proof(rid,proof)
        published.append(name)
    for rid, proofs in collector.extra_proofs.items():
        if rid not in QUALITY_IDS: raise AdapterUnavailable('unexpected native quality proof identity')
        for proof in proofs:
            if proof.type in {'X','V'}: await store.publish_native_proof(rid,proof)
    return published


async def collect_native_quality(state, contract, source_root, snapshot_hash, supervisor_root, *, validator=None, timing_recorder=None):
    """Publish measured quality observations from a sealed independently reviewed plan.

    Return OBTAINED/PARTIAL/NOT_VERIFIED, never acceptance PASS. Missing plan,
    fixtures, browser, SQL tracing or native mutation remain explicit limits.
    Model/provider calls and producer-supplied callbacks are not accepted.
    An optional factory-owned shared NativeTimingRecorder retains the precise
    install/tests clocks and measures browser API calls separately. Its caller
    owns subsequent build/docker timing and complete diagnostic publication.
    """
    if not isinstance(snapshot_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', snapshot_hash):
        raise AdapterUnavailable('canonical source identity required')
    source, control = Path(source_root).absolute(),Path(supervisor_root).absolute()
    if (source.resolve()!=source or control.resolve()!=control or control.is_relative_to(source)):
        raise AdapterUnavailable('quality roots must be distinct canonical owned directories')
    control.mkdir(parents=True,exist_ok=True)
    output = control/'native-quality'/snapshot_hash/uuid4().hex
    if source_snapshot(source).digest != snapshot_hash:
        raise AdapterUnavailable('quality source snapshot drift')
    store = coordinator.SupervisorEvidenceStore(control,snapshot_hash,contract.contract_hash)
    try:
        plan = load_reviewed_quality_plan(contract,source,snapshot_hash,control)
    except AdapterUnavailable:
        return dict(status='NOT_VERIFIED',snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash,
            observations=[],limits=['independent sealed native quality plan unavailable'])
    validator = validator or IsolatedValidator(control/'linux-cache',docker=settings.docker_cmd,
                                               timeout=settings.test_suite_timeout_s)
    identity = _IdentityAdapter(contract,source,store)
    async def sqlite_probe(adapter,snapshot,oracle):
        if oracle!=contract.contract_hash:raise AdapterUnavailable('SQLite oracle differs')
        return await coordinator.sqlite_quality_probe(state,contract,source,snapshot,control)
    captured = _ReceiptValidator(validator,store,output,timing_recorder)
    browser_timings = []
    collector = NativeQualityCollector(contract,identity,captured,product_root=source,evidence_root=output,
        suites=plan['suites'],mapping_path=plan['mapping_path'],review=plan['review'],e2e_mode=plan['e2e_mode'],
        mutation=plan['mutation'],mutation_probe=_mutation_callback(contract,source,snapshot_hash,control,plan),
        sqlite_probe=sqlite_probe,browser_factory=lambda:_BrowserRun(contract,source,snapshot_hash,control,browser_timings,timing_recorder))
    await collector.collect(snapshot_hash)
    if source_snapshot(source).digest != snapshot_hash:
        raise AdapterUnavailable('quality source changed before publication')
    published = await _publish_collection(collector,store,output)
    limits = [name+': '+','.join(values) for name,values in sorted(collector.errors.items())]+captured.limits
    if captured.receipts:
        path = output/'native-receipts.json'
        atomic_json(path,dict(snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash,value=captured.receipts))
    if 'browser_e2e' in published:
        publisher = getattr(coordinator,'publish_reviewed_e2e',None)
        if publisher is None:
            limits.append('sealed E2E cache publication port unavailable')
        else:
            await publisher(store,collector.records['browser_e2e'],
                plan_path=control/'source-reviews'/snapshot_hash/'quality'/'quality-review-package.json',
                review=plan['review'],source_root=source)
    receipt = dict(version=1,status='PARTIAL' if limits else 'OBTAINED',snapshot_hash=snapshot_hash,
        contract_hash=contract.contract_hash,observations=published,limits=limits,
        native_receipts=captured.receipts,timings=captured.timings+browser_timings,
        scope='native collection only; independent quality/final acceptance remains mandatory')
    path = output/'collection.json';atomic_json(path,receipt)
    return dict(receipt,path=str(path))
