"""Supervisor metatests; nominal Docker/HTTP/TLS/SQLite are opt-in, never mocked."""
import hashlib
import io
import base64
import json
import os
import shutil
from uuid import uuid4
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from autospec.validation.coordinator import EvidenceAdapter, SupervisorEvidenceStore
from autospec.validation.product_harness import OwnedProductHarnessSession, ReviewedProductBindings
from autospec.validation.security_observations import (BoundedSecretScanner,
    CookieDeploymentMode, SecurityObservationBindings, validate_security_environment)
from autospec.validation.support_adapter import AdapterUnavailable
from tests.test_product_harness import (CONTRACT, ROOT, fixture_definition, make_bindings,
    reviewed_fixture_file, write_json)


def observations():
    return SecurityObservationBindings('sid', 'VERTICAL', 'alice', 'main', 'app', {
        'https': CookieDeploymentMode({'SESSION_COOKIE_SECURE': 'true'}, True),
        'http_local_explicit': CookieDeploymentMode({'SESSION_COOKIE_SECURE': 'false'}, False),
        'http_without_exception': CookieDeploymentMode({'SESSION_COOKIE_SECURE': 'true'}, False),
    }, ('.',))


@pytest.mark.parametrize('field,value', [('cookie_name',''),('actor','../x'),('app_module','main;exec'),
    ('artifact_roots',('../foreign',)),('artifact_roots',()),('modes',{})])
def test_security_binding_unknown_or_incomplete_is_not_a_default(field, value):
    with pytest.raises(ValueError): replace(observations(), **{field:value}).validate()


@pytest.mark.parametrize('environment', [{'PATH':'true'},{'ANTHROPIC_API_KEY':'dev'},
    {'DATABASE_URL':'prod'},{'PYTHONPATH':'dev'},{'SESSION_COOKIE_SECURE':True},{'SESSION_COOKIE_SECURE':'false;cmd'},{}])
def test_reviewed_mode_environment_cannot_be_credentials_or_process_injection(environment):
    with pytest.raises(ValueError): validate_security_environment(environment)


def test_scanner_is_complete_bounded_and_never_saves_raw_findings(tmp_path):
    secret='fictitious-known-probe-secret-only'
    scanner=BoundedSecretScanner({secret})
    scanner.scan(io.BytesIO(b'x'*65530+secret.encode()+b' end'), scope='logs', name='owned-log')
    value, proof=scanner.receipt(tmp_path, scopes=['logs','artifacts'], snapshot='a'*64,
        contract='c'*64, provenance={'scope':'independent metatest'})
    assert value['findings'] and proof.passed is False
    assert secret not in Path(proof.path).read_text()
    assert proof.intact(snapshot_hash='a'*64, contract_hash='c'*64)
    too_large=BoundedSecretScanner(set());too_large.MAX_BYTES=5
    with pytest.raises(AdapterUnavailable): too_large.scan(io.BytesIO(b'123456'),scope='logs',name='bounded')


def fictional_pem():
    # Deliberately nonfunctional public metatest material, not a credential or
    # TLS key. Complete PEM/base64/DER structure exercises conservative detection.
    integers=b''.join(b'\x02\x05'+bytes([number])*5 for number in range(9))
    der=b'\x30'+bytes([len(integers)])+integers
    return b'-----BEGIN RSA PRIVATE KEY-----\n'+base64.b64encode(der)+b'\n-----END RSA PRIVATE KEY-----\n'


def test_vendor_known_values_and_complete_pem_cannot_hide_behind_scope_rules():
    secret=b'fictitious-only-vendor-cache-canary'
    scanner=BoundedSecretScanner({secret.decode()})
    scanner.scan(io.BytesIO(secret+b'\n'+fictional_pem()),scope='image',name='layer:opt/vendor/cache/example.txt')
    assert {f['kind'] for f in scanner.findings}=={'known_probe_secret','private_key'}
    marker=BoundedSecretScanner(set())
    marker.scan(io.BytesIO(b'-----BEGIN RSA PRIVATE KEY-----'),scope='image',name='layer:usr/lib/format-marker.so')
    assert marker.findings==[]


