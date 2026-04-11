# File: src/scripts/09_music_debug.py
from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import soundfile as sf

from doa.dsp import bandpass_sos, clip_center_window
from doa.geometry import CH_ORDER, MICS, unit_direction
from doa.pairwise import pick_event_window


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MUSIC DOA debug on one 4ch wav file.")
    p.add_argument("--wav", required=True, help="Path to one 4ch wav file.")
    p.add_argument("--bandpass", nargs=2, type=float, default=None, metavar=("LO_HZ", "HI_HZ"))
    p.add_argument("--win-s", type=float, default=0.15)
    p.add_argument("--time-range", nargs=2, type=float, default=None, metavar=("T0", "T1"))

    p.add_argument("--auto-window", action="store_true")
    p.add_argument("--auto-window-len", type=float, default=0.40)
    p.add_argument("--auto-window-hop", type=float, default=0.01)
    p.add_argument("--auto-window-expand", type=float, default=0.05)
    p.add_argument("--auto-window-min-gap", type=float, default=0.80)

    p.add_argument("--nfft", type=int, default=2048)
    p.add_argument("--fmin", type=float, default=700.0)
    p.add_argument("--fmax", type=float, default=5000.0)
    p.add_argument("--theta-step", type=float, default=1.0)
    p.add_argument("--topk", type=int, default=5)

    return p.parse_args(argv)


def _music_spectrum(
    xw: np.ndarray,
    fs: int,
    theta_grid_deg: np.ndarray,
    fmin: float,
    fmax: float,
    nfft: int,
) -> np.ndarray:
    xw = np.asarray(xw, dtype=np.float64)
    n, m = xw.shape
    if m != 4:
        raise ValueError(f"Expected 4 channels after CH_ORDER, got {m}")

    if n < 32:
        raise ValueError("Window too short for MUSIC")

    nperseg = min(int(nfft), n)
    if nperseg < 64:
        raise ValueError("nperseg too small for MUSIC")

    step = max(nperseg // 2, 1)
    starts = list(range(0, max(1, n - nperseg + 1), step))
    if not starts:
        starts = [0]

    window = np.hanning(nperseg)
    freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)
    use_bins = np.where((freqs >= float(fmin)) & (freqs <= float(fmax)))[0]
    if use_bins.size == 0:
        raise ValueError("No frequency bins inside fmin..fmax")

    spectra = []
    for s in starts:
        seg = xw[s : s + nperseg]
        if seg.shape[0] < nperseg:
            pad = np.zeros((nperseg - seg.shape[0], m), dtype=np.float64)
            seg = np.vstack([seg, pad])
        seg = seg * window[:, None]
        X = np.fft.rfft(seg, axis=0)
        spectra.append(X)
    Xall = np.stack(spectra, axis=0)  # [frames, bins, mics]

    P = np.zeros(theta_grid_deg.shape[0], dtype=np.float64)
    c = 343.0

    for b in use_bins:
        f = float(freqs[b])
        Xf = Xall[:, b, :]  # [frames, mics]

        R = np.zeros((m, m), dtype=np.complex128)
        for frame in range(Xf.shape[0]):
            x = Xf[frame, :][:, None]
            R += x @ x.conj().T
        R /= max(Xf.shape[0], 1)

        evals, evecs = np.linalg.eigh(R)
        idx = np.argsort(evals)[::-1]
        evecs = evecs[:, idx]

        # 1 source -> noise subspace uses remaining vectors
        En = evecs[:, 1:]
        if En.shape[1] == 0:
            continue

        k = 2.0 * np.pi * f / c

        for i, theta in enumerate(theta_grid_deg):
            u = unit_direction(float(theta))
            delays = -(MICS @ u) / c
            a = np.exp(-1j * 2.0 * np.pi * f * delays)[:, None]
            denom = np.linalg.norm(En.conj().T @ a) ** 2
            P[i] += 1.0 / max(float(denom.real), 1e-12)

    return P


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)

    x, fs = sf.read(args.wav, always_2d=True)
    if args.bandpass is not None:
        lo, hi = map(float, args.bandpass)
        x = bandpass_sos(x, fs, lo, hi)

    x = x[:, CH_ORDER]
    x_mono = np.mean(x, axis=1).astype(np.float64)

    event = pick_event_window(
        x=x,
        fs=fs,
        x_mono=x_mono,
        time_range=tuple(args.time_range) if args.time_range is not None else None,
        auto_window=bool(args.auto_window),
        auto_window_len_s=float(args.auto_window_len),
        auto_window_hop_s=float(args.auto_window_hop),
        auto_window_expand_s=float(args.auto_window_expand),
        auto_window_min_gap_s=float(args.auto_window_min_gap),
    )

    center = int(float(event.center_time_s) * fs)
    s, t = clip_center_window(center, fs, x.shape[0], float(args.win_s))
    xw = x[s:t]

    theta_grid = np.arange(0.0, 360.0, float(args.theta_step), dtype=np.float64)
    P = _music_spectrum(
        xw=xw,
        fs=fs,
        theta_grid_deg=theta_grid,
        fmin=float(args.fmin),
        fmax=float(args.fmax),
        nfft=int(args.nfft),
    )

    top_idx = np.argsort(P)[::-1][: max(1, int(args.topk))]
    best_idx = int(top_idx[0])
    best_theta = float(theta_grid[best_idx])

    Pn = P / max(float(np.max(P)), 1e-12)

    print(f"\n=== {args.wav} ===")
    print(
        f"Selected event ({event.mode}): "
        f"raw={event.window_t0:.2f}-{event.window_t1:.2f}s, "
        f"used={event.expanded_t0:.2f}-{event.expanded_t1:.2f}s, "
        f"center={event.center_time_s:.2f}s, rms={event.rms:.6f}"
    )
    print(
        f"MUSIC: best_theta={best_theta:.2f}° "
        f"fmin={float(args.fmin):.1f}Hz fmax={float(args.fmax):.1f}Hz "
        f"nfft={int(args.nfft)} win={float(args.win_s):.3f}s"
    )
    print("Top peaks:")
    for idx in top_idx:
        print(f"  theta={float(theta_grid[idx]):.2f}° score={float(P[idx]):.6f} norm={float(Pn[idx]):.6f}")


if __name__ == "__main__":
    main()