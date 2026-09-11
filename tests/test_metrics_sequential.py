from task_validation.model.metrics import auroc, operating_point
from task_validation.sampling.sequential import step


def test_auroc_perfect_and_chance():
    y = [0, 0, 1, 1]
    assert auroc(y, [0.1, 0.2, 0.8, 0.9]) == 1.0
    chance = auroc(y, [0.5, 0.5, 0.5, 0.5])
    assert chance == 0.5


def test_invalid_among_accepted():
    y = [1, 1, 0, 0]
    p = [0.9, 0.1, 0.2, 0.05]
    op = operating_point(y, p, 0.5)
    # accepted = scores < 0.5 → indices 1,2,3 with labels 1,0,0 → 1/3 invalid
    assert op["n_accepted"] == 3
    assert abs(op["invalid_among_accepted"] - 1 / 3) < 1e-12


def test_sequential_release_and_reject():
    # k=0, n=59, N=10000, epsilon=0.05 should release
    st = step(N=10000, n=59, k=0, epsilon=0.05)
    assert st.decision == "release"
    # already more invalids than epsilon even at census
    st2 = step(N=100, n=20, k=20, epsilon=0.05)
    assert st2.decision == "reject"
    st3 = step(N=10000, n=10, k=0, epsilon=0.05)
    assert st3.decision == "continue"
