"""Real CSPRNG argument/digest observations, never token-length heuristics."""
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from autospec.validation.entropy_protocol import (ENTROPY_BOOTSTRAP, ENTROPY_INSTALL,
    correlate_entropy, entropy_execution_proof, validate_entropy_evidence)
from autospec.validation.product_harness import (InstrumentationBinding, ProductHarness,
    OwnedProductHarnessSession, instrumented_command, TRUSTED_ASGI_LAUNCHER)
from autospec.validation.security_contracts import SecurityVerifier
from autospec.validation.support_adapter import AdapterUnavailable, Proof
from tests.fixtures.security.app import SecurityApplication, security_contract
from tests.test_product_harness import (CONTRACT, make_bindings, reviewed_fixture_file,
    write_json, linux_fixture_source)


def actual_primitive(primitive, invocation="(32)", *, replace_symbol=False, dependency_replacement=False):
    # Only constant supervisor fixture code runs in this isolated Python child.
    module, attribute = primitive.rsplit(".", 1)
    setup = "import secrets; secrets.token_urlsafe=lambda n: 'f'*43" if replace_symbol else ""
    script = "import os,json,threading,importlib\n" + ENTROPY_BOOTSTRAP + "\n" + setup + "\n"
    script += "b=" + repr(dict(entropy_module=module, entropy_attribute=attribute, entropy_primitive=primitive)) + "\n"
    script += "guard=threading.RLock();state={'session_entropy':[]}\n" + ENTROPY_INSTALL + "\n"
    if dependency_replacement: script += "_entropy_secrets._sysrand.getrandbits=lambda n: 0\n"
    script += f"value=getattr(importlib.import_module({module!r}),{attribute!r}){invocation}\n"
    script += "print(json.dumps({'journal':state['session_entropy'],'value':value if isinstance(value,str) else value.hex()}))\n"
    return subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("primitive", ["secrets.token_urlsafe", "secrets.token_hex", "secrets.token_bytes", "os.urandom"])
def test_actual_csprng_preserves_return_and_canonical_runtime_byte_argument(primitive):
    result=actual_primitive(primitive)
    assert result.returncode==0,result.stderr
    data=json.loads(result.stdout)
    cookie_hash=hashlib.sha256(data["value"].encode("utf-8")).hexdigest()
    observation=correlate_entropy(data["journal"],cookie_hash)
    assert observation["entropy_bits"]==256 and observation["nbytes"]==32
    assert observation["cryptographic"] is True and observation["default_argument"] is False
    assert observation["encoding"]==(["hex"] if primitive in {"os.urandom","secrets.token_bytes"} else ["utf8"])


def test_default_count_is_captured_from_trusted_stdlib_not_token_shape():
    result=actual_primitive("secrets.token_urlsafe","()")
    assert result.returncode==0,result.stderr
    data=json.loads(result.stdout); record=data["journal"][0]
    import secrets
    assert record["nbytes"]==secrets.DEFAULT_ENTROPY and record["default_argument"] is True


@pytest.mark.parametrize("invocation", ["(True)", "(0)", "(32,nbytes=16)", "(nbytes='32')"])
def test_noncanonical_arguments_cannot_attest_entropy(invocation):
    result=actual_primitive("secrets.token_urlsafe",invocation)
    assert result.returncode!=0 and "cannot be attested" in result.stderr or result.returncode!=0 and "integer" in result.stderr


@pytest.mark.parametrize("dependency", [False,True])
def test_symbol_or_rng_dependency_replacement_is_refused_not_self_attested(dependency):
    result=actual_primitive("secrets.token_urlsafe",replace_symbol=not dependency,dependency_replacement=dependency)
    assert result.returncode!=0 and ("captured stdlib CSPRNG" in result.stderr or "dependency was replaced" in result.stderr)


def test_truncated_cookie_and_duplicate_native_records_are_not_qualifiable():
    data=json.loads(actual_primitive("secrets.token_urlsafe").stdout)
    with pytest.raises(AdapterUnavailable,match="correlated"):
        correlate_entropy(data["journal"],hashlib.sha256(data["value"][:10].encode()).hexdigest())
    with pytest.raises(AdapterUnavailable,match="uniquely"):
        correlate_entropy(data["journal"]*2,hashlib.sha256(data["value"].encode()).hexdigest())


