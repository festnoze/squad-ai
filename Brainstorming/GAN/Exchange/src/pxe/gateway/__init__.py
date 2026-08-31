"""The agent gateway of Prediction Exchange (pxe): the one impure seam.

This package is the only asynchronous surface of the system (CONTRACTS
section 2.7). It turns "one observation" into "one
:class:`~pxe.gateway.protocol.AgentReply`" for every seat of a tick, in
parallel, with a timeout and a budget, and it hands the runner a fully formed
reply object. It never validates an action, never mutates engine state and
never emits an event.

Per CONTRACTS section 1 this ``__init__`` carries a docstring and nothing else:
no import and no re-export. Import by full path
(``from pxe.gateway.protocol import BaseGateway``), never from the package.
"""
