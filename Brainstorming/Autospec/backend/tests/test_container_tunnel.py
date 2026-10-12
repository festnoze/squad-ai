"""Negative control-ingress admission; no product/browser script on host."""
import pytest

from autospec.orchestrator.container_tunnel import OwnedControlTunnel
from autospec.orchestrator.isolated_validation import RuntimeSession


def capability(tmp_path, monkeypatch):
    runtime=RuntimeSession(tmp_path,"image",["python"],port=8000)
    state={"container_id":"a"*64,"network_mode":"none","running":True,"published_ports":{}}
    monkeypatch.setattr(runtime,"_assert_owned",lambda:state["container_id"])
    monkeypatch.setattr(runtime,"inspect_configuration",lambda:dict(state))
    # No real container was created: close reserved sockets explicitly.
    return runtime,state


@pytest.mark.parametrize("port",[True,0,65536,8000,"9222"])
def test_control_ingress_refuses_invalid_or_product_ports(tmp_path,monkeypatch,port):
    runtime,_=capability(tmp_path,monkeypatch)
    try:
        with pytest.raises(RuntimeError): OwnedControlTunnel(runtime,port)
    finally: runtime.server.server_close()


@pytest.mark.parametrize("problem",["network","publish","stopped","id"])
def test_control_ingress_requires_exact_unpublished_running_netnone_namespace(tmp_path,monkeypatch,problem):
    runtime,state=capability(tmp_path,monkeypatch)
    if problem=="network":state["network_mode"]="bridge"
    elif problem=="publish":state["published_ports"]={"9222/tcp":[]}
    elif problem=="stopped":state["running"]=False
    else:state["container_id"]="not immutable"
    try:
        with pytest.raises(RuntimeError):OwnedControlTunnel(runtime,9222)
    finally:runtime.server.server_close()


def test_control_ingress_never_adopts_restarted_parent_and_closes_without_removing_it(tmp_path,monkeypatch):
    runtime,state=capability(tmp_path,monkeypatch)
    tunnel=OwnedControlTunnel(runtime,9222)
    state["container_id"]="b"*64
    try:
        with pytest.raises(RuntimeError):tunnel._assert_owned()
        tunnel.close();tunnel.close()
        assert tunnel.closed and not runtime.closed
    finally:runtime.server.server_close()


def test_control_ingress_cannot_be_requested_by_a_model_shaped_object():
    with pytest.raises(RuntimeError):OwnedControlTunnel(object(),9222)
