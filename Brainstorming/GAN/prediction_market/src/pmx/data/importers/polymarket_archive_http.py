"""Public, TLS-verified acquisition for the pinned Polymarket research archive."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

REPOSITORY = "TimeSeventeen/Polymarket-v1"
REVISION = "5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa"
DEFAULT_RPC = "https://polygon.drpc.org"


def atomic_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".tmp")
    partial.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def create_inventory(archive_dir: Path) -> dict[str, Any]:
    """Record immutable names, LFS SHA-256 and sizes before downloading any large file."""
    from huggingface_hub import HfApi
    from huggingface_hub.hf_api import RepoFile

    files: list[dict[str, Any]] = []
    for entry in HfApi().list_repo_tree(REPOSITORY, repo_type="dataset", revision=REVISION, recursive=True):
        if not isinstance(entry, RepoFile):
            continue
        path = entry.path
        if not (path.startswith("daily_aligned/") and path.endswith(".parquet")) and path not in (
            "CTF/preparations.parquet",
            "CTF/resolutions.parquet",
            "README.md",
        ):
            continue
        lfs = getattr(entry, "lfs", None)
        digest = lfs.sha256 if lfs is not None else None
        files.append(
            {"path": path, "bytes": entry.size, "sha256": digest, "git_blob_id": entry.blob_id, "status": "pending"}
        )
    if not files or not all(
        any(row["path"] == path for row in files)
        for path in (
            "CTF/preparations.parquet",
            "CTF/resolutions.parquet",
        )
    ):
        raise ValueError("Pinned inventory is missing required CTF files")
    result = {
        "schema": "pmx.archive-download.v1",
        "repository": REPOSITORY,
        "revision": REVISION,
        "license": "CC-BY-4.0",
        "attribution": "Boka Qin and Rui Yang, Polymarket-v1 Database (2026)",
        "files": sorted(files, key=lambda row: str(row["path"])),
        "total_bytes": sum(int(row["bytes"]) for row in files),
    }
    atomic_json(archive_dir / "download-manifest.json", result)
    return result


def verify_entry(path: Path, entry: dict[str, Any]) -> bool:
    if not path.is_file() or path.stat().st_size != entry["bytes"]:
        return False
    if entry.get("sha256"):
        return bool(sha256_file(path) == entry["sha256"])
    # README is a Git blob, not an LFS object: verify the published Git object id.
    content = path.read_bytes()
    return bool(
        hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() == entry["git_blob_id"]
    )


def archive_path(archive_dir: Path, name: str) -> Path:
    path = (archive_dir / name).resolve()
    if Path(name).is_absolute() or ".." in Path(name).parts or not path.is_relative_to(archive_dir.resolve()):
        raise ValueError(f"Unsafe archive path: {name!r}")
    return path


def download_archive(
    archive_dir: Path,
    *,
    progress: Callable[[str], None] = print,
    max_workers: int = 6,
    start_date: str | None = None,
    end_date: str | None = None,
    skip_ctf: bool = False,
) -> dict[str, Any]:
    """Hugging Face resumes its incomplete objects; only verified files enter the final archive."""
    from huggingface_hub import hf_hub_download

    manifest_path = archive_dir / "download-manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else create_inventory(archive_dir)
    )
    if manifest["repository"] != REPOSITORY or manifest["revision"] != REVISION:
        raise ValueError("Download manifest is not the pinned research source")
    if (start_date is None) != (end_date is None):
        raise ValueError("Both start_date and end_date are required for bounded acquisition")
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC) if start_date else None
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=UTC) if end_date else None
    if start is not None and end is not None and start >= end:
        raise ValueError("Bounded acquisition end must follow start")

    def requested(entry: dict[str, Any]) -> bool:
        if entry["path"].startswith("CTF/"):
            return not skip_ctf
        if start is not None and end is not None and entry["path"].startswith("daily_aligned/"):
            day = datetime.strptime(Path(entry["path"]).stem, "%Y_%m_%d").replace(tzinfo=UTC)
            return start - timedelta(days=1) <= day <= end + timedelta(days=1)
        return True

    queue = [(index, entry) for index, entry in enumerate(manifest["files"]) if requested(entry)]
    progress(
        f"Requested {len(queue)} pinned files, {sum(entry['bytes'] for _, entry in queue):,} bytes; "
        "verified files are reused"
    )
    lock = Lock()

    def download_one(index: int, entry: dict[str, Any]) -> None:
        destination = archive_path(archive_dir, entry["path"])
        if verify_entry(destination, entry):
            entry["status"] = "verified"
            return
        progress(f"[{index + 1}/{len(manifest['files'])}] {entry['path']} ({entry['bytes']} bytes)")
        # Separate staging prevents unverified files being mistaken for complete source files.
        staged = Path(
            hf_hub_download(
                REPOSITORY, entry["path"], repo_type="dataset", revision=REVISION, local_dir=archive_dir / ".staging"
            )
        )
        if not verify_entry(staged, entry):
            with lock:
                entry["status"] = "verification_failed"
                atomic_json(manifest_path, manifest)
            raise ValueError(f"Published checksum/size mismatch: {entry['path']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(destination)
        digest = sha256_file(destination)
        with lock:
            entry["status"] = "verified"
            entry["verified_sha256"] = digest
            atomic_json(manifest_path, manifest)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(download_one, index, entry) for index, entry in queue]
        try:
            for future in as_completed(futures):
                future.result()
        except Exception:
            for future in futures:
                future.cancel()
            raise
    atomic_json(manifest_path, manifest)
    return manifest


class BlockTimestampResolver:
    """Persist complete public block responses; never estimate resolution times from nearby blocks."""

    def __init__(self, cache_dir: Path, rpc_url: str = DEFAULT_RPC):
        if not rpc_url.startswith("https://"):
            raise ValueError("Polygon RPC must use verified HTTPS")
        self.cache_dir, self.rpc_url = cache_dir, rpc_url
        self._client = httpx.Client(timeout=40, follow_redirects=True)
        self._chain_verified = False
        self._chain_lock = Lock()

    def __call__(self, block_number: int) -> dict[str, Any]:
        path = self.cache_dir / f"137_{block_number}.json"
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8"))
        else:
            client = self._client
            with self._chain_lock:
                if not self._chain_verified:
                    self._verify_chain(client)
                    self._chain_verified = True
            response = client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "eth_getBlockByNumber",
                    "params": [hex(block_number), False],
                },
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body.get("result"), dict):
                raise ValueError(f"No timestamp available for Polygon block {block_number}: {body}")
            block = body["result"]
            result = {
                "chain_id": 137,
                "block_number": block_number,
                "timestamp_ms": int(block["timestamp"], 16) * 1000,
                "block_hash": block["hash"],
                "source_url": self.rpc_url,
                "rpc_response": body,
            }
        block = result["rpc_response"]["result"]
        if (
            result["chain_id"] != 137
            or int(block["number"], 16) != block_number
            or result["block_number"] != block_number
            or result["timestamp_ms"] != int(block["timestamp"], 16) * 1000
            or result["block_hash"] != block["hash"]
        ):
            raise ValueError(f"Invalid cached Polygon timestamp evidence: {block_number}")
        atomic_json(path, result)
        return dict(result)

    def _verify_chain(self, client: httpx.Client) -> None:
        chain = client.post(self.rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
        chain.raise_for_status()
        if chain.json().get("result") != "0x89":
            raise ValueError("Public RPC did not confirm Polygon chain 137")


def validate_range_response(response: httpx.Response, *, start: int, end: int, total: int) -> None:
    expected = f"bytes {start}-{end}/{total}"
    if response.status_code != 206 or response.headers.get("content-range") != expected:
        raise ValueError(f"Unexpected Content-Range, wanted {expected}")
    if len(response.content) != end - start + 1:
        raise ValueError("Truncated range response")
    if not response.headers.get("etag"):
        raise ValueError("Range response has no immutable-object ETag")


def cached_range(
    archive_path_name: str, *, start: int, end: int, total: int, cache_dir: Path, client: httpx.Client | None = None
) -> tuple[Path, dict[str, Any]]:
    """Verified HTTPS ranges are explicitly distinct from whole-object SHA-256 verification."""
    url = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{archive_path_name}"
    target = cache_dir / f"{start}-{end}.bin"
    receipt = target.with_suffix(".json")
    if target.exists() and receipt.exists():
        meta = json.loads(receipt.read_text(encoding="utf-8"))
        if (
            meta.get("url") == url
            and meta.get("content_range") == f"bytes {start}-{end}/{total}"
            and meta.get("revision") == REVISION
            and meta.get("status") == 206
            and isinstance(meta.get("etag"), str)
            and bool(meta["etag"])
            and meta.get("bytes") == end - start + 1
            and target.stat().st_size == end - start + 1
            and sha256_file(target) == meta.get("sha256")
        ):
            return target, meta
        raise ValueError("Cached range failed its retained receipt/hash")
    owned = client is None
    transport = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        response = transport.get(url, headers={"Range": f"bytes={start}-{end}"})
        response.raise_for_status()
        validate_range_response(response, start=start, end=end, total=total)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".partial")
        temporary.write_bytes(response.content)
        temporary.replace(target)
        meta = {
            "url": url,
            "revision": REVISION,
            "status": response.status_code,
            "content_range": response.headers["content-range"],
            "etag": response.headers["etag"],
            "bytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "verification": (
                "TLS verified pinned revision + exact range and retained fragment hash; not full LFS hash"
            ),
        }
        atomic_json(receipt, meta)
        return target, meta
    finally:
        if owned:
            transport.close()
