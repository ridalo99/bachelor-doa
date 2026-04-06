# src/scripts/tap_map.py
"""
Tap mapping helper.

Usage:
  python3 src/scripts/tap_map.py --wav audio/tap_check.wav

Outputs which channel dominates in each tap block.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class BlockResult:
    t0: float
    t1: float
    peak_per_ch: List[float]
    best_ch: int


def _find_blocks(env: np.ndarray, fs: int, thr: float, min_gap_s: float = 0.6) -> List[Tuple[int, int]]:
    active = env > thr
    idx = np.where(active)[0]
    if idx.size == 0:
        return []
    # group active indices into blocks separated by gaps
    blocks = []
    start = idx[0]
    prev = idx[0]
    min_gap = int(min_gap_s * fs)
    for i in idx[1:]:
        if i - prev > min_gap:
            blocks.append((start, prev))
            start = i
        prev = i
    blocks.append((start, prev))
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--thr-ratio", type=float, default=6.0, help="threshold = median(env) * thr_ratio")
    ap.add_argument("--env-hop-ms", type=float, default=5.0)
    args = ap.parse_args()

    x, fs = sf.read(args.wav, always_2d=True)
    x = x.astype(np.float64, copy=False)
    n, ch = x.shape
    print("shape:", x.shape, "fs:", fs)

    mono = np.mean(np.abs(x), axis=1)
    hop = max(1, int(args.env_hop_ms / 1000.0 * fs))
    env = mono[::hop]
    thr = float(np.median(env) * args.thr_ratio)

    blocks_ds = _find_blocks(env, fs=fs // hop if hop > 1 else fs, thr=thr)
    if not blocks_ds:
        raise SystemExit("No tap blocks found. Try lower --thr-ratio or tap louder with pauses.")

    # convert downsampled indices to sample indices
    blocks = [(s * hop, min(n - 1, e * hop)) for s, e in blocks_ds]

    results: List[BlockResult] = []
    for (s, e) in blocks[:6]:
        seg = x[s : e + 1]
        peak = np.max(np.abs(seg), axis=0)
        best = int(np.argmax(peak)) + 1  # 1-based
        results.append(
            BlockResult(
                t0=s / fs,
                t1=e / fs,
                peak_per_ch=[float(p) for p in peak],
                best_ch=best,
            )
        )

    print("\nDetected tap blocks (showing up to 6):")
    for i, r in enumerate(results, 1):
        peaks = " ".join([f"ch{k+1}:{p:.5f}" for k, p in enumerate(r.peak_per_ch)])
        print(f"  block{i}: {r.t0:.2f}-{r.t1:.2f}s | best=ch{r.best_ch} | {peaks}")

    print("\nIf you tapped in order M1->M2->M3->M4 with clear pauses, map:")
    for i, r in enumerate(results[:4], 1):
        print(f"  tap{i} -> ch{r.best_ch}")


if __name__ == "__main__":
    main()