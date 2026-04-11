# src/doa/pipeline.py
"""
End-to-end pipeline used by CLI and later ROS2.

Key features:
- SRP-PHAT DOA on a 4-mic square array
- multi-window aggregation
- auto-burst (tone)
- auto-window (broadband / unknown timing)
- auto-window can detect TOP-K loud events in a file/buffer and aggregate them
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf

from .aggregate import circular_mean_deg_weighted, cluster_quality_mode_tol
from .dsp import apply_offset, bandpass_sos, clip_center_window
from .geometry import CH_ORDER, PAIRS_ALL
from .music import music_topk
from .segments import auto_segment_centers
from .srp import srp_phat_scan


@dataclass(frozen=True)
class DoaResult:
    theta_raw: float
    score: float
    confidence: float
    topk: List[Tuple[float, float]]
    center_time_s: float


@dataclass(frozen=True)
class AutoEventResult:
    event_idx: int
    window_t0: float
    window_t1: float
    expanded_t0: float
    expanded_t1: float
    theta_deg: float
    dom_ratio: float
    best_conf: float
    used: int
    total: int
    rms: float


def eval_center(
    x: np.ndarray,
    fs: int,
    center_time_s: float,
    win_s: float,
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
) -> DoaResult:
    center = int(float(center_time_s) * fs)
    s, t = clip_center_window(center, fs, x.shape[0], float(win_s))
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


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x)))


def _circ_dist_deg(a: float, b: float) -> float:
    d = abs((float(a) - float(b)) % 360.0)
    return min(d, 360.0 - d)


def _candidate_dir_xy(theta_deg: float) -> np.ndarray:
    rad = np.deg2rad(float(theta_deg))
    return np.array([np.sin(rad), np.cos(rad)], dtype=np.float64)


def _ild_vector_for_window(
    x: np.ndarray,
    fs: int,
    center_time_s: float,
    win_s: float,
) -> np.ndarray:
    center = int(float(center_time_s) * fs)
    s, t = clip_center_window(center, fs, x.shape[0], float(win_s))
    xw = x[s:t][:, CH_ORDER]

    if xw.shape[0] == 0:
        return np.zeros(2, dtype=np.float64)

    rms_ch = np.sqrt(np.mean(np.square(xw), axis=0) + 1e-12)

    # CH_ORDER => M1, M2, M3, M4
    right = float(rms_ch[0] + rms_ch[1])
    left = float(rms_ch[2] + rms_ch[3])
    top = float(rms_ch[1] + rms_ch[2])
    bottom = float(rms_ch[0] + rms_ch[3])

    vec = np.array([right - left, top - bottom], dtype=np.float64)
    nrm = float(np.linalg.norm(vec))
    if nrm < 1e-12:
        return np.zeros(2, dtype=np.float64)
    return vec / nrm


def _resolve_180_ambiguity_with_ild(
    topk: Sequence[Tuple[float, float]],
    ild_vec: np.ndarray,
    score_ratio_min: float = 0.90,
    angle_tol_deg: float = 20.0,
) -> Optional[float]:
    if len(topk) < 2:
        return None

    a0, s0 = float(topk[0][0]), float(topk[0][1])
    a1, s1 = float(topk[1][0]), float(topk[1][1])

    if s0 <= 0.0 or s1 <= 0.0:
        return None

    if _circ_dist_deg(a0, a1) < (180.0 - float(angle_tol_deg)):
        return None

    if min(s0, s1) / max(s0, s1) < float(score_ratio_min):
        return None

    if float(np.linalg.norm(ild_vec)) < 1e-12:
        return None

    v0 = _candidate_dir_xy(a0)
    v1 = _candidate_dir_xy(a1)

    d0 = float(np.dot(v0, ild_vec))
    d1 = float(np.dot(v1, ild_vec))

    return a0 if d0 >= d1 else a1


def _is_event_ambiguous(best_r: DoaResult) -> bool:
    if len(best_r.topk) < 2:
        return False

    a0, s0 = float(best_r.topk[0][0]), float(best_r.topk[0][1])
    a1, s1 = float(best_r.topk[1][0]), float(best_r.topk[1][1])

    if s0 <= 0.0:
        return False

    near_tie = (s1 / s0) >= 0.90
    low_conf = float(best_r.confidence) < 0.08
    wide_ambiguity = _circ_dist_deg(a0, a1) >= 150.0

    return low_conf and near_tie and wide_ambiguity


def _eval_onset_probe(
    x: np.ndarray,
    fs: int,
    event_start_s: float,
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
) -> Optional[DoaResult]:
    probe_specs = [
        (0.03, 0.015),
        (0.05, 0.025),
    ]

    candidates: List[DoaResult] = []
    file_tmax = float(x.shape[0] / fs)

    for probe_win_s, probe_center_offset_s in probe_specs:
        ct = float(event_start_s) + float(probe_center_offset_s)
        if ct <= 0.0 or ct >= file_tmax:
            continue

        try:
            r = eval_center(
                x=x,
                fs=fs,
                center_time_s=ct,
                win_s=float(probe_win_s),
                srp_subband=int(srp_subband),
                sym_pair=bool(sym_pair),
                source_distance_m=source_distance_m,
            )
            candidates.append(r)
        except Exception:
            continue

    if not candidates:
        return None

    return sorted(candidates, key=lambda r: (r.confidence, r.score), reverse=True)[0]


def _event_window_channels(
    x: np.ndarray,
    fs: int,
    center_time_s: float,
    win_s: float,
) -> np.ndarray:
    center = int(float(center_time_s) * fs)
    s, t = clip_center_window(center, fs, x.shape[0], float(win_s))
    return x[s:t][:, CH_ORDER]


def _resolve_ambiguous_event_with_music(
    x: np.ndarray,
    fs: int,
    center_time_s: float,
    win_s: float,
    theta_offset_deg: float,
) -> Optional[Tuple[float, float, List[Tuple[float, float]]]]:
    xw = _event_window_channels(
        x=x,
        fs=fs,
        center_time_s=float(center_time_s),
        win_s=float(win_s),
    )
    theta_grid = np.arange(0.0, 360.0, 1.0, dtype=np.float64)

    try:
        music_theta_raw, music_sharpness, music_peaks, _ = music_topk(
            xw=xw,
            fs=fs,
            theta_grid_deg=theta_grid,
            fmin=700.0,
            fmax=5000.0,
            nfft=1024,
            n_sources=1,
            topk=5,
        )
    except Exception:
        return None

    music_theta = float(apply_offset(music_theta_raw, float(theta_offset_deg)))
    return music_theta, float(music_sharpness), music_peaks


def find_topk_loud_windows(
    x_mono: np.ndarray,
    fs: int,
    t0: float,
    t1: float,
    win_s: float,
    hop_s: float,
    topk: int,
    min_gap_s: float,
) -> List[Tuple[float, float, float]]:
    """
    Returns list of (w0, w1, rms) for up to topk loudest windows within [t0,t1],
    enforcing a minimum gap between selected windows.
    """
    t0 = max(0.0, float(t0))
    t1 = min(float(len(x_mono) / fs), float(t1))
    if t1 <= t0:
        raise ValueError("auto-window invalid range")

    win = max(1, int(win_s * fs))
    hop = max(1, int(hop_s * fs))
    s0 = int(t0 * fs)
    s1 = int(t1 * fs)

    if (s1 - s0) < win:
        mid = 0.5 * (t0 + t1)
        w0 = max(0.0, mid - 0.5 * win_s)
        w1 = min(float(len(x_mono) / fs), mid + 0.5 * win_s)
        seg = x_mono[int(w0 * fs) : int(w1 * fs)]
        return [(w0, w1, _rms(seg))]

    starts = list(range(s0, s1 - win + 1, hop))
    env = np.zeros(len(starts), dtype=np.float64)
    for i, s in enumerate(starts):
        env[i] = _rms(x_mono[s : s + win])

    chosen: List[Tuple[float, float, float]] = []
    suppress = int(max(0.0, float(min_gap_s)) / float(hop_s)) if hop_s > 0 else len(env)

    env_work = env.copy()
    for _ in range(max(1, int(topk))):
        idx = int(np.argmax(env_work))
        if env_work[idx] <= 0.0:
            break

        s = starts[idx]
        w0 = s / fs
        w1 = (s + win) / fs
        chosen.append((float(w0), float(w1), float(env[idx])))

        lo = max(0, idx - suppress)
        hi = min(len(env_work), idx + suppress + 1)
        env_work[lo:hi] = -1.0

    chosen.sort(key=lambda a: a[0])
    return chosen


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
) -> Tuple[float, int, int, float]:
    t0 = float(max(0.0, t0))
    t1 = float(min(float(x.shape[0] / fs), t1))
    if t1 <= t0:
        raise ValueError("multi-range invalid: t1 <= t0")

    centers = np.arange(t0 + float(win_s), t1 - float(win_s), float(hop_s), dtype=float)
    if centers.size == 0:
        raise ValueError("multi-range too short for given win-s/hop-s")

    results: List[DoaResult] = [
        eval_center(
            x=x,
            fs=fs,
            center_time_s=float(ct),
            win_s=float(win_s),
            srp_subband=int(srp_subband),
            sym_pair=bool(sym_pair),
            source_distance_m=source_distance_m,
        )
        for ct in centers
    ]

    good = [r for r in results if r.confidence >= float(ambig_eps)]
    used = good if good else results

    angles = np.array([apply_offset(r.theta_raw, float(theta_offset_deg)) for r in used], dtype=float)
    weights = np.array([max(1e-6, float(r.confidence)) for r in used], dtype=float)

    if str(agg) == "mode":
        mode_theta, dom_ratio, _ = cluster_quality_mode_tol(angles, weights, tol_deg=3)
        final_theta = float(mode_theta)
    elif str(agg) == "mean":
        dom_ratio = 1.0
        final_theta = float(circular_mean_deg_weighted(angles, weights))
    else:
        raise ValueError(f"unknown agg: {agg}")

    if debug:
        print("Multi-window results (top 12 by confidence):")
        top = sorted(results, key=lambda r: (r.confidence, r.score), reverse=True)[:12]
        for r in top:
            th = apply_offset(r.theta_raw, float(theta_offset_deg))
            print(
                f"  t={r.center_time_s:.2f}s -> theta={th:.1f}° raw={r.theta_raw:.1f}° "
                f"conf={r.confidence:.4f} score={r.score:.6f}"
            )
        print(f"Multi-window: used {len(used)}/{len(results)} windows (ambig_eps={ambig_eps:.3f}, agg={agg})")

    return float(final_theta), int(len(used)), int(len(results)), float(dom_ratio)


def auto_window_events_doa(
    x: np.ndarray,
    fs: int,
    x_mono: np.ndarray,
    search_range: Tuple[float, float],
    theta_offset_deg: float,
    source_distance_m: Optional[float],
    win_s: float,
    hop_s: float,
    srp_subband: int,
    sym_pair: bool,
    ambig_eps: float,
    agg: str,
    auto_len_s: float,
    auto_hop_s: float,
    auto_expand_s: float,
    auto_topk: int,
    auto_min_gap_s: float,
    auto_dom_min: float,
    event_min_conf: float,
    event_min_dom: float,
    debug: bool,
) -> Tuple[float, List[AutoEventResult], float, int, int]:
    t0, t1 = search_range
    windows = find_topk_loud_windows(
        x_mono=x_mono,
        fs=fs,
        t0=t0,
        t1=t1,
        win_s=float(auto_len_s),
        hop_s=float(auto_hop_s),
        topk=int(auto_topk),
        min_gap_s=float(auto_min_gap_s),
    )

    events: List[AutoEventResult] = []
    file_tmax = float(x.shape[0] / fs)

    for k, (w0, w1, wrms) in enumerate(windows, 1):
        ext0 = max(0.0, w0 - float(auto_expand_s))
        ext1 = min(file_tmax, w1 + float(auto_expand_s))

        centers = np.arange(ext0 + float(win_s), ext1 - float(win_s), float(hop_s), dtype=float)
        if centers.size == 0:
            ct = 0.5 * (w0 + w1)
            r = eval_center(x, fs, ct, win_s, srp_subband, sym_pair, source_distance_m)
            theta = apply_offset(r.theta_raw, theta_offset_deg)
            events.append(
                AutoEventResult(
                    event_idx=k,
                    window_t0=w0,
                    window_t1=w1,
                    expanded_t0=ext0,
                    expanded_t1=ext1,
                    theta_deg=float(theta),
                    dom_ratio=1.0,
                    best_conf=float(r.confidence),
                    used=1,
                    total=1,
                    rms=float(wrms),
                )
            )
            continue

        results = [
            eval_center(
                x=x,
                fs=fs,
                center_time_s=float(ct),
                win_s=float(win_s),
                srp_subband=int(srp_subband),
                sym_pair=bool(sym_pair),
                source_distance_m=source_distance_m,
            )
            for ct in centers
        ]

        good = [r for r in results if r.confidence >= float(ambig_eps)]
        used = good if good else results
        best_r = sorted(used, key=lambda r: (r.confidence, r.score), reverse=True)[0]
        best_theta = float(apply_offset(best_r.theta_raw, float(theta_offset_deg)))
        best_conf = float(best_r.confidence)

        # First, evaluate raw SRP event consistency before any fallback
        angles_srp = np.array([apply_offset(r.theta_raw, float(theta_offset_deg)) for r in used], dtype=float)
        weights_srp = np.array([max(1e-6, float(r.confidence)) for r in used], dtype=float)
        mode_theta_srp, dom_ratio_srp, _ = cluster_quality_mode_tol(angles_srp, weights_srp, tol_deg=3)

        ild_vec = _ild_vector_for_window(
            x=x,
            fs=fs,
            center_time_s=float(best_r.center_time_s),
            win_s=float(win_s),
        )
        ild_theta_raw = _resolve_180_ambiguity_with_ild(best_r.topk, ild_vec)
        if ild_theta_raw is not None:
            best_theta = float(apply_offset(ild_theta_raw, float(theta_offset_deg)))

        onset_r = None
        used_onset_fallback = False

        music_theta = None
        music_sharpness = None
        music_peaks = None
        used_music_fallback = False

        need_music = _is_event_ambiguous(best_r) or (float(dom_ratio_srp) < max(float(auto_dom_min)+0.10,0.55))

        if need_music:
            onset_r = _eval_onset_probe(
                x=x,
                fs=fs,
                event_start_s=float(w0),
                srp_subband=int(srp_subband),
                sym_pair=bool(sym_pair),
                source_distance_m=source_distance_m,
            )
            if onset_r is not None and float(onset_r.confidence) >= float(best_r.confidence) + 0.01:
                best_theta = float(apply_offset(onset_r.theta_raw, float(theta_offset_deg)))
                best_conf = float(onset_r.confidence)
                used_onset_fallback = True

            music_res = _resolve_ambiguous_event_with_music(
                x=x,
                fs=fs,
                center_time_s=float(best_r.center_time_s),
                win_s=float(win_s),
                theta_offset_deg=float(theta_offset_deg),
            )
            if music_res is not None:
                music_theta, music_sharpness, music_peaks = music_res
                if float(music_sharpness) >= 0.015:
                    best_theta = float(music_theta)
                    best_conf = max(float(best_conf), float(music_sharpness))
                    print(f"  music_accept_threshold=0.02")
                    used_music_fallback = True

        angles = np.array(
            [
                best_theta
                if (
                    r.center_time_s == best_r.center_time_s
                    and (ild_theta_raw is not None or used_onset_fallback or used_music_fallback)
                )
                else apply_offset(r.theta_raw, float(theta_offset_deg))
                for r in used
            ],
            dtype=float,
        )
        weights = np.array([max(1e-6, float(r.confidence)) for r in used], dtype=float)

        mode_theta, dom_ratio, _ = cluster_quality_mode_tol(angles, weights, tol_deg=3)

        if used_music_fallback and music_sharpness is not None:
            # SRP-dom_ratio is no longer the right quality metric once MUSIC decided the angle.
            # Map MUSIC sharpness to a stable event-quality score for acceptance/final output.
            dom_ratio = max(float(dom_ratio), 0.60 + min(0.30, 4.0 * float(music_sharpness)))

        if int(auto_topk) == 1:
            event_theta = best_theta
        else:
            if str(agg) == "mode":
                event_theta = float(mode_theta) if dom_ratio >= float(auto_dom_min) else best_theta
            elif str(agg) == "mean":
                mean_theta = float(circular_mean_deg_weighted(angles, weights))
                event_theta = mean_theta if dom_ratio >= float(auto_dom_min) else best_theta
            else:
                raise ValueError(f"unknown agg: {agg}")

        if debug:
            print(f"\n[auto-event {k}] window {w0:.2f}-{w1:.2f}s rms={wrms:.6f} expanded {ext0:.2f}-{ext1:.2f}s")
            top = sorted(results, key=lambda r: (r.confidence, r.score), reverse=True)[:6]
            for r in top:
                th = apply_offset(r.theta_raw, float(theta_offset_deg))
                print(f"  t={r.center_time_s:.2f}s -> theta={th:.1f}° raw={r.theta_raw:.1f}° conf={r.confidence:.4f}")
            if ild_theta_raw is not None:
                print(f"  ild_resolved_theta={apply_offset(ild_theta_raw, float(theta_offset_deg)):.2f}°")
            if onset_r is not None:
                print(
                    f"  onset_probe: theta={apply_offset(onset_r.theta_raw, float(theta_offset_deg)):.2f}° "
                    f"conf={onset_r.confidence:.4f}"
                )
            if used_onset_fallback:
                print("  onset_fallback_applied=True")
            if music_theta is not None:
                print(
                    f"  music_fallback: theta={music_theta:.2f}° "
                    f"sharpness={music_sharpness:.4f}"
                )
                top2 = ", ".join([f"({a:.1f}°, {s:.4f})" for a, s in music_peaks[:2]])
                print(f"  music_top2=[{top2}]")
            if used_music_fallback:
                print("  music_fallback_applied=True")
            if used_music_fallback and music_sharpness is not None:
                print(f"  dom_ratio_promoted_from_music={dom_ratio:.2f}")    
            print(f"  srp_dom_ratio_pre_fallback={dom_ratio_srp:.2f} need_music={need_music}")
            print(f"  dom_ratio={dom_ratio:.2f} best_conf={best_conf:.4f} event_theta={event_theta:.2f}°")

        events.append(
            AutoEventResult(
                event_idx=k,
                window_t0=w0,
                window_t1=w1,
                expanded_t0=ext0,
                expanded_t1=ext1,
                theta_deg=float(event_theta),
                dom_ratio=float(dom_ratio),
                best_conf=float(best_conf),
                used=int(len(used)),
                total=int(len(results)),
                rms=float(wrms),
            )
        )

    if not events:
        raise RuntimeError("auto-window: no events found")

    max_event_rms = max(float(e.rms) for e in events) if events else 0.0
    event_rms_rel_min = 0.10

    accepted = [
        e for e in events
        if (e.best_conf >= float(event_min_conf))
        and (e.dom_ratio >= float(event_min_dom))
        and (float(e.rms) >= event_rms_rel_min * max_event_rms)
    ]

    if len(accepted) == 1:
        return float(accepted[0].theta_deg), events, float(accepted[0].dom_ratio), 1, len(events)

    def circ_dist_deg(a: float, b: float) -> float:
        d = (a - b) % 360.0
        return d - 360.0 if d > 180.0 else d

    if len(accepted) >= 2:
        ang = np.array([e.theta_deg for e in accepted], dtype=float)
        wts = np.array([max(1e-6, e.rms) * max(1e-3, e.best_conf) for e in accepted], dtype=float)

        idx = np.argsort(wts)[::-1]
        a1, a2 = float(ang[idx[0]]), float(ang[idx[1]])
        d = abs(circ_dist_deg(a1, a2))

        if abs(d - 180.0) <= 15.0:
            best = int(idx[0])
            return float(ang[best]), events, 0.0, len(accepted), len(events)

    if debug:
        print("\nAuto-window events summary:")
        for e in events:
            status = "ACCEPT" if e in accepted else "REJECT"
            rel_rms = (float(e.rms) / max_event_rms) if max_event_rms > 0.0 else 0.0
            print(
                f"  event{e.event_idx}: win={e.window_t0:.2f}-{e.window_t1:.2f}s "
                f"theta={e.theta_deg:.2f}° dom={e.dom_ratio:.2f} best_conf={e.best_conf:.4f} "
                f"rms={e.rms:.6f} rel_rms={rel_rms:.3f} "
                f"used={e.used}/{e.total} -> {status}"
            )

    if not accepted:
        weights_all = np.array(
            [max(1e-6, e.rms) * max(1e-3, e.best_conf) for e in events],
            dtype=float
        )
        best_idx = int(np.argmax(weights_all))
        fallback_theta = float(events[best_idx].theta_deg)
        fallback_dom = float(events[best_idx].dom_ratio)
        return fallback_theta, events, fallback_dom, 0, len(events)

    ang = np.array([e.theta_deg for e in accepted], dtype=float)
    wts = np.array([max(1e-6, e.rms) * max(1e-3, e.best_conf) for e in accepted], dtype=float)

    mode_theta, dom_ratio, _ = cluster_quality_mode_tol(ang, wts, tol_deg=5)

    if dom_ratio >= 0.60:
        final_theta = float(mode_theta)
        final_dom = float(dom_ratio)
    else:
        best_idx = int(np.argmax(wts))
        final_theta = float(accepted[best_idx].theta_deg)
        final_dom = float(dom_ratio)

    return final_theta, events, final_dom, len(accepted), len(events)


def calibrate(
    out_json: str,
    items: List[str],
    win_s: float,
    bandpass: Optional[Tuple[float, float]],
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
    use_multi_range: Optional[Tuple[float, float]],
    hop_s: float,
    ambig_eps: float,
    agg: str,
    tone_hz: float,
    tone_bw_hz: float,
    seg_thr_ratio: float,
    seg_min_len_s: float,
    seg_pad_s: float,
    debug: bool,
) -> None:
    from .calibration import compute_offset_from_refs, save_calibration

    if len(items) < 2:
        raise SystemExit("Calibration needs at least two refs: OUT_JSON wav=deg wav=deg ...")

    refs: List[dict] = []
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
            measured, used, total, _dom = multi_window_doa(
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
                agg=str(agg),
                source_distance_m=source_distance_m,
                debug=debug,
            )
            measured_raw = float(measured)
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

        refs.append({"known_deg": float(known), "measured_raw_deg": float(measured_raw), "wav": wav})
        pairs.append((known, measured_raw))

    theta_offset = compute_offset_from_refs(pairs)
    save_calibration(out_json, theta_offset, refs)
    print(f"Saved calibration: {out_json}")
    print(f"theta_offset_deg = {theta_offset:.2f}  (applied as (raw + offset) % 360)")


def run_one(
    wav_path: str,
    win_s: float,
    theta_offset_deg: float,
    bandpass: Optional[Tuple[float, float]],
    srp_subband: int,
    sym_pair: bool,
    source_distance_m: Optional[float],
    time_range: Optional[Tuple[float, float]],
    auto_burst: bool,
    multi_range: Optional[Tuple[float, float]],
    hop_s: float,
    ambig_eps: float,
    agg: str,
    tone_hz: float,
    tone_bw_hz: float,
    seg_thr_ratio: float,
    seg_min_len_s: float,
    seg_pad_s: float,
    debug: bool,
    event_min_conf: float,
    event_min_dom: float,
    auto_window: bool,
    auto_window_len_s: float,
    auto_window_hop_s: float,
    auto_window_expand_s: float,
    auto_window_topk: int,
    auto_window_min_gap_s: float,
    auto_dom_min: float,
) -> None:
    x, fs = sf.read(wav_path, always_2d=True)
    if bandpass is not None:
        x = bandpass_sos(x, fs, float(bandpass[0]), float(bandpass[1]))
    x_mono = np.mean(x, axis=1).astype(np.float64)

    print(f"\n=== {wav_path} ===")
    print(
        f"Model: {'near-field (r=' + str(source_distance_m) + ' m)' if source_distance_m is not None else 'far-field (plane-wave)'}"
    )

    if auto_window or (not auto_burst and time_range is None and multi_range is None):
        search_t0, search_t1 = 0.0, float(x.shape[0] / fs)
        if multi_range is not None:
            search_t0, search_t1 = map(float, multi_range)

        final_theta, events, final_dom, n_acc, n_total = auto_window_events_doa(
            x=x,
            fs=fs,
            x_mono=x_mono,
            search_range=(float(search_t0), float(search_t1)),
            theta_offset_deg=float(theta_offset_deg),
            source_distance_m=source_distance_m,
            win_s=float(win_s),
            hop_s=float(hop_s),
            srp_subband=int(srp_subband),
            sym_pair=bool(sym_pair),
            ambig_eps=float(ambig_eps),
            agg=str(agg),
            auto_len_s=float(auto_window_len_s),
            auto_hop_s=float(auto_window_hop_s),
            auto_expand_s=float(auto_window_expand_s),
            auto_topk=int(auto_window_topk),
            auto_min_gap_s=float(auto_window_min_gap_s),
            auto_dom_min=float(auto_dom_min),
            event_min_conf=float(event_min_conf),
            event_min_dom=float(event_min_dom),
            debug=bool(debug),
        )

        if final_dom < 0.50:
            print(f"\nFinal DOA (auto-window): UNCERTAIN (accepted {n_acc}/{n_total}, dom={final_dom:.2f})")
        else:
            print(f"\nFinal DOA (auto-window): {final_theta:.2f}° (accepted {n_acc}/{n_total}, dom={final_dom:.2f})")
        return

    if multi_range is not None:
        t0, t1 = map(float, multi_range)
        final_theta, used, total, dom_ratio = multi_window_doa(
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
        if str(agg) == "mode" and dom_ratio < 0.60:
            print(f"\nFinal DOA (multi-window): UNCERTAIN (mixed clusters, dom={dom_ratio:.2f})")
        else:
            print(f"\nFinal DOA (multi-window): {final_theta:.2f}° (dom={dom_ratio:.2f})")
        return

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
        theta = apply_offset(res.theta_raw, float(theta_offset_deg))
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
            print("Try: use --auto-window for horn/broadband signals.")
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
        best = sorted(cand, key=lambda r: (r.confidence, r.score), reverse=True)[0]
        theta = apply_offset(best.theta_raw, float(theta_offset_deg))
        print(
            f"\nBest window@{best.center_time_s:.2f}s -> "
            f"theta={theta:.2f}° (raw={best.theta_raw:.2f}°) conf={best.confidence:.4f}"
        )
        return

    raise SystemExit("No mode selected. Use --auto-window, --auto-burst, --time-range, or --multi-range.")