@pytest.mark.parametrize("extras", [dict(entropy_module="secrets"),dict(entropy_primitive="secrets.token_urlsafe"),
    dict(entropy_module="main",entropy_attribute="rng",entropy_primitive="main.self_attested")])
def test_entropy_binding_is_an_explicit_complete_allowlisted_source_symbol(extras):
    with pytest.raises(ValueError): InstrumentationBinding("main","app",**extras).validate()


def test_launcher_captures_before_product_path_and_instruments_before_app():
    command=instrumented_command(InstrumentationBinding("main","app",entropy_module="secrets",
        entropy_attribute="token_urlsafe",entropy_primitive="secrets.token_urlsafe"))
    import base64,zlib
    assert all(len(arg)<=4096 for arg in command)
    script=zlib.decompress(base64.b64decode(''.join(command[5:-1]))).decode("utf-8")
    assert script==TRUSTED_ASGI_LAUNCHER
    assert script.index("_entropy_originals=")<script.index("sys.path.insert(0,'/app')")<script.index("if b.get('entropy_module')")
    assert script.index("setattr(_entropy_module")<script.index("app=getattr(")
    compile(script,"supervisor-launcher","exec")


async def entropy_family(tmp_path,bug="",reviews=True,provider=None):
    contract=security_contract();app=SecurityApplication(tmp_path/"product",broken=bug,only="SEC-05")
    adapter,snapshot,_=app.adapter(contract,reviews=reviews)
    if provider: adapter._ports["observe"]=provider(adapter._ports["observe"])
    rows=await SecurityVerifier(contract,adapter).verify(snapshot)
    return next(row for row in rows if row["id"]=="SEC-05")


@pytest.mark.parametrize("bug,status", [("","PASS"),("entropy_small","FAIL"),("entropy_missing","NOT_VERIFIED"),
    ("entropy_truncated","NOT_VERIFIED"),("entropy_forged","NOT_VERIFIED")])
async def test_actual_argon2_http_cookie_sqlite_entropy_family_good_and_counterexamples(tmp_path,bug,status):
    row=await entropy_family(tmp_path,bug)
    assert row["status"]==status,row
    assert not any("minimum_bits_shape" in check["check"] for check in row["observed"])
    if bug=="entropy_small":
        assert any(check["check"]=="session_minimum_entropy_bits" and not check["passed"] for check in row["observed"])


async def test_generic_source_review_cannot_replace_dedicated_entropy_propagation_review(tmp_path):
    def remove_scope(original):
        async def observe(name,**params):
            value=await original(name,**params)
            if name=="session_entropy":
                for proof in value["proofs"]:
                    if proof["type"]=="R": proof["checks"]=["SEC-05","PRODUCT:bindings"]
            return value
        return observe
    assert (await entropy_family(tmp_path,provider=remove_scope))["status"]=="NOT_VERIFIED"


async def test_declarative_cryptographic_boolean_without_native_x_is_not_a_pass(tmp_path):
    def remove_x(original):
        async def observe(name,**params):
            value=await original(name,**params)
            if name=="session_entropy": value["proofs"]=[p for p in value["proofs"] if p["type"]!="X"]
            return value
        return observe
    assert (await entropy_family(tmp_path,provider=remove_x))["status"]=="NOT_VERIFIED"


