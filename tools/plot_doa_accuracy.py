# tools/plot_doa_accuracy.py
"""
Run DOA estimation on a set of WAV files, export CSV, and plot accuracy vs distance.

Assumptions:
- Filenames like: test_140deg_50cm.wav OR test_0deg_181cm.wav OR r0.50m_140deg_take1.wav
- Uses 05_estimate_doa.py (your pipeline) in multi-window mode by default.

Edit CONFIG section if you want different time windows / bandpass / etc.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt


# -------------------------
# CONFIG defaults (match your proven settings)
# -------------------------
DEFAULT_BANDPASS = (500, 6000)
DEFAULT_MULTI_RANGE = (1.7, 11.3)
DEFAULT_WIN_S = 0.25
DEFAULT_HOP_S = 0.5
DEFAULT_SRP_SUBBAND = 32
DEFAULT_AMBIG_EPS = 0.05
DEFAULT_AGG = "mode"


# -------------------------
# Parsing helpers
# -------------------------
def circular_error_deg(est: float, gt: float) -> float:
    """Return signed circular error in [-180, 180]."""
    d = (est - gt) % 360.0
    if d > 180.0:
        d -= 360.0
    return float(d)


@dataclass(frozen=True)
class FileMeta:
    path: Path
    distance_m: float
    gt_deg: float
    take: int


def parse_meta_from_name(p: Path) -> Optional[FileMeta]:
    name = p.name

    # Pattern A: test_140deg_50cm.wav / test_0deg_181cm.wav
    m = re.search(r"(?i)(\d+(?:\.\d+)?)\s*deg.*?(\d+(?:\.\d+)?)\s*cm", name)
    if m:
        gt = float(m.group(1))
        cm = float(m.group(2))
        take = 1
        m_take = re.search(r"(?i)take(\d+)", name)
        if m_take:
            take = int(m_take.group(1))
        return FileMeta(path=p, distance_m=cm / 100.0, gt_deg=gt, take=take)

    # Pattern B: r0.50m_140deg_take1.wav
    m = re.search(r"(?i)r(\d+(?:\.\d+)?)m.*?(\d+(?:\.\d+)?)deg", name)
    if m:
        dist = float(m.group(1))
        gt = float(m.group(2))
        take = 1
        m_take = re.search(r"(?i)take(\d+)", name)
        if m_take:
            take = int(m_take.group(1))
        return FileMeta(path=p, distance_m=dist, gt_deg=gt, take=take)

    return None


def run_estimator(
    doa_script: Path,
    wav_path: Path,
    distance_m: float,
    calib_file: Optional[Path],
    bandpass: Tuple[int, int],
    multi_range: Tuple[float, float],
    win_s: float,
    hop_s: float,
    srp_subband: int,
    ambig_eps: float,
    agg: str,
) -> Tuple[float, int, int, str]:
    """
    Returns: (final_deg, used_windows, total_windows, raw_output)
    """
    cmd = [
        sys.executable,
        str(doa_script),
        "--wav",
        str(wav_path),
        "--bandpass",
        str(bandpass[0]),
        str(bandpass[1]),
        "--multi-range",
        str(multi_range[0]),
        str(multi_range[1]),
        "--win-s",
        str(win_s),
        "--hop-s",
        str(hop_s),
        "--srp-subband",
        str(srp_subband),
        "--ambig-eps",
        str(ambig_eps),
        "--agg",
        str(agg),
        "--source-distance-m",
        str(distance_m),
    ]
    if calib_file is not None and calib_file.exists():
        cmd += ["--calib-file", str(calib_file)]

    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)

    # Parse "Final DOA (multi-window): X°"
    m_final = re.search(r"Final DOA \(multi-window\):\s*([0-9.]+)", out)
    if not m_final:
        raise RuntimeError(f"Could not parse final DOA from output of {wav_path.name}\n\n{out}")

    final_deg = float(m_final.group(1))

    # Parse "Multi-window: used X/Y"
    m_used = re.search(r"Multi-window:\s*used\s+(\d+)\s*/\s*(\d+)", out)
    if not m_used:
        used, total = -1, -1
    else:
        used, total = int(m_used.group(1)), int(m_used.group(2))

    return final_deg, used, total, out


def ensure_calib(
    doa_script: Path,
    files: List[FileMeta],
    distance_m: float,
    calib_path: Path,
    bandpass: Tuple[int, int],
    multi_range: Tuple[float, float],
    win_s: float,
    hop_s: float,
    srp_subband: int,
    ambig_eps: float,
    agg: str,
) -> None:
    """
    If calib file doesn't exist, auto-calibrate from gt 0° and 90° for that distance.
    """
    if calib_path.exists():
        return

    f0 = next((f for f in files if abs(f.distance_m - distance_m) < 1e-6 and abs((f.gt_deg % 360) - 0) < 1e-6), None)
    f90 = next((f for f in files if abs(f.distance_m - distance_m) < 1e-6 and abs((f.gt_deg % 360) - 90) < 1e-6), None)

    if f0 is None or f90 is None:
        raise RuntimeError(
            f"Need 0° and 90° files for distance {distance_m:.2f} m to auto-calibrate.\n"
            f"Missing: {'0°' if f0 is None else ''} {'90°' if f90 is None else ''}"
        )

    cmd = [
        sys.executable,
        str(doa_script),
        "--calibrate",
        str(calib_path),
        f"{f0.path}=0",
        f"{f90.path}=90",
        "--calib-multi-range",
        str(multi_range[0]),
        str(multi_range[1]),
        "--bandpass",
        str(bandpass[0]),
        str(bandpass[1]),
        "--win-s",
        str(win_s),
        "--hop-s",
        str(hop_s),
        "--srp-subband",
        str(srp_subband),
        "--ambig-eps",
        str(ambig_eps),
        "--agg",
        str(agg),
        "--source-distance-m",
        str(distance_m),
    ]
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doa-script", type=Path, default=Path("05_estimate_doa.py"))
    ap.add_argument("--glob", type=str, default="test_*deg_*cm*.wav")
    ap.add_argument("--out-csv", type=Path, default=Path("results.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("plots"))
    ap.add_argument("--no-auto-calib", action="store_true")
    args = ap.parse_args()

    wavs = sorted(Path(".").glob(args.glob))
    metas: List[FileMeta] = []
    for w in wavs:
        meta = parse_meta_from_name(w)
        if meta:
            metas.append(meta)

    if not metas:
        raise SystemExit(f"No wavs matched meta pattern using glob='{args.glob}' in {Path('.').resolve()}")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Group by distance
    distances = sorted({m.distance_m for m in metas})

    rows: List[Dict[str, object]] = []
    for dist in distances:
        calib = Path(f"calib_{int(round(dist*100)):03d}cm.json")  # e.g. calib_050cm.json
        if not args.no_auto_calib:
            ensure_calib(
                doa_script=args.doa_script,
                files=metas,
                distance_m=dist,
                calib_path=calib,
                bandpass=DEFAULT_BANDPASS,
                multi_range=DEFAULT_MULTI_RANGE,
                win_s=DEFAULT_WIN_S,
                hop_s=DEFAULT_HOP_S,
                srp_subband=DEFAULT_SRP_SUBBAND,
                ambig_eps=DEFAULT_AMBIG_EPS,
                agg=DEFAULT_AGG,
            )

        for m in [x for x in metas if abs(x.distance_m - dist) < 1e-6]:
            final_deg, used, total, _ = run_estimator(
                doa_script=args.doa_script,
                wav_path=m.path,
                distance_m=dist,
                calib_file=(calib if calib.exists() else None),
                bandpass=DEFAULT_BANDPASS,
                multi_range=DEFAULT_MULTI_RANGE,
                win_s=DEFAULT_WIN_S,
                hop_s=DEFAULT_HOP_S,
                srp_subband=DEFAULT_SRP_SUBBAND,
                ambig_eps=DEFAULT_AMBIG_EPS,
                agg=DEFAULT_AGG,
            )
            err = circular_error_deg(final_deg, m.gt_deg)
            rows.append(
                {
                    "wav": str(m.path),
                    "distance_m": dist,
                    "angle_gt_deg": m.gt_deg,
                    "take": m.take,
                    "final_deg": final_deg,
                    "error_deg": err,
                    "abs_error_deg": abs(err),
                    "used_windows": used,
                    "total_windows": total,
                    "used_ratio": (used / total) if used > 0 and total > 0 else math.nan,
                    "calib_file": str(calib) if calib.exists() else "",
                }
            )

    # Write CSV
    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Plot 1: MAE vs distance
    by_dist: Dict[float, List[float]] = {}
    for r in rows:
        by_dist.setdefault(float(r["distance_m"]), []).append(float(r["abs_error_deg"]))
    d_sorted = sorted(by_dist.keys())
    mae = [sum(by_dist[d]) / len(by_dist[d]) for d in d_sorted]

    plt.figure()
    plt.plot(d_sorted, mae, marker="o")
    plt.xlabel("Distance (m)")
    plt.ylabel("Mean Absolute Error (deg)")
    plt.title("DOA Accuracy vs Distance (MAE)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(args.out_dir / "mae_vs_distance.png", dpi=200)
    plt.close()

    # Plot 2: Scatter error vs distance
    plt.figure()
    plt.scatter([float(r["distance_m"]) for r in rows], [float(r["error_deg"]) for r in rows])
    plt.xlabel("Distance (m)")
    plt.ylabel("Signed Error (deg)")
    plt.title("DOA Error vs Distance")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(args.out_dir / "error_scatter_vs_distance.png", dpi=200)
    plt.close()

    print(f"Wrote: {args.out_csv}")
    print(f"Plots in: {args.out_dir}/ (mae_vs_distance.png, error_scatter_vs_distance.png)")


if __name__ == "__main__":
    main()