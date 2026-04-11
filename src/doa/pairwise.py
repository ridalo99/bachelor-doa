from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .dsp import apply_offset, clip_center_window
from .geometry import CH_ORDER, PAIRS_ALL
from .pipeline import find_topk_loud_windows
from .srp import srp_phat_scan


@dataclass(frozen=True)
class PairwiseDoaResult:
    pair: Tuple[int, int]
    theta_raw: float
    theta_deg: float
    score: float
    confidence: float
    topk: List[Tuple[float, float]]
    center_time_s: float


@dataclass(frozen=True)
class PairwiseEventWindow:
    mode: str
    window_t0: float
    window_t1: float
    expanded_t0: float
    expanded_t1: float
    center_time_s: float
    rms: float


def eval_center_single_pair(
    x: np.ndarray,
    fs: int,
    center_time_s: float,
    win_s: float,
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
    theta_offset_deg: float,
    pair: Tuple[int, int],
) -> PairwiseDoaResult:
    center = int(float(center_time_s) * fs)
    s, t = clip_center_window(center, fs, x.shape[0], float(win_s))
    xw = x[s:t][:, CH_ORDER]

    grid = np.arange(0, 360, 1, dtype=np.float64)
    _, best_theta, conf, topk = srp_phat_scan(
        xw=xw,
        fs=fs,
        pairs=[pair],
        theta_grid_deg=grid,
        n_subbands=int(srp_subband),
        sym_pair=bool(sym_pair),
        source_distance_m=source_distance_m,
    )
    score = float(topk[0][1])
    theta_deg = apply_offset(best_theta, float(theta_offset_deg))
    return PairwiseDoaResult(
        pair=pair,
        theta_raw=float(best_theta),
        theta_deg=float(theta_deg),
        score=float(score),
        confidence=float(conf),
        topk=topk,
        center_time_s=float(center_time_s),
    )


def eval_center_all_pairs(
    x: np.ndarray,
    fs: int,
    center_time_s: float,
    win_s: float,
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
    theta_offset_deg: float,
    pairs: Sequence[Tuple[int, int]] = PAIRS_ALL,
) -> List[PairwiseDoaResult]:
    results = [
        eval_center_single_pair(
            x=x,
            fs=fs,
            center_time_s=float(center_time_s),
            win_s=float(win_s),
            srp_subband=int(srp_subband),
            sym_pair=bool(sym_pair),
            source_distance_m=source_distance_m,
            theta_offset_deg=float(theta_offset_deg),
            pair=pair,
        )
        for pair in pairs
    ]
    return sorted(results, key=lambda r: (r.confidence, r.score), reverse=True)


def pick_event_window(
    x: np.ndarray,
    fs: int,
    x_mono: np.ndarray,
    *,
    time_range: Optional[Tuple[float, float]],
    auto_window: bool,
    auto_window_len_s: float,
    auto_window_hop_s: float,
    auto_window_expand_s: float,
    auto_window_min_gap_s: float,
) -> PairwiseEventWindow:
    file_tmax = float(x.shape[0] / fs)

    if time_range is not None:
        t0, t1 = map(float, time_range)
        t0 = max(0.0, t0)
        t1 = min(file_tmax, t1)
        if t1 <= t0:
            raise ValueError("invalid --time-range")
        center = 0.5 * (t0 + t1)
        seg = x_mono[int(t0 * fs): int(t1 * fs)]
        rms = float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0
        return PairwiseEventWindow(
            mode="time-range",
            window_t0=float(t0),
            window_t1=float(t1),
            expanded_t0=float(t0),
            expanded_t1=float(t1),
            center_time_s=float(center),
            rms=float(rms),
        )

    if auto_window:
        windows = find_topk_loud_windows(
            x_mono=x_mono,
            fs=fs,
            t0=0.0,
            t1=file_tmax,
            win_s=float(auto_window_len_s),
            hop_s=float(auto_window_hop_s),
            topk=1,
            min_gap_s=float(auto_window_min_gap_s),
        )
        if not windows:
            raise RuntimeError("auto-window found no event")
        w0, w1, wrms = windows[0]
        ext0 = max(0.0, w0 - float(auto_window_expand_s))
        ext1 = min(file_tmax, w1 + float(auto_window_expand_s))
        center = 0.5 * (ext0 + ext1)
        return PairwiseEventWindow(
            mode="auto-window",
            window_t0=float(w0),
            window_t1=float(w1),
            expanded_t0=float(ext0),
            expanded_t1=float(ext1),
            center_time_s=float(center),
            rms=float(wrms),
        )

    raise ValueError("pick_event_window needs either time_range or auto_window=True")


def format_pair(pair: Tuple[int, int]) -> str:
    return f"pair({pair[0]},{pair[1]})"