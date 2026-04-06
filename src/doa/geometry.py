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

MIC_TO_CH: Dict[str, int] = {"M1": 1, "M2": 0, "M3": 2, "M4": 3}
MIC_ORDER = ["M1", "M2", "M3", "M4"]
CH_ORDER = [MIC_TO_CH[m] for m in MIC_ORDER]
W = 0.21   # M1 <-> M4 horizontal distance (m)
H_right = 0.215  # M1 -> M2 vertical distance (m)
H_left  = 0.215   # M4 -> M3 vertical distance (m)
# Define points in a local frame, then center to the array centroid
M1 = np.array([+W / 2.0, -H_right / 2.0])  # bottom-right
M2 = np.array([+W / 2.0, +H_right / 2.0])  # top-right
M4 = np.array([-W / 2.0, -H_left / 2.0])   # bottom-left
M3 = np.array([-W / 2.0, +H_left / 2.0])   # top-left

# NOTE: columns must match MIC_ORDER: M1, M2, M3, M4
MICS = np.array([M1, M2, M3, M4], dtype=float)

PAIRS_ALL: List[Tuple[int, int]] = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def pair_max_tau(i: int, j: int, margin: float = 1e-4) -> float:
    d = float(np.linalg.norm(MICS[i] - MICS[j]))
    return d / C + margin


def unit_direction(theta_deg: float) -> np.ndarray:
    rad = np.deg2rad(float(theta_deg))
    return np.array([-np.sin(rad), np.cos(rad)], dtype=np.float64)  # 0°=+y (front), 90°=-x (left), 270°=+x (right)