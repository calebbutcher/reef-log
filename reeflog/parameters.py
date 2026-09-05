"""
Metric names deliberately match what the HYDROS exporter would emit if a probe
or tester ever reported the same parameter, so the two histories merge on
`max by (name)` instead of living under separate names forever. Only this app
sets source="manual"; the exporter's own series carry no source label.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

# Specific gravity is what a refractometer reads; a HYDROS salinity probe
# reports ppt. Publishing SG under the ppt metric would merge 1.026 with 35 and
# produce nonsense, so SG is stored as measured and ppt is derived alongside it.
#
# Linear through two reference points for SG at 25 C referred to water at 25 C:
# 1.0226 -> 30 ppt and 1.0264 -> 35 ppt. Checks out against a third, 1.0210 ->
# 27.9 vs a published 28. Good to ~0.2 ppt across the reef range, and wrong if
# the refractometer is calibrated at another temperature.
SG_REFERENCE = (1.0226, 30.0)
SG_PPT_PER_UNIT = 5.0 / (1.0264 - 1.0226)


def sg_to_ppt(sg: float) -> float:
    base_sg, base_ppt = SG_REFERENCE
    return base_ppt + (sg - base_sg) * SG_PPT_PER_UNIT


@dataclass(frozen=True)
class Derived:
    metric: str
    helptext: str
    basis: str
    convert: Callable[[float], float]


@dataclass(frozen=True)
class Parameter:
    key: str
    name: str
    basis: str
    metric: str
    helptext: str
    minimum: float
    maximum: float
    derived: tuple[Derived, ...] = field(default_factory=tuple)

    def check(self, value: float) -> None:
        if not self.minimum <= value <= self.maximum:
            raise ValueError(
                f"{self.name} must be between {self.minimum:g} and {self.maximum:g}"
            )


PARAMETERS = {
    p.key: p
    for p in (
        Parameter(
            key="phosphate",
            name="Phosphate",
            basis="PO4",
            metric="hydros_input_phosphate_ppm",
            helptext="Phosphate as PO4 in parts per million.",
            minimum=0.0,
            maximum=10.0,
        ),
        Parameter(
            key="nitrate",
            name="Nitrate",
            basis="NO3",
            metric="hydros_input_nitrate_ppm",
            helptext="Nitrate as NO3 in parts per million.",
            minimum=0.0,
            maximum=500.0,
        ),
        Parameter(
            key="alkalinity",
            name="Alkalinity",
            basis="dKH",
            # The name the exporter already reserves for a HYDROS alkalinity
            # tester, so a manual entry and a future Alky merge untouched.
            metric="hydros_input_alkalinity_dkh",
            helptext="Alkalinity in degrees of carbonate hardness.",
            minimum=0.0,
            maximum=25.0,
        ),
        Parameter(
            key="calcium",
            name="Calcium",
            # Calcium is only ever reported as elemental Ca in ppm, so unlike
            # phosphate or nitrate there is no competing basis to record. The
            # column is still populated so every row states its own.
            basis="Ca",
            metric="hydros_input_calcium_ppm",
            helptext="Calcium as Ca in parts per million.",
            minimum=0.0,
            maximum=1000.0,
        ),
        Parameter(
            key="salinity",
            name="Salinity",
            basis="SG",
            metric="hydros_input_specific_gravity",
            helptext="Specific gravity as read on a refractometer.",
            minimum=1.0,
            maximum=1.045,
            derived=(
                Derived(
                    metric="hydros_input_salinity_ppt",
                    helptext="Salinity in parts per thousand, derived from specific gravity.",
                    basis="SG-derived",
                    convert=sg_to_ppt,
                ),
            ),
        ),
    )
}

MEASURED_AT_METRIC = "hydros_input_measured_timestamp_seconds"
MEASURED_AT_HELP = "Unix time the reading was actually measured."
SOURCE = "manual"
