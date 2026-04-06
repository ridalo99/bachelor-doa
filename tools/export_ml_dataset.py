from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.doa.pipeline import run_one


ANGLE_RE = re.compile(r"(\d+)deg", re.IGNORECASE)
DIST_RE = re.compile(r"(\d+)cm", re.IGNORECASE)
TAKE_RE = re.compile(r"take(\d+)", re.IGNORECASE)


def parse_meta(filename: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    angle = None
    dist = None
    take = None

    m = ANGLE_RE.search(filename)
    if m:
        angle = int(m.group(1))

    m = DIST_RE.search(filename)
    if m:
        dist = int(m.group(1))

    m = TAKE_RE.search(filename)
    if m:
        take = int(m.group(1))

    return angle, dist, take


def main() -> None:
    audio_dir = Path("audio")
    out_csv = Path("tools/doa_dataset.csv")
    calib_file = "configs/setup_front.json"

    wav_files = sorted(audio_dir.glob("chirp_*deg_*cm_take*.wav"))

    rows = []

    for wav_path in wav_files:
        gt_angle, dist_cm, take = parse_meta(wav_path.name)

        try:
            result = run_one(
                wav_path=str(wav_path),
                band=(500.0, 4000.0),
                tone_hz=None,
                tone_bw_hz=None,
                seg_thr_ratio=2.0,
                debug=False,
                calib_file=calib_file,
                auto_window=True,
                model="far",
            )
        except Exception as e:
            print(f"[WARN] Fehler bei {wav_path.name}: {e}")
            continue

        final_theta = result.get("theta_deg")
        final_dom = result.get("dom_ratio")
        accepted = result.get("accepted_events")
        total_events = result.get("total_events")

        rows.append(
            {
                "file": wav_path.name,
                "gt_angle_deg": gt_angle,
                "distance_cm": dist_cm,
                "take": take,
                "pred_angle_deg": final_theta,
                "dom_ratio": final_dom,
                "accepted_events": accepted,
                "total_events": total_events,
            }
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "file",
                "gt_angle_deg",
                "distance_cm",
                "take",
                "pred_angle_deg",
                "dom_ratio",
                "accepted_events",
                "total_events",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Gespeichert: {out_csv}")


if __name__ == "__main__":
    main()