import numpy as np
import soundfile as sf

WAV = "test_0deg_70cm.wav"  # <-- anpassen

x, fs = sf.read(WAV, always_2d=True)
print("File:", WAV)
print("fs:", fs)
print("shape (samples, channels):", x.shape)

C = x.shape[1]
print("\nRMS pro Kanal:")
rms = np.sqrt(np.mean(x**2, axis=0))
for i, r in enumerate(rms, 1):
    print(f"  ch{i}: {r:.6f}")

print("\nKorrelationen (Duplikat-Check):")
for i in range(C):
    for j in range(i + 1, C):
        a = x[:, i] - x[:, i].mean()
        b = x[:, j] - x[:, j].mean()
        corr = (a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)
        print(f"  ch{i+1}-ch{j+1}: {corr:.6f}")