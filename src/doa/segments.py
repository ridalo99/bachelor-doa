"""
Tone segment detection used by --auto-burst.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from .dsp import bandpass_sos, short_time_rms


def detect_tone_segments(
    x_mono: np.ndarray,
    fs: int,
    tone_hz: float,
    tone_bw_hz: float,
    env_win_s: float,
    env_hop_s: float,
    thr_ratio: float,
    min_len_s: float,
    pad_s: float,
) -> List[Tuple[float, float]]:
    lo = max(1.0, float(tone_hz) - float(tone_bw_hz) / 2.0)
    hi = min(fs / 2.0 - 50.0, float(tone_hz) + float(tone_bw_hz) / 2.0)

    y = bandpass_sos(x_mono[:, None], fs, lo, hi, order=6)[:, 0]
    t, env = short_time_rms(y, fs, win_s=float(env_win_s), hop_s=float(env_hop_s))
    if env.size == 0:
        return []

    thr = float(np.median(env) * float(thr_ratio))
    active = env > thr

    segs: List[Tuple[float, float]] = []
    start: Optional[int] = None
    for i, a_ in enumerate(active):
        if a_ and start is None:
            start = i
        if ((not a_) or (i == len(active) - 1)) and start is not None:
            end = i if not a_ else i + 1
            t0 = float(t[start])
            t1 = float(t[end - 1])
            if (t1 - t0) >= float(min_len_s):
                t0p = max(0.0, t0 - float(pad_s))
                t1p = min(float(len(x_mono) / fs), t1 + float(pad_s))
                segs.append((t0p, t1p))
            start = None        
    if not segs:
        return []

    segs.sort()
    merged: List[Tuple[float, float]] = [segs[0]]
    for t0, t1 in segs[1:]:
        p0, p1 = merged[-1]
        if t0 <= p1 + 0.05:
            merged[-1] = (p0, max(p1, t1))
        else:
            merged.append((t0, t1))
    return merged


def auto_segment_centers(
    x_mono: np.ndarray,
    fs: int,
    tone_hz: float,
    tone_bw_hz: float,
    seg_thr_ratio: float,
    seg_min_len_s: float,
    seg_pad_s: float,
) -> List[Tuple[float, float, float]]:
    segs = detect_tone_segments(
        x_mono=x_mono,
        fs=fs, 
        tone_hz=float(tone_hz),
        tone_bw_hz=float(tone_bw_hz),
        env_win_s=0.05,
        env_hop_s=0.01,
        thr_ratio=float(seg_thr_ratio),
        min_len_s=float(seg_min_len_s),
        pad_s=float(seg_pad_s),
    )
    if not segs:
        return []

    lo = max(1.0, float(tone_hz) - float(tone_bw_hz) / 2.0)
    hi = min(fs / 2.0 - 50.0, float(tone_hz) + float(tone_bw_hz) / 2.0)
    y = bandpass_sos(x_mono[:, None], fs, lo, hi, order=6)[:, 0]

    out: List[Tuple[float, float, float]] = []
    for (t0, t1) in segs:
        s = int(max(0.0, float(t0)) * fs)
        e = int(min(float(len(y) / fs), float(t1)) * fs)
        if e - s < int(0.02 * fs):
            continue
        times, env = short_time_rms(y[s:e], fs, win_s=0.05, hop_s=0.01)
        if env.size == 0:
            ct = 0.5 * (float(t0) + float(t1))
        else:
             ct = float((s / fs) + times[int(np.argmax(env))])
        out.append((float(t0), float(t1), float(ct)))
    return out
       