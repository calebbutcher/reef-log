# reef-log

A small web form for hand-entered reef tank readings, exposed to Prometheus.

Some tank parameters are measured with a test kit rather than a probe, so they
never appear in any controller API. This records them and publishes them
alongside probe telemetry.

## Metrics

Readings are published under the names a HYDROS exporter would use for the same
parameter, with a `source="manual"` label:

```
hydros_input_phosphate_ppm{name="Phosphate",     basis="PO4", source="manual"}
hydros_input_nitrate_ppm{name="Nitrate",         basis="NO3", source="manual"}
hydros_input_alkalinity_dkh{name="Alkalinity",   basis="dKH", source="manual"}
hydros_input_calcium_ppm{name="Calcium",         basis="Ca",  source="manual"}
hydros_input_magnesium_ppm{name="Magnesium",     basis="Mg",  source="manual"}
hydros_input_specific_gravity{name="Salinity",   basis="SG",  source="manual"}
hydros_input_salinity_ppt{name="Salinity", basis="SG-derived", source="manual"}
hydros_input_measured_timestamp_seconds{name="Phosphate", source="manual"}
```

Salinity is the one parameter that cannot share the probe's name: a probe
reports ppt (~35) and a refractometer reads specific gravity (~1.026), so the
measured value keeps its own metric and a derived ppt series is published
beside it.

Matching names is deliberate. If a controller API later reports the same
parameter, `max by (name) (...)` merges both into one continuous series, and
`{source=""} or {source="manual"}` prefers the API where it exists:

```promql
max by (name) (hydros_input_phosphate_ppm{source=""})
  or max by (name) (hydros_input_phosphate_ppm{source="manual"})
```

The measurement basis (PO4 vs P, NO3 vs N, dKH vs meq/L) is stored per reading,
because it is the one thing that cannot be reconstructed later. The label is
`basis` rather than `compound` because dKH and specific gravity are not
compounds; calcium and magnesium have only the one basis each but still
record it.

## Routes

| Route | |
|---|---|
| `GET /` | Entry form and recent readings |
| `POST /` | Record a reading |
| `GET /metrics` | Latest value per parameter |
| `GET /healthz` | Liveness |

## Running

```sh
pip install -r requirements.txt
python -m reeflog --db ./reef-log.db --port 8080
```

| Environment | Default |
|---|---|
| `REEFLOG_DB` | `/data/reef-log.db` |
| `REEFLOG_PORT` | `8080` |
| `REEFLOG_LOG_LEVEL` | `INFO` |
| `TZ` | container default — decides how the form's local time is read |

The container runs as uid 1000 with a read-only root filesystem; only `/data`
needs to be writable.

There is no authentication. Put it behind an authenticating proxy; `POST`
rejects cross-origin submissions so a proxy session cookie cannot be replayed
from another site.

## Tests

```sh
pip install -r requirements-dev.txt
pytest -q
```
