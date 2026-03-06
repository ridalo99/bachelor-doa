"""
Array geometry + coordinate convention.

Convention:
- 0° points +y (towards M3/M4)
- 90° points +x (towards M1/M4)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

C = 343.0

MIC_TO_CH: Dict[str, int] = {"M1": 2, "M2": 0, "M3": 1, "M4": 3}
MIC_ORDER = ["M1", "M2", "M3", "M4"]
CH_ORDER = [MIC_TO_CH[m] for m in MIC_ORDER]

a = 0.175
MICS = np.array(
    [
        [+a, -a],  # M1 bottom-right
        [-a, -a],  # M2 bottom-left
        [-a, +a],  # M3 top-left
        [+a, +a],  # M4 top-right
    ],
    dtype=float,
)

PAIRS_ALL: List[Tuple[int, int]] = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def pair_max_tau(i: int, j: int, margin: float = 1e-4) -> float:
    d = float(np.linalg.norm(MICS[i] - MICS[j]))
    return d / C + margin


def unit_direction(theta_deg: float) -> np.ndarray:
    rad = np.deg2rad(float(theta_deg))
    return np.array([np.sin(rad), np.cos(rad)], dtype=np.float64)  # 0°=+y, 90°=+x
