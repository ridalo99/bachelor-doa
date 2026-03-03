import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

def bandpass(x: np.ndarray, fs: int, lo: float, hi: float, order: int = 6) -> np.ndarray:
    sos = butter(order, [lo, hi], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, x)

def chirp_lin(fs: int, dur: float, f0: float, f1: float, amp: float) -> np.ndarray:
    t = np.linspace(0, dur, int(fs * dur), endpoint=False)
    k = (f1 - f0) / dur
    phase = 2 * np.pi * (f0 * t + 0.5 * k * t * t)
    return (amp * np.sin(phase)).astype(np.float32)

def make_band_noise(fs: int, dur: float, lo: float, hi: float, amp: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(int(fs * dur)).astype(np.float64)
    y = bandpass(x, fs, lo, hi)
    y /= (np.max(np.abs(y)) + 1e-12)
    return (amp * y).astype(np.float32)

def fade(x: np.ndarray, fs: int, fade_ms: float = 20.0) -> np.ndarray:
    n = len(x)
    f = int(fs * fade_ms / 1000)
    if f <= 1:
        return x
    w = np.ones(n, dtype=np.float32)
    ramp = np.linspace(0, 1, f, endpoint=False).astype(np.float32)
    w[:f] = ramp
    w[-f:] = ramp[::-1]
    return x * w

def marker_beep(fs: int, dur: float = 0.15, f: float = 2000.0, amp: float = 0.4) -> np.ndarray:
    t = np.linspace(0, dur, int(fs * dur), endpoint=False)
    y = amp * np.sin(2 * np.pi * f * t)
    return y.astype(np.float32)

def main(
    out="doa_test_30cm_noise500-6000_chirp.wav",
    fs=48000,
):
    # Layout:
    # 0.2s beep, 0.2s silence,
    # 1.0s chirp 500->6000,
    # 0.2s silence,
    # 10s band-noise,
    # 0.2s silence,
    # 1.0s chirp 6000->500,
    # 0.2s silence, 0.2s beep
    s = []

    s.append(marker_beep(fs))
    s.append(np.zeros(int(0.2 * fs), dtype=np.float32))

    s.append(chirp_lin(fs, dur=1.0, f0=500, f1=6000, amp=0.5))
    s.append(np.zeros(int(0.2 * fs), dtype=np.float32))

    s.append(make_band_noise(fs, dur=10.0, lo=500, hi=6000, amp=0.5, seed=1))
    s.append(np.zeros(int(0.2 * fs), dtype=np.float32))

    s.append(chirp_lin(fs, dur=1.0, f0=6000, f1=500, amp=0.5))
    s.append(np.zeros(int(0.2 * fs), dtype=np.float32))

    s.append(marker_beep(fs))
    y = np.concatenate(s)

    y = fade(y, fs, 20.0)
    sf.write(out, y, fs)
    print("Wrote:", out, "len_s=", len(y)/fs)

if __name__ == "__main__":
    main()