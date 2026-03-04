# tools/make_doa_plots.py
"""
Make BA-ready DOA plots from an exported window-level CSV (e.g. ml_windows_calib.csv).

What it does:
- Reads the window CSV.
- Builds a FILE-level summary by aggregating windows per wav (confidence-weighted MODE over used windows).
- Writes: file_level_summary.csv
- Creates plots:
  1) MAE vs distance (file-level)
  2) Estimated vs GT (file-level)
  3) Abs error vs confidence (window-level, used windows)
  4) Abs error vs used_ratio (file-level)

Usage:
  python3 tools/make_doa_plots.py --csv ml_windows_calib.csv --outdir plots/today
  python3 tools/make_doa_plots.py --csv results/ml_windows_calib_all.csv --outdir plots/2026-03-04

Notes:
- Expects columns (from our exporter): wav, distance_m, angle_gt_deg, t_center_s, theta_calib_deg, confidence, used_flag
- If used_flag is string "0"/"1", the script converts it to int.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def circular_error_deg(est: float, gt: float) -> float:
    d = (est - gt) % 360.0
    if d > 180.0:
        d -= 360.0
    return float(d)


def weighted_mode_deg(angles_deg: np.ndarray, weights: np.ndarray) -> float:
    a = (np.round(np.asarray(angles_deg)) % 360).astype(int)
    w = np.maximum(1e-6, np.asarray(weights, dtype=float))
    acc = np.zeros(360, dtype=float)
    for ai, wi in zip(a, w):
        acc[ai] += float(wi)
    return float(int(np.argmax(acc)))


def ensure_cols(df: pd.DataFrame, required: Tuple[str, ...]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"CSV missing columns: {missing}\nGot: {list(df.columns)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True, help="Window-level CSV (ml_windows_*.csv).")
    ap.add_argument("--outdir", type=Path, required=True, help="Output folder for plots and summaries.")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.csv)
    ensure_cols(
        df,
        required=("wav", "distance_m", "angle_gt_deg", "t_center_s", "theta_calib_deg", "confidence", "used_flag"),
    )

    df["t_center_s_num"] = pd.to_numeric(df["t_center_s"], errors="coerce")
    dfw = df[df["t_center_s_num"].notna()].copy()

    dfw["used_flag"] = pd.to_numeric(dfw["used_flag"], errors="coerce").fillna(0).astype(int)
    dfw["confidence"] = pd.to_numeric(dfw["confidence"], errors="coerce").fillna(0.0).astype(float)
    dfw["theta_calib_deg"] = pd.to_numeric(dfw["theta_calib_deg"], errors="coerce").astype(float)
    dfw["angle_gt_deg"] = pd.to_numeric(dfw["angle_gt_deg"], errors="coerce").astype(float)
    dfw["distance_m"] = pd.to_numeric(dfw["distance_m"], errors="coerce").astype(float)

    # -------------------------
    # FILE-level summary
    # -------------------------
    file_rows = []
    for wav, g in dfw.groupby("wav"):
        used = g[g["used_flag"] == 1]
        base = used if len(used) else g  # fallback: if everything is ambiguous, still summarize

        est = weighted_mode_deg(base["theta_calib_deg"].values, base["confidence"].values)
        gt = float(base["angle_gt_deg"].iloc[0])
        dist = float(base["distance_m"].iloc[0])

        err = circular_error_deg(est, gt)
        file_rows.append(
            {
                "wav": wav,
                "distance_m": dist,
                "gt_deg": gt,
                "est_deg": est,
                "err_deg": err,
                "abs_err_deg": abs(err),
                "used_windows": int(len(used)),
                "total_windows": int(len(g)),
                "used_ratio": (len(used) / len(g)) if len(g) else math.nan,
                "mean_conf": float(g["confidence"].mean()),
                "median_conf": float(g["confidence"].median()),
            }
        )

    file_df = pd.DataFrame(file_rows).sort_values(["distance_m", "gt_deg", "wav"]).reset_index(drop=True)
    summary_csv = args.outdir / "file_level_summary.csv"
    file_df.to_csv(summary_csv, index=False)

    mae_by_dist = file_df.groupby("distance_m")["abs_err_deg"].mean().reset_index().sort_values("distance_m")

    # -------------------------
    # Plot 1: MAE vs distance
    # -------------------------
    plt.figure()
    plt.plot(mae_by_dist["distance_m"], mae_by_dist["abs_err_deg"], marker="o")
    plt.xlabel("Distance (m)")
    plt.ylabel("Mean Absolute Error (deg)")
    plt.title("DOA Accuracy vs Distance (file-level MAE)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(args.outdir / "mae_vs_distance.png", dpi=200)
    plt.close()

    # -------------------------
    # Plot 2: Estimated vs GT
    # -------------------------
    plt.figure()
    plt.scatter(file_df["gt_deg"], file_df["est_deg"])
    plt.plot([0, 360], [0, 360])
    plt.xlabel("Ground truth angle (deg)")
    plt.ylabel("Estimated angle (deg)")
    plt.title("Estimated vs Ground Truth (file-level)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(args.outdir / "est_vs_gt.png", dpi=200)
    plt.close()

    # -------------------------
    # Plot 3: Abs error vs confidence (window-level, used windows)
    # -------------------------
    used_w = dfw[dfw["used_flag"] == 1].copy()
    used_w["abs_err_deg"] = (used_w["theta_calib_deg"] - used_w["angle_gt_deg"]).apply(
        lambda x: abs(((x % 360) - 360) if (x % 360) > 180 else (x % 360))
    )

    plt.figure()
    plt.scatter(used_w["confidence"], used_w["abs_err_deg"])
    plt.xlabel("Confidence")
    plt.ylabel("Absolute error (deg)")
    plt.title("Window-level error vs confidence (used windows)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(args.outdir / "abs_err_vs_conf_used.png", dpi=200)
    plt.close()

    # -------------------------
    # Plot 4: File-level error vs used_ratio
    # -------------------------
    plt.figure()
    plt.scatter(file_df["used_ratio"], file_df["abs_err_deg"])
    plt.xlabel("Used window ratio")
    plt.ylabel("Absolute error (deg)")
    plt.title("File-level error vs used-window ratio")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(args.outdir / "abs_err_vs_used_ratio.png", dpi=200)
    plt.close()

    print(f"Wrote: {summary_csv}")
    print(f"Plots in: {args.outdir}")
    print("  - mae_vs_distance.png")
    print("  - est_vs_gt.png")
    print("  - abs_err_vs_conf_used.png")
    print("  - abs_err_vs_used_ratio.png")


if __name__ == "__main__":
    main()