# tools/export_ml_dataset.py
"""
Export a window-level dataset for ML from your recorded WAV files.

- Parses ground-truth angle + distance from filenames like:
    test_140deg_50cm.wav
    test_0deg_100cm.wav
- Runs the SAME SRP-PHAT code by importing 05_estimate_doa.py dynamically.
- Exports CSV with per-window features + labels.

Usage example:
  python3 tools/export_ml_dataset.py \
    --doa-script 05_estimate_doa.py \
    --glob "test_*deg_*cm*.wav" \
    --bandpass 500 6000 \
    --multi-range 1.7 11.3 \
    --win-s 0.25 --hop-s 0.5 --srp-subband 32 --ambig-eps 0.05 --agg mode \
    --out ml_windows.csv
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Meta:
    wav: Path
    gt_deg: float
    distance_m: float


def parse_meta(p: Path) -> Optional[Meta]:
    # test_140deg_50cm.wav
    m = re.search(r"(?i)(\d+(?:\.\d+)?)deg.*?(\d+(?:\.\d+)?)cm", p.name)
    if not m:
        return None
    gt = float(m.group(1))
    cm = float(m.group(2))
    return Meta(wav=p, gt_deg=gt, distance_m=cm / 100.0)


def calib_name_for_distance(distance_m: float) -> str:
    cm = int(round(distance_m * 100))
    return f"calib_{cm:03d}cm.json"  # e.g. calib_050cm.json


def load_module_from_path(py_path: Path):
    import sys
    import importlib.util

    module_name = f"doa_module_{py_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(py_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {py_path}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod  # <-- critical for dataclasses in py3.12
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doa-script", type=Path, default=Path("05_estimate_doa.py"))
    ap.add_argument("--glob", type=str, default="test_*deg_*cm*.wav")
    ap.add_argument("--out", type=Path, default=Path("ml_windows.csv"))

    ap.add_argument("--bandpass", nargs=2, type=float, default=(500.0, 6000.0))
    ap.add_argument("--multi-range", nargs=2, type=float, default=(1.7, 11.3))
    ap.add_argument("--win-s", type=float, default=0.25)
    ap.add_argument("--hop-s", type=float, default=0.5)
    ap.add_argument("--srp-subband", type=int, default=32)
    ap.add_argument("--ambig-eps", type=float, default=0.05)
    ap.add_argument("--agg", choices=["mode", "mean"], default="mode")

    ap.add_argument("--use-calib", action="store_true", help="If set, load calib_XXXcm.json per distance when it exists.")
    ap.add_argument("--no-nearfield", action="store_true", help="If set, do not pass source_distance_m (far-field).")

    args = ap.parse_args()

    doa = load_module_from_path(args.doa_script)

    wavs = sorted(Path(".").glob(args.glob))
    metas: List[Meta] = []
    for w in wavs:
        m = parse_meta(w)
        if m:
            metas.append(m)

    if not metas:
        raise SystemExit(f"No matching wavs for glob='{args.glob}'")

    rows: List[Dict[str, object]] = []
    for meta in metas:
        x, fs = doa.sf.read(str(meta.wav), always_2d=True)

        # optional bandpass on channels
        lo, hi = float(args.bandpass[0]), float(args.bandpass[1])
        x = doa.bandpass_sos(x, fs, lo, hi)

        theta_offset = 0.0
        calib_file = Path(calib_name_for_distance(meta.distance_m))
        if args.use_calib and calib_file.exists():
            theta_offset = float(doa.load_calibration(str(calib_file)))

        t0, t1 = float(args.multi_range[0]), float(args.multi_range[1])
        centers = []
        ct = t0 + args.win_s
        while ct <= t1 - args.win_s:
            centers.append(ct)
            ct += float(args.hop_s)

        used = 0
        total = 0

        for ct in centers:
            total += 1
            res = doa.eval_center(
                x=x,
                fs=fs,
                center_time_s=float(ct),
                win_s=float(args.win_s),
                srp_subband=int(args.srp_subband),
                sym_pair=False,
                source_distance_m=(None if args.no_nearfield else float(meta.distance_m)),
            )

            theta_calib = float((res.theta_raw + theta_offset) % 360)
            used_flag = float(res.confidence) >= float(args.ambig_eps)
            if used_flag:
                used += 1

            # top-2
            top1_deg, top1_score = res.topk[0]
            top2_deg, top2_score = res.topk[1] if len(res.topk) > 1 else (math.nan, math.nan)

            rows.append(
                {
                    "wav": str(meta.wav),
                    "distance_m": meta.distance_m,
                    "angle_gt_deg": meta.gt_deg,
                    "t_center_s": float(ct),
                    "theta_raw_deg": float(res.theta_raw),
                    "theta_calib_deg": float(theta_calib),
                    "theta_offset_deg": float(theta_offset),
                    "confidence": float(res.confidence),
                    "score_top1": float(res.score),
                    "top1_deg": float(top1_deg),
                    "top1_score": float(top1_score),
                    "top2_deg": float(top2_deg),
                    "top2_score": float(top2_score),
                    "used_flag": int(used_flag),
                    "calib_file": str(calib_file) if calib_file.exists() else "",
                }
            )

        # optional summary row per file (handy for debugging)
        rows.append(
            {
                "wav": str(meta.wav),
                "distance_m": meta.distance_m,
                "angle_gt_deg": meta.gt_deg,
                "t_center_s": "SUMMARY",
                "theta_raw_deg": "",
                "theta_calib_deg": "",
                "theta_offset_deg": float(theta_offset),
                "confidence": "",
                "score_top1": "",
                "top1_deg": "",
                "top1_score": "",
                "top2_deg": "",
                "top2_score": "",
                "used_flag": f"{used}/{total}",
                "calib_file": str(calib_file) if calib_file.exists() else "",
            }
        )

    # write CSV
    fieldnames = list(rows[0].keys())
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {args.out} with {len(rows)} rows.")
    print("Tip: use --use-calib to apply per-distance calibration (does NOT use ground truth at inference).")


if __name__ == "__main__":
    main()