# EMG Muscle Sensor → Piano Notes + Live Graph
---

## What this project does

1. Reads the muscle's electrical signal through the MyoWare EMG sensor
2. Converts the signal to a number (0 – 65535) using the MCP3008 chip
3. Maps that number to a piano note (40 = relaxed, 90 = max tension)
4. Plays the note through the Pi's speaker in real time
5. Shows a live scrolling graph of the muscle signal

**Relax the arm → low note (like bottom of piano)**
**Squeeze hard   → high note (like top of piano)**

---

## Wiring diagram

```
MyoWare 2.0 EMG sensor
  SIG pin ──────────────────────── MCP3008 CH0 (pin 1)
  VCC pin ──────────────────────── Pi 3.3V
  GND pin ──────────────────────── Pi GND

MCP3008 chip (looking at flat side, pins left to right)
  Pin 1  CH0  ← MyoWare SIG
  Pin 9  VDD  → Pi 3.3V  (pin 1)
  Pin 10 VREF → Pi 3.3V  (pin 1)
  Pin 11 AGND → Pi GND   (pin 6)
  Pin 12 CLK  → GPIO 11  (Pi pin 23)
  Pin 13 DOUT → GPIO 9   (Pi pin 21)
  Pin 14 DIN  → GPIO 10  (Pi pin 19)
  Pin 15 CS   → GPIO 8   (Pi pin 24)
  Pin 16 DGND → Pi GND   (pin 6)

Speaker
  → Pi 3.5mm audio jack (green port)
```

---

## Install libraries

```bash
pip install adafruit-circuitpython-mcp3xxx pygame matplotlib numpy
```

---

## Run the project

```bash
python emg_piano.py
```

A window opens showing the live graph.
Close the window to stop.

---

## How the code works

```
Muscle contracts
      ↓
Electrode pads pick up ~1–5 mV signal
      ↓
MyoWare 2.0 amplifies to 0–3.3 V
      ↓
MCP3008 converts to number: 0–65535
  (Adafruit library does this automatically)
      ↓
Python maps number to MIDI note 40–90
  note = interp(value, [0, 65535], [40, 90])
      ↓
pygame plays piano sound through speaker
      ↓
matplotlib draws live graph on screen
```

---

## MIDI Piano Notes reference

| MIDI Note | Name | What it sounds like |
|-----------|------|-------------------|
| 40 | E2 | Very low, deep rumble — fully relaxed |
| 50 | D3 | Low note — mild activity |
| 60 | C4 | Middle C — moderate tension |
| 70 | A#4 | Getting higher — strong squeeze |
| 80 | G#5 | High — near maximum |
| 90 | F#6 | Very high — maximum tension |

---

## Biofeedback Tool

People with fibromyalgia can't easily feel when their muscles are tense.
This device lets them **hear** their tension instead of trying to feel it.
A lower note = more relaxed. They can practice making the note go lower.
This is called **biofeedback** — used in real clinics to treat chronic pain.
Our $105 device does the same thing as $3,000 clinical machines.
