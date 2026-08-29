from prometheus_client.core import GaugeMetricFamily

from .parameters import MEASURED_AT_HELP, MEASURED_AT_METRIC, PARAMETERS, SOURCE
from .store import Store


class ReadingCollector:
    """
    Publishes the latest reading per parameter. The value is held between tests
    rather than expiring, because a water parameter genuinely persists -- unlike
    live telemetry, where a stale value would be fiction. The companion
    measured-at metric is what keeps the real test time visible.
    """

    def __init__(self, store: Store) -> None:
        self._store = store

    def describe(self):
        return []

    def collect(self):
        latest = self._store.latest()
        measured = GaugeMetricFamily(
            MEASURED_AT_METRIC, MEASURED_AT_HELP, labels=["name", "source"]
        )
        for key, parameter in PARAMETERS.items():
            reading = latest.get(key)
            if reading is None:
                continue
            gauge = GaugeMetricFamily(
                parameter.metric, parameter.helptext, labels=["name", "compound", "source"]
            )
            gauge.add_metric(
                [parameter.name, parameter.compound, SOURCE], reading.value
            )
            yield gauge
            measured.add_metric([parameter.name, SOURCE], reading.measured_at)
        yield measured
