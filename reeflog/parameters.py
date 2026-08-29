"""
Metric names deliberately match what the HYDROS exporter would emit if CoralVue
ever exposed these readings, so the two histories merge on `max by (name)`
instead of living under separate names forever. Only this app sets
source="manual"; the exporter's own series carry no source label.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Parameter:
    key: str
    name: str
    compound: str
    metric: str
    helptext: str
    minimum: float
    maximum: float

    def check(self, value: float) -> None:
        if not self.minimum <= value <= self.maximum:
            raise ValueError(
                f"{self.name} must be between {self.minimum} and {self.maximum} ppm"
            )


PARAMETERS = {
    p.key: p
    for p in (
        Parameter(
            key="phosphate",
            name="Phosphate",
            compound="PO4",
            metric="hydros_input_phosphate_ppm",
            helptext="Phosphate as PO4 in parts per million.",
            minimum=0.0,
            maximum=10.0,
        ),
        Parameter(
            key="nitrate",
            name="Nitrate",
            compound="NO3",
            metric="hydros_input_nitrate_ppm",
            helptext="Nitrate as NO3 in parts per million.",
            minimum=0.0,
            maximum=500.0,
        ),
    )
}

MEASURED_AT_METRIC = "hydros_input_measured_timestamp_seconds"
MEASURED_AT_HELP = "Unix time the reading was actually measured."
SOURCE = "manual"
