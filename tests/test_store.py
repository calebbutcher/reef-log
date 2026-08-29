import time

import pytest

from reeflog.parameters import PARAMETERS
from reeflog.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    yield s
    s.close()


def test_add_and_read_back(store):
    store.add("phosphate", 0.04)
    latest = store.latest()
    assert latest["phosphate"].value == pytest.approx(0.04)
    assert latest["phosphate"].compound == "PO4"


def test_compound_is_recorded_per_reading(store):
    """The convention is what cannot be reconstructed later, so it is stored."""
    store.add("nitrate", 5.0)
    assert store.latest()["nitrate"].compound == "NO3"


def test_latest_is_by_measurement_time_not_entry_order(store):
    now = int(time.time())
    store.add("phosphate", 0.10, measured_at=now)
    store.add("phosphate", 0.02, measured_at=now - 86400)   # entered later, older test
    assert store.latest()["phosphate"].value == pytest.approx(0.10)


def test_history_is_kept(store):
    for value in (0.01, 0.02, 0.03):
        store.add("phosphate", value)
    assert len(store.recent()) == 3


def test_unknown_parameter_is_rejected(store):
    with pytest.raises(ValueError):
        store.add("iodine", 0.06)


@pytest.mark.parametrize("key,value", [("phosphate", 99.0), ("nitrate", 9999.0),
                                       ("phosphate", -1.0)])
def test_out_of_range_values_are_rejected(store, key, value):
    with pytest.raises(ValueError):
        store.add(key, value)


def test_future_measurements_are_rejected(store):
    with pytest.raises(ValueError):
        store.add("phosphate", 0.05, measured_at=int(time.time()) + 90 * 86400)


def test_metric_names_match_the_exporter_convention():
    assert PARAMETERS["phosphate"].metric == "hydros_input_phosphate_ppm"
    assert PARAMETERS["nitrate"].metric == "hydros_input_nitrate_ppm"
