# Bachelorarbeit – DOA/TDOA Log

## Array Setup
- 4 Mikrofone
- Quadrat, 20 cm Seitenlänge
- Koordinaten:
  ch1: (-0.10, -0.10)
  ch2: (0.10, -0.10)
  ch3: (0.10, 0.10)
  ch4: (-0.10, 0.10)
- Samplingrate: 48 kHz
- Distanz Quelle: 0.70 m
- Testwinkel: 0°, 90°

## Validierung
- Duplikat-Test erfolgreich
- GCC-PHAT implementiert
- Peak-basiertes Fenster (100 ms)
- max_tau aus Geometrie berechnet

## Beobachtung
- 0° ≈ symmetrische TDOA
- 90° ≠ symmetrisch
- Maximalverschiebung ≈ 17 Samples (plausibel)

## Aktueller Stand (2026-03-03)
### Pipeline/Code
- Vorverarbeitung: Bandpass (typisch 500–4000 Hz) + Ton-Fokus (tone-hz/tone-bw-hz) zur robusteren Segmentierung.
- Segmentierung: automatische Auswahl aktiver Ton-Segmente (z. B. 4.05–8.41 s), Center-Zeitpunkt pro Segment.
- DOA-Schätzung: SRP-PHAT über diskrete Winkelgitter; Ausgabe: theta (deg), raw-theta (interne Referenz), score + einfache confidence-Heuristik.
- Debug-Ausgaben dokumentiert: RMS pro Kanal, erkannte Segmente, Top-k Peaks im SRP-Spektrum.

### Beobachtungen/Probleme
- Teilweise Spiegelungen/180°-Verwechslung in den Schätzwinkeln (z. B. 60°-Aufnahme liefert ~169° oder ~34° je nach Zeitfenster).
- Starke Abhängigkeit vom gewählten Zeitfenster (forced time-range vs. automatische Segmentwahl) → Hinweis auf Mehrwege/Reflexionen oder wechselnde Signalqualität.
- Bei manchen Dateien “Nur kurze Aktivität” → Fallback auf Energie-Peak.
- Koordinaten-/Winkel-Referenz (0°/90°/180°) und Mapping von raw-theta → theta muss eindeutig festgelegt und konsistent dokumentiert werden (Definition: 0° Richtung +x? +y? im Raum?).

### Nächste technische Schritte
- Daten-Sanity-Checks: Labels (JSON degree), Distanz, Dateinamen ↔ Ground Truth konsistent prüfen; Ausreißerwerte (z. B. 1228.5/1755.0) markieren/filtern.
- Windowing verbessern: Onset-basierte Fensterwahl (Attack des Tons), adaptive Fensterlänge, ggf. mehrere Events clustern.
- Subsample-TDOA: Interpolation um Peak-Lage genauer als 1 Sample zu schätzen (parabolische Interpolation / GCC-PHAT Interp.).
- Robustheit: SRP-PHAT auf mehreren kurzen Fenstern → Median/Cluster der Winkel statt 1 Fenster.
- Systematische Messkampagne: gleiches Setup, definierte Distanzen, definierte Winkel, Wiederholungen (>=3) pro Winkel.

## Offene Dokumentationspunkte (ToDo)
- Koordinatensystem & Referenzwinkel (Skizze + Textdefinition).
- Exakter Messaufbau: Raum, Reflexionsquellen, Mikrofon- und Quellenhöhe, Distanzmessung, Markierung der Winkel.
- Signalquelle: Tonart (Sinus/Chirp/MLS/White noise), Lautstärke, Abspielgerät, Dauer; warum gewählt.
- Parameter-Tabelle: fs, bandpass, tone-hz, tone-bw-hz, seg-thr-ratio, window length, Winkelraster.
- Evaluationsmetriken: Winkelfehler (circular error), Anteil innerhalb ±5°/±10°, Konfidenz-Kalibrierung.
- Failure-Cases: Beispiele mit Spiegelung/Mehrwege + plausible Ursachen + geplante Fixes.

## Plots, die du erstellen solltest
1) **Zeitbereich + Segmentierung**
   - Waveform (pro Kanal oder Summensignal) + Energy/RMS-Kurve + markierte Ton-Segmente + ausgewähltes Fensterzentrum.
2) **GCC-PHAT pro Mikrofonpaar**
   - Kreuzkorrelation (Tau-Achse) mit markiertem Peak; Vergleich “saubere” vs. “problematische” Aufnahme.
3) **SRP-PHAT Spatial Spectrum**
   - Polarplot (0–360°) mit Score pro Winkel; Top-3 Peaks markieren; zeigt Ambiguitäten (z. B. 0° vs. 180°).
