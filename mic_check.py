import soundfile as sf
import numpy as np

files = {
    "Mic1": "tap_mic1.wav",
    "Mic2": "tap_mic2.wav",
    "Mic3": "tap_mic3.wav",
    "Mic4": "tap_mic4.wav",
}

for mic, path in files.items():
    x, fs = sf.read(path, always_2d=True)
    # Energie pro Kanal (robust): 99.9%-Quantil der Absolutwerte
    q = np.quantile(np.abs(x), 0.999, axis=0)
    dom = int(np.argmax(q))
    print(mic, "-> ch", dom, "| q999 =", np.round(q, 6))