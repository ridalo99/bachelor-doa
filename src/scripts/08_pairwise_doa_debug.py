# ==========================================
# File: src/scripts/08_pairwise_doa_debug.py
# ==========================================
from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import soundfile as sf

from doa.dsp import bandpass_sos
from doa.pair_fusion import grouped_pair_fusions, majority_pair_theta
from doa.pairwise import eval_center_all_pairs, format_pair, pick_event_window


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pairwise DOA diagnostics on one 4ch wav file.")
    p.add_argument("--wav", required=True, help="Path to one 4ch wav file.")
    p.add_argument("--bandpass", nargs=2, type=float, default=None, metavar=("LO_HZ", "HI_HZ"))
    p.add_argument("--win-s", type=float, default=0.15)
    p.add_argument("--srp-subband", type=int, default=16)
    p.add_argument("--theta-offset-deg", type=float, default=0.0)
    p.add_argument("--source-distance-m", type=float, default=None)
    p.add_argument("--sym-pair", action="store_true")

    p.add_argument("--time-range", nargs=2, type=float, default=None, metavar=("T0", "T1"))

    p.add_argument("--auto-window", action="store_true")
    p.add_argument("--auto-window-len", type=float, default=0.40)
    p.add_argument("--auto-window-hop", type=float, default=0.01)
    p.add_argument("--auto-window-expand", type=float, default=0.05)
    p.add_argument("--auto-window-min-gap", type=float, default=0.80)

    p.add_argument("--fusion-topn", type=int, default=2)
    p.add_argument("--fusion-tol-deg", type=float, default=12.0)

    return p.parse_args(argv)


def print_fusion_result(title: str, fused) -> None:
    print(f"\n{title}:")
    print(
        f"  theta={fused.theta_deg:.2f}° "
        f"support_pairs={fused.support_pairs} "
        f"total_candidates={fused.total_candidates} "
        f"cluster_weight={fused.cluster_weight:.6f}"
    )
    print("  cluster members:")
    for c in fused.members:
        print(
            f"    {format_pair(c.pair)} rank={c.rank} "
            f"angle={c.angle_deg:.2f}° score={c.score:.6f}"
        )


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)

    x, fs = sf.read(args.wav, always_2d=True)
    if args.bandpass is not None:
        lo, hi = map(float, args.bandpass)
        x = bandpass_sos(x, fs, lo, hi)

    x_mono = np.mean(x, axis=1).astype(np.float64)

    event = pick_event_window(
        x=x,
        fs=fs,
        x_mono=x_mono,
        time_range=tuple(args.time_range) if args.time_range is not None else None,
        auto_window=bool(args.auto_window),
        auto_window_len_s=float(args.auto_window_len),
        auto_window_hop_s=float(args.auto_window_hop),
        auto_window_expand_s=float(args.auto_window_expand),
        auto_window_min_gap_s=float(args.auto_window_min_gap),
    )

    print(f"\n=== {args.wav} ===")
    print(
        f"Selected event ({event.mode}): "
        f"raw={event.window_t0:.2f}-{event.window_t1:.2f}s, "
        f"used={event.expanded_t0:.2f}-{event.expanded_t1:.2f}s, "
        f"center={event.center_time_s:.2f}s, rms={event.rms:.6f}"
    )

    results = eval_center_all_pairs(
        x=x,
        fs=fs,
        center_time_s=float(event.center_time_s),
        win_s=float(args.win_s),
        srp_subband=int(args.srp_subband),
        sym_pair=bool(args.sym_pair),
        source_distance_m=float(args.source_distance_m) if args.source_distance_m is not None else None,
        theta_offset_deg=float(args.theta_offset_deg),
    )

    print("\nPairwise DOA results (sorted by confidence):")
    for r in results:
        top3 = ", ".join([f"({a:.1f}°, {sc:.6f})" for a, sc in r.topk[:3]])
        print(
            f"  {format_pair(r.pair)} -> theta={r.theta_deg:.2f}° "
            f"(raw={r.theta_raw:.2f}°) conf={r.confidence:.4f} "
            f"score={r.score:.6f} top3=[{top3}]"
        )

    fused = majority_pair_theta(
        results,
        topn_per_pair=int(args.fusion_topn),
        tol_deg=float(args.fusion_tol_deg),
    )
    print_fusion_result("Pair-fusion result", fused)

    grouped = grouped_pair_fusions(
        results,
        topn_per_pair=int(args.fusion_topn),
        tol_deg=float(args.fusion_tol_deg),
    )

    print("\nGrouped pair-fusion report:")
    for group_name in ("horizontal", "vertical", "diagonal"):
        if group_name in grouped:
            print_fusion_result(f"group={group_name}", grouped[group_name])


if __name__ == "__main__":
    main()