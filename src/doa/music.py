# src/doa/music.py
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from .geometry import MICS, unit_direction


def music_spectrum(
    xw: np.ndarray,
    fs: int,
    theta_grid_deg: np.ndarray,
    fmin: float = 700.0,
    fmax: float = 5000.0,
    nfft: int = 1024,
    n_sources: int = 1,
) -> np.ndarray:
    xw = np.asarray(xw, dtype=np.float64)
    n, m = xw.shape
    if m != 4:
        raise ValueError(f"Expected 4 channels, got {m}")
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
    Xall = np.stack(spectra, axis=0)

    P = np.zeros(theta_grid_deg.shape[0], dtype=np.float64)
    c = 343.0

    for b in use_bins:
        f = float(freqs[b])
        Xf = Xall[:, b, :]

        R = np.zeros((m, m), dtype=np.complex128)
        for frame in range(Xf.shape[0]):
            x = Xf[frame, :][:, None]
            R += x @ x.conj().T
        R /= max(Xf.shape[0], 1)

        evals, evecs = np.linalg.eigh(R)
        idx = np.argsort(evals)[::-1]
        evecs = evecs[:, idx]

        noise_dim = max(1, m - int(n_sources))
        En = evecs[:, -noise_dim:]
        if En.shape[1] == 0:
            continue

        for i, theta in enumerate(theta_grid_deg):
            u = unit_direction(float(theta))
            delays = -(MICS @ u) / c
            a = np.exp(-1j * 2.0 * np.pi * f * delays)[:, None]
            denom = np.linalg.norm(En.conj().T @ a) ** 2
            P[i] += 1.0 / max(float(denom.real), 1e-12)

    return P


def music_topk(
    xw: np.ndarray,
    fs: int,
    theta_grid_deg: np.ndarray,
    fmin: float = 700.0,
    fmax: float = 5000.0,
    nfft: int = 1024,
    n_sources: int = 1,
    topk: int = 5,
) -> Tuple[float, float, List[Tuple[float, float]], np.ndarray]:
    P = music_spectrum(
        xw=xw,
        fs=fs,
        theta_grid_deg=theta_grid_deg,
        fmin=fmin,
        fmax=fmax,
        nfft=nfft,
        n_sources=n_sources,
    )
    idx = np.argsort(P)[::-1]
    best_idx = int(idx[0])
    best = float(P[best_idx])
    second = float(P[idx[1]]) if len(idx) > 1 else 0.0
    sharpness = (best - second) / max(best, 1e-12)
    peaks = [(float(theta_grid_deg[i]), float(P[i])) for i in idx[: max(1, int(topk))]]
    return float(theta_grid_deg[best_idx]), float(sharpness), peaks, P