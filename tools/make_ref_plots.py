from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def circular_error_deg(pred: float, true: float) -> float:
    d = (pred - true + 180.0) % 360.0 - 180.0
    return abs(d)


def main() -> None:
    csv_path = Path("ref_results_2026-04-09.csv")
    out_dir = Path("plots_ref_2026-04-09")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    df["abs_circ_err_deg"] = [
        circular_error_deg(p, t) for p, t in zip(df["pred_deg"], df["angle_deg"])
    ]

    status_order = {"good": 0, "usable": 1, "bad": 2, "reject": 3}
    df["status_order"] = df["status"].map(status_order).fillna(99)

    best_df = (
        df.sort_values(["angle_deg", "status_order", "take"])
        .groupby("angle_deg", as_index=False)
        .first()
    )

    # Plot 1: all takes, true vs predicted
    plt.figure(figsize=(8, 6))
    for status, g in df.groupby("status"):
        plt.scatter(g["angle_deg"], g["pred_deg"], label=status)
    plt.plot([0, 360], [0, 360], linestyle="--")
    plt.xlim(-5, 365)
    plt.ylim(-5, 365)
    plt.xlabel("Sollwinkel [deg]")
    plt.ylabel("Geschaetzter Winkel [deg]")
    plt.title("Alle Takes: Sollwinkel vs. geschaetzter Winkel")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "01_all_takes_true_vs_pred.png", dpi=180)
    plt.close()

    # Plot 2: best/representative per angle
    plt.figure(figsize=(8, 6))
    plt.scatter(best_df["angle_deg"], best_df["pred_deg"])
    for _, row in best_df.iterrows():
        plt.annotate(
            f'{int(row["pred_deg"])}°',
            (row["angle_deg"], row["pred_deg"]),
            textcoords="offset points",
            xytext=(4, 4),
        )
    plt.plot([0, 360], [0, 360], linestyle="--")
    plt.xlim(-5, 365)
    plt.ylim(-5, 365)
    plt.xlabel("Sollwinkel [deg]")
    plt.ylabel("Repraesentativer geschaetzter Winkel [deg]")
    plt.title("Repraesentativer Winkel pro Sollwinkel")
    plt.tight_layout()
    plt.savefig(out_dir / "02_best_per_angle_true_vs_pred.png", dpi=180)
    plt.close()

    # Plot 3: circular error for representative results
    plt.figure(figsize=(9, 4.8))
    plt.bar(best_df["angle_deg"].astype(str), best_df["abs_circ_err_deg"])
    plt.xlabel("Sollwinkel [deg]")
    plt.ylabel("Absoluter zirkulaerer Fehler [deg]")
    plt.title("Repraesentativer Fehler pro Sollwinkel")
    plt.tight_layout()
    plt.savefig(out_dir / "03_best_per_angle_circular_error.png", dpi=180)
    plt.close()

    # Summary table
    summary_path = out_dir / "summary_best_per_angle.csv"
    best_df[["angle_deg", "take", "pred_deg", "status", "note", "abs_circ_err_deg"]].to_csv(
        summary_path, index=False
    )

    print(f"Plots geschrieben nach: {out_dir.resolve()}")
    print(f"Summary CSV: {summary_path.resolve()}")


if __name__ == "__main__":
    main()
