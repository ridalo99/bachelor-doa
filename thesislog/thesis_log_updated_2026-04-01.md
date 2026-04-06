# Bachelorarbeit – DOA/TDOA Log

*(Stand: 2026-04-01, Europe/Berlin – aktualisiert bis heute)*

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

## Update (2026-03-09 bis heute) – Kanal-Mapping (Tap-Test), neue Geometrie (Metallplatte), Chirp-Auto-Window Tuning

### Setup-Änderung (Hardware/Anordnung)
- Array auf **Metallplatte**, 4 Mikrofone an den Ecken, Mikrofone zeigen nach oben (leicht nach innen, mechanisch bedingt).
- Physisches Layout (Draufsicht):
  - **oben:** M3 (links), M2 (rechts)
  - **unten:** M4 (links), M1 (rechts)
- Grobe Messwerte (Membranmitte→Membranmitte, später mit Maßband finalisieren):
  - M1→M2 (rechts vertikal): ~**21.5 cm**
  - M4→M3 (links vertikal): ~**20.0 cm**
  - M4→M1 (unten horizontal): ~**21.0 cm** (approx., konsistent zu M2↔M3 ~21 cm)
- Hinweis: Für SRP-PHAT/TDOA ist primär die **Position** der Membran relevant; die Ausrichtung nach oben ist zweitrangig, solange alle ähnlich ausgerichtet sind.

### Kritischer Schritt: Tap-Test zur Kanalzuordnung (Mic ↔ WAV-Channel)
Ziel: Sicherstellen, dass die 4 WAV-Kanäle wirklich 4 unabhängige Mics sind und die Zuordnung korrekt ist.

- Anfangsproblem: Tap-Test zeigte nur 2 aktive Kanäle (z.B. ch1/ch3) → Aufnahme-/Routing/Mode war falsch (Stereo/duplizierte Kanäle oder tote Kanäle).
- Fix: Neue Tap-Aufnahme mit klaren Pausen + Tap direkt am Mic-Gehäuse (nicht auf die Metallplatte).
- Robuster Tap-Analyzer:
  - Scan + Auswahl „global loudest“ + „best window per channel“ (zeigt, ob **ch2/ch3/ch4** wirklich existieren und wann).
- Validiertes Ergebnis (Tap-Reihenfolge: Mic4 → Mic1 → Mic2 → Mic3):
  - Mic4 → ch4
  - Mic1 → ch1
  - Mic2 → ch2
  - Mic3 → ch3
- Daraus folgt (0-based in Python / soundfile):
  - **MIC_TO_CH = {M1:0, M2:1, M3:2, M4:3}**

### Geometrie im Code (geometry.py)
- `MICS` als XY-Positionen (Meter) zum Arrayzentrum, passend zum oben beschriebenen Layout:
  - M1 bottom-right, M2 top-right, M3 top-left, M4 bottom-left.
- Empfehlung: MICS direkt zentriert definieren (statt Altvariable `a=...`/Doppeldeklarationen), um Verwechslungen zu vermeiden.

### Winkel-Konvention (0°/90°/270°) & typische Fehlerquelle
- Im Code wird die Richtungsfunktion über `unit_direction(theta_deg)` definiert.
- Konvention muss **explizit** dokumentiert und mit dem physischen Aufbau abgeglichen werden:
  - Zieldefinition (Projekt): **0° vorne** (zwischen M2/M3), **90° links** (zwischen M4/M3), **270° rechts** (zwischen M1/M2).
- Praktische Debug-Regel:
  - Ohne calib-file gilt: **theta == raw** → wenn Winkel „falsch“ ist, ist es **keine Offset-Frage**, sondern Definition/Geometrie/Reflexion/Ground-Truth.

### Auto-Window (Top-K Events) vs. „forced time-range“
- `--time-range` wurde als Debug genutzt, um zu verifizieren, dass SRP-PHAT im richtigen Chirp-Fenster grundsätzlich korrekt ist.
- Für das finale System soll die Schätzung ohne manuelles Fenster laufen → Auto-Window muss robust sein.
- Beobachtung: Ausgabe `UNCERTAIN` kann auftreten, obwohl ein Winkel geschätzt wurde, weil die Ausgabe-Schwelle `final_dom < 0.60` als „UNCERTAIN“ labelt.

### Chirp-Experimente (500–3000 Hz, Wiederholung 3×)
Problem: Bei Standardparametern wurde teils nur 1 Event erkannt oder es gab gemischte Cluster (0° vs. 180°).

**Tuning, das stabil 3 Chirps erkennt und konsistent aggregiert (ohne time-range):**
- Bandpass: **500–3000 Hz**
- Auto-window:
  - `--auto-window-topk 3`
  - `--auto-window-len 0.45`
  - `--auto-window-hop 0.01`
  - `--auto-window-expand 0.10`
  - `--auto-window-min-gap 0.80`
- SRP windows:
  - `--win-s 0.20`
  - `--hop-s 0.05`
- Gating / Fallback:
  - `--auto-dom-min 0.20`
  - `--event-min-dom 0.20`
  - `--event-min-conf 0.05`

**Ergebnis (0° Take):**
- 3 Events erkannt (accepted 3/3)
- Final DOA ~ **1°** (dom=1.00) → stabil & reproduzierbar.

### 1m vs 2m Beobachtung (Outdoor/Indoor)
- 2m häufig stabiler als 1m (bei 1m mehr `UNCERTAIN` / Cluster-Sprünge).
- Vermutete Ursachen:
  - Übersteuerung/AGC/Clipping bei 1m
  - stärkere Boden-/Plattenreflexionen im Nahfeld
  - Auto-window findet nicht immer den „sauberen“ Chirp-Teil.
