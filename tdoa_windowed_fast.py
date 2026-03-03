import numpy as np
import soundfile as sf


MICS = np.array([
    [-0.10, -0.10],  # ch1
    [ 0.10, -0.10],  # ch2
    [ 0.10,  0.10],  # ch3
    [-0.10,  0.10],  # ch4
], dtype=float)

C = 343.0  # Schallgeschwindigkeit (m/s)

def pair_max_tau(i, j, margin=1e-4):
    """Physikalisch sinnvolles Suchfenster aus Geometrie."""
    d = np.linalg.norm(MICS[i] - MICS[j])
    return d / C + margin

def gcc_phat_tdoa(sig, ref, fs, max_tau):
    """GCC-PHAT: robustere TDOA-Schätzung als normale Korrelation."""
    sig = sig - np.mean(sig)
    ref = ref - np.mean(ref)

    n = len(sig) + len(ref) - 1
    SIG = np.fft.rfft(sig, n=n)
    REF = np.fft.rfft(ref, n=n)

    R = SIG * np.conj(REF)
    R /= (np.abs(R) + 1e-12)  # PHAT weighting

    cc = np.fft.irfft(R, n=n)
    center = len(cc) // 2

    max_shift = int(max_tau * fs)
    lo = center - max_shift
    hi = center + max_shift + 1
    cc_win = cc[lo:hi]

    shift = np.argmax(np.abs(cc_win)) - max_shift
    tau = shift / fs
    return tau, shift

def find_peak_window(x, fs, win_s=0.1):
    """Fenster um das stärkste Ereignis (Energie-Peak)."""
    energy = np.sum(x**2, axis=1)
    peak_idx = int(np.argmax(energy))
    win = int(win_s * fs)
    start = max(0, peak_idx - win)
    end = min(len(x), peak_idx + win)
    return x[start:end], peak_idx, (start, end)

def analyze(wav_path):
    x, fs = sf.read(wav_path, always_2d=True)
    if x.shape[1] != 4:
        raise ValueError(f"Erwarte 4 Kanäle, habe {x.shape[1]}")

    xw, peak_idx, (s, e) = find_peak_window(x, fs, win_s=0.1)
    print("\n===", wav_path, "===")
    print("fs:", fs, "full shape:", x.shape)
    print("peak_idx:", peak_idx, "window:", (s, e), "window shape:", xw.shape)

    pairs = [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]
    for i, j in pairs:
        max_tau = pair_max_tau(i, j)
        tau, shift = gcc_phat_tdoa(xw[:, i], xw[:, j], fs, max_tau=max_tau)
        print(f"ch{i+1}-ch{j+1}: max_tau={max_tau:.6e}s shift={shift:+d} tau={tau:+.6e}s")

if __name__ == "__main__":
    analyze("test_0deg_70cm.wav")   
    analyze("test_90deg_70cm.wav")  