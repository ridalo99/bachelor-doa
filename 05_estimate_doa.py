# /Users/rida/BAchelor_Arbeit/05_estimate_doa.py
"""
SRP-PHAT DOA estimation for a 4-mic square array (works for far-field and near-field).

What this script provides (BA-friendly):
- Far-field (plane-wave) model for large distances (default).
- Near-field (spherical) model when source distance is known (--source-distance-m).
- Robust multi-window evaluation over a time interval (recommended for broadband/noise phases).
- Tone-segment auto selection (--auto-burst) that does NOT depend on absolute timestamps.
- Calibration workflow that computes and saves an angle offset to JSON (no manual offset needed afterwards).
- Aggregation options for multi-window: weighted MODE (default, robust) or weighted circular MEAN.

Coordinate convention (matches your definition):
- 0° points "up" towards M3/M4.
- 90° points "right" towards M1/M4.

Mic layout (square, side length 0.35 m):
- a = 0.175 m is center-to-mic distance.
- M1 bottom-right, M2 bottom-left, M3 top-left, M4 top-right
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

C = 343.0  # speed of sound (m/s)

# Channel mapping:
# Mic1->ch2, Mic2->ch0, Mic3->ch1, Mic4->ch3
MIC_TO_CH: Dict[str, int] = {"M1": 2, "M2": 0, "M3": 1, "M4": 3}
MIC_ORDER = ["M1", "M2", "M3", "M4"]
CH_ORDER = [MIC_TO_CH[m] for m in MIC_ORDER]

# Geometry (square). a is center->mic distance in meters. Side length = 2a = 0.35 m
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


@dataclass(frozen=True)
class DoaResult:
    theta_raw: float
    score: float
    confidence: float
    topk: List[Tuple[float, float]]
    center_time_s: float


# ----------------------------
# Basics
# ----------------------------
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


def pair_max_tau(i: int, j: int, margin: float = 1e-4) -> float:
    d = float(np.linalg.norm(MICS[i] - MICS[j]))
    return d / C + margin


def _clip_window(center: int, fs: int, n: int, win_s: float) -> Tuple[int, int]:
    half = int(win_s * fs)
    s = max(0, center - half)
    t = min(n, center + half)
    if (t - s) < max(256, half):
        s = max(0, center - max(256, half))
        t = min(n, center + max(256, half))
    return s, t


def _apply_offset(theta_raw: float, theta_offset_deg: float) -> float:
    return float((theta_raw + theta_offset_deg) % 360)


# ----------------------------
# Tone segment detection for --auto-burst
# ----------------------------
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
    lo = max(1.0, tone_hz - tone_bw_hz / 2.0)
    hi = min(fs / 2.0 - 50.0, tone_hz + tone_bw_hz / 2.0)

    y = bandpass_sos(x_mono[:, None], fs, lo, hi, order=6)[:, 0]
    t, env = short_time_rms(y, fs, win_s=env_win_s, hop_s=env_hop_s)
    if env.size == 0:
        return []

    thr = float(np.median(env) * thr_ratio)
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
            if (t1 - t0) >= min_len_s:
                t0p = max(0.0, t0 - pad_s)
                t1p = min(float(len(x_mono) / fs), t1 + pad_s)
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

    lo = max(1.0, tone_hz - tone_bw_hz / 2.0)
    hi = min(fs / 2.0 - 50.0, tone_hz + tone_bw_hz / 2.0)
    y = bandpass_sos(x_mono[:, None], fs, lo, hi, order=6)[:, 0]

    out: List[Tuple[float, float, float]] = []
    for (t0, t1) in segs:
        s = int(max(0.0, t0) * fs)
        e = int(min(float(len(y) / fs), t1) * fs)
        if e - s < int(0.02 * fs):
            continue
        times, env = short_time_rms(y[s:e], fs, win_s=0.05, hop_s=0.01)
        if env.size == 0:
            ct = 0.5 * (t0 + t1)
        else:
            ct = float((s / fs) + times[int(np.argmax(env))])
        out.append((float(t0), float(t1), float(ct)))
    return out


# ----------------------------
# GCC-PHAT + SRP-PHAT core
# ----------------------------
def _linear_interp_centered(cc: np.ndarray, shift: float, max_shift: int) -> float:
    x = shift + max_shift
    if x <= 0:
        return float(cc[0])
    if x >= len(cc) - 1:
        return float(cc[-1])
    i0 = int(np.floor(x))
    frac = x - i0
    return float((1.0 - frac) * cc[i0] + frac * cc[i0 + 1])


def gcc_phat_cc_subband(sig: np.ndarray, ref: np.ndarray, max_shift: int, fbin_lo: int, fbin_hi: int) -> np.ndarray:
    sig = sig - float(np.mean(sig))
    ref = ref - float(np.mean(ref))

    n = len(sig) + len(ref)
    SIG = np.fft.rfft(sig, n=n)
    REF = np.fft.rfft(ref, n=n)

    mask = np.zeros_like(SIG, dtype=np.float64)
    fbin_lo = max(0, int(fbin_lo))
    fbin_hi = min(int(fbin_hi), SIG.shape[0])
    if fbin_hi <= fbin_lo + 1:
        fbin_lo = 0
        fbin_hi = SIG.shape[0]
    mask[fbin_lo:fbin_hi] = 1.0

    R = SIG * np.conj(REF)
    R /= (np.abs(R) + 1e-12)
    R *= mask

    cc = np.fft.irfft(R, n=n)
    cc = np.concatenate((cc[-max_shift:], cc[: max_shift + 1]))
    return cc.astype(np.float64, copy=False)


def _expected_shift_samples(
    i: int,
    j: int,
    fs: int,
    u: np.ndarray,
    source_distance_m: Optional[float],
) -> float:
    if source_distance_m is None:
        dij = MICS[j] - MICS[i]
        return float((dij @ u) / C * fs)

    # Near-field (spherical): source position p = r*u
    p = float(source_distance_m) * u
    di = float(np.linalg.norm(p - MICS[i]))
    dj = float(np.linalg.norm(p - MICS[j]))
    return float(((dj - di) / C) * fs)


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
        rad = np.deg2rad(theta)
        u = np.array([np.sin(rad), np.cos(rad)], dtype=np.float64)  # 0°=+y, 90°=+x

        s = 0.0
        for (i, j) in pairs:
            shift = _expected_shift_samples(i=i, j=j, fs=fs, u=u, source_distance_m=source_distance_m)

            for b in range(len(bins) - 1):
                cc, max_shift = cc_map[(i, j, b)]
                sh = float(np.clip(shift, -max_shift, max_shift))
                v = _linear_interp_centered(cc, sh, max_shift)
                if sym_pair:
                    v2 = _linear_interp_centered(cc, -sh, max_shift)
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


def eval_center(
    x: np.ndarray,
    fs: int,
    center_time_s: float,
    win_s: float,
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
) -> DoaResult:
    center = int(center_time_s * fs)
    s, t = _clip_window(center, fs, x.shape[0], win_s)
    xw = x[s:t][:, CH_ORDER]

    grid = np.arange(0, 360, 1, dtype=np.float64)
    _, best_theta, conf, topk = srp_phat_scan(
        xw=xw,
        fs=fs,
        pairs=PAIRS_ALL,
        theta_grid_deg=grid,
        n_subbands=int(srp_subband),
        sym_pair=bool(sym_pair),
        source_distance_m=source_distance_m,
    )
    score = float(topk[0][1])
    return DoaResult(
        theta_raw=float(best_theta),
        score=float(score),
        confidence=float(conf),
        topk=topk,
        center_time_s=float(center_time_s),
    )


# ----------------------------
# Multi-window aggregation (BA-friendly)
# ----------------------------
def circular_mean_deg_weighted(angles_deg: np.ndarray, weights: np.ndarray) -> float:
    a = np.deg2rad(angles_deg.astype(float))
    w = np.maximum(1e-12, weights.astype(float))
    s = np.sum(w * np.sin(a))
    c = np.sum(w * np.cos(a))
    return float(np.degrees(np.arctan2(s, c)) % 360)


def weighted_mode_deg(angles_deg: np.ndarray, weights: np.ndarray) -> float:
    """
    Weighted mode on a 1° grid (robust for SRP 1° scanning).
    """
    a_int = (np.round(angles_deg).astype(int)) % 360
    w = np.maximum(1e-12, weights.astype(float))
    acc = np.zeros(360, dtype=float)
    for ai, wi in zip(a_int, w):
        acc[ai] += float(wi)
    return float(int(np.argmax(acc)))


def multi_window_doa(
    x: np.ndarray,
    fs: int,
    t0: float,
    t1: float,
    win_s: float,
    hop_s: float,
    srp_subband: int,
    sym_pair: bool,
    theta_offset_deg: float,
    ambig_eps: float,
    agg: str,
    source_distance_m: Optional[float],
    debug: bool,
) -> Tuple[float, int, int]:
    t0 = float(max(0.0, t0))
    t1 = float(min(float(x.shape[0] / fs), t1))
    if t1 <= t0:
        raise ValueError("multi-range invalid: t1 <= t0")

    centers = np.arange(t0 + win_s, t1 - win_s, float(hop_s), dtype=float)
    if centers.size == 0:
        raise ValueError("multi-range too short for given win-s/hop-s")

    results: List[DoaResult] = [
        eval_center(
            x=x,
            fs=fs,
            center_time_s=float(ct),
            win_s=win_s,
            srp_subband=srp_subband,
            sym_pair=sym_pair,
            source_distance_m=source_distance_m,
        )
        for ct in centers
    ]

    good = [r for r in results if r.confidence >= float(ambig_eps)]
    used = good if good else results

    angles = np.array([_apply_offset(r.theta_raw, theta_offset_deg) for r in used], dtype=float)
    weights = np.array([max(1e-6, r.confidence) for r in used], dtype=float)

    if agg == "mode":
        final_theta = weighted_mode_deg(angles, weights)
    elif agg == "mean":
        final_theta = circular_mean_deg_weighted(angles, weights)
    else:
        raise ValueError(f"unknown agg: {agg}")

    if debug:
        print("Multi-window results (top 12 by confidence):")
        top = sorted(results, key=lambda r: (r.confidence, r.score), reverse=True)[:12]
        for r in top:
            th = _apply_offset(r.theta_raw, theta_offset_deg)
            print(f"  t={r.center_time_s:.2f}s -> theta={th:.1f}° raw={r.theta_raw:.1f}° conf={r.confidence:.4f} score={r.score:.6f}")
        print(f"Multi-window: used {len(used)}/{len(results)} windows (ambig_eps={ambig_eps:.3f}, agg={agg})")

    return float(final_theta), len(used), len(results)


# ----------------------------
# Calibration (no more manual offset)
# ----------------------------
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
    """
    refs_known_measured: [(known_deg, measured_raw_deg), ...]
    offset is circular-mean of (known - measured_raw) mod 360.
    """
    errs = np.array([(known - raw) % 360 for (known, raw) in refs_known_measured], dtype=float)
    return float(circular_mean_deg_weighted(errs, np.ones_like(errs)))


def calibrate(
    out_json: str,
    items: List[str],
    win_s: float,
    bandpass: Optional[Tuple[float, float]],
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
    # selection method:
    use_multi_range: Optional[Tuple[float, float]],
    hop_s: float,
    ambig_eps: float,
    agg: str,
    # tone auto-burst params:
    tone_hz: float,
    tone_bw_hz: float,
    seg_thr_ratio: float,
    seg_min_len_s: float,
    seg_pad_s: float,
    debug: bool,
) -> None:
    if len(items) < 2:
        raise SystemExit("Calibration needs at least two refs: OUT_JSON wav=deg wav=deg ...")

    refs: List[Dict[str, float]] = []
    pairs: List[Tuple[float, float]] = []

    for it in items:
        if "=" not in it:
            raise SystemExit(f"Bad calibration item '{it}'. Use wav=deg")
        wav, deg_s = it.split("=", 1)
        known = float(deg_s)

        x, fs = sf.read(wav, always_2d=True)
        if bandpass is not None:
            x = bandpass_sos(x, fs, float(bandpass[0]), float(bandpass[1]))
        x_mono = np.mean(x, axis=1).astype(np.float64)

        if use_multi_range is not None:
            t0, t1 = use_multi_range
            # raw offset = 0 in calibration, we want theta_raw estimate from the aggregated result.
            # We'll run multi-window with offset 0, then reverse-apply offset=0 (no-op).
            # This yields final theta in global frame; for calibration we want measured_raw approx,
            # but multi-window returns already (raw+0)%360, so treat that as measured_raw.
            measured, used, total = multi_window_doa(
                x=x,
                fs=fs,
                t0=float(t0),
                t1=float(t1),
                win_s=float(win_s),
                hop_s=float(hop_s),
                srp_subband=int(srp_subband),
                sym_pair=bool(sym_pair),
                theta_offset_deg=0.0,
                ambig_eps=float(ambig_eps),
                agg=agg,
                source_distance_m=source_distance_m,
                debug=debug,
            )
            measured_raw = float(measured)
            if debug:
                print(f"[calib] {wav}: known={known:.1f} measured_raw~={measured_raw:.1f} (multi-window used {used}/{total})")
        else:
            centers = auto_segment_centers(
                x_mono=x_mono,
                fs=fs,
                tone_hz=float(tone_hz),
                tone_bw_hz=float(tone_bw_hz),
                seg_thr_ratio=float(seg_thr_ratio),
                seg_min_len_s=float(seg_min_len_s),
                seg_pad_s=float(seg_pad_s),
            )
            if not centers:
                raise SystemExit(f"Calibration: no tone segments found in {wav}. Try --calib-multi-range for broadband.")
            cand = [
                eval_center(
                    x=x,
                    fs=fs,
                    center_time_s=ct,
                    win_s=float(win_s),
                    srp_subband=int(srp_subband),
                    sym_pair=bool(sym_pair),
                    source_distance_m=source_distance_m,
                )
                for (_, _, ct) in centers
            ]
            best = sorted(cand, key=lambda r: (r.confidence, r.score), reverse=True)[0]
            measured_raw = float(best.theta_raw)
            if debug:
                print(f"[calib] {wav}: known={known:.1f} measured_raw={measured_raw:.1f} (auto-burst t={best.center_time_s:.2f}s conf={best.confidence:.4f})")

        refs.append({"known_deg": float(known), "measured_raw_deg": float(measured_raw), "wav": wav})
        pairs.append((known, measured_raw))

    theta_offset = compute_offset_from_refs(pairs)
    save_calibration(out_json, theta_offset, refs)
    print(f"Saved calibration: {out_json}")
    print(f"theta_offset_deg = {theta_offset:.2f}  (applied as (raw + offset) % 360)")


# ----------------------------
# Main run pipeline
# ----------------------------
def run_one(
    wav_path: str,
    win_s: float,
    theta_offset_deg: float,
    bandpass: Optional[Tuple[float, float]],
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
    # selection:
    time_range: Optional[Tuple[float, float]],
    auto_burst: bool,
    multi_range: Optional[Tuple[float, float]],
    hop_s: float,
    ambig_eps: float,
    agg: str,
    # tone params for auto-burst
    tone_hz: float,
    tone_bw_hz: float,
    seg_thr_ratio: float,
    seg_min_len_s: float,
    seg_pad_s: float,
    debug: bool,
) -> None:
    x, fs = sf.read(wav_path, always_2d=True)
    if bandpass is not None:
        x = bandpass_sos(x, fs, float(bandpass[0]), float(bandpass[1]))
    x_mono = np.mean(x, axis=1).astype(np.float64)

    print(f"\n=== {wav_path} ===")

    if source_distance_m is not None:
        print(f"Model: near-field (r={source_distance_m:.3f} m)")
    else:
        print("Model: far-field (plane-wave)")

    # 1) Multi-window (recommended for noise)
    if multi_range is not None:
        t0, t1 = map(float, multi_range)
        final_theta, used, total = multi_window_doa(
            x=x,
            fs=fs,
            t0=t0,
            t1=t1,
            win_s=float(win_s),
            hop_s=float(hop_s),
            srp_subband=int(srp_subband),
            sym_pair=bool(sym_pair),
            theta_offset_deg=float(theta_offset_deg),
            ambig_eps=float(ambig_eps),
            agg=str(agg),
            source_distance_m=source_distance_m,
            debug=debug,
        )
        print(f"\nFinal DOA (multi-window): {final_theta:.2f}°")
        return

    # 2) Forced time-range single window
    if time_range is not None:
        t0, t1 = map(float, time_range)
        t0 = max(0.0, t0)
        t1 = min(float(x.shape[0] / fs), t1)
        ct = 0.5 * (t0 + t1)
        res = eval_center(
            x=x,
            fs=fs,
            center_time_s=float(ct),
            win_s=float(win_s),
            srp_subband=int(srp_subband),
            sym_pair=bool(sym_pair),
            source_distance_m=source_distance_m,
        )
        theta = _apply_offset(res.theta_raw, float(theta_offset_deg))
        if debug:
            print(f"Forced time-range: {t0:.2f}-{t1:.2f}s -> center {ct:.2f}s")
        print(
            f"SRP-PHAT: theta={theta:.2f}° (raw={res.theta_raw:.2f}°) "
            f"score={res.score:.6f} confidence={res.confidence:.4f} window@{ct:.2f}s"
        )
        if debug:
            print("Top-3 raw:", [(round(a, 2), round(sc, 6)) for a, sc in res.topk[:3]])
        print(f"\nFinal DOA: {theta:.2f}°")
        return

    # 3) Auto-burst (tone segments)
    if auto_burst:
        centers = auto_segment_centers(
            x_mono=x_mono,
            fs=fs,
            tone_hz=float(tone_hz),
            tone_bw_hz=float(tone_bw_hz),
            seg_thr_ratio=float(seg_thr_ratio),
            seg_min_len_s=float(seg_min_len_s),
            seg_pad_s=float(seg_pad_s),
        )
        if not centers:
            print("Auto-burst: no tone segments found.")
            print("Try: increase --tone-bw-hz, lower --seg-thr-ratio, or use --multi-range for broadband/noise.")
            return

        cand = [
            eval_center(
                x=x,
                fs=fs,
                center_time_s=ct,
                win_s=float(win_s),
                srp_subband=int(srp_subband),
                sym_pair=bool(sym_pair),
                source_distance_m=source_distance_m,
            )
            for (_, _, ct) in centers
        ]
        cand_sorted = sorted(cand, key=lambda r: (r.confidence, r.score), reverse=True)
        best = cand_sorted[0]
        theta = _apply_offset(best.theta_raw, float(theta_offset_deg))

        print("Auto-burst (tone segments) candidates (sorted by confidence/score):")
        for r in cand_sorted:
            th = _apply_offset(r.theta_raw, float(theta_offset_deg))
            print(f"  t={r.center_time_s:.2f}s -> theta={th:.1f}° raw={r.theta_raw:.1f}° conf={r.confidence:.4f} score={r.score:.6f}")

        print(
            f"\nBest window@{best.center_time_s:.2f}s -> "
            f"theta={theta:.2f}° (raw={best.theta_raw:.2f}°) "
            f"score={best.score:.6f} confidence={best.confidence:.4f}"
        )
        if debug:
            print("Top-3 raw:", [(round(a, 2), round(sc, 6)) for a, sc in best.topk[:3]])
        print(f"\nFinal DOA: {theta:.2f}°")
        return

    raise SystemExit("No mode selected. Use --auto-burst, --time-range, or --multi-range.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()

    p.add_argument("--wav", nargs="*", default=[], help="One or more wav files (4ch).")
    p.add_argument("--debug", action="store_true")

    # Model control
    p.add_argument("--source-distance-m", type=float, default=None,
                   help="If set, use near-field spherical model with known range r (meters). "
                        "Use 0.30 for 30 cm, 1.81 for 181 cm.")
    p.add_argument("--sym-pair", action="store_true",
                   help="Evaluate symmetric +/- shift per pair (can reduce sign sensitivity; usually keep OFF).")

    # Global processing
    p.add_argument("--bandpass", nargs=2, type=float, default=None, metavar=("LO_HZ", "HI_HZ"),
                   help="Optional bandpass applied to channels before SRP.")
    p.add_argument("--win-s", type=float, default=0.10, help="Half-window length around each center time.")
    p.add_argument("--srp-subband", type=int, default=16, help="Number of SRP subbands.")
    p.add_argument("--theta-offset-deg", type=float, default=0.0,
                   help="Angle offset applied after estimation. Usually loaded from --calib-file instead.")
    p.add_argument("--calib-file", type=str, default=None, help="Load theta offset from a calibration JSON file.")

    # Modes
    p.add_argument("--time-range", nargs=2, type=float, default=None, metavar=("T0", "T1"))
    p.add_argument("--auto-burst", action="store_true")

    p.add_argument("--multi-range", nargs=2, type=float, default=None, metavar=("T0", "T1"),
                   help="Evaluate many windows within [T0,T1] and aggregate robustly.")
    p.add_argument("--hop-s", type=float, default=0.5, help="Hop size for --multi-range.")
    p.add_argument("--ambig-eps", type=float, default=0.05,
                   help="Discard windows with confidence < ambig-eps in --multi-range.")
    p.add_argument("--agg", choices=["mode", "mean"], default="mode",
                   help="Aggregation for --multi-range. mode is robust (recommended).")

    # Tone params for auto-burst
    p.add_argument("--tone-hz", type=float, default=1000.0)
    p.add_argument("--tone-bw-hz", type=float, default=400.0)
    p.add_argument("--seg-thr-ratio", type=float, default=2.0)
    p.add_argument("--seg-min-len", type=float, default=0.05)
    p.add_argument("--seg-pad", type=float, default=0.10)

    # Calibration
    p.add_argument("--calibrate", nargs="+", default=None, metavar=("OUT_JSON", "wav=deg"),
                   help="Compute and save theta offset. Example: --calibrate calib.json a.wav=0 b.wav=90")
    p.add_argument("--calib-multi-range", nargs=2, type=float, default=None, metavar=("T0", "T1"),
                   help="During --calibrate, use --multi-window over [T0,T1] (recommended for broadband/noise).")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    bp = tuple(args.bandpass) if args.bandpass is not None else None
    theta_offset = float(args.theta_offset_deg)
    if args.calib_file:
        theta_offset = load_calibration(args.calib_file)

    # Calibration mode
    if args.calibrate is not None:
        out = args.calibrate[0]
        items = args.calibrate[1:]
        calibrate(
            out_json=out,
            items=items,
            win_s=float(args.win_s),
            bandpass=bp,
            srp_subband=int(args.srp_subband),
            sym_pair=bool(args.sym_pair),
            source_distance_m=(float(args.source_distance_m) if args.source_distance_m is not None else None),
            use_multi_range=(tuple(args.calib_multi_range) if args.calib_multi_range is not None else None),
            hop_s=float(args.hop_s),
            ambig_eps=float(args.ambig_eps),
            agg=str(args.agg),
            tone_hz=float(args.tone_hz),
            tone_bw_hz=float(args.tone_bw_hz),
            seg_thr_ratio=float(args.seg_thr_ratio),
            seg_min_len_s=float(args.seg_min_len),
            seg_pad_s=float(args.seg_pad),
            debug=bool(args.debug),
        )
        return

    if not args.wav:
        raise SystemExit("Pass at least one wav via --wav ...")

    tr = tuple(args.time_range) if args.time_range is not None else None
    mr = tuple(args.multi_range) if args.multi_range is not None else None
    r = float(args.source_distance_m) if args.source_distance_m is not None else None

    for w in args.wav:
        run_one(
            wav_path=w,
            win_s=float(args.win_s),
            theta_offset_deg=float(theta_offset),
            bandpass=bp,
            srp_subband=int(args.srp_subband),
            sym_pair=bool(args.sym_pair),
            source_distance_m=r,
            time_range=tr,
            auto_burst=bool(args.auto_burst),
            multi_range=mr,
            hop_s=float(args.hop_s),
            ambig_eps=float(args.ambig_eps),
            agg=str(args.agg),
            tone_hz=float(args.tone_hz),
            tone_bw_hz=float(args.tone_bw_hz),
            seg_thr_ratio=float(args.seg_thr_ratio),
            seg_min_len_s=float(args.seg_min_len),
            seg_pad_s=float(args.seg_pad),
            debug=bool(args.debug),
        )


if __name__ == "__main__":
    main()