# Thesis Log – 2026-04-09 – Pairwise-Analyse und Diagnose der Zwischenwinkel

## Kontext
Aktueller Fokus der Arbeit ist die Richtungsbestimmung per TDOA / SRP-PHAT als Basissystem des geplanten Schallsignalortungssystems. Die Aufgabenstellung verlangt die Untersuchung und Bewertung von Verfahren zur Richtungsbestimmung sowie eine spätere kritische Analyse von Genauigkeit, Robustheit und Datenqualität.

## Aktiver technischer Stand
- Array-Geometrie im Code: ca. 0.36 m horizontal und vertikal
- Kanalzuordnung per Tap-Test bestätigt:
  - M1 -> ch2
  - M2 -> ch1
  - M3 -> ch3
  - M4 -> ch4
- Auswertung aktuell mit:
  - Einzel-Chirp als Referenzsignal
  - topk = 1
  - Auto-window zur Ereignisfindung
  - SRP-PHAT / TDOA als Hauptverfahren

## Referenzsignal
Neuer Einzel-Chirp als kontrolliertes Referenzsignal:
- Bereich: 700–5000 Hz
- Dauer: 0.40 s
- Ziel: stabilere Validierung der Richtungsbestimmung vor späteren Schiffshorn-Aufnahmen

## Ergebnisstand vor Pairwise-Diagnose
### Stabil / reproduzierbar
- 0° -> 359° ≈ 0°
- 90° -> 89° / 90° (nach Wiederholung stabil)
- 180° -> 180°
- 270° -> 269°
- 150° -> 135° / 135° (brauchbar, systematisch verschoben)

### Problematisch / nicht reproduzierbar
- 30° -> 225° / 225°
- 60° -> 315° / 45° / 180°
- 120° -> 135° / 0° / 315°
- 300° -> 225° / 135° / 45°

## Motivation für die Pairwise-Analyse
Da insbesondere Zwischenwinkel unter Indoor-Bedingungen instabil waren, wurde als nächster algorithmischer Schritt eine modulare paarweise DOA-Diagnose vorbereitet. Ziel war es zu verstehen, welche Mikrofonpaare bei guten Winkeln konsistent arbeiten und welche Paare bei problematischen Winkeln falsche Peaks treiben.

## Implementierter Diagnose-Schritt
Neu eingeführt wurden:
- eine modulare paarweise Auswertung pro Mikrofonpaar
- ein separates Debug-Script für Pairwise-DOA
- eine erste einfache Paar-Fusion / Cluster-Fusion als Diagnosewerkzeug

Wichtig: Die bestehende Hauptpipeline wurde dafür nicht grundlegend umgebaut. Die Pairwise-Analyse wurde bewusst als separates Diagnosemodul angelegt.

## Pairwise-Befund – problematischer Winkel 120°
Für `ref_120deg_take1.wav` lieferten die Einzelpaare stark widersprüchliche Richtungen:
- pair(0,1) -> 89° / 271°
- pair(1,3) -> 45° / 225°
- pair(0,3) -> 178° / 2°
- pair(2,3) -> 238° / 122°
- pair(0,2) -> 136° / 314°
- pair(1,2) -> 7° / 173°

Wesentliche Beobachtungen:
- nahezu alle Paare sind bereits einzeln 180°-ambig
- verschiedene Paare bevorzugen verschiedene Richtungscluster
- es gibt keinen stabil dominierenden globalen Paar-Konsens

Die erste naive Pair-Fusion ergab:
- theta ≈ 5°
- support_pairs = 2

Das war für 120° klar falsch.

### Interpretation
Das Problem bei 120° ist nicht nur ein schlechter globaler Peak, sondern bereits eine inkonsistente paarweise Richtungsinformation. Damit wurde sichtbar, dass die Instabilität problematischer Zwischenwinkel auf Ebene der Paarbeiträge selbst entsteht.

## Pairwise-Befund – guter Winkel 180°
Für `ref_180deg_take1.wav` zeigten die Paare ebenfalls starke 180°-Ambiguitäten:
- pair(1,3) -> 45° / 225°
- pair(0,2) -> 135° / 315°
- pair(0,3) -> 0° / 180°
- pair(2,3) -> 90° / 270°
- pair(1,2) -> 0° / 180°
- pair(0,1) -> 90° / 270°

Trotzdem ergab die globale Hauptpipeline korrekt:
- 180° -> 180°

Die naive Pair-Fusion ergab jedoch:
- theta = 90°
- support_pairs = 2

also einen falschen Wert.

### Interpretation
Selbst bei einem global gut funktionierenden Winkel sind die Einzelpaare häufig noch ambig. Der korrekte globale Winkel entsteht daher nicht, weil einzelne Paare bereits eindeutig sind, sondern weil die Kombination aller Paare im globalen SRP-Scan das richtige Ergebnis hervorbringt.

## Zentrale Erkenntnis des Tages
Die Pairwise-Analyse ist für die Arbeit sehr wertvoll, aber:
- nicht als direkter Ersatz der Hauptschätzung
- nicht als naive Mehrheitsentscheidung
- sondern als Diagnosewerkzeug

### Methodische Schlussfolgerung
- Einzelpaare sind aufgrund der symmetrischen Array-Geometrie häufig 180°-ambig.
- Eine einfache paarweise Mehrheits- oder Clusterfusion ist deshalb nicht ausreichend.
- Die Pairwise-Auswertung eignet sich jedoch sehr gut, um:
  - Ambiguitäten sichtbar zu machen
  - gute und schlechte Winkel zu unterscheiden
  - die Beiträge verschiedener Paargruppen zu analysieren

## Fachliche Bedeutung für die Bachelorarbeit
Dieser Befund ist direkt thesis-relevant:
1. Das Basissystem (globales SRP-PHAT) funktioniert auf Hauptachsen.
2. Zwischenwinkel sind unter Indoor-Bedingungen deutlich instabiler.
3. Die Ursache liegt nicht nur auf globaler Ebene, sondern bereits in den paarweisen TDOA-Beiträgen.
4. Daraus folgt als sinnvoller nächster Schritt:
   - gruppierte Paaranalyse (horizontal / vertikal / diagonal)
   - danach ggf. gewichtete Paarfusion
   - und erst später Vergleich mit weiteren Ansätzen wie ILD oder MUSIC

## Aktueller Arbeitsstand
### Positiv gesichert
- Hauptachsenblock mit Referenzsignal ist brauchbar
- Pairwise-Diagnose funktioniert
- Symmetrie-/Ambiguitätsproblem wurde sichtbar gemacht

### Noch offen
- Gruppierte Paaranalyse
- Entscheidung, welche Paargruppen bei welchen Winkeln informativer sind
- späterer Vergleich mit weiterem klassischen Verfahren (z. B. ILD)

## Nächste Schritte
1. Pairwise-Ausgabe um Gruppenreport erweitern:
   - horizontale Paare
   - vertikale Paare
   - diagonale Paare
2. Prüfen, ob bestimmte Paargruppen bei guten Winkeln konsistenter sind als andere.
3. Erst danach über eine intelligentere Fusion entscheiden.
4. Bestehende Hauptpipeline zunächst unverändert lassen.
