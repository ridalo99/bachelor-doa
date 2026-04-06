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

    grouped = df.groupby("gt_angle_deg")["abs_error_deg"].mean().reset_index()

    plt.figure(figsize=(7, 5))
    plt.plot(grouped["gt_angle_deg"], grouped["abs_error_deg"], marker="o")
    plt.xlabel("Sollwinkel [deg]")
    plt.ylabel("Mittlerer absoluter Fehler [deg]")
    plt.title("Mittlerer Fehler pro Winkel")
    plt.grid(True)
    plt.savefig(out_dir / "mean_error_per_angle.png", dpi=160, bbox_inches="tight")
    plt.close()

    print(f"Gespeichert: {out_dir / 'mean_error_per_angle.png'}")


if __name__ == "__main__":
    main()