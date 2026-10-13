"""Opt-in real-Docker proof for Autospec's shared service network.

Set ``AUTOSPEC_DOCKER_COMMON_NETWORK_TESTS=1`` to run. The test requires the
factory Python base image to already be local; it never pulls an image. All
resources use a per-run UUID and an ownership label, and cleanup addresses only
the exact IDs created by this test.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from autospec.orchestrator import docker_deploy


_OPT_IN = "AUTOSPEC_DOCKER_COMMON_NETWORK_TESTS"
_RUN_LABEL = "autospec.e2e.run"
_BASE_IMAGE = "ghcr.io/astral-sh/uv:python3.12-bookworm-slim"
_REAL_DOCKER = pytest.mark.skipif(
    os.environ.get(_OPT_IN) != "1",
    reason=f"set {_OPT_IN}=1 to opt into Docker resource creation",
)


def _inspect_network(name: str) -> dict | None:
    rc, output = docker_deploy._docker(["network", "inspect", name], timeout=5)
    if rc == 0:
        try:
            return json.loads(output)[0]
        except (ValueError, IndexError, TypeError) as exc:
            raise AssertionError(f"invalid Docker network inspect output: {output[:500]}") from exc
    if "no such network" in output.lower() or "not found" in output.lower():
        return None
    pytest.fail(f"cannot safely inspect test network {name}: {output}")


def _inspect_image(reference: str) -> dict | None:
    rc, output = docker_deploy._docker(["image", "inspect", reference], timeout=5)
    if rc == 0:
        try:
            return json.loads(output)[0]
        except (ValueError, IndexError, TypeError) as exc:
            raise AssertionError(f"invalid Docker image inspect output: {output[:500]}") from exc
    if "no such image" in output.lower() or "not found" in output.lower():
        return None
    pytest.fail(f"cannot safely inspect test image {reference}: {output}")


def _tag_verified_base_alias(base_id: str, alias: str) -> str:
    """Create a unique local tag and prove it resolves to the inspected base ID."""
    rc, output = docker_deploy._docker(["image", "tag", base_id, alias], timeout=15)
    if rc != 0:
        raise AssertionError(f"failed to tag local base image {base_id}: {output}")
    image = _inspect_image(alias)
    if image is None or image.get("Id") != base_id:
        raise AssertionError(f"local base alias {alias} did not resolve to {base_id}")
    return image["Id"]


def _remove_verified_base_alias(alias: str, expected_base_id: str) -> str:
    """Remove only this alias when it still points at the expected base image."""
    image = _inspect_image(alias)
    if image is None or image.get("Id") != expected_base_id:
        return ""  # missing or retagged aliases are not this test's cleanup target
    rc, output = docker_deploy._docker(["image", "rm", alias], timeout=20)
    if rc != 0 and "no such image" not in output.lower():
        return output
    return ""


def _test_service_dockerfile(base_alias: str, run_id: str) -> str:
    return (
        f"FROM {base_alias}\n"
        f"LABEL {_RUN_LABEL}={run_id}\n"
        "COPY service.py /service.py\n"
        'ENTRYPOINT ["/usr/local/bin/python"]\n'
        'CMD ["-I", "-u", "/service.py"]\n'
    )


def _build_test_service_image(image_tag: str, context: Path) -> tuple[int, str]:
    return docker_deploy._docker(
        ["build", "--pull=false", "--tag", image_tag, str(context)], timeout=90
    )


def _inspect_service(name: str) -> dict | None:
    return docker_deploy._inspect_container(name)


def _owned_container(info: dict, *, name: str, project: str, run_id: str,
                     image_id: str) -> bool:
    labels = info.get("Config", {}).get("Labels") or {}
    names = info.get("Names") or [info.get("Name", "")]
    return (
        info.get("Id")
        and {entry.lstrip("/") for entry in names} == {name}
        and labels.get(_RUN_LABEL) == run_id
        and labels.get(docker_deploy.LABEL_PROJECT) == project
        and info.get("Image") == image_id
    )


def test_extra_labels_are_forwarded_without_overriding_managed_labels(monkeypatch):
    calls: list[list[str]] = []

    def fake_docker(args, *, timeout, cwd=None):
        calls.append(list(args))
        if args[:2] == ["network", "inspect"]:
            return 1, "Error: No such network: isolated-fixture"
        return 0, "created"

    monkeypatch.setattr(docker_deploy, "_docker", fake_docker)
    assert docker_deploy.ensure_network(
        "isolated-fixture", extra_labels={_RUN_LABEL: "fictional-run"}
    ) == (True, "")
    assert calls[-1] == [
        "network", "create", "--label", f"{_RUN_LABEL}=fictional-run", "isolated-fixture"
    ]

    ok, _ = docker_deploy.replace_container(
        "fictional-image", "fictional-container", "isolated-fixture", 0, 8000,
        "fictional-project", extra_labels={_RUN_LABEL: "fictional-run"},
    )
    assert ok
    run = calls[-1]
    assert run[0:2] == ["run", "-d"]
    assert run[run.index("--network") + 1] == "isolated-fixture"
    assert run.count("--label") == 4
    assert f"{_RUN_LABEL}=fictional-run" in run
    with pytest.raises(ValueError, match="managed label"):
        docker_deploy._validated_extra_labels({docker_deploy.LABEL_PROJECT: "foreign"})


def test_local_base_alias_tags_and_cleans_only_the_unique_reference(monkeypatch):
    base_id = "sha256:fictional-base-id"
    base_reference = _BASE_IMAGE
    alias = "autospec-e2e/base-fictional-run:local"
    images = {base_reference: base_id, base_id: base_id}
    calls: list[list[str]] = []

    def fake_docker(args, *, timeout, cwd=None):
        calls.append(list(args))
        if args[:2] == ["image", "inspect"]:
            image_id = images.get(args[2])
            if image_id is None:
                return 1, f"Error: No such image: {args[2]}"
            return 0, json.dumps([{"Id": image_id}])
        if args[:2] == ["image", "tag"]:
            images[args[3]] = images[args[2]]
            return 0, ""
        if args[0] == "build":
            return 0, "fictional image built locally"
        if args[:2] == ["image", "rm"]:
            images.pop(args[2], None)
            return 0, ""
        raise AssertionError(f"unexpected Docker command in fake: {args}")

    monkeypatch.setattr(docker_deploy, "_docker", fake_docker)
    assert _tag_verified_base_alias(base_id, alias) == base_id
    assert images[alias] == base_id
    dockerfile = _test_service_dockerfile(alias, "fictional-run")
    assert dockerfile.startswith(f"FROM {alias}\n")
    assert "FROM sha256:" not in dockerfile
    assert f"LABEL {_RUN_LABEL}=fictional-run" in dockerfile
    assert _build_test_service_image("autospec-e2e/service-fictional:local", Path("fictional-context")) == (
        0, "fictional image built locally"
    )
    assert _remove_verified_base_alias(alias, base_id) == ""
    assert alias not in images
    assert images[base_reference] == base_id  # the base image itself remains tagged
    assert calls == [
        ["image", "tag", base_id, alias],
        ["image", "inspect", alias],
        ["build", "--pull=false", "--tag", "autospec-e2e/service-fictional:local", "fictional-context"],
        ["image", "inspect", alias],
        ["image", "rm", alias],
    ]

    # A changed alias is foreign to this test and must not be removed.
    foreign_alias = "autospec-e2e/base-foreign-run:local"
    images[foreign_alias] = "sha256:other-image"
    assert _remove_verified_base_alias(foreign_alias, base_id) == ""
    assert images[foreign_alias] == "sha256:other-image"
    assert calls[-1] == ["image", "inspect", foreign_alias]


@_REAL_DOCKER
def test_two_project_services_reach_each_other_on_a_unique_common_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    available, reason = docker_deploy.docker_available()
    if not available:
        pytest.skip(f"Docker engine unavailable: {reason}")

    base_rc, base_id = docker_deploy._docker(
        ["image", "inspect", _BASE_IMAGE, "--format", "{{.Id}}"], timeout=5
    )
    if base_rc != 0 or not base_id.strip():
        pytest.skip(f"pre-existing local factory image required; no pull attempted: {base_id}")
    base_id = base_id.strip()

    run_id = uuid.uuid4().hex
    network_name = f"autospec-e2e-common-{run_id}"
    project_ids = [f"fictional-{run_id}-alpha", f"fictional-{run_id}-beta"]
    # Use the production canonical names so the active-delivery label is 1 and
    # the real deployed-container registry admits the test-owned services.
    service_names = [docker_deploy.container_name(project_id) for project_id in project_ids]
    image_tag = f"autospec-e2e/common-{run_id}:test"
    base_alias = f"autospec-e2e/base-{run_id}:local"
    run_label = {_RUN_LABEL: run_id}

    # Collision checks happen before the first write. In the extraordinarily
    # unlikely event of a UUID collision, leave all pre-existing resources alone.
    if _inspect_network(network_name) is not None:
        pytest.skip("unique test network name already exists; refusing to adopt it")
    if _inspect_image(image_tag) is not None:
        pytest.skip("unique test image tag already exists; refusing to adopt it")
    if _inspect_image(base_alias) is not None:
        pytest.skip("unique local-base alias already exists; refusing to adopt it")
    for name in service_names:
        if _inspect_service(name) is not None:
            pytest.skip("unique test container name already exists; refusing to adopt it")

    owned_network_id: str | None = None
    owned_image_id: str | None = None
    base_alias_may_be_ours = False
    known_container_ids: dict[str, str] = {}
    try:
        ok, detail = docker_deploy.ensure_network(network_name, extra_labels=run_label)
        assert ok, f"failed to create isolated common network: {detail}"
        network = _inspect_network(network_name)
        assert network is not None
        network_labels = network.get("Labels") or {}
        assert network_labels.get(_RUN_LABEL) == run_id, "refusing to adopt a network not labelled by this test"
        owned_network_id = network.get("Id")
        assert owned_network_id, "Docker did not return the owned test network ID"
        assert network.get("Driver") == "bridge", f"unexpected common network driver: {network.get('Driver')}"

        # Docker's builder resolves FROM by repository reference rather than
        # accepting a bare image ID. Give the already-inspected local image a
        # UUID alias, verify alias -> ID, then use --pull=false to forbid pulls.
        assert _tag_verified_base_alias(base_id, base_alias) == base_id
        base_alias_may_be_ours = True

        # This is test-only fictional data and uses Python's standard library.
        context = tmp_path / "fictional-service-image"
        context.mkdir()
        (context / "service.py").write_text(
            "import json, socket\n"
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200)\n"
            "        self.send_header('Content-Type', 'application/json')\n"
            "        self.end_headers()\n"
            "        body = {'service': socket.gethostname(), 'result': 'fixture-ok'}\n"
            "        self.wfile.write(json.dumps(body).encode())\n"
            "    def log_message(self, *args):\n"
            "        pass\n"
            "HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()\n",
            encoding="utf-8",
        )
        (context / "Dockerfile").write_text(
            _test_service_dockerfile(base_alias, run_id), encoding="utf-8"
        )
        built, build_output = _build_test_service_image(image_tag, context)
        assert built == 0, f"offline test image build failed: {build_output}"
        image = _inspect_image(image_tag)
        assert image is not None
        assert (image.get("Config", {}).get("Labels") or {}).get(_RUN_LABEL) == run_id
        owned_image_id = image.get("Id")
        assert owned_image_id, "Docker did not return the owned test image ID"

        service_hostnames: dict[str, str] = {}
        for name, project_id in zip(service_names, project_ids, strict=True):
            started, start_detail = docker_deploy.replace_container(
                owned_image_id,
                name,
                network_name,
                0,  # Docker chooses a loopback-only ephemeral host port.
                8000,
                project_id,
                extra_labels=run_label,
            )
            assert started, f"failed to start {name}: {start_detail}"
            info = _inspect_service(name)
            assert info is not None
            assert _owned_container(
                info, name=name, project=project_id, run_id=run_id, image_id=owned_image_id
            ), f"container {name} does not have this test's ownership markers"
            known_container_ids[name] = info["Id"]
            service_hostnames[name] = info.get("Config", {}).get("Hostname", "")
            networks = info.get("NetworkSettings", {}).get("Networks") or {}
            assert network_name in networks, f"{name} is not attached to the common test network"
            host_port = docker_deploy._published_port(info, 8000)
            healthy, health_detail = docker_deploy.wait_healthy(
                name, host_port, timeout=15, strict_http=True
            )
            assert healthy, f"{name} did not become healthy: {health_detail}"
        assert all(service_hostnames.values()) and len(set(service_hostnames.values())) == 2

        deployed = docker_deploy.list_deployed(network=network_name)
        assert {entry["project"] for entry in deployed} == set(project_ids)
        monkeypatch.setattr(docker_deploy, "_PROBE_RETRY_DELAY_S", 0.25)
        reachable, detail = docker_deploy.check_cross_reachability(service_names[0], deployed)
        assert reachable, f"bidirectional Autospec service probe failed:\n{detail}"
        assert f"OK   {service_names[0]} -> {service_names[1]}:8000" in detail
        assert f"OK   {service_names[1]} -> {service_names[0]}:8000" in detail

        # The production probe treats any HTTP response as proof of reachability;
        # also assert each distinct container identity in the response to catch
        # false-green DNS/TCP-only outcomes or accidental self-reachability.
        for source, destination in ((service_names[0], service_names[1]),
                                    (service_names[1], service_names[0])):
            script = (
                "import json, urllib.request; "
                f"assert json.load(urllib.request.urlopen('http://{destination}:8000/', timeout=3)) "
                f"== {{'service': {service_hostnames[destination]!r}, 'result': 'fixture-ok'}}"
            )
            rc, output = docker_deploy._docker(
                ["exec", source, "python", "-I", "-c", script], timeout=10
            )
            assert rc == 0, f"{source} did not receive the expected fictional payload: {output}"
    finally:
        cleanup_errors: list[str] = []

        # Inspect identity markers again and remove exact IDs only. A name alone
        # is never cleanup authority; mismatched resources are left untouched.
        if owned_image_id:
            for name, project_id in zip(service_names, project_ids, strict=True):
                try:
                    info = _inspect_service(name)
                    if info is None:
                        continue
                    if not _owned_container(
                        info, name=name, project=project_id, run_id=run_id, image_id=owned_image_id
                    ):
                        continue
                    container_id = info["Id"]
                    if name in known_container_ids and known_container_ids[name] != container_id:
                        continue
                    rc, output = docker_deploy._docker(["rm", "--force", container_id], timeout=20)
                    if rc != 0 and "no such container" not in output.lower():
                        cleanup_errors.append(f"container {container_id}: {output}")
                except Exception as exc:  # cleanup failure is surfaced after other owned resources
                    cleanup_errors.append(f"container {name}: {exc}")

        if owned_network_id:
            try:
                network = _inspect_network(network_name)
                if network and network.get("Id") == owned_network_id and (
                    (network.get("Labels") or {}).get(_RUN_LABEL) == run_id
                ):
                    rc, output = docker_deploy._docker(
                        ["network", "rm", owned_network_id], timeout=20
                    )
                    if rc != 0 and "not found" not in output.lower():
                        cleanup_errors.append(f"network {owned_network_id}: {output}")
            except Exception as exc:
                cleanup_errors.append(f"network {network_name}: {exc}")

        # An image may be removed only if its immutable ID still carries this
        # test's UUID label; never remove a pre-existing or retagged image.
        try:
            image = _inspect_image(image_tag)
            if image and (image.get("Config", {}).get("Labels") or {}).get(_RUN_LABEL) == run_id:
                image_id = image.get("Id")
                if owned_image_id is not None and image_id != owned_image_id:
                    image_id = None  # a retagged replacement is not ours to remove
            else:
                image_id = None
            if image_id:
                rc, output = docker_deploy._docker(
                    ["image", "rm", image_id], timeout=20
                )
                if rc != 0 and "no such image" not in output.lower():
                    cleanup_errors.append(f"image {image_id}: {output}")
        except Exception as exc:
            cleanup_errors.append(f"image {image_tag}: {exc}")

        if base_alias_may_be_ours:
            try:
                alias_error = _remove_verified_base_alias(base_alias, base_id)
                if alias_error:
                    cleanup_errors.append(f"base image alias {base_alias}: {alias_error}")
            except Exception as exc:
                cleanup_errors.append(f"base image alias {base_alias}: {exc}")

        if cleanup_errors:
            pytest.fail("test-owned Docker resources could not all be cleaned: " + "; ".join(cleanup_errors))