4) **Ergebnisqualität über alle Winkel**
   - Scatter: True Angle vs. Estimated Angle (mit 1:1 Linie).
   - Plot: Winkelfehler (circular) vs. True Angle (oder als Boxplot pro Winkel).
5) **Ablations-/Parameterstudie**
   - Fehler vs. Fensterlänge (z. B. 50/100/200 ms), Fehler vs. bandpass, Fehler vs. tone-hz/tone-bw.
6) **Konfidenzdiagnostik**
   - Histogramm confidence; Scatter confidence vs. Fehler (sollte negativ korrelieren).

## Update (2026-03-04) – 150 cm Messblock, Mixed-Cluster Diagnose, Plot-Workflow

### Neue Messungen (Indoor)
- **150 cm**: 0° (3 Takes), 90° (3 Takes), 110° (2 Takes), 180° (2 Takes), 40° (mehrere Takes).
- Ergebnisse:
  - 0° und 90°: stabil und korrekt (nahe 0° bzw. 90°).
  - 110°: stabil (~111°).
  - 180°: stabil (~179–180°).
  - 40°: einzelne Takes zeigen **stark gemischte Winkel-Cluster** (z.B. 38°/40° vs. 135°/180°/225°), abhängig vom Zeitfenster.

### Diagnose: Warum 40° bei 150 cm manchmal „springt“
- In problematischen Takes treten mehrere **konkurrierende DOA-Cluster** innerhalb desselben Signals auf (Mehrwege/Reflexionen oder Übergangsbereiche im Testsignal).
- Dadurch kann eine reine Mode-Aggregation über einen zu breiten Zeitbereich den falschen Cluster gewinnen.
- Lösung: **Multi-range einschränken** auf einen stabilen Mittelteil der Noise-Phase (z.B. **4.0–10.0 s**), wodurch die Schätzung deutlich stabiler wurde.

### Plot-/Reporting Workflow
- Export der Fensterdaten als CSV (raw + calib) und automatische Plot-Erzeugung mit `tools/make_doa_plots.py`.
- Erzeugte Kernplots:
  - MAE vs Distanz (file-level)
  - Estimated vs Ground Truth (file-level)
  - Abs error vs confidence (used windows)
  - Abs error vs used-window ratio
- Beobachtung: hohe MAE bei **181 cm** wird sehr wahrscheinlich von **wenigen Ausreißern** dominiert (z.B. falsche Takes / Mixed-Cluster / ungeeigneter Zeitbereich).

### Empfehlungen (nächste Schritte)
- Für alle Distanzen: Standardmäßig **stabilen Zeitbereich** nutzen (z.B. 4–10 s innerhalb der Noise-Phase) oder auto-detect des stabilen Segments.
- Für 181 cm:
  - Vergleich **Far-field vs Near-field** (bei großen Distanzen Far-field oft robuster).
  - Mehr Takes für Zwischenwinkel (z.B. 40°/60°/140°) + Outlier-Handling.
  - Optional: „UNCERTAIN“/Quality-Gate bei Mixed-Cluster Fällen (statt falschen Winkel auszugeben).

### ML-Vorbereitung (ohne Training)
- Window-level CSV enthält pro Fenster: distance, gt-angle, theta_raw/theta_calib, confidence, used_flag, top-peaks.
- Mixed-Cluster/Outlier Fälle als eigene Klasse/Flag (label_quality) markieren, nicht blind ins Training mischen.
## Update (heute) – Auto-Window (Top-K Events), Event-Gating, Near-field Horn-Tests

### Neue Funktionalität
- Auto-window wurde erweitert: statt nur 1 loud window werden TOP-K laute Events (Horn) erkannt (min-gap).
- Pro Event: DOA + dom_ratio + best_conf; Events werden per Gate gefiltert (event_min_conf, event_min_dom).
- Final DOA wird aus akzeptierten Events aggregiert (Mode), bei Konflikt/zu wenig Qualität Fallback auf bestes Event.

### Beobachtung
- Bei 55 cm (near-field) + tonal horn treten häufig 180°-Ambiguitäten zwischen Events auf (θ vs θ+180).
- Event-Gating reduziert “falsche” Events; stabile Events liefern konsistente Winkel (z.B. ~180° bei 180° Ground Truth).

### Nächste Schritte
- 110 cm Testblock (0° neu aufgenommen): Auto-window + Event-Gating validieren.
- ML-Vorbereitung: Export window-/event-level Dataset (CSV) mit Features: event_theta, dom_ratio, best_conf, rms, distance_cm, gt_angle.
- Label-Quality Flag setzen: ACCEPT/REJECT pro Event, und “AMBIGUOUS” bei 180°-Konflikt zwischen akzeptierten Events.