@pytest.mark.parametrize('body_limit',[False,True])
@pytest.mark.parametrize('start',[65520,32767])
def test_full_pem_crosses_chunk_and_maximum_body_without_losing_begin(body_limit,start):
    if body_limit:
        # Public fictional DER-shaped material; no real key/credential. Exactly
        # 32768 base64 bytes plus both complete wrappers exceed old tail32768.
        pem=b'-----BEGIN RSA PRIVATE KEY-----\n'+base64.b64encode(b'\x30'+b'\x00'*24575)+b'\n-----END RSA PRIVATE KEY-----'
    else:pem=fictional_pem()
    scanner=BoundedSecretScanner(set())
    scanner.scan(io.BytesIO(b'x'*start+pem+b' end'),scope='image',name='layer:opt/vendor/cache/fixture.pem')
    assert any(f['kind']=='private_key' for f in scanner.findings)


def test_artifact_scan_rejects_alias_and_foreign_scope(tmp_path):
    root=tmp_path/'scope';root.mkdir();foreign=tmp_path/'foreign';foreign.write_text('not read')
    link=root/'alias'
    try: link.symlink_to(foreign)
    except OSError: pytest.skip('OS did not grant symlink creation')
    with pytest.raises(Exception): BoundedSecretScanner(set()).scan_tree(root,scope='artifacts')


async def test_security_observation_does_not_reuse_a_stale_external_scan(tmp_path):
    store=SupervisorEvidenceStore(tmp_path,'a'*64,'c'*64)
    class MissingNative: pass
    with pytest.raises(AdapterUnavailable): await EvidenceAdapter(MissingNative(),store).observe('secret_scan',scope='logs_artifacts')
    with pytest.raises(AdapterUnavailable): await EvidenceAdapter(MissingNative(),store).observe('cookie_modes')


REAL=pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_SECURITY_OBSERVATIONS')!='1',
    reason='opt-in owned native secret/TLS probes, not campaign generation')


@pytest.fixture(scope='module')
def native_source(tmp_path_factory):
    from autospec.orchestrator.validation_environment import LinuxEnvironmentManager
    from autospec.validation.final_gate import source_snapshot
    base=tmp_path_factory.mktemp('native-security');source=base/'source';source.mkdir()
    shutil.copyfile(Path(__file__).parent/'fixtures/security_native/main.py',source/'main.py')
    for name in ('pyproject.toml','uv.lock'): shutil.copyfile(ROOT/name,source/name)
    manager=LinuxEnvironmentManager(base/'cache',timeout=300)
    manager.ensure_lock(source,'python');manager.prepare(source,'python','runtime')
    return base,source,source_snapshot(source).digest


def context(native, root, *, bad=False):
    base,source,snapshot=native
    binding=make_bindings(root,source,snapshot)
    binding=replace(binding,security_observations=observations())
    binding=replace(binding,review=replace(binding.review,
        checks=('PRODUCT:bindings','PRODUCT:bindings:'+binding.fingerprint())))
    definition=fixture_definition()
    if bad: definition['commands']['seed']['payload']['bug']='insecure-production'
    fixtures=reviewed_fixture_file(root,source,snapshot,definition)
    async def source_hash():return snapshot
    async def contract_hash():return CONTRACT
    return OwnedProductHarnessSession(binding,source_root=source,stage_root=root/'stage',
        evidence_root=root/'evidence',cache_root=base/'cache',fixtures_path=fixtures,
        snapshot_hash=source_hash,contract_hash=contract_hash)


@REAL
@pytest.mark.parametrize('bad',[False,True])
async def test_real_cookie_headers_three_modes_tls_and_insecure_counterexample(native_source,tmp_path,bad):
    async with context(native_source,tmp_path,bad=bad) as h:
        await h.adapter.prepare_case('VERTICAL')
        rows,proofs=await h.collect_security_observation('cookie_modes')
        expected={'https':True,'http_local_explicit':False,'http_without_exception':True}
        assert {r['mode'] for r in rows}==set(expected)
        assert next(r for r in rows if r['mode']=='https')['tls_version'].startswith('TLS')
        assert all(r['image_id']==rows[0]['image_id'] for r in rows)
        assert len({r['container_id'] for r in rows})==3
        mismatches=[r['mode'] for r in rows if r['secure']!=expected[r['mode']]]
        assert bool(mismatches) is bad
        assert len(proofs)==3 and all(p.intact(snapshot_hash=native_source[2],contract_hash=CONTRACT) for p in proofs)
        for account in h.manifest.accounts.values():
            assert all(account.password not in Path(p.path).read_text() for p in proofs)


