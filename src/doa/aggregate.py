"""
Aggregation for multi-window DOA.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def circular_mean_deg_weighted(angles_deg: np.ndarray, weights: np.ndarray) -> float:
    a = np.deg2rad(angles_deg.astype(float))
    w = np.maximum(1e-12, weights.astype(float))
    s = float(np.sum(w * np.sin(a)))
    c = float(np.sum(w * np.cos(a)))
    return float(np.degrees(np.arctan2(s, c)) % 360.0)
def cluster_quality_mode_tol(
    angles_deg: np.ndarray,
    weights: np.ndarray,
    tol_deg: int = 3,
) -> Tuple[float, float, float]:
    a = (np.round(np.asarray(angles_deg)) % 360).astype(int)
    w = np.maximum(1e-12, np.asarray(weights, dtype=float))

    hist = np.zeros(360, dtype=float)
    for ai, wi in zip(a, w):
        hist[ai] += float(wi)

    k = int(max(0, tol_deg))
    if k > 0:
        smooth = np.zeros_like(hist)
        for shift in range(-k, k + 1):
            smooth += np.roll(hist, shift)
    else:
        smooth = hist.copy()

    total = float(np.sum(hist))
    if total <= 0.0:
        return 0.0, 0.0, 0.0
    best_idx = int(np.argmax(smooth))
    best_w = float(smooth[best_idx])

    mask = np.ones(360, dtype=bool)
    for shift in range(-k, k + 1):
        mask[(best_idx + shift) % 360] = False
    second_w = float(np.max(smooth[mask])) if np.any(mask) else 0.0

    dom = best_w / total
    sec = second_w / total
    return float(best_idx), float(dom), float(sec)