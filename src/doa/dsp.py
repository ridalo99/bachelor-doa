"""
DSP helpers: bandpass, energy envelope, and window cropping.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
from scipy.signal import butter, sosfiltfilt


def bandpass_sos(x: np.ndarray, fs: int, lo: float, hi: float, order: int = 4) -> np.ndarray:
    lo = max(1.0, float(lo))
    hi = min(float(hi), fs / 2.0 - 50.0)
    if not (lo < hi):
        return x
    sos = butter(order, [lo, hi], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, x, axis=0)
def short_time_rms(x: np.ndarray, fs: int, win_s: float, hop_s: float) -> Tuple[np.ndarray, np.ndarray]:
    win = max(1, int(win_s * fs))
    hop = max(1, int(hop_s * fs))
    n = x.shape[0]
    times: List[float] = []
    env: List[float] = []
    for s in range(0, n - win + 1, hop):
        seg = x[s : s + win]
        env.append(float(np.sqrt(np.mean(seg**2))))
        times.append((s + win / 2) / fs)
    return np.array(times, dtype=float), np.array(env, dtype=float)


def clip_center_window(center: int, fs: int, n: int, win_s: float) -> Tuple[int, int]:
    half = int(win_s * fs)
    s = max(0, center - half)
    t = min(n, center + half)
    if (t - s) < max(256, half):
        s = max(0, center - max(256, half))
        t = min(n, center + max(256, half))
    return s, t
def apply_offset(theta_raw: float, theta_offset_deg: float) -> float:
    return float((float(theta_raw) + float(theta_offset_deg)) % 360.0)