@REAL
async def test_real_dynamic_scan_sees_pre_tail_secret_and_refuses_overflow(native_source,tmp_path):
    async with context(native_source,tmp_path) as h:
        await h.adapter.prepare_case('VERTICAL')
        store=SupervisorEvidenceStore(tmp_path,native_source[2],CONTRACT)
        adapter=EvidenceAdapter(h.adapter,store)
        before=await adapter.observe('secret_scan',scope='logs_artifacts')
        assert before['findings']==[] and before['complete'] is True
        secret=h.manifest.accounts['alice'].password
        response=await h.adapter.request(None,'POST','/probe/negative',json={'password':secret})
        assert response.status_code==503
        after=await adapter.observe('secret_scan',scope='logs_artifacts')
        assert any(f['kind']=='known_probe_secret' and f['scope']=='logs' for f in after['findings'])
        assert any(f['kind']=='known_probe_secret' and f['scope']=='artifacts' for f in after['findings'])
        assert secret not in h.runtime.logs() # old tail100 cannot see it
        assert (await store.observe('secret_scan',scope='logs_artifacts'))['findings']==after['findings']
        with pytest.raises(Exception): await __import__('asyncio').to_thread(h.runtime.capture_security_logs,limit=10)
        for artifact in after['artifacts']: assert secret not in Path(artifact['path']).read_text()


@REAL
async def test_real_image_layer_scan_exact_digest_and_source_label(native_source,tmp_path):
    from autospec.orchestrator.isolated_validation import build_delivery_image
    base,source,snapshot=native_source
    ok,_=build_delivery_image(source,'autospec/security-observer-meta:'+snapshot[:12],
        evidence_root=tmp_path/'build',snapshot_hash=snapshot,runtime_command=['/opt/venv/bin/python','main.py'])
    assert ok
    image=json.loads((tmp_path/'build/delivery-build.json').read_text())['image_id']
    async with context(native_source,tmp_path/'harness') as h:
        await h.adapter.prepare_case('VERTICAL')
        value,proofs=await h.collect_security_observation('secret_scan',scope='source_image_logs',image_id=image)
        assert set(value['scopes'])=={'source','image','logs'}
        assert value['complete'] and proofs[0].intact(snapshot_hash=snapshot,contract_hash=CONTRACT)
        # Actual stock image contains full PEM vectors in GnuTLS. These are
        # unresolved observations, not a blanket "vendor" exclusion or PASS.
        assert value['findings'] and proofs[0].passed is False
        assert all(f['kind']=='private_key' and 'libgnutls.so.30.34.3' in f['file'] for f in value['findings'])
        assert any(item['scope']=='image' for item in json.loads(Path(proofs[0].path).read_text())['inventory'])
        with pytest.raises(Exception): await __import__('asyncio').to_thread(h.runtime.scan_security_image,image,'0'*64,lambda *a:pytest.fail('foreign image was scanned'))
        # Independent deliberately bad image derivative, never a delivery
        # qualification fixture. Factory-only COPY, no generated Dockerfile.
        from autospec.orchestrator.sandbox import _docker_call
        secret='fictitious-only-native-vendor-cache-canary'
        build=tmp_path/'negative-layer';build.mkdir()
        (build/'canary').write_bytes(secret.encode()+b'\n'+fictional_pem())
        identity=uuid4().hex
        (build/'Dockerfile').write_text('FROM '+image+'\nCOPY canary /opt/vendor/cache/native-canary\nLABEL autospec.security_metatest="'+identity+'"\n')
        result=_docker_call(['docker','build','--network=none','--pull=false','-q',str(build)],capture_output=True,text=True,timeout=30)
        assert result.returncode==0
        bad_image=result.stdout.strip().splitlines()[-1]
        try:
            h._security_secrets.add(secret)
            bad,proofs=await h.collect_security_observation('secret_scan',scope='source_image_logs',image_id=bad_image)
            assert proofs[0].passed is False
            assert {'known_probe_secret','private_key'} <= {f['kind'] for f in bad['findings'] if '/opt/vendor/cache/' in f['file'] or ':opt/vendor/cache/' in f['file']}
            assert secret not in Path(proofs[0].path).read_text()
        finally:
            removed=_docker_call(['docker','image','rm',bad_image],capture_output=True,text=True,timeout=15)
            assert removed.returncode==0
