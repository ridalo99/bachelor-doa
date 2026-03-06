from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf

from .aggregate import circular_mean_deg_weighted, cluster_quality_mode_tol
from .dsp import apply_offset, bandpass_sos, clip_center_window
from .geometry import CH_ORDER, PAIRS_ALL
from .segments import auto_segment_centers
from .srp import srp_phat_scan

@dataclass(frozen=True)
class DoaResult:
    theta_raw: float
    score: float
    confidence: float
    topk: List[Tuple[float, float]]
    center_time_s: float


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
        mode_theta, dom_ratio, _second_ratio = cluster_quality_mode_tol(angles, weights, tol_deg=3)
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
                print(
                    f"[calib] {wav}: known={known:.1f} measured_raw={measured_raw:.1f} "
                    f"(auto-burst t={best.center_time_s:.2f}s conf={best.confidence:.4f})"
                )

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
) -> None:
    x, fs = sf.read(wav_path, always_2d=True)
    if bandpass is not None:
        x = bandpass_sos(x, fs, float(bandpass[0]), float(bandpass[1]))
    x_mono = np.mean(x, axis=1).astype(np.float64)

    print(f"\n=== {wav_path} ===")
    print(f"Model: {'near-field (r=' + str(source_distance_m) + ' m)' if source_distance_m is not None else 'far-field (plane-wave)'}")

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
        theta = apply_offset(best.theta_raw, float(theta_offset_deg))

        print("Auto-burst (tone segments) candidates (sorted by confidence/score):")
        for r in cand_sorted:
            th = apply_offset(r.theta_raw, float(theta_offset_deg))
            print(
                f"  t={r.center_time_s:.2f}s -> theta={th:.1f}° raw={r.theta_raw:.1f}° "
                f"conf={r.confidence:.4f} score={r.score:.6f}"
            )
        print(
            f"\nBest window@{best.center_time_s:.2f}s -> "
            f"theta={theta:.2f}° (raw={best.theta_raw:.2f}°) "
            f"score={best.score:.6f} confidence={best.confidence:.4f}"
        )
        if debug:
            print("Top-3 raw:", [(round(a, 2), round(sc, 6)) for a, sc in best.topk[:3]])
        return

    raise SystemExit("No mode selected. Use --auto-burst, --time-range, or --multi-range.")    
