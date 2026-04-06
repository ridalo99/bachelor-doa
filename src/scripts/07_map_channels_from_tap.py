# scripts/map_channels_from_tap_auto.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import soundfile as sf


WAV = "/Users/rida/Bachelor_Arbeit/audio/tap_test.wav"  # <-- anpassen


@dataclass(frozen=True)
class TapEvent:
    center_s: float
    strongest_ch: int  # 1-based
    ch_energy: np.ndarray
    env_rms: float


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x)))


def scan_tap_candidates(
    x: np.ndarray,
    fs: int,
    win_s: float = 0.25,
    hop_s: float = 0.01,
) -> List[TapEvent]:
    """
    Scan whole file on a hop grid, return a TapEvent for every window.
    Later we pick peaks / per-channel best windows.
    """
    x = np.asarray(x, dtype=np.float64)
    x_mono = np.mean(x, axis=1)

    win = max(1, int(win_s * fs))
    hop = max(1, int(hop_s * fs))
    starts = np.arange(0, max(1, len(x_mono) - win + 1), hop, dtype=int)

    events: List[TapEvent] = []
    for s in starts:
        seg = x[s : s + win]
        env = _rms(np.mean(seg, axis=1))
        e_ch = np.mean(seg**2, axis=0)
        strongest = int(np.argmax(e_ch)) + 1  # 1-based
        center_s = (s + win // 2) / fs
        events.append(TapEvent(center_s=center_s, strongest_ch=strongest, ch_energy=e_ch, env_rms=env))
    return events


def pick_topk_events(events: List[TapEvent], topk: int, min_gap_s: float) -> List[TapEvent]:
    """
    Pick global top-k by env_rms, enforcing a time gap.
    """
    evs = sorted(events, key=lambda e: e.env_rms, reverse=True)
    chosen: List[TapEvent] = []
    for e in evs:
        if all(abs(e.center_s - c.center_s) >= min_gap_s for c in chosen):
            chosen.append(e)
            if len(chosen) >= topk:
                break
    return sorted(chosen, key=lambda e: e.center_s)


def best_event_per_channel(events: List[TapEvent]) -> Dict[int, TapEvent]:
    """
    For each channel (1..N), find the window where that channel's energy is maximal.
    """
    n_ch = len(events[0].ch_energy)
    best: Dict[int, Tuple[float, TapEvent]] = {}
    for ch in range(1, n_ch + 1):
        best[ch] = (-1.0, events[0])

    for e in events:
        for ch in range(1, n_ch + 1):
            val = float(e.ch_energy[ch - 1])
            if val > best[ch][0]:
                best[ch] = (val, e)

    return {ch: ev for ch, (_, ev) in best.items()}


def main() -> None:
    wav_path = Path(WAV)
    x, fs = sf.read(str(wav_path), always_2d=True)
    print("Loaded:", wav_path, "fs:", fs, "shape:", x.shape)

    # 1) Full scan
    events = scan_tap_candidates(x, fs, win_s=0.25, hop_s=0.01)

    # 2) Show global loudest events (for sanity)
    chosen = pick_topk_events(events, topk=12, min_gap_s=0.6)
    print("\nGlobal loudest tap-like windows (chronological):")
    for i, ev in enumerate(chosen, 1):
        print(f"\nTap {i} @ {ev.center_s:.2f}s -> strongest channel: ch{ev.strongest_ch}  env_rms={ev.env_rms:.6e}")
        for ch_idx, val in enumerate(ev.ch_energy, 1):
            print(f"  ch{ch_idx} energy: {val:.6e}")

    # 3) Critical: ensure every channel appears somewhere
    per_ch = best_event_per_channel(events)
    print("\n=== Best window per channel (proves channel exists if energy is non-trivial) ===")
    for ch, ev in per_ch.items():
        e = float(ev.ch_energy[ch - 1])
        print(f"ch{ch}: best_energy={e:.6e} at t={ev.center_s:.2f}s (strongest in that window: ch{ev.strongest_ch})")

    # Heuristic warning
    energies = [float(per_ch[ch].ch_energy[ch - 1]) for ch in sorted(per_ch)]
    mx = max(energies)
    for ch, e in enumerate(energies, 1):
        if mx > 0 and (e / mx) < 1e-3:
            print(f"WARNING: ch{ch} looks very weak vs best channel (ratio={e/mx:.2e}). Might be untapped / dead / wrong routing.")


if __name__ == "__main__":
    main()