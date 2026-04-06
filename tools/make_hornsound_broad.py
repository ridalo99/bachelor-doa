# tools/make_hornsound_doa_v2.py
"""
DOA-robust horn-like signal for indoor + near-field:

- Horn-ish harmonic stack (keeps the character)
- Strong band-limited noise (broadband TDOA stability)
- Short chirp sweep (breaks front/back ambiguity)
- Longer click (survives phone/speaker AGC better than 5 ms)
- ADSR envelope

Output: mono WAV. Play it, record 4ch, run auto-window/topk.
"""

from __future__ import annotations

import argparse
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt, chirp


def bandpass(x: np.ndarray, fs: int, lo: float, hi: float, order: int = 6) -> np.ndarray:
    sos = butter(order, [lo, hi], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, x)


def adsr(n: int, fs: int, a: float, d: float, s_level: float, r: float) -> np.ndarray:
    na = max(1, int(a * fs))
    nd = max(1, int(d * fs))
    nr = max(1, int(r * fs))
    ns = max(1, n - na - nd - nr)

    env_a = np.linspace(0.0, 1.0, na, endpoint=False)
    env_d = np.linspace(1.0, s_level, nd, endpoint=False)
    env_s = np.full(ns, s_level, dtype=np.float64)
    env_r = np.linspace(s_level, 0.0, nr, endpoint=True)
    env = np.concatenate([env_a, env_d, env_s, env_r])
    if env.size < n:
        env = np.pad(env, (0, n - env.size))
    return env[:n]


def make_signal(fs: int, dur_s: float, f0: float) -> np.ndarray:
    n = int(fs * dur_s)
    t = np.arange(n) / fs

    # Horn-ish harmonic stack
    vibrato_hz = 5.5
    vibrato_depth = 0.01
    f_inst = f0 * (1.0 + vibrato_depth * np.sin(2 * np.pi * vibrato_hz * t))
    phase = 2 * np.pi * np.cumsum(f_inst) / fs

    y_h = np.zeros(n, dtype=np.float64)
    amps = {1: 1.0, 2: 0.65, 3: 0.40, 4: 0.28, 5: 0.20, 6: 0.12}
    for k, a in amps.items():
        y_h += a * np.sin(k * phase)

    # Strong broadband noise bed (key for DOA)
    rng = np.random.default_rng(0)
    noise = rng.normal(0.0, 1.0, n).astype(np.float64)
    noise = bandpass(noise, fs, 250.0, 3500.0)
    noise /= (np.std(noise) + 1e-12)

    # Chirp burst (breaks θ vs θ+180 ambiguity better than pure tones)
    chirp_len = int(0.20 * fs)
    c = np.zeros(n, dtype=np.float64)
    c[:chirp_len] = chirp(t[:chirp_len], f0=300.0, f1=3200.0, t1=t[:chirp_len][-1], method="linear")
    c[:chirp_len] *= np.hanning(chirp_len)

    # Longer click (phone AGC-friendly)
    click_len = int(0.020 * fs)  # 20 ms
    click = np.zeros(n, dtype=np.float64)
    click[:click_len] = np.hanning(click_len) * 2.0

    # Mix (noise stronger than before)
    y = 0.55 * y_h + 0.85 * noise + 0.60 * c + 0.50 * click

    # Envelope
    y *= adsr(n, fs, a=0.02, d=0.10, s_level=0.75, r=0.30)

    # Normalize
    y /= (np.max(np.abs(y)) + 1e-12)
    return (0.95 * y).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audio/horn_doa_v2.wav")
    ap.add_argument("--fs", type=int, default=48000)
    ap.add_argument("--dur", type=float, default=2.0)
    ap.add_argument("--f0", type=float, default=440.0)
    args = ap.parse_args()

    y = make_signal(args.fs, args.dur, args.f0)
    sf.write(args.out, y, args.fs)
    print("Wrote:", args.out)


if __name__ == "__main__":
    main()