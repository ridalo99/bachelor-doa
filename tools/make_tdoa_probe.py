from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import numpy as np


def fade_io(x: np.ndarray, fs: int, fade_ms: float = 10.0) -> np.ndarray:
    n = max(1, int(fs * fade_ms / 1000.0))
    if len(x) < 2 * n:
        return x
    y = x.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float64)
    y[:n] *= ramp
    y[-n:] *= ramp[::-1]
    return y


def silence(fs: int, dur_s: float) -> np.ndarray:
    return np.zeros(int(round(fs * dur_s)), dtype=np.float64)


def log_chirp(fs: int, dur_s: float, f0: float, f1: float, amp: float) -> np.ndarray:
    t = np.arange(int(round(fs * dur_s)), dtype=np.float64) / fs
    k = math.log(f1 / f0) / dur_s
    phase = 2.0 * math.pi * f0 * (np.exp(k * t) - 1.0) / k
    x = amp * np.sin(phase)
    return fade_io(x, fs)


def normalize(x: np.ndarray, peak: float = 0.95) -> np.ndarray:
    mx = float(np.max(np.abs(x))) if x.size else 0.0
    if mx <= 1e-12:
        return x
    return x * (peak / mx)


def save_wav_mono_16bit(path: Path, x: np.ndarray, fs: int) -> None:
    x = np.clip(x, -1.0, 1.0)
    pcm = (x * 32767.0).astype(np.int16)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(pcm.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="Erzeugt einen einzelnen TDOA-freundlichen Log-Chirp.")
    parser.add_argument("--out", default="audio/tdoa_single_chirp_700_5000.wav")
    parser.add_argument("--fs", type=int, default=48000)
    parser.add_argument("--f0", type=float, default=700.0)
    parser.add_argument("--f1", type=float, default=5000.0)
    parser.add_argument("--chirp-s", type=float, default=0.40)
    parser.add_argument("--lead-s", type=float, default=1.00)
    parser.add_argument("--tail-s", type=float, default=1.00)
    parser.add_argument("--amp", type=float, default=0.85)
    args = parser.parse_args()

    if args.fs <= 0:
        raise SystemExit("fs muss > 0 sein")
    if args.f0 <= 0 or args.f1 <= 0 or args.f1 <= args.f0:
        raise SystemExit("Es muss 0 < f0 < f1 gelten")
    if args.chirp_s <= 0 or args.lead_s < 0 or args.tail_s < 0:
        raise SystemExit("Zeiten ungueltig")
    if not (0.0 < args.amp <= 1.0):
        raise SystemExit("amp muss im Bereich (0, 1] liegen")

    x = np.concatenate(
        [
            silence(args.fs, args.lead_s),
            log_chirp(args.fs, args.chirp_s, args.f0, args.f1, args.amp),
            silence(args.fs, args.tail_s),
        ]
    )
    x = normalize(x, peak=0.95)

    out_path = Path(args.out)
    save_wav_mono_16bit(out_path, x, args.fs)

    print(f"WAV geschrieben: {out_path}")
    print(f"Laenge: {len(x) / args.fs:.2f} s")
    print(f"Samplingrate: {args.fs} Hz")
    print(f"Chirp: {args.f0:.0f}-{args.f1:.0f} Hz, Dauer {args.chirp_s:.2f} s")


if __name__ == "__main__":
    main()