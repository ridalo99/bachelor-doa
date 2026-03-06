"""
Calibration: save/load offset JSON and compute offset from reference measurements.
"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple

import numpy as np

from .aggregate import circular_mean_deg_weighted
def save_calibration(path: str, theta_offset_deg: float, refs: List[Dict[str, float]]) -> None:
    payload = {
        "theta_offset_deg": float(theta_offset_deg),
        "refs": refs,
        "notes": "theta_offset_deg is applied as (theta_raw + offset) % 360",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_calibration(path: str) -> float:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return float(payload["theta_offset_deg"])


def compute_offset_from_refs(refs_known_measured: List[Tuple[float, float]]) -> float:
    errs = np.array([(float(known) - float(raw)) % 360.0 for (known, raw) in refs_known_measured], dtype=float)
    return float(circular_mean_deg_weighted(errs, np.ones_like(errs)))