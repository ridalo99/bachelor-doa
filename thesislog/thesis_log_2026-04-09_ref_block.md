# Thesis Log – 2026-04-09 – Indoor-Referenzblock mit Einzel-Chirp

## Kontext
- Fokus: Richtungsbestimmung per TDOA / SRP-PHAT als Basissystem.
- Zielbezug zur Aufgabenstellung:
  - Aufbau und Kalibrierung des Systems
  - Einlesen und Vorverarbeitung der Audiodaten
  - Richtungsbestimmung mittels Zeitdifferenz
  - spätere Bewertung von Genauigkeit, Robustheit und Datenqualität
- Aktueller aktiver Stand:
  - Geometrie im Code auf ca. 0.36 m horizontal / vertikal gesetzt
  - Kanalzuordnung per Tap-Test bestätigt:
    - M1 -> ch2
    - M2 -> ch1
    - M3 -> ch3
    - M4 -> ch4
  - Auswertung mit `topk=1`
  - Einzel-Chirp als neues Referenzsignal verwendet
  - Indoor-Aufbau: Lautsprecher bleibt fest, Winkel werden durch Rotation des Arrays erzeugt

## Referenzsignal
- Einzelner Log-Chirp
- Bereich: 700–5000 Hz
- Dauer: 0.40 s
- Führungs- und Nachlaufstille vorhanden
- Ziel: kontrolliertes TDOA-freundliches Testsignal zur Validierung des Systems vor späteren Schiffshorn-Aufnahmen

## Verwendete Standardparameter
- Bandpass: 700–5000 Hz
- Auto-window:
  - topk = 1
  - auto-window-len = 0.40
  - auto-window-hop = 0.01
  - auto-window-expand = 0.05
  - auto-window-min-gap = 0.80
- SRP:
  - win-s = 0.15
  - hop-s = 0.05
- Event-Gates:
  - auto-dom-min = 0.20
  - event-min-dom = 0.20
  - event-min-conf = 0.05

## Wichtigste technische Erkenntnis des Tages
Die Korrektur der Array-Geometrie auf ca. 0.36 m war ein entscheidender Schritt. Mit der kleineren früheren Modellgeometrie traten systematische Fehlrichtungen auf. Mit der aktualisierten Geometrie wurde erstmals ein stabiler Hauptachsen-Referenzblock erreicht.

## Ergebnisse – Hauptachsen
- 0° -> 359° ≈ 0°  (stabil / korrekt)
- 90°:
  - Take1 -> 45° (problematisch)
  - Take2 -> 89° (korrekt)
  - Take3 -> 90° (korrekt)
- 180° -> 180° (stabil / korrekt)
- 270° -> 269° (stabil / korrekt)

### Interpretation Hauptachsen
- Das Basissystem funktioniert unter Indoor-Bedingungen auf den Hauptachsen grundsätzlich stabil.
- 90° zeigte im ersten Take noch eine Abweichung, konnte aber in zwei Wiederholungen korrekt geschätzt werden.
- Damit ist ein erster thesis-tauglicher Referenzblock für die Validierung des TDOA/SRP-PHAT-Ansatzes vorhanden.

## Ergebnisse – Zwischenwinkel
### 150°
- Take1 -> 135°
- Take2 -> 135°
- Bewertung: reproduzierbar / brauchbar, aber systematisch leicht verschoben

### 30°
- Take1 -> 225°
- Take2 -> 225°
- Bewertung: reproduzierbar falsch

### 60°
- Take1 -> 315°
- Take2 -> 45°
- Take3 -> 180° (REJECT)
- Bewertung: nicht reproduzierbar

### 120°
- Take1 -> 135°
- Take2 -> 0°
- Take3 -> 315°
- Bewertung: nicht reproduzierbar

### 300°
- Take1 -> 225° (REJECT)
- Take2 -> 135°
- Take3 -> 45°
- Bewertung: nicht reproduzierbar

## Fachliche Gesamteinschätzung
### Positiver Befund
- Hauptachsen sind mit dem aktuellen Setup stabil genug, um als Referenzblock in der Arbeit verwendet zu werden.
- Damit ist die TDOA/SRP-PHAT-Basis nicht gescheitert, sondern grundsätzlich validiert.

### Negativer / kritischer Befund
- Zwischenwinkel zeigen unter Indoor-Bedingungen deutlich schlechtere Reproduzierbarkeit.
- Das Fehlermuster ist nicht zufällig, sondern deutet auf:
  - starke Reflexionseinflüsse
  - Ambiguitäten des symmetrischen Arrays
  - hohe Sensitivität kleiner Orientierungsänderungen
hin.

### Methodische Konsequenz
- Der aktuelle Indoor-Referenzblock eignet sich gut, um zu zeigen:
  - dass das Basissystem auf Hauptachsen funktioniert
  - dass Zwischenwinkel deutlich schwieriger sind
  - dass Robustheit stark von Aufbau und Umgebung abhängt
- Genau dieser Kontrast ist für die spätere kritische Analyse der Datenqualität und Systemgrenzen wertvoll.

## Verwenden / Nicht verwenden
### Direkt verwendbar als positiver Referenzblock
- 0°
- 90° (Take2/Take3)
- 180°
- 270°
- 150° als zusätzlicher brauchbarer Zwischenwinkel

### Als Failure Cases / kritische Beispiele dokumentieren
- 30°
- 60°
- 120°
- 300°

## Nächste Schritte
1. Ergebnisse tabellarisch und grafisch aufbereiten:
   - Sollwinkel vs. geschätzter Winkel
   - zirkulärer Fehler
   - Qualitätswerte / Stabilität
2. Diesen Referenzblock als Arbeitsstand festhalten.
3. Danach methodisch entscheiden:
   - weitere Zwischenwinkel mit gleichem Signal messen
   - oder als nächsten Vergleichsschritt ILD / zweites Verfahren ergänzen
4. Später Vergleich mit Schiffshorn-Aufnahmen unter gleichem Auswerteprinzip.
