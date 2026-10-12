# Owned NETNONE publication — checkpoint

Scope: trusted factory registry/HTTP relay, not a new acceptance authority.
No paid provider/model call was made.

## Results

- First Linux factory-only replay: 41 PASS / 1 FAIL / 4 excluded in 14.89 s. The failure was an old test's AF_UNIX `socketpair` assumption (Windows uses TCP); the fixture now explicitly models a kernel IPv4 peer. Its JUnit lived on container tmpfs and disappeared at exit; no receipt is fabricated.
- Human explicitly authorized local supervisor/mocks and owned Docker probes after two host pytest requests were denied. No refused command was routed through another agent or disguised host execution.
- Native/compatibility replay: **46 PASS, 77.40 s**, `20261012-publication-native-v1.xml`.
- Strengthened replay: **17 PASS, 80.04 s**, `20261012-publication-native-v2.xml`. Includes real Windows owned-Job factory-process death, then fresh-registry recovery of the SAME immutable container ID, port/origin and SQLite volume.
- Raw Docker configuration and initial/recovered resource identities: `publication-native.json`. HTTP mutation remains present after graceful handoff, supervisor death, stop and restart. Product fixture only executes inside Linux Docker.
- UID65532, read-only image `/app`, capdrop ALL, no-new-privileges, network NONE, no Docker-published port, only exact owned named DB volume. No host source overlay, Docker socket, credentials or implicit seed. Container-side connections to the owned host canary via `host.docker.internal` and to external `1.1.1.1:443` fail. Host canary remains alive. 403/404 readiness is rejected.

## Integration API

`deploy_and_verify` retains existing arguments and accepts explicit reviewed facts:

```
publication_root=external_supervisor_root / "publication"
publication_contract_hash=contract.hash
publication_internal_port=binding.internal_port
publication_local_cookie_mode=binding.local_cookie_mode
publication_database_path=binding.database_path
publication_health_path=literal_contract_health_path
publication_migration_command=literal_reviewed_argv_or_None
```

Existing `qualified_image_id`, `expected_snapshot`, `expected_runtime_command` are required. The web result is `ok=True, packaged=False`, with actual immutable CID and retained loopback port. No bridge, rebuild, producer Dockerfile or command override is used. A missing publication port still yields the existing honest packaged/not-deployed result.

`inspect_deployment(id, publication_root=...)` is read-only and does not revive stale state. It reports active only when the exact container is running AND ingress is retained by this factory process. On factory startup, explicitly call `recover_publication(id, root)` for records intended to be active. Do not revive deliberately stopped records automatically.

`undeploy(id, publication_root=...)` stops/removes only the exact owned container/relay and preserves DB. `recover_publication(id, root)` restarts the same image with the same port/DB, or reattaches to a surviving exact hardened CID. `destroy_publication_data(id, root)` is separate irreversible explicit authority, accepted only after stop and fresh volume identity verification. Image removal is not implicit in database cleanup.

`PublicationRegistry.release_ingress(id)` is a graceful factory shutdown/handoff, retaining daemon app and DB. A foreign occupied port is refused, never killed. Journal ownership intent is durable before daemon effects; schema, containment, labels, CID/creation time, volume creation identity, exact source/image/CMD and full container configuration fingerprint are rechecked. Uncertain journal/cleanup and ambiguous migration outcomes block recovery.

## Deliberate limits

- Currently supports reviewed Python `/opt/venv/bin/python` and Node `node`, fixed SQLite path `/var/lib/autospec-validation/support.sqlite`, literal health path, IPv4 loopback publication only. This is local functional publication, not public Internet hosting or TLS.
- Different image/source/contract/config updates are refused while an existing service exists, preserving that service. Cross-version database migration/backup/rollback requires an explicit future policy; it is not silently simulated.
- Optional source-reviewed migration argv executes exactly once on the initial new volume; no stdin/parameter guessing and no fixture seed. Pending/failed migration blocks resume, preserving DB until explicit disposition. Without migration, the exact image must make its health URL work on its own empty factory volume.
- Factory process death briefly removes ingress; recovery is explicit. Docker resource/data identities survive. No guessed PID/name sweep or automatic host process adoption is added.
- These scoped probes do not close remediation tasks or substitute for final source review/business acceptance. Parent must connect startup/stop/status APIs and independently qualify actual delivery.

Linux offline recipe is retained in `publication-factory-build/Dockerfile`; copy the current `backend/pyproject.toml` and `backend/uv.lock` into that build context before building. Only those factory manifests enter its networked dependency builder. Runtime tests used immutable image `sha256:26f566256d3707c44817a225536b7a61c2969f0f1b11b2b4328b11aa01934ab2`, read-only factory code, nonroot/capsdrop/NETNONE, without Docker socket.
