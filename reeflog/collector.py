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
            yield _gauge(parameter.metric, parameter.helptext, parameter.name,
                         parameter.basis, reading.value)
            for derived in parameter.derived:
                yield _gauge(derived.metric, derived.helptext, parameter.name,
                             derived.basis, derived.convert(reading.value))
            measured.add_metric([parameter.name, SOURCE], reading.measured_at)
        yield measured


def _gauge(metric, helptext, name, basis, value):
    gauge = GaugeMetricFamily(metric, helptext, labels=["name", "basis", "source"])
    gauge.add_metric([name, basis, SOURCE], value)
    return gauge
