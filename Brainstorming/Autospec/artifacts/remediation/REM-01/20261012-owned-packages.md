# Durable qualified CLI/library packages

First replay: **26 PASS, 12.69 s**, `20261012-owned-packages-native-v1.xml`.
Final replay including creation/reuse/cancellation races and publication
compatibility: **47 PASS, 87.60 s**, `20261012-owned-packages-native-v2.xml`.
Native receipts: `package-native.json` (exact alias removed; same immutable image
and a separate alias remain). Product fixture deliberately raises if started;
packaging never starts it. No paid model/provider call.

## Root integration

- CLI/library `deploy_and_verify(..., packaging_root=supervisor/'packages', qualified_image_id=SHA, expected_snapshot=SHA, expected_runtime_command=reviewed_argv)` takes the exact contract identity from `state.acceptance_contract_hash`. Registry is mandatory, never latest/legacy fallback.
- `inspect_packaged_image(id, packaging_root=root)` inspects the journal subject and fresh actual alias/image. Optional `qualified_image_id`, `expected_snapshot`, `expected_runtime_command`, `expected_contract_hash` assert exact caller facts; when image ID is supplied all facts are required. Without a journal, image-facts-only inspection is read-only and confers NO removal authority.
- `undeploy(id, packaging_root=root)` removes only the exact journaled/preflight-absent UUID alias after fresh expected image/source/CMD/entrypoint/OS checks. Never passes `publication_root` simultaneously, never removes image by SHA, shared tags, dependency cache, containers, source files or legacy names.
- `DockerDeployResult.created_package_alias` is nonempty ONLY when the tag was newly created during this exact successful call. Empty for prior package reuse/recovery, even if state image/CID was never flushed before a crash. Root cancellation must not infer creation from state-image differences.
- Late cancellation of a new alias: `undeploy(id, packaging_root=root, expected_package_alias=result.created_package_alias, expected_package_image_id=result.image)` only when the creation field is nonempty. This atomically compares journal identity under its external lock and freshly checks the alias before deletion. A newer replacement package is refused/preserved.

Prepared ownership intent is durable BEFORE tag mutation. Canonical bounded
external journal, exact owner/UUID alias, source snapshot, immutable image and
default-command identities are required. Foreign/replaced alias, unknown/corrupt
journal, missing previously complete alias and uncertain daemon state never cause
adoption or unbounded cleanup. Tag request cancellation cleans only its proven
owned alias; ambiguous cleanup records uncertainty. Spec updates require explicit
detach, preserving any previous package.

These are scoped resource/behavior proofs, not business acceptance or independent
source review. Root must connect startup/status/stop calls. The legacy API remains
only for callers without qualified facts/contract; qualified CLI/library paths
require the journal and never enter legacy container/name deletion.