- Zwischenlösung: härtere Gates (höherer dom/conf) → weniger falsche Winkel, mehr „UNCERTAIN“.
- Empfohlene (noch nicht implementierte) Verbesserung: **Chirp Matched-Filter** zur Peak-Detektion statt RMS-TopK.

### Debug-Learnings (wichtig fürs Reporting)
- „Falscher“ Winkel kann durch **unklare Ground Truth** entstehen (Lautsprecher „irgendwo im Raum“).
- Für Validierung müssen Winkel im Raum **markiert** werden (mind. 0/90/180/270 Linien relativ zur Platte).
- Bei Ambiguität zeigen `Top-3 raw` häufig mehrere Peaks (z.B. 315°, 46°, 135°) → Indiz für Reflexionen/Geometrie-Ambiguität.

### Reproduzierbarer Kommando-Block (Chirp-Mode, autonom)
```bash
python3 src/scripts/05_estimate_doa.py \
  --wav audio/test_*deg_take*.wav \
  --calib-file configs/Setup_front.json \
  --bandpass 500 3000 \
  --source-distance-m 2.0 \
  --auto-window \
  --auto-window-topk 3 \
  --auto-window-len 0.45 \
  --auto-window-hop 0.01 \
  --auto-window-expand 0.10 \
  --auto-window-min-gap 0.80 \
  --win-s 0.20 \
  --hop-s 0.05 \
  --auto-dom-min 0.20 \
  --event-min-dom 0.20 \
  --event-min-conf 0.05 \
  --debug
```

### ToDos (für Thesis + nächste Engineering-Schritte)
- Final: Messung der Mic-Positionen mit Maßband/Schieblehre (Membranmitte→Membranmitte), inkl. Unsicherheit.
- Dokumentation der Winkel-Konvention (Skizze + Text) und eindeutiger Bezug auf `unit_direction`.
- Optional: Änderung der „UNCERTAIN“-Schwelle / Ausgabe-Logik (dom als Qualitätswert reporten).
- Implementieren: Chirp Matched-Filter Event-Detektion (Peak times), Export Event-Level CSV (theta, dom_ratio, best_conf, rms).

## Update (2026-04-01) – Chirp-Mode (3× Chirp), Channel-Mapping verifiziert, Auto-Window Parameter-Tuning

### Kanal-Mapping (Tap-Test)
- Tap-Test automatisiert (Top-K Tap-Events + per-channel Best-Window).
- Ergebnis: alle 4 Kanäle aktiv; Mapping (1-based Tap-Test → 0-based Code):
  - M1 → ch1 → 0
  - M2 → ch2 → 1
  - M3 → ch3 → 2
  - M4 → ch4 → 3
- Wichtig: Tap-Reihenfolge muss dokumentiert werden; Top-K zeigt Tap-Events (nicht “Mic5..Mic8”).

### Geometrie/Anordnung (Metallplatte)
- Mikros auf Metallplatte in Ecken; Ausrichtung nach oben/leicht nach innen.
- Physikalisches Layout dokumentiert: oben (M3, M2), unten (M4, M1).
- Grobe Maßwerte (noch ohne Maßband final verifiziert): W≈0.21 m, H_right≈0.215 m, H_left≈0.20 m.
- Hinweis: spätere finale Messkampagne benötigt Membranmitte↔Membranmitte, mehrfach gemessen (Mittelwert±Std).

### Chirp-Tests (500–3000 Hz) & Autonomie ohne manuelles Time-Range
- Problem: Auto-window nahm anfangs nur 1 Event (bei 3× Chirp) oder “UNCERTAIN” wegen dom<0.60.
- Lösung: Parameter so abgestimmt, dass 3 Chirps als 3 Events erkannt und stabil aggregiert werden (Top-K + min-gap).
- Bewährte “Chirp-Mode” Parameter:
  - bandpass: 500–3000 Hz
  - auto-window-topk: 3
  - auto-window-len: 0.45 s
  - auto-window-hop: 0.01 s
  - auto-window-expand: 0.10 s
  - auto-window-min-gap: 0.80 s
  - win-s: 0.20 s
  - hop-s: 0.05 s
  - auto-dom-min: 0.20
  - event-min-dom: 0.20
  - event-min-conf: 0.05
- Ergebnisbeispiel (0°): Final DOA ~1° (accepted 3/3, dom=1.00) mit konsistenten Event-Thetas (~2–6°).

### Winkelkonvention / Ground-Truth Problem
- Tests zeigen: ohne Calib (raw==theta) kann “270°-Label” falsch sein, wenn Lautsprecher nicht exakt auf Winkel-Linie platziert wird.
- In Indoor-Setup mit Reflexionen kann SRP-PHAT mehrere konkurrierende Peaks liefern (z.B. 315°, 46°, 135°), niedrige confidence → ambig.
- Konsequenz: Für Validierung müssen Winkelachsen am Boden/Setup markiert werden; ansonsten ist “falsch” nicht interpretierbar.
- ToDo: endgültige Definition “0° vorne (zwischen M2/M3)” und “90° links (zwischen M3/M4)” als Text+Skizze; unit_direction/Definition konsistent dazu halten.

### Nächste Schritte
- Neue Calibration-Datei für das finale Setup erstellen (mind. 0°+90°, besser 0/90/180/270).
- Optional: Chirp-Detektion via Matched Filter als robustere Alternative zu RMS-TopK (falls später Horn → andere Detektion).
- Für Thesis: Plots (True vs Pred, Error vs Angle, Confidence vs Error, UNCERTAIN-Rate) aus Logfiles automatisieren.
