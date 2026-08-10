## INTERNAL TEST SUITE ONLY-- TO CONFIRM CACHE SPEEDS
from nexttrack.observability.timing import StageTimings


def test_empty_summary_returns_empty_dict():
    st = StageTimings()
    assert st.summary() == {}


def test_single_record_n1():
    st = StageTimings()
    st.record("similarity", 42.0)
    s = st.summary()
    assert s["similarity"] == {"p50": 42.0, "p95": 42.0, "max": 42.0, "n": 1.0}


def test_two_records_n2():
    st = StageTimings()
    st.record("similarity", 10.0)
    st.record("similarity", 20.0)
    s = st.summary()
    assert s["similarity"]["n"] == 2.0
    assert s["similarity"]["max"] == 20.0
    assert s["similarity"]["p50"] <= s["similarity"]["p95"]


def test_multiple_stages_independent():
    st = StageTimings()
    st.record("similarity", 50.0)
    st.record("tags", 100.0)
    s = st.summary()
    assert set(s.keys()) == {"similarity", "tags"}
    assert s["similarity"]["n"] == 1.0
    assert s["tags"]["n"] == 1.0


def test_p95_ordering():
    st = StageTimings()
    for i in range(100):
        st.record("similarity", float(i))
    s = st.summary()
    assert s["similarity"]["p50"] < s["similarity"]["p95"]
    assert s["similarity"]["p95"] <= s["similarity"]["max"]


def test_p50_median_of_sorted():
    st = StageTimings()
    # 100 values 1..100; p50 at index 49 should be near 50
    for i in range(1, 101):
        st.record("sim", float(i))
    s = st.summary()
    assert 49.0 <= s["sim"]["p50"] <= 51.0


def test_max_correct_after_many_records():
    st = StageTimings()
    for v in [5.0, 1.0, 9.0, 3.0]:
        st.record("tags", v)
    assert st.summary()["tags"]["max"] == 9.0


def test_record_does_not_mutate_other_stage():
    st = StageTimings()
    st.record("a", 10.0)
    st.record("b", 20.0)
    st.record("a", 30.0)
    s = st.summary()
    assert s["a"]["n"] == 2.0
    assert s["b"]["n"] == 1.0
