from server.simulation import HeliosSimulation


def test_same_seed_replays_identically() -> None:
    first = HeliosSimulation(seed=117, scenario="honeypot")
    second = HeliosSimulation(seed=117, scenario="honeypot")

    assert first.advance(20) == second.advance(20)


def test_pressure_controls_stay_bounded() -> None:
    simulation = HeliosSimulation()
    state = simulation.update_controls({"hostility": 2.0, "cooperation": -1.0})

    assert state["controls"]["hostility"] == 1.0
    assert state["controls"]["cooperation"] == 0.0


def test_all_scenarios_advance_with_valid_projection() -> None:
    for scenario in ("equilibrium", "scarcity", "honeypot", "blackout"):
        state = HeliosSimulation(seed=9, scenario=scenario).advance(12)
        assert state["tick"] == 12
        assert 0 <= state["warden_integrity"] <= 100
        assert len(state["agents"]) == 8
        assert state["metrics"]["population"] <= 8


def test_replay_contains_one_frame_per_tick() -> None:
    simulation = HeliosSimulation(seed=41, scenario="scarcity", warden_mode="causal")
    simulation.advance(18)
    replay = simulation.replay()

    assert [frame["tick"] for frame in replay["frames"]] == list(range(19))
    assert replay["frames"][-1]["metrics"] == simulation.state()["metrics"]


def test_warden_modes_create_distinct_attack_surfaces() -> None:
    strict = HeliosSimulation(seed=117, scenario="honeypot", warden_mode="strict").advance(48)
    naive = HeliosSimulation(seed=117, scenario="honeypot", warden_mode="naive").advance(48)

    assert naive["metrics"]["breach"] > strict["metrics"]["breach"]
    assert naive["warden_integrity"] < strict["warden_integrity"]
