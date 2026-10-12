"""Constant, supervisor-owned CSPRNG observation (never product self-attestation).

The bootstrap fragment must run before /app enters sys.path. Installation may
import only an explicitly source-reviewed symbol inside the isolated runtime.
No random return value or cookie is retained, only digests of lossless encodings.
This diagnostic instrumentation is not a hostile-process TEE.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from .support_adapter import AdapterUnavailable, Proof

ENTROPY_PRIMITIVES = frozenset({"secrets.token_urlsafe", "secrets.token_hex", "secrets.token_bytes", "os.urandom"})
ENTROPY_CHECK = "SEC-05:entropy"

# Capture before any generated module can shadow stdlib or replace a primitive.
ENTROPY_BOOTSTRAP = r'''
import base64 as _entropy_b64, hashlib as _entropy_hash, secrets as _entropy_secrets
_entropy_originals={'secrets.token_urlsafe':_entropy_secrets.token_urlsafe,
 'secrets.token_hex':_entropy_secrets.token_hex,'secrets.token_bytes':_entropy_secrets.token_bytes,'os.urandom':os.urandom}
_entropy_default=_entropy_secrets.DEFAULT_ENTROPY
_entropy_csprng_bytes=_entropy_secrets.token_bytes
_entropy_csprng_getrandbits=_entropy_secrets._sysrand.getrandbits
_entropy_csprng_randbytes=_entropy_secrets._sysrand.randbytes
_entropy_csprng_urandom=__import__('random')._urandom
_entropy_codes={_k:getattr(_v,'__code__',None) for _k,_v in _entropy_originals.items()}
'''

ENTROPY_INSTALL = r'''
if b.get('entropy_module'):
 _entropy_primitive=b['entropy_primitive']; _entropy_original=_entropy_originals[_entropy_primitive]
 _entropy_module=importlib.import_module(b['entropy_module'])
 if getattr(_entropy_module,b['entropy_attribute']) is not _entropy_original:
  raise RuntimeError('reviewed entropy symbol is not the captured stdlib CSPRNG')
 def _entropy_call(*args,**kw):
  # Never change the argument or replace authentication/RNG with a fixture.
  # Strict argument structure prevents bool/ambiguous metadata becoming bits.
  if len(args)>1 or set(kw)-{'nbytes'} or (args and 'nbytes' in kw):
   raise RuntimeError('entropy invocation argument cannot be attested')
  _n=args[0] if args else kw.get('nbytes')
  _default=_n is None and _entropy_primitive!='os.urandom'
  if _default: _n=_entropy_default
  if type(_n) is not int or _n<1 or _n>1048576:
   raise RuntimeError('entropy invocation requires an actual positive integer byte count')
  # Source can mutate secrets/random after import; reject rather than claiming
  # a cryptographic source from a function name alone. Check after call too.
  def _intact():
   return (_entropy_secrets._sysrand.getrandbits==_entropy_csprng_getrandbits and
    _entropy_secrets._sysrand.randbytes==_entropy_csprng_randbytes and
    __import__('random')._urandom is _entropy_csprng_urandom and
    (_entropy_primitive=='os.urandom' or os.urandom is _entropy_originals['os.urandom']) and
    _entropy_secrets.DEFAULT_ENTROPY==_entropy_default and type(_entropy_secrets.DEFAULT_ENTROPY) is int and
    all(getattr(_v,'__code__',None) is _entropy_codes[_k] for _k,_v in _entropy_originals.items()) and
    (_entropy_primitive=='secrets.token_bytes' or _entropy_secrets.token_bytes is _entropy_csprng_bytes))
  if not _intact(): raise RuntimeError('captured entropy dependency was replaced')
  _value=_entropy_original(*args,**kw)
  if not _intact(): raise RuntimeError('captured entropy dependency changed during invocation')
  if isinstance(_value,str): _encoded={'utf8':_value.encode('utf-8')}
  elif isinstance(_value,bytes):
   _encoded={'hex':_value.hex().encode('ascii'),'base64':_entropy_b64.b64encode(_value),
    'base64url':_entropy_b64.urlsafe_b64encode(_value),'base64url-nopad':_entropy_b64.urlsafe_b64encode(_value).rstrip(b'=')}
  else: raise RuntimeError('captured entropy return type cannot be correlated')
  _record={'generator':_entropy_primitive,'nbytes':_n,'default_argument':_default,
   'entropy_bits':8*_n,'cryptographic':True,
   'encoded_sha256':{_k:_entropy_hash.sha256(_v).hexdigest() for _k,_v in _encoded.items()}}
  with guard:
   if len(state['session_entropy'])>=4096: raise RuntimeError('bounded entropy observation journal full')
   state['session_entropy'].append(_record)
  return _value
 setattr(_entropy_module,b['entropy_attribute'],_entropy_call)
'''


def correlate_entropy(records, token_sha256):
    """Match the full observed cookie to a lossless original CSPRNG return."""
    if not isinstance(token_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", token_sha256):
        raise AdapterUnavailable("exact observed cookie SHA256 required")
    if not isinstance(records, list) or len(records) > 4096:
        raise AdapterUnavailable("native entropy journal unavailable")
    matches = []
    for record in records:
        if not isinstance(record, dict): raise AdapterUnavailable("native entropy record malformed")
        encodings = record.get("encoded_sha256")
        if not isinstance(encodings, dict): raise AdapterUnavailable("native entropy encoding record missing")
        matching = [name for name, digest in encodings.items() if digest == token_sha256]
        if not matching: continue
        count = record.get("nbytes")
        if (type(count) is not int or not 0 < count <= 1048576 or
                record.get("generator") not in ENTROPY_PRIMITIVES or
                record.get("cryptographic") is not True or
                type(record.get("entropy_bits")) is not int or record["entropy_bits"] != count * 8 or
                type(record.get("default_argument")) is not bool or
                any(name not in {"utf8", "hex", "base64", "base64url", "base64url-nopad"} for name in matching)):
            raise AdapterUnavailable("native entropy invocation inconsistent")
        matches.append({k: record[k] for k in ("generator", "nbytes", "default_argument", "entropy_bits", "cryptographic")} |
                       {"token_sha256": token_sha256, "encoding": sorted(matching)})
    if len(matches) != 1:
        raise AdapterUnavailable("cookie is not uniquely correlated with an intact CSPRNG return")
    return matches[0]


def entropy_execution_proof(root: Path, observation: dict, snapshot: str, contract: str) -> Proof:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ("session-entropy-" + uuid4().hex + ".json")
    path.write_bytes(json.dumps({"check": ENTROPY_CHECK, "snapshot_hash": snapshot,
        "contract_hash": contract, "observation": observation,
        "scope": "actual captured CSPRNG invocation; digest-only lossless-cookie correlation",
        "limits": ["diagnostic source-reviewed instrumentation, not a hostile-process TEE"]},
        sort_keys=True, ensure_ascii=True).encode("utf-8"))
    return Proof("X", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), snapshot, contract, ("SEC-05", ENTROPY_CHECK), True)


def validate_entropy_evidence(value, *, token_sha256, snapshot, contract):
    """Require the intact exact native payload and a dedicated independent R."""
    if not isinstance(value, dict) or value.get("token_sha256") != token_sha256:
        raise AdapterUnavailable("entropy observation not bound to this cookie")
    if (value.get("generator") not in ENTROPY_PRIMITIVES or value.get("cryptographic") is not True or
            type(value.get("nbytes")) is not int or type(value.get("entropy_bits")) is not int or
            not 0 < value["nbytes"] <= 1048576 or value["entropy_bits"] != value["nbytes"] * 8 or
            type(value.get("default_argument")) is not bool or not isinstance(value.get("encoding"), list) or
            not value["encoding"] or any(x not in {"utf8", "hex", "base64", "base64url", "base64url-nopad"} for x in value["encoding"])):
        raise AdapterUnavailable("entropy must come from a canonical native invocation")
    proofs = []
    for raw in value.get("proofs", []):
        proof = raw if isinstance(raw, Proof) else Proof(**raw)
        if (proof.type not in {"X", "R"} or proof.passed is not True or ENTROPY_CHECK not in proof.checks or
                not proof.intact(snapshot_hash=snapshot, contract_hash=contract)):
            raise AdapterUnavailable("exact intact dedicated entropy proof required")
        if proof.type == "X":
            payload = json.loads(Path(proof.path).read_text(encoding="utf-8"))
            if (payload.get("check") != ENTROPY_CHECK or payload.get("snapshot_hash") != snapshot or
                    payload.get("contract_hash") != contract or payload.get("observation") != {k: v for k, v in value.items() if k != "proofs"}):
                raise AdapterUnavailable("native entropy proof payload does not match this observation")
        proofs.append(proof)
    if {p.type for p in proofs} != {"X", "R"}:
        raise AdapterUnavailable("CSPRNG propagation needs runtime X and dedicated source R")
    return proofs
