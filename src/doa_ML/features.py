from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re

import numpy as np
import soundfile as sf


ANGLE_RE = re.compile(r"(\d+)deg", re.IGNORECASE)
DIST_RE = re.compile(r"(\d+)cm", re.IGNORECASE)
TAKE_RE = re.compile(r"take(\d+)", re.IGNORECASE)


@dataclass
class FeatureRow:
    file: str
    gt_angle_deg: Optional[int]
    distance_cm: Optional[int]
    take: Optional[int]
    rms_mean: float
    rms_std: float
    peak_amp: float
    duration_s: float
    fs: int


def parse_meta(filename: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    angle = None
    dist = None
    take = None

    m = ANGLE_RE.search(filename)
    if m:
        angle = int(m.group(1))

    m = DIST_RE.search(filename)
    if m:
        dist = int(m.group(1))

    m = TAKE_RE.search(filename)
    if m:
        take = int(m.group(1))

    return angle, dist, take


def extract_basic_features(wav_path: str | Path) -> FeatureRow:
    wav_path = Path(wav_path)
    x, fs = sf.read(str(wav_path), always_2d=True)

    mono = np.mean(x, axis=1)
    gt_angle, dist_cm, take = parse_meta(wav_path.name)

    frame = int(0.02 * fs)
    hop = int(0.01 * fs)

    rms_vals = []
    for i in range(0, max(1, len(mono) - frame), hop):
        seg = mono[i:i + frame]
        if len(seg) == 0:
            continue
        rms_vals.append(float(np.sqrt(np.mean(seg ** 2))))

    rms_vals = np.array(rms_vals, dtype=float) if rms_vals else np.array([0.0])

    return FeatureRow(
        file=wav_path.name,
        gt_angle_deg=gt_angle,
        distance_cm=dist_cm,
        take=take,
        rms_mean=float(np.mean(rms_vals)),
        rms_std=float(np.std(rms_vals)),
        peak_amp=float(np.max(np.abs(mono))),
        duration_s=float(len(mono) / fs),
        fs=int(fs),
    )