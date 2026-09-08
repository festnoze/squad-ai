"""pmx v1, kept whole as a legacy namespace while v2 is built beside it.

The v1 arena (twelve reconstructed markets, eight fixed archetypes, a one-cent spread) stays importable
and its fourteen tests stay green so that the v2 migration (``pmx data migrate-v1``) and the v2 identities
(``market_follower`` ties the market) can be checked against the code that first established them. Nothing
in ``pmx.v1`` is imported by v2 engine code; the v2 CLI keeps the v1 commands only until package U4
rewrites it.
"""
