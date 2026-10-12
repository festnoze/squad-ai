"""Exact, independently source-reviewed public self-test material, not a waiver.

Only one byte-identical vendor binary and the listed public PEM hashes qualify.
Application copies, changed binaries, extra candidates and known probe secrets
remain findings. This neither attests supply-chain integrity nor issues product R.
The factory engine/protocol hash covers this entire classification policy.
"""
from __future__ import annotations


LIBRARY_PATH = "usr/lib/x86_64-linux-gnu/libgnutls.so.30.34.3"
LIBRARY_SHA256 = "750be5c0ce95061563e1561019e382823eb1e011ffe7980e9e005eeafd82efa3"
SOURCE_URL = "https://raw.githubusercontent.com/gnutls/gnutls/ca61668d7764fc29fb4cc2aa396cb035e176636d/lib/crypto-selftests-pk.c"
SOURCE_SHA256 = "c3d79122e072177f55dc30a98f68b949c0f36f6159a363aae9512a22a9280ed0"
PUBLIC_PEM_SYMBOLS = {
    "d039c8119a029ab9f9c83c04d67002d887b6bc6026c4264402ab27cdf24cf138": "rsa_2048_privkey",
    "7c4c63ee462e0e700cd9e29c8e0f730b3f1b484c4abdd83f1e69fcd477c061fa": "dsa_2048_privkey",
    "91ea1699ff6b1a34b4a1d500a9c75a808441e47b9ea68da6fb0195e01ce1dc61": "ecdsa_secp256r1_privkey",
    "934b3e9bfd9936c5e30c7f0ed7d36a05e2044f755c0aa433e1d6bef6a68d1391": "ecdsa_secp192r1_privkey",
    "a0b9679665e29ac220dfb0b366317e1b9dd5fe31e9def8b2e511669a041389ae": "ecdsa_secp224r1_privkey",
    "293216817f0d585f0b54f225582f59e7b2e2a795b5f8002e2d71c5e3d49ce9b0": "ecdsa_secp384r1_privkey",
    "f8766749b0c6f9b5661364568226af0ba7ae8d87c0073df24e440de4417521cd": "ecdsa_secp521r1_privkey",
    "ef237ea8db4f2ae9ee100e8ced96d29b5dceb0e6a948443e6b8a00b1791f9ec9": "gost01_privkey",
    "fa0b06a72461ec0a963dcfccb8d5b61bd88a6074fc7271573bff68ab86b8c1af": "gost12_256_privkey",
    "a4d138d7ef9748464117b44fb9c0a4b5b85a1599a127d02690abaa96d03c16e6": "gost12_512_privkey",
}


def classify_public_vendor_material(finding, *, file_sha256):
    """Return a retained classification only for exact current measured bytes."""
    if (finding.get("scope") != "image" or finding.get("kind") != "private_key" or
            file_sha256 != LIBRARY_SHA256 or
            finding.get("file", "").partition(":")[2] != LIBRARY_PATH):
        return None
    symbol = PUBLIC_PEM_SYMBOLS.get(finding.get("value_sha256"))
    if symbol is None:
        return None
    return {**finding, "classification": "PUBLIC_NON_CREDENTIAL_SELF_TEST",
        "file_sha256": file_sha256, "source_url": SOURCE_URL, "source_sha256": SOURCE_SHA256,
        "source_symbol": symbol, "independent_review": "REM-15/20261012-public-vendor-material/REVIEW.md",
        "limits": "public material identity only; no application credential or full binary provenance approval"}
