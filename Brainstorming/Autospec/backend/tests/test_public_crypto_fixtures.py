"""Classifier scope tests; never proof that a generated image is secret-free."""
import pytest

from autospec.validation.public_crypto_fixtures import (LIBRARY_PATH, LIBRARY_SHA256,
    PUBLIC_PEM_SYMBOLS, SOURCE_SHA256, classify_public_vendor_material)


def finding(digest):
    return dict(scope="image", file="exact-layer-sha256:" + LIBRARY_PATH,
                kind="private_key", value_sha256=digest)


@pytest.mark.parametrize("digest,symbol", PUBLIC_PEM_SYMBOLS.items())
def test_only_exact_independently_reviewed_public_material_is_classified(digest, symbol):
    assert len(digest) == 64
    result = classify_public_vendor_material(finding(digest), file_sha256=LIBRARY_SHA256)
    assert result["classification"] == "PUBLIC_NON_CREDENTIAL_SELF_TEST"
    assert result["source_symbol"] == symbol
    assert result["source_sha256"] == SOURCE_SHA256
    assert "no application credential" in result["limits"]


@pytest.mark.parametrize("field,value", [
    ("scope", "source"), ("scope", "logs"), ("scope", "artifacts"),
    ("kind", "known_probe_secret"), ("kind", "credential_assignment"),
    ("file", "layer:app/libgnutls.so.30.34.3"),
    ("file", "layer:usr/lib/../lib/x86_64-linux-gnu/libgnutls.so.30.34.3"),
    ("file", "layer:" + LIBRARY_PATH + "/extra"),
    ("file", "unqualified:" + LIBRARY_PATH.upper()),
    ("value_sha256", "f" * 64)])
def test_other_surface_candidate_path_or_known_secret_remains_finding(field, value):
    candidate = finding(next(iter(PUBLIC_PEM_SYMBOLS)))
    candidate[field] = value
    assert classify_public_vendor_material(candidate, file_sha256=LIBRARY_SHA256) is None


def test_changed_vendor_binary_cannot_inherit_public_material_classification():
    assert classify_public_vendor_material(finding(next(iter(PUBLIC_PEM_SYMBOLS))),
                                          file_sha256="f" * 64) is None


@pytest.mark.parametrize("fault,expected", [(None,True), ("hash",False),
    ("missing",False), ("ambiguous",False), ("application",False), ("known_secret",False)])
def test_scanner_receipt_retains_candidates_and_only_measured_exact_classification(tmp_path, fault, expected):
    from autospec.validation.security_observations import BoundedSecretScanner
    candidate = finding(next(iter(PUBLIC_PEM_SYMBOLS)))
    if fault == "application": candidate["file"] = "layer:app/copied-public-key.pem"
    if fault == "known_secret": candidate["kind"] = "known_probe_secret"
    scanner = BoundedSecretScanner(set())
    scanner.findings = [candidate]  # Typed receipt metatest; not a real scan.
    item = dict(scope=candidate["scope"],file=candidate["file"],
                sha256="f"*64 if fault == "hash" else LIBRARY_SHA256)
    scanner.inventory = [] if fault == "missing" else [item]
    if fault == "ambiguous": scanner.inventory.append(dict(item))
    value, proof = scanner.receipt(tmp_path, scopes=["source","image","logs"],
        snapshot="a"*64,contract="b"*64,provenance={"scope":"typed supervisor receipt metatest only"})
    assert proof.passed is expected
    assert value["detector_candidates"] == [candidate]
    assert len(value["public_non_credentials"]) == int(expected)
    assert len(value["findings"]) == int(not expected)
    assert proof.intact(snapshot_hash="a"*64,contract_hash="b"*64)
