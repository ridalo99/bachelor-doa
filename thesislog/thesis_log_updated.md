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
