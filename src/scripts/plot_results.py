# scripts/plot_results.py
from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt


RE_FILE = re.compile(r"^===\s+(.*?)\s+===", re.M)
RE_MODEL = re.compile(r"Model:\s+near-field\s+\(r=(\d+(?:\.\d+)?)\s+m\)")
RE_FINAL = re.compile(
    r"Final DOA.*?:\s+(UNCERTAIN|(\d+(?:\.\d+)?))°\s+\(accepted\s+(\d+)/(\d+),\s+dom=([0-9.]+)\)"
)
RE_GT = re.compile(r"_(\d+)deg_")


@dataclass(frozen=True)
class Row:
    file: str
    r_m: float
    gt_deg: float
    pred_deg: Optional[float]  # None if UNCERTAIN
    accepted: int
    total: int
    dom: float


def circ_err_deg(gt: float, pred: float) -> float:
    """Smallest absolute angular difference in degrees (0..180)."""
    d = (pred - gt) % 360.0
    if d > 180.0:
        d -= 360.0
    return abs(d)


def parse_log(path: Path) -> list[Row]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = RE_FILE.split(text)
    # blocks: [prefix, file1, rest1, file2, rest2, ...]
    rows: list[Row] = []
    for i in range(1, len(blocks), 2):
        file_path = blocks[i].strip()
        body = blocks[i + 1]

        m_model = RE_MODEL.search(body)
        if not m_model:
            continue
        r_m = float(m_model.group(1))

        m_gt = RE_GT.search(file_path)
        if not m_gt:
            # fall back: search inside body
            m_gt = RE_GT.search(body)
        if not m_gt:
            continue
        gt = float(m_gt.group(1)) % 360.0

        m_final = RE_FINAL.search(body)
        if not m_final:
            continue

        if m_final.group(1) == "UNCERTAIN":
            pred = None
        else:
            pred = float(m_final.group(2)) % 360.0

        accepted = int(m_final.group(3))
        total = int(m_final.group(4))
        dom = float(m_final.group(5))

        rows.append(Row(file=file_path, r_m=r_m, gt_deg=gt, pred_deg=pred, accepted=accepted, total=total, dom=dom))
    return rows


def summarize(rows: list[Row]) -> dict[str, float]:
    n = len(rows)
    n_unc = sum(1 for r in rows if r.pred_deg is None)
    decided = [r for r in rows if r.pred_deg is not None]
    errors = [circ_err_deg(r.gt_deg, float(r.pred_deg)) for r in decided]
    mae = sum(errors) / len(errors) if errors else float("nan")
    med = sorted(errors)[len(errors) // 2] if errors else float("nan")
    return {
        "n": n,
        "n_decided": len(decided),
        "n_uncertain": n_unc,
        "uncertain_rate": (n_unc / n) if n else float("nan"),
        "mae_deg": mae,
        "median_err_deg": med,
    }


def save_text_summary(outdir: Path, name: str, stats: dict[str, float]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"{name}_summary.txt"
    lines = [
        f"n={int(stats['n'])}",
        f"n_decided={int(stats['n_decided'])}",
        f"n_uncertain={int(stats['n_uncertain'])}",
        f"uncertain_rate={stats['uncertain_rate']:.3f}",
        f"mae_deg={stats['mae_deg']:.2f}",
        f"median_err_deg={stats['median_err_deg']:.2f}",
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_scatter(outdir: Path, name: str, rows: list[Row]) -> None:
    decided = [r for r in rows if r.pred_deg is not None]
    if not decided:
        return
    xs = [r.gt_deg for r in decided]
    ys = [float(r.pred_deg) for r in decided]

    plt.figure()
    plt.scatter(xs, ys, s=18)
    plt.xlabel("Ground truth angle (deg)")
    plt.ylabel("Predicted angle (deg)")
    plt.title(f"{name}: true vs predicted (decided only)")
    plt.xlim(-5, 365)
    plt.ylim(-5, 365)
    plt.grid(True, alpha=0.3)
    plt.savefig(outdir / f"{name}_scatter.png", dpi=180, bbox_inches="tight")
    plt.close()


def plot_error_by_angle(outdir: Path, name: str, rows: list[Row]) -> None:
    # group by gt angle
    groups: dict[int, list[float]] = {}
    for r in rows:
        if r.pred_deg is None:
            continue
        k = int(round(r.gt_deg)) % 360
        groups.setdefault(k, []).append(circ_err_deg(r.gt_deg, float(r.pred_deg)))

    if not groups:
        return

    angles = sorted(groups.keys())
    means = [sum(groups[a]) / len(groups[a]) for a in angles]
    counts = [len(groups[a]) for a in angles]

    plt.figure()
    plt.scatter(angles, means, s=22)
    plt.xlabel("Ground truth angle (deg)")
    plt.ylabel("Mean absolute error (deg)")
    plt.title(f"{name}: mean error per angle (decided only)")
    plt.grid(True, alpha=0.3)
    plt.savefig(outdir / f"{name}_mean_error_per_angle.png", dpi=180, bbox_inches="tight")
    plt.close()

    plt.figure()
    plt.scatter(angles, counts, s=22)
    plt.xlabel("Ground truth angle (deg)")
    plt.ylabel("Decided count")
    plt.title(f"{name}: decided samples per angle")
    plt.grid(True, alpha=0.3)
    plt.savefig(outdir / f"{name}_decided_count_per_angle.png", dpi=180, bbox_inches="tight")
    plt.close()


def plot_uncertain_rate_by_angle(outdir: Path, name: str, rows: list[Row]) -> None:
    totals: dict[int, int] = {}
    uncs: dict[int, int] = {}
    for r in rows:
        k = int(round(r.gt_deg)) % 360
        totals[k] = totals.get(k, 0) + 1
        if r.pred_deg is None:
            uncs[k] = uncs.get(k, 0) + 1

    angles = sorted(totals.keys())
    rates = [(uncs.get(a, 0) / totals[a]) for a in angles]

    plt.figure()
    plt.scatter(angles, rates, s=22)
    plt.xlabel("Ground truth angle (deg)")
    plt.ylabel("UNCERTAIN rate")
    plt.title(f"{name}: UNCERTAIN rate per angle")
    plt.ylim(-0.05, 1.05)
    plt.grid(True, alpha=0.3)
    plt.savefig(outdir / f"{name}_uncertain_rate_per_angle.png", dpi=180, bbox_inches="tight")
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("logfiles", nargs="+", help="Log files, e.g. results_1m.log results_2m.log")
    ap.add_argument("--outdir", default="plots", help="Output directory for plots")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for lf in args.logfiles:
        p = Path(lf)
        rows = parse_log(p)
        name = p.stem

        stats = summarize(rows)
        save_text_summary(outdir, name, stats)
        plot_scatter(outdir, name, rows)
        plot_error_by_angle(outdir, name, rows)
        plot_uncertain_rate_by_angle(outdir, name, rows)

        print(f"[{name}] n={int(stats['n'])} decided={int(stats['n_decided'])} "
              f"unc={int(stats['n_uncertain'])} unc_rate={stats['uncertain_rate']:.3f} "
              f"MAE={stats['mae_deg']:.2f} median={stats['median_err_deg']:.2f}")

    print(f"Saved plots + summaries to: {outdir.resolve()}")


if __name__ == "__main__":
    main()