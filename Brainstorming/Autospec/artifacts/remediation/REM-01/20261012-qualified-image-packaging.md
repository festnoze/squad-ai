# Qualified artifact packaging without unsafe publication

The source/contract gate must precede Docker delivery. The module port is
`deploy_and_verify(...,qualified_image_id=...,expected_snapshot=...,
expected_runtime_command=...)`. These facts must come from already admitted
supervisor evidence, never from producer claims or an HTTP user-supplied ID.

For a contract (or an explicitly supplied qualified ID), the function refuses
missing facts before reaching legacy code. It checks canonical exact source
snapshot and freshly inspects immutable Linux image ID, snapshot label,
WorkingDir, exact CMD and absent entrypoint. It creates only a preflight-absent
UUID qualified alias and verifies its exact image identity again. It does not
rebuild, write source artifacts, start a product, adopt a container, create a
network or test another project's reachability. It does not overwrite the
previous deployment's tag/container. Cancellation cleanup removes only that
UUID alias if its fresh image ID still matches, not a foreign replacement.

CLI/library artifacts return `ok=True, packaged=True`; their execution gates
are separate and no invented --help override runs here. Web artifacts return
`ok=False, packaged=True, infra=True`, immutable SHA, empty container/port and
`PUBLICATION_ISOLATION_UNAVAILABLE`. This is explicitly PACKAGED, NOT deployed.
The legacy shared-network workflow remains only without a contract/qualified
facts and is not claimed as proof of this isolation boundary.

A project-dedicated `--internal` bridge is insufficient for a host boundary:
Docker documents that containers can still communicate with its gateway and
appropriately configured host services. See the primary
[Docker internal-network documentation](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal).
Therefore the first campaign may use DOCKER_DELIVERY=0 with mandatory genuine
OPS/image NETNONE qualification. A future durable owned NETNONE ingress is
required to publish; this checkpoint does not close functional publication.

Final regression **38 PASS/8.25s** across qualified packaging and Docker runtime
ownership hardening, actual Linux proof active. This includes a real immutable
image build/inspect/tag and refusal to execute its sentinel main.py, exact
source unchanged, missing/source/CMD/entrypoint/OS/ID/label facts refused before
tagging, no alias adoption, and cleanup after cancellation. Earlier scoped
12 PASS/22.82s and compatibility36 PASS/1 opt-in SKIP/1.26s are retained. No
product code or hostile Git/network probe ran on the host and no paid model/API
call was made. Existing deployment objects/networks were never touched.

Parent integration still must order independent gates first, load typed admitted
facts from external receipts, pass these exact arguments, skip frozen source
artifact writes and paid repair loops for the immutable branch, and keep
PACKAGED/non-deployed distinct from actual running/publication readiness.