def test_entropy_payload_must_match_its_exact_intact_native_artifact(tmp_path):
    data=json.loads(actual_primitive("secrets.token_urlsafe").stdout)
    token_hash=hashlib.sha256(data["value"].encode()).hexdigest()
    value=correlate_entropy(data["journal"],token_hash)
    native=entropy_execution_proof(tmp_path,value,"a"*64,"b"*64)
    review_path=tmp_path/"review.json";review_path.write_text("source and propagation reviewed",encoding="utf-8")
    review=Proof("R",str(review_path),hashlib.sha256(review_path.read_bytes()).hexdigest(),"a"*64,"b"*64,("SEC-05:entropy",))
    actual={**value,"proofs":[native,review]}
    assert validate_entropy_evidence(actual,token_sha256=token_hash,snapshot="a"*64,contract="b"*64)
    actual["nbytes"]=64;actual["entropy_bits"]=512
    with pytest.raises(AdapterUnavailable,match="payload"):
        validate_entropy_evidence(actual,token_sha256=token_hash,snapshot="a"*64,contract="b"*64)


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_PRODUCT_HARNESS")!="1",reason="opt-in owned Linux real auth entropy proof")
@pytest.mark.parametrize("nbytes", [32,16])
async def test_real_owned_linux_csprng_argument_and_actual_http_cookie(linux_fixture_source,tmp_path,nbytes):
    from autospec.validation.final_gate import source_snapshot
    import shutil
    base,original,_=linux_fixture_source
    source=tmp_path/"source";source.mkdir()
    for name in ("main.py","pyproject.toml","uv.lock"):shutil.copyfile(original/name,source/name)
    # Supervisor-owned fixture variant only, never mutate a benchmark snapshot.
    path=source/"main.py"
    path.write_bytes(path.read_bytes().replace(b"secrets.token_urlsafe(32)",f"secrets.token_urlsafe({nbytes})".encode()))
    snapshot=source_snapshot(source).digest
    binding=make_bindings(tmp_path,source,snapshot)
    hook=replace(binding.instrumentation,entropy_module="secrets",entropy_attribute="token_urlsafe",entropy_primitive="secrets.token_urlsafe")
    binding=replace(binding,instrumentation=hook)
    binding=replace(binding,review=replace(binding.review,checks=("PRODUCT:bindings","PRODUCT:bindings:"+binding.fingerprint())))
    profile=tmp_path/"bindings.json";write_json(profile,asdict(binding))
    fixtures=reviewed_fixture_file(tmp_path,source,snapshot)
    review_path=tmp_path/"entropy-review.json"
    write_json(review_path,dict(scope="independent supervisor fixture source review",symbol="main.login",
        generator="secrets.token_urlsafe",nbytes=nbytes,propagation="unmodified token variable set as session cookie",
        source_files=binding.source_files))
    proof=Proof("R",str(review_path),hashlib.sha256(review_path.read_bytes()).hexdigest(),snapshot,CONTRACT,("SEC-05:entropy",))
    async def source_review(rid):return [proof] if rid=="SEC-05" else []
    async def identity():return source_snapshot(source).digest
    async def oracle():return CONTRACT
    owner=OwnedProductHarnessSession.from_bindings(profile,source_root=source,stage_root=tmp_path/"stage",
        evidence_root=tmp_path/"evidence",cache_root=base/"cache",fixtures_path=fixtures,
        snapshot_hash=identity,contract_hash=oracle,proof_provider=source_review,instrumented=True)
    async with owner as h:
        await h.adapter.prepare_case("INSTRUMENTED")
        login=await h.adapter.login("alice");assert login.status_code==200
        token=login.cookies.get("sid");assert token
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        result=await h.adapter.observe("session_entropy",token_sha256=token_hash)
        assert result["nbytes"]==nbytes and result["entropy_bits"]==nbytes*8
        assert validate_entropy_evidence(result,token_sha256=token_hash,snapshot=snapshot,contract=CONTRACT)
        assert h.runtime.identifier
        assert token not in json.dumps(result)
        assert source_snapshot(source).digest==snapshot
        selected=os.environ.get("AUTOSPEC_ENTROPY_EVIDENCE_ROOT")
        if selected:
            target=Path(selected).resolve()/str(nbytes);target.mkdir(parents=True,exist_ok=True)
            retained=json.loads(json.dumps(result))
            for item in retained["proofs"]:
                original=Path(item["path"])
                assert original.resolve().is_relative_to(tmp_path.resolve()) and original.suffix==".json"
                destination=target/original.name;shutil.copyfile(original,destination)
                item["path"]=str(destination)
                assert hashlib.sha256(destination.read_bytes()).hexdigest()==item["sha256"]
            write_json(target/"native-observation.json",dict(scope="owned fixture meta-test, not campaign acceptance",
                snapshot_hash=snapshot,contract_hash=CONTRACT,observation=retained,
                nominal_http_status=login.status_code,runtime=h.runtime.inspect_configuration(),
                entropy_sufficient=nbytes*8>=256,source_unchanged=True))
