import numpy as np
import soundfile as sf

WAV = "tap_test.wav"  # <-- anpassen, falls anders

x, fs = sf.read(WAV, always_2d=True)
print("Loaded:", WAV, "fs:", fs, "shape:", x.shape)

# Energie pro Sample (über alle Kanäle)
e = np.sum(x**2, axis=1)

# Wir teilen die Aufnahme in 4 Zeitabschnitte,
# weil du (hoffentlich) nacheinander Mic1..Mic4 getappt hast.
T = x.shape[0]
cuts = np.linspace(0, T, 5).astype(int)

mapping = []
for k in range(4):
    s, t = cuts[k], cuts[k+1]
    e_ch = np.mean(x[s:t]**2, axis=0)
    ch = int(np.argmax(e_ch)) + 1
    mapping.append(ch)
    print(f"\nAbschnitt {k+1} (Samples {s}:{t})")
    for i, val in enumerate(e_ch, 1):
        print(f"  ch{i} energy: {val:.6e}")
    print("  => stärkster Kanal:", ch)

print("\n=== Ergebnis (nur korrekt, wenn Abschnitte Mic1..Mic4 entsprechen) ===")
print("Mic1 -> ch", mapping[0])
print("Mic2 -> ch", mapping[1])
print("Mic3 -> ch", mapping[2])
print("Mic4 -> ch", mapping[3])