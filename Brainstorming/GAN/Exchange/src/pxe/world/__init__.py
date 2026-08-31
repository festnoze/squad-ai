"""World generation (A03): templates, latent processes, correlations, priors.

A world is a pure function of its seed (FR-5.2.1 to FR-5.2.4). Nothing in this
package reads a clock, the filesystem or the network, and every draw comes from
a registered ``world.*`` substream of :class:`pxe.rng.RngTree`.

Per CONTRACTS section 1 this file holds a docstring and nothing else: no import
and no re-export. Import submodules by full path, for example
``from pxe.world.generator import generate_world``.
"""
