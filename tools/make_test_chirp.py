import numpy as np
import wave

def linear_chirp(f0, f1, duration, sr):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    k = (f1 - f0) / duration
    phase = 2 * np.pi * (f0 * t + 0.5 * k * t**2)
    return np.sin(phase)

def apply_fade(x, sr, fade_ms=20):
    n = int(sr * fade_ms / 1000)
    if n > 0 and 2 * n < len(x):
        fade_in = np.linspace(0, 1, n)
        fade_out = np.linspace(1, 0, n)
        x[:n] *= fade_in
        x[-n:] *= fade_out
    return x

def save_wav(filename="test_chirp_500_3000.wav", sr=48000):
    silence_1s = np.zeros(sr, dtype=np.float32)

    chirp = linear_chirp(500, 3000, 0.4, sr).astype(np.float32)
    chirp = apply_fade(chirp, sr, fade_ms=20)

    signal = np.concatenate([
        silence_1s,
        chirp,
        silence_1s,
        chirp,
        silence_1s,
        chirp,
        silence_1s
    ])

    signal /= np.max(np.abs(signal))
    signal *= 0.8

    pcm = np.int16(signal * 32767)

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    print(f"Gespeichert: {filename}")

if __name__ == "__main__":
    save_wav()