"""
CLI entrypoint. Mirrors the original arguments for backward compatibility.
"""

from __future__ import annotations

import argparse
from typing import Optional, Tuple

from .calibration import load_calibration
from .pipeline import calibrate, run_one


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()

    p.add_argument("--wav", nargs="*", default=[], help="One or more wav files (4ch).")
    p.add_argument("--debug", action="store_true")

    p.add_argument(
        "--source-distance-m",
        type=float,
        default=None,
        help="If set, use near-field spherical model with known range r (meters). Use 0.30 for 30 cm, 1.81 for 181 cm.",
    )
    p.add_argument(
        "--sym-pair",
        action="store_true",
        help="Evaluate symmetric +/- shift per pair (can reduce sign sensitivity; usually keep OFF).",
    )

    p.add_argument("--bandpass", nargs=2, type=float, default=None, metavar=("LO_HZ", "HI_HZ"))
    p.add_argument("--win-s", type=float, default=0.10)
    p.add_argument("--srp-subband", type=int, default=16)
    p.add_argument("--theta-offset-deg", type=float, default=0.0)
    p.add_argument("--calib-file", type=str, default=None)

    p.add_argument("--time-range", nargs=2, type=float, default=None, metavar=("T0", "T1"))
    p.add_argument("--auto-burst", action="store_true")
    p.add_argument("--multi-range", nargs=2, type=float, default=None, metavar=("T0", "T1"))
    p.add_argument("--hop-s", type=float, default=0.5)
    p.add_argument("--ambig-eps", type=float, default=0.05)
    p.add_argument("--agg", choices=["mode", "mean"], default="mode")

    p.add_argument("--tone-hz", type=float, default=1000.0)
    p.add_argument("--tone-bw-hz", type=float, default=400.0)
    p.add_argument("--seg-thr-ratio", type=float, default=2.0)
    p.add_argument("--seg-min-len", type=float, default=0.05)
    p.add_argument("--seg-pad", type=float, default=0.10)

    p.add_argument(
        "--calibrate",
        nargs="+",
        default=None,
        metavar=("OUT_JSON", "wav=deg"),
        help="Compute and save theta offset. Example: --calibrate calib.json a.wav=0 b.wav=90",
    )
    p.add_argument("--calib-multi-range", nargs=2, type=float, default=None, metavar=("T0", "T1"))

    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)

    bp: Optional[Tuple[float, float]] = tuple(args.bandpass) if args.bandpass is not None else None
    theta_offset = float(args.theta_offset_deg)
    if args.calib_file:
        theta_offset = load_calibration(args.calib_file)

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
