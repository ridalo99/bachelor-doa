"""
GCC-PHAT correlation helpers.
"""

from __future__ import annotations

import numpy as np


def linear_interp_centered(cc: np.ndarray, shift: float, max_shift: int) -> float:
    x = float(shift) + float(max_shift)
    if x <= 0.0:
        return float(cc[0])
    if x >= float(len(cc) - 1):
        return float(cc[-1])
    i0 = int(np.floor(x))
    frac = x - i0
    return float((1.0 - frac) * cc[i0] + frac * cc[i0 + 1])
def gcc_phat_cc_subband(sig: np.ndarray, ref: np.ndarray, max_shift: int, fbin_lo: int, fbin_hi: int) -> np.ndarray:
    sig = sig - float(np.mean(sig))
    ref = ref - float(np.mean(ref))

    n = len(sig) + len(ref)
    sig_f = np.fft.rfft(sig, n=n)
    ref_f = np.fft.rfft(ref, n=n)

    mask = np.zeros_like(sig_f, dtype=np.float64)
    fbin_lo = max(0, int(fbin_lo))
    fbin_hi = min(int(fbin_hi), sig_f.shape[0])
    if fbin_hi <= fbin_lo + 1:
        fbin_lo = 0
        fbin_hi = sig_f.shape[0]
    mask[fbin_lo:fbin_hi] = 1.0

    r = sig_f * np.conj(ref_f)
    r /= (np.abs(r) + 1e-12)
    r *= mask

    cc = np.fft.irfft(r, n=n)
    cc = np.concatenate((cc[-max_shift:], cc[: max_shift + 1]))
    return cc.astype(np.float64, copy=False)
