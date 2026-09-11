from task_validation.sampling.designs import hybrid, simple_random, stratified_random


def test_srs_reproducible_and_records_pi():
    ids = [f"t{i}" for i in range(20)]
    a = simple_random(ids, 5, "seed-a")
    b = simple_random(ids, 5, "seed-a")
    c = simple_random(ids, 5, "seed-b")
    assert a.ids() == b.ids()
    assert a.ids() != c.ids()
    assert all(abs(u.inclusion_prob - 5 / 20) < 1e-12 for u in a.units)


def test_stratified_hits_every_stratum():
    ids = [f"a{i}" for i in range(10)] + [f"b{i}" for i in range(10)]
    strata = {i: i[0] for i in ids}
    draw = stratified_random(ids, 8, "s", strata)
    seen = {u.stratum for u in draw.units}
    assert seen == {"a", "b"}
    assert len(draw.units) == 8


def test_hybrid_has_srs_arm():
    ids = [f"t{i}" for i in range(40)]
    strata = {i: "x" if int(i[1:]) < 20 else "y" for i in ids}
    risks = {i: int(i[1:]) / 40 for i in ids}
    draw = hybrid(ids, 20, "h", strata, risks)
    arms = {u.arm for u in draw.units}
    assert "srs" in arms
    assert len(draw.units) == len(set(draw.ids()))
