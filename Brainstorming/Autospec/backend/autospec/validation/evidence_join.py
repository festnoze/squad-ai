"""Join current native and browser receipts, never turn a partial report green."""
from dataclasses import replace

from .support_adapter import AdapterUnavailable, Proof


CROSSED_IDS = frozenset({"SEC-10", "SEC-12", "FUN-02", "FUN-06", "FUN-12"})


async def publish_backend_receipt(store, row):
    """Tag an actual complete native artifact, not its overall acceptance status.

    The verifier emitted ``native_complete`` before considering supplemental
    evidence. We additionally bind the retained bytes to its observed checks.
    A complete observed failure remains a failed X; no R is minted here.
    """
    rid = row["id"]
    if rid not in CROSSED_IDS or row.get("native_complete") is not True:
        return False
    observed = row.get("observed")
    if not isinstance(observed, list) or not observed:
        return False
    matched = []
    for value in row.get("proofs", []):
        proof = Proof(**value)
        if proof.type != "X":
            continue
        checked = store._proof(value, rid)
        data = store._read(checked.path)
        if ((data.get("snapshot_hash"), data.get("contract_hash")) != (store.snapshot, store.contract)
                or (data.get("id", data.get("requirement_id")) != rid)):
            continue
        checks = data.get("checks", data.get("observed"))
        if checks != observed:
            continue
        actual_passed = all(check.get("passed") is True for check in observed)
        if checked.passed != actual_passed:
            raise AdapterUnavailable("native backend result differs from retained actual checks")
        matched.append(checked)
    if not matched:
        return False
    for proof in matched:
        await store.publish_native_proof(rid, replace(proof, checks=(rid + ":backend",) + proof.checks))
    return True


async def publish_browser_receipts(store, rows):
    """Publish measured X/V even when R/backend prerequisites are still pending."""
    for row in rows:
        rid = row["id"]
        for value in row.get("proofs", []):
            proof = Proof(**value)
            if proof.type in {"X", "V"}:
                await store.publish_native_proof(rid, proof)


def join_rechecked_native(previous, current, browser=None):
    """Only a fresh native replay can consume newly collected UI checks/types.

    Original native FAIL or missing native execution is never erased. A
    browser PASS alone cannot promote NV. Current native execution is mandatory.
    """
    from .coordinator import _merge
    identity = (previous["id"], previous.get("snapshot_hash"), previous.get("contract_hash"))
    if (not all(identity) or identity != (current["id"], current.get("snapshot_hash"), current.get("contract_hash"))
            or (browser is not None and identity != (browser["id"], browser.get("snapshot_hash"), browser.get("contract_hash")))):
        raise AdapterUnavailable("cross-layer requirement/snapshot/oracle identity differs")
    if previous.get("status") == "FAIL" or previous.get("native_complete") is not True:
        result = {**previous, "proofs": list(previous.get("proofs", [])),
                  "observed": list(previous.get("observed", [])), "limits": list(previous.get("limits", []))}
        _merge(result, current)
        if result["status"] != "FAIL":
            result["status"] = "NOT_VERIFIED"
    else:
        result = {**current, "proofs": list(current.get("proofs", [])),
                  "observed": list(current.get("observed", [])), "limits": list(current.get("limits", []))}
        result["prior_native_observation"] = {"status": previous["status"],
                                              "limits": list(previous.get("limits", []))}
        result["proofs"].extend(previous.get("proofs", []))
        if current.get("native_complete") is not True and result["status"] != "FAIL":
            result["status"] = "NOT_VERIFIED"
            result["limits"].append("fresh native cross-layer execution incomplete")
    if browser is not None:
        _merge(result, browser)
    unique = {}
    for proof in result["proofs"]:
        key = (proof.get("type"), proof.get("path"), proof.get("sha256"), tuple(proof.get("checks", ())))
        unique.setdefault(key, proof)
    result["proofs"] = list(unique.values())
    return result
