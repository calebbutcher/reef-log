import sqlite3
import time

import pytest

from reeflog.parameters import PARAMETERS, sg_to_ppt
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
    assert latest["phosphate"].basis == "PO4"


def test_basis_is_recorded_per_reading(store):
    """The convention is what cannot be reconstructed later, so it is stored."""
    store.add("nitrate", 5.0)
    assert store.latest()["nitrate"].basis == "NO3"


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


def v010_database(path):
    """The 0.1.0 schema, which named the basis column `compound`."""
    db = sqlite3.connect(str(path))
    db.executescript(
        "CREATE TABLE reading (id INTEGER PRIMARY KEY, parameter TEXT NOT NULL,"
        " value REAL NOT NULL, compound TEXT NOT NULL, measured_at INTEGER NOT NULL,"
        " entered_at INTEGER NOT NULL);"
    )
    db.commit()
    db.close()


def test_upgrading_from_the_old_column_name_still_accepts_writes(tmp_path):
    """
    CREATE TABLE IF NOT EXISTS leaves an existing table alone, so renaming the
    column in SCHEMA alone broke every INSERT on an already-deployed database.
    """
    path = tmp_path / "old.db"
    v010_database(path)
    store = Store(str(path))
    store.add("phosphate", 0.04)
    assert store.latest()["phosphate"].basis == "PO4"
    store.close()


def test_upgrade_preserves_existing_rows(tmp_path):
    path = tmp_path / "old.db"
    v010_database(path)
    db = sqlite3.connect(str(path))
    db.execute("INSERT INTO reading (parameter, value, compound, measured_at, entered_at)"
               " VALUES ('nitrate', 5.0, 'NO3', 1000, 1000)")
    db.commit()
    db.close()

    store = Store(str(path))
    assert store.latest()["nitrate"].value == pytest.approx(5.0)
    assert store.latest()["nitrate"].basis == "NO3"
    store.close()


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "old.db"
    v010_database(path)
    for _ in range(3):
        store = Store(str(path))
        store.close()
    store = Store(str(path))
    store.add("alkalinity", 8.6)
    assert store.latest()["alkalinity"].basis == "dKH"
    store.close()


def test_metric_names_match_the_exporter_convention():
    assert PARAMETERS["phosphate"].metric == "hydros_input_phosphate_ppm"
    assert PARAMETERS["nitrate"].metric == "hydros_input_nitrate_ppm"
    # The exporter already reserves this name for a HYDROS alkalinity tester.
    assert PARAMETERS["alkalinity"].metric == "hydros_input_alkalinity_dkh"


def test_specific_gravity_is_not_published_as_ppt():
    """1.026 under the ppt metric would merge with a probe's 35 and be nonsense."""
    salinity = PARAMETERS["salinity"]
    assert salinity.metric == "hydros_input_specific_gravity"
    assert [d.metric for d in salinity.derived] == ["hydros_input_salinity_ppt"]


@pytest.mark.parametrize("sg,ppt", [(1.0226, 30.0), (1.0264, 35.0), (1.0210, 27.9)])
def test_sg_converts_to_ppt_against_published_reference_points(sg, ppt):
    assert sg_to_ppt(sg) == pytest.approx(ppt, abs=0.2)


def test_alkalinity_and_salinity_round_trip(store):
    store.add("alkalinity", 8.6)
    store.add("salinity", 1.026)
    latest = store.latest()
    assert latest["alkalinity"].basis == "dKH"
    assert latest["salinity"].value == pytest.approx(1.026)
    assert latest["salinity"].basis == "SG"


@pytest.mark.parametrize("key,value", [("alkalinity", 40.0), ("salinity", 1.5),
                                       ("salinity", 0.5)])
def test_new_parameters_reject_impossible_values(store, key, value):
    with pytest.raises(ValueError):
        store.add(key, value)
