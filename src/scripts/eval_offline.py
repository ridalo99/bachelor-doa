# src/scripts/eval_offline.py
"""
Offline regression runner for DOA.

- Scans WAVs like: test_90deg_120cm_take3.wav
- Parses expected_deg and dist_cm from filename
- Applies setup offset (preferred) or distance calib file from configs/
- Runs doa.pipeline.multi_window_doa()
- Writes CSV + prints summary

Why: makes offline validation reproducible and later reusable in ROS2 (same core pipeline).
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import soundfile as sf

from doa.calibration import load_calibration, load_setup  # load_setup is optional; if you don't have it yet, see note below
from doa.dsp import bandpass_sos
from doa.pipeline import multi_window_doa


@dataclass(frozen=True)
class ParsedName:
    expected_deg: Optional[float]
    dist_cm: Optional[int]


def parse_name(path: str) -> ParsedName:
    name = os.path.basename(path)
    m_deg = re.search(r"_(\d{1,3})deg_", name)
    m_cm = re.search(r"_(\d{2,3})cm_", name)
    expected = float(m_deg.group(1)) if m_deg else None
    dist_cm = int(m_cm.group(1)) if m_cm else None
    return ParsedName(expected_deg=expected, dist_cm=dist_cm)


def circular_error_deg(pred: float, expected: float) -> float:
    d = (pred - expected) % 360.0
    d = d - 360.0 if d > 180.0 else d
    return float(d)


def find_dist_calib(configs_dir: str, dist_cm: int) -> Optional[str]:
    cands = [
        os.path.join(configs_dir, f"calib_{dist_cm:03d}cm.json"),
        os.path.join(configs_dir, f"calib_{dist_cm}cm.json"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def run_one(
    wav_path: str,
    theta_offset_deg: float,
    t0: float,
    t1: float,
    bandpass: Optional[Tuple[float, float]],
    srp_subband: int,
    hop_s: float,
    ambig_eps: float,
    agg: str,
) -> Tuple[float, float, int, int]:
    x, fs = sf.read(wav_path, always_2d=True)
    if bandpass is not None:
        x = bandpass_sos(x, fs, float(bandpass[0]), float(bandpass[1]))

    theta, used, total, dom = multi_window_doa(
        x=x,
        fs=fs,
        t0=float(t0),
        t1=float(t1),
        win_s=0.10,
        hop_s=float(hop_s),
        srp_subband=int(srp_subband),
        sym_pair=False,
        theta_offset_deg=float(theta_offset_deg),
        ambig_eps=float(ambig_eps),
        agg=str(agg),
        source_distance_m=None,
        debug=False,
    )
    return float(theta), float(dom), int(used), int(total)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="audio")
    ap.add_argument("--pattern", default="test_*deg_*cm_take*.wav")
    ap.add_argument("--configs-dir", default="configs")
    ap.add_argument("--setup-file", default=None, help="Preferred: setup JSON with theta_offset_deg (and optional mapping later).")
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float, default=10.0)
    ap.add_argument("--bandpass", nargs=2, type=float, default=(300.0, 3000.0))
    ap.add_argument("--srp-subband", type=int, default=16)
    ap.add_argument("--hop-s", type=float, default=0.5)
    ap.add_argument("--ambig-eps", type=float, default=0.05)
    ap.add_argument("--agg", choices=["mode", "mean"], default="mode")
    ap.add_argument("--out", default="results/offline_eval.csv")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    files = sorted(glob.glob(os.path.join(args.audio_dir, args.pattern)))
    if not files:
        raise SystemExit(f"No files found: {os.path.join(args.audio_dir, args.pattern)}")

    setup_offset: Optional[float] = None
    if args.setup_file:
        # If you didn't implement load_setup yet, replace next 2 lines with:
        # setup_offset = load_calibration(args.setup_file)
        setup = load_setup(args.setup_file)
        setup_offset = float(setup.theta_offset_deg)

    rows = []
    unreadable = 0

    for f in files:
        meta = parse_name(f)
        theta_offset = 0.0

        if setup_offset is not None:
            theta_offset = setup_offset
            calib_used = args.setup_file
        else:
            calib_used = None
            if meta.dist_cm is not None:
                cfile = find_dist_calib(args.configs_dir, meta.dist_cm)
                if cfile:
                    theta_offset = float(load_calibration(cfile))
                    calib_used = cfile

        try:
            pred, dom, used, total = run_one(
                wav_path=f,
                theta_offset_deg=theta_offset,
                t0=args.t0,
                t1=args.t1,
                bandpass=tuple(args.bandpass) if args.bandpass else None,
                srp_subband=args.srp_subband,
                hop_s=args.hop_s,
                ambig_eps=args.ambig_eps,
                agg=args.agg,
            )
        except Exception as e:
            unreadable += 1
            rows.append(
                {
                    "file": f,
                    "expected_deg": meta.expected_deg,
                    "pred_deg": None,
                    "err_deg": None,
                    "dom_ratio": None,
                    "used": None,
                    "total": None,
                    "calib_used": calib_used,
                    "theta_offset_deg": theta_offset,
                    "status": f"ERROR: {e}",
                }
            )
            continue

        err = None
        if meta.expected_deg is not None:
            err = circular_error_deg(pred, meta.expected_deg)

        rows.append(
            {
                "file": f,
                "expected_deg": meta.expected_deg,
                "pred_deg": round(pred, 3),
                "err_deg": (round(err, 3) if err is not None else None),
                "dom_ratio": round(dom, 3),
                "used": used,
                "total": total,
                "calib_used": calib_used,
                "theta_offset_deg": round(theta_offset, 3),
                "status": "OK",
            }
        )

    with open(args.out, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(
            fp,
            fieldnames=[
                "file",
                "expected_deg",
                "pred_deg",
                "err_deg",
                "dom_ratio",
                "used",
                "total",
                "calib_used",
                "theta_offset_deg",
                "status",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if r["status"] == "OK" and r["err_deg"] is not None]
    errs = np.array([float(r["err_deg"]) for r in ok], dtype=float) if ok else np.array([], dtype=float)
    doms = np.array([float(r["dom_ratio"]) for r in rows if r["status"] == "OK" and r["dom_ratio"] is not None], dtype=float)

    print(f"Wrote: {args.out}")
    print(f"Total files: {len(rows)} | unreadable: {unreadable}")
    if errs.size:
        print(f"Abs error mean: {np.mean(np.abs(errs)):.2f}° | median: {np.median(np.abs(errs)):.2f}° | max: {np.max(np.abs(errs)):.2f}°")
    if doms.size:
        print(f"dom_ratio mean: {np.mean(doms):.2f} | low(<0.60): {int(np.sum(doms < 0.60))}/{doms.size}")


if __name__ == "__main__":
    main()