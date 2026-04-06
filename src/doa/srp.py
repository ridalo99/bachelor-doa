"""
SRP-PHAT scan and expected time-shift models.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .gcc import gcc_phat_cc_subband, linear_interp_centered
from .geometry import C, MICS, pair_max_tau, unit_direction


def expected_shift_samples(
    i: int,
    j: int,
    fs: int,
    u: np.ndarray,
    source_distance_m: Optional[float],
) -> float:
    if source_distance_m is None:
        dij = MICS[j] - MICS[i]
        return float(-(dij @ u) / C * fs)
    p = float(source_distance_m) * u
    di = float(np.linalg.norm(p - MICS[i]))
    dj = float(np.linalg.norm(p - MICS[j]))
    return float(((di - dj) / C ) * fs)


def srp_phat_scan(
    xw: np.ndarray,
    fs: int,
    pairs: Sequence[Tuple[int, int]],
    theta_grid_deg: np.ndarray,
    n_subbands: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
) -> Tuple[np.ndarray, float, float, List[Tuple[float, float]]]:
    eps = 1e-12
    scores = np.zeros_like(theta_grid_deg, dtype=np.float64)

    n_fft = xw.shape[0] + xw.shape[0]
    n_rfft = n_fft // 2 + 1
    bins = np.linspace(1, n_rfft, num=max(2, int(n_subbands) + 1), dtype=int)

    cc_map: Dict[Tuple[int, int, int], Tuple[np.ndarray, int]] = {}
    for i, j in pairs:
        max_shift = int(np.ceil(pair_max_tau(i, j) * fs))
        for b in range(len(bins) - 1):
            cc = gcc_phat_cc_subband(xw[:, j], xw[:, i], max_shift, bins[b], bins[b + 1])
            cc_map[(i, j, b)] = (cc, max_shift)

    for k, theta in enumerate(theta_grid_deg):
        u = unit_direction(float(theta))
        s = 0.0
        for (i, j) in pairs:
            shift = expected_shift_samples(i=i, j=j, fs=fs, u=u, source_distance_m=source_distance_m)
            for b in range(len(bins) - 1):
                cc, max_shift = cc_map[(i, j, b)]
                sh = float(np.clip(shift, -max_shift, max_shift))
                v = linear_interp_centered(cc, sh, max_shift)
                if sym_pair:
                    v2 = linear_interp_centered(cc, -sh, max_shift)
                    v = max(v, v2)
                s += v
        scores[k] = s
    idx = int(np.argmax(scores))
    best = float(scores[idx])
    sorted_scores = np.sort(scores)[::-1]
    second = float(sorted_scores[1]) if sorted_scores.size > 1 else -np.inf
    confidence = float((best - second) / (abs(best) + eps))
    top_idx = np.argsort(scores)[::-1][:5]
    topk = [(float(theta_grid_deg[i]), float(scores[i])) for i in top_idx]
    best_theta = float(theta_grid_deg[idx])
    return scores, best_theta, confidence, topk