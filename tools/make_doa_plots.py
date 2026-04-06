from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def circular_error_deg(gt: float, pred: float) -> float:
    d = (pred - gt + 180.0) % 360.0 - 180.0
    return abs(d)


def main() -> None:
    csv_path = Path("tools/doa_dataset.csv")
    out_dir = Path("tools/plots")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["gt_angle_deg", "pred_angle_deg"]).copy()

    df["abs_error_deg"] = [
        circular_error_deg(gt, pred)
        for gt, pred in zip(df["gt_angle_deg"], df["pred_angle_deg"])
    ]

    # Plot 1: GT vs Pred
    plt.figure(figsize=(7, 6))
    plt.scatter(df["gt_angle_deg"], df["pred_angle_deg"])
    plt.xlabel("Sollwinkel [deg]")
    plt.ylabel("Geschätzter Winkel [deg]")
    plt.title("Sollwinkel vs. geschätzter Winkel")
    plt.grid(True)
    plt.savefig(out_dir / "gt_vs_pred.png", dpi=160, bbox_inches="tight")
    plt.close()

    # Plot 2: Fehler pro Datei
    plt.figure(figsize=(10, 5))
    plt.bar(df["file"], df["abs_error_deg"])
    plt.xticks(rotation=90)
    plt.ylabel("Absoluter Fehler [deg]")
    plt.title("Fehler pro Datei")
    plt.grid(True, axis="y")
    plt.savefig(out_dir / "error_per_file.png", dpi=160, bbox_inches="tight")
    plt.close()

    print(f"Plots gespeichert in: {out_dir}")


if __name__ == "__main__":
    main()