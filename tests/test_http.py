import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest
from prometheus_client import CollectorRegistry

from reeflog.app import build_handler
from reeflog.collector import ReadingCollector
from reeflog.store import Store


@pytest.fixture
def server(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    registry = CollectorRegistry()
    registry.register(ReadingCollector(store))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(store, registry))
    httpd.daemon_threads = True
    Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", store
    httpd.shutdown()
    store.close()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.read().decode()


def post(url, fields, headers=None):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req) as r:
        return r.status, r.read().decode()


def test_form_renders(server):
    base, _ = server
    status, body = get(f"{base}/")
    assert status == 200
    assert "Phosphate" in body and "Nitrate" in body


def test_healthz(server):
    base, _ = server
    assert get(f"{base}/healthz")[0] == 200


def test_metrics_are_empty_until_a_reading_exists(server):
    base, _ = server
    assert "hydros_input_phosphate_ppm" not in get(f"{base}/metrics")[1]


def test_posting_a_reading_publishes_the_expected_series(server):
    base, _ = server
    post(f"{base}/", {"parameter": "phosphate", "value": "0.04"})
    body = get(f"{base}/metrics")[1]
    assert 'hydros_input_phosphate_ppm{basis="PO4",name="Phosphate",source="manual"} 0.04' in body
    assert 'hydros_input_measured_timestamp_seconds{name="Phosphate",source="manual"}' in body


def test_source_label_is_only_ever_manual(server):
    """The exporter's own series must stay label-free, so ours is the odd one out."""
    base, _ = server
    post(f"{base}/", {"parameter": "nitrate", "value": "5"})
    body = get(f"{base}/metrics")[1]
    assert 'source="manual"' in body
    assert 'source="api"' not in body


def test_measured_at_is_honoured(server):
    base, store = server
    when = time.strftime("%Y-%m-%dT%H:%M", time.localtime(time.time() - 3600))
    post(f"{base}/", {"parameter": "nitrate", "value": "8", "measured_at": when})
    assert store.latest()["nitrate"].measured_at < int(time.time()) - 60


def test_bad_value_is_rejected_without_writing(server):
    base, store = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{base}/", {"parameter": "phosphate", "value": "99"})
    assert exc.value.code == 400
    assert store.latest() == {}


def test_non_numeric_value_is_rejected(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{base}/", {"parameter": "phosphate", "value": "abc"})
    assert exc.value.code == 400


def test_cross_origin_post_is_rejected(server):
    base, store = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{base}/", {"parameter": "phosphate", "value": "0.04"},
             headers={"Origin": "https://evil.example"})
    assert exc.value.code == 403
    assert store.latest() == {}


def test_same_origin_post_is_allowed(server):
    base, store = server
    host = urllib.parse.urlsplit(base).netloc
    post(f"{base}/", {"parameter": "phosphate", "value": "0.04"},
         headers={"Origin": f"http://{host}"})
    assert store.latest()["phosphate"].value == pytest.approx(0.04)


def test_salinity_publishes_both_sg_and_derived_ppt(server):
    base, _ = server
    post(f"{base}/", {"parameter": "salinity", "value": "1.026"})
    body = get(f"{base}/metrics")[1]
    assert 'hydros_input_specific_gravity{basis="SG",name="Salinity",source="manual"} 1.026' in body
    ppt = [l for l in body.splitlines() if l.startswith("hydros_input_salinity_ppt{")]
    assert ppt and 34.0 < float(ppt[0].rsplit(" ", 1)[1]) < 35.5


def test_calcium_publishes_in_ppm(server):
    base, _ = server
    post(f"{base}/", {"parameter": "calcium", "value": "430"})
    body = get(f"{base}/metrics")[1]
    assert 'hydros_input_calcium_ppm{basis="Ca",name="Calcium",source="manual"} 430.0' in body


def test_alkalinity_uses_the_name_the_exporter_reserves(server):
    base, _ = server
    post(f"{base}/", {"parameter": "alkalinity", "value": "8.6"})
    body = get(f"{base}/metrics")[1]
    assert 'hydros_input_alkalinity_dkh{basis="dKH",name="Alkalinity",source="manual"} 8.6' in body


def test_unknown_path_is_404(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{base}/nope")
    assert exc.value.code == 404
