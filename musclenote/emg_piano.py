# ============================================================
#  EMG MUSCLE SENSOR → PIANO NOTES + LIVE GRAPH
#  Science Fair Project — Raspberry Pi 4
#
#  Hardware needed:
#    - Raspberry Pi 4
#    - MyoWare 2.0 EMG sensor
#    - MCP3008 ADC chip (wired via SPI)
#    - Speaker connected to Pi's 3.5mm audio jack
#    - Electrode pads on your forearm
#
#  Wiring (MCP3008 → Raspberry Pi 4):
#    MCP3008 VDD  → Pi 3.3V   (pin 1)
#    MCP3008 VREF → Pi 3.3V   (pin 1)
#    MCP3008 AGND → Pi GND    (pin 6)
#    MCP3008 DGND → Pi GND    (pin 6)
#    MCP3008 CLK  → GPIO 11   (SPI clock)
#    MCP3008 DOUT → GPIO 9    (SPI MISO)
#    MCP3008 DIN  → GPIO 10   (SPI MOSI)
#    MCP3008 CS   → GPIO 8    (SPI chip select)
#    MCP3008 CH0  → MyoWare SIG pin
#
#  Install libraries first (run in terminal):
#    pip install adafruit-circuitpython-mcp3xxx pygame matplotlib
#
# ============================================================

import time
import board
import busio
import digitalio
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

import pygame
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque

# ============================================================
#  STEP 1 — SET UP THE MCP3008 USING ADAFRUIT LIBRARY
# ============================================================

# Create the SPI bus
spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

# Create the chip select pin
cs = digitalio.DigitalInOut(board.CE0)

# Create the MCP3008 object
mcp = MCP.MCP3008(spi, cs)

# Read from channel 0 (where MyoWare SIG pin is connected)
channel = AnalogIn(mcp, MCP.P0)

print("✅ MCP3008 connected using Adafruit library!")
print("   channel.value    → 0 to 65535  (raw reading)")
print("   channel.voltage  → 0.0 to 3.3  (volts)")
print()

# ============================================================
#  STEP 2 — MUSICAL SCALE SETUP
#
#  Instead of mapping to ANY number between 40–90 (which sounds
#  random and out-of-tune), we only allow notes that belong to
#  the C major pentatonic scale. Every note in this list sounds
#  good with every other note — like a xylophone or a harp.
#
#  These are MIDI note numbers:
#    C3=48, D3=50, E3=52, G3=55, A3=57,
#    C4=60, D4=62, E4=64, G4=67, A4=69,
#    C5=72, D5=74, E5=76, G5=79, A5=81
#
#  Low muscle activity → picks notes from the left of this list
#  High muscle activity → picks notes from the right of this list
# ============================================================

# C major pentatonic scale — spans 3 octaves, always sounds musical
# Every note here harmonises with every other — impossible to sound bad!
SCALE = [
    48, 50, 52, 55, 57,   # C3  D3  E3  G3  A3  (low — very relaxed)
    60, 62, 64, 67, 69,   # C4  D4  E4  G4  A4  (middle — mild tension)
    72, 74, 76, 79, 81,   # C5  D5  E5  G5  A5  (high — strong squeeze)
]

# Smoothing buffer — holds the last 8 raw readings.
# We take the average before picking a note so that
# tiny muscle twitches don't jump the note around wildly.
SMOOTH_SIZE = 8
smooth_buffer = deque([0.0] * SMOOTH_SIZE, maxlen=SMOOTH_SIZE)

# --- Helper: convert MIDI note number to frequency in Hz ---
def midi_to_hz(note):
    """
    Piano uses MIDI note numbers.
    Note 69 = A4 = 440 Hz (middle A on piano).
    Each note up = multiply frequency by 2^(1/12).
    """
    return 440.0 * (2.0 ** ((note - 69) / 12.0))

# --- Helper: generate a short piano-like sound as audio samples ---
def make_piano_note(midi_note, duration=0.4, sample_rate=44100):
    """
    Creates a piano-like sound using sine waves.
    A real piano has many overtones — we fake it by
    adding several harmonics (2x, 3x the base frequency).
    The sound fades out like a real piano note.

    Converts MIDI note → frequency
    Builds a sine wave (basic tone)
    Adds harmonics (timbre / “piano-ness”)
    Applies decay envelope (natural fading)
    Converts to audio format
    Outputs stereo sound
    """
    freq = midi_to_hz(midi_note)
    t    = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

    # Combine harmonics to sound more like a piano
    wave  = 0.50 * np.sin(2 * np.pi * freq * t)         # base note
    wave += 0.25 * np.sin(2 * np.pi * freq * 2 * t)     # 1st overtone
    wave += 0.12 * np.sin(2 * np.pi * freq * 3 * t)     # 2nd overtone
    wave += 0.06 * np.sin(2 * np.pi * freq * 4 * t)     # 3rd overtone

    # Fade out so it sounds natural (not a hard cut)
    fade_curve = np.exp(-3.5 * t / duration)
    wave = wave * fade_curve

    # Scale to 16-bit audio range and make it stereo
    wave = (wave * 32767).astype(np.int16)
    stereo = np.column_stack([wave, wave])   # left + right channels
    return stereo

# --- Set up pygame audio ---
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
pygame.mixer.set_num_channels(4)   # allow a few notes at once

# Pre-make sounds for only the notes in our scale
# (much faster than building 50 notes like before)
print("🎹 Preparing piano notes for C major pentatonic scale ...")
note_sounds = {}
for note_num in SCALE:
    samples = make_piano_note(note_num, duration=0.5)
    sound   = pygame.sndarray.make_sound(samples)
    sound.set_volume(0.7)
    note_sounds[note_num] = sound

print(f"✅ Piano ready! {len(SCALE)} notes: {SCALE[0]} (relaxed) → {SCALE[-1]} (max tension)")
print()

# ============================================================
#  STEP 3 — MAP EMG READING TO A MUSICAL SCALE NOTE
# ============================================================

def emg_to_note(raw_value):
    """
    1. Add raw_value to the smoothing buffer
    2. Average the last 8 readings  →  removes jitter
    3. Normalise the average to 0.0–1.0
    4. Use that to pick an index into SCALE list
    5. Return the MIDI note at that index

    Because we only pick from SCALE, the output is always
    a proper musical note — never an out-of-tune in-between value.

    Example:
      raw_value = 20000  →  normalised = 0.30
      index     = int(0.30 * 14) = 4
      SCALE[4]  = 57  (A3)  ← always in tune!
    """
    # Step 1 — add new reading to buffer
    smooth_buffer.append(raw_value)

    # Step 2 — average the buffer to smooth out noise
    smooth = np.mean(smooth_buffer)

    # Step 3 — normalise: 0.0 = fully relaxed, 1.0 = max tension
    normalised = smooth / 65535.0

    # Step 4 — pick an index into our scale list
    # Multiply by (len-1) so index never goes out of bounds
    idx = int(normalised * (len(SCALE) - 1))
    idx = max(0, min(idx, len(SCALE) - 1))   # safety clamp

    # Step 5 — return the actual musical note
    return SCALE[idx]

# ============================================================
#  STEP 4 — LIVE GRAPH SETUP WITH MATPLOTLIB
# ============================================================

# How many seconds of data to show on the graph
GRAPH_SECONDS = 10
SAMPLE_RATE_HZ = 20   # read sensor 20 times per second
MAX_POINTS = GRAPH_SECONDS * SAMPLE_RATE_HZ   # = 200 points on screen

# Rolling buffers — old values fall off the left side of the graph
emg_values  = deque(maxlen=MAX_POINTS)   # raw ADC values (0–65535)
time_values = deque(maxlen=MAX_POINTS)   # timestamps in seconds

# Fill with zeros so the graph shows immediately
for _ in range(MAX_POINTS):
    emg_values.append(0)
    time_values.append(0.0)

# --- Create the matplotlib figure ---
fig, ax = plt.subplots(figsize=(10, 5))
fig.patch.set_facecolor('#0e1a0e')   # dark green-black background
ax.set_facecolor('#0e1a0e')

# The line that shows the EMG signal
line, = ax.plot([], [], color='#00ff88', linewidth=1.8, label='EMG Signal')

# Graph labels
ax.set_ylim(0, 65535)
ax.set_xlabel('Time (seconds)', color='white', fontsize=12)
ax.set_ylabel('EMG Reading (0 – 65535)', color='white', fontsize=12)
ax.set_title('🎹  Live Muscle Signal → C Major Pentatonic Piano\n'
             'Relax = low note (C3) | Squeeze = high note (A5)',
             color='white', fontsize=13, fontweight='bold')
ax.tick_params(colors='white')
ax.spines['bottom'].set_color('#336633')
ax.spines['left'].set_color('#336633')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(color='#1a3a1a', linewidth=0.6)
ax.legend(loc='upper right', facecolor='#1a3a1a', labelcolor='white')

# Note label shown on the graph in real time
note_text = ax.text(
    0.02, 0.92, '',
    transform=ax.transAxes,
    color='#ffcc00', fontsize=14, fontweight='bold',
    bbox=dict(boxstyle='round,pad=0.4', facecolor='#1a3a1a', edgecolor='#336633')
)

# ============================================================
#  STEP 5 — TIMING + NOTE PLAYBACK CONTROL
# ============================================================

start_time    = time.time()
last_note     = -1       # track last note so we don't repeat same note
last_play_time = 0.0     # when we last played a note
NOTE_COOLDOWN = 0.25     # seconds between note plays — quarter note feel

# ============================================================
#  STEP 6 — ANIMATION FUNCTION (runs every frame)
#  This function is called by matplotlib ~20 times per second
# ============================================================

def update_frame(frame):
    """
    Called automatically by matplotlib's animation system.
    Each call:
      1. Reads one EMG sample from the sensor
      2. Maps it to a piano note
      3. Plays the note if it changed (and cooldown passed)
      4. Updates the live graph
    """
    global last_note, last_play_time

    # -- Read EMG sensor --
    raw_value  = channel.value     # 0 to 65535  (Adafruit gives us this directly)
    voltage    = channel.voltage   # 0.0 to 3.3 volts (nice and readable!)
    elapsed    = time.time() - start_time

    # -- Map EMG to piano note (musical scale + smoothing) --
    note = emg_to_note(raw_value)
    idx  = SCALE.index(note)   # position in scale (0=lowest, 14=highest)

    # -- Play note if it changed and cooldown has passed --
    now = time.time()
    note_changed = (note != last_note)
    cooldown_ok  = (now - last_play_time) >= NOTE_COOLDOWN

    if note_changed and cooldown_ok:
        note_sounds[note].play()
        last_note      = note
        last_play_time = now

    # -- Store data for graph --
    emg_values.append(raw_value)
    time_values.append(elapsed)

    # -- Update the graph line --
    times = list(time_values)
    vals  = list(emg_values)

    line.set_data(times, vals)

    # Scroll the x-axis so we always see the last 10 seconds
    ax.set_xlim(max(0, elapsed - GRAPH_SECONDS), max(GRAPH_SECONDS, elapsed))

    # -- Update the note label on the graph --
    # Show the note name (C, D, E, G, A) alongside the MIDI number
    NOTE_NAMES = {48:'C3',50:'D3',52:'E3',55:'G3',57:'A3',
                  60:'C4',62:'D4',64:'E4',67:'G4',69:'A4',
                  72:'C5',74:'D5',76:'E5',79:'G5',81:'A5'}
    note_name = NOTE_NAMES.get(note, str(note))
    note_label = (
        f"♪ {note_name}  (MIDI {note})  |  {voltage:.2f} V  |  "
        f"{'🟢 RELAXED' if idx < 5 else '🟡 MILD' if idx < 10 else '🔴 HIGH TENSION'}"
    )
    note_text.set_text(note_label)

    # -- Print to terminal too (easy to read) --
    bar   = '█' * int(raw_value / 3000)
    print(f"\r  EMG: {raw_value:6d}  |  {voltage:.2f}V  |  Note: {note:3d}  |  {bar:<22}", end='', flush=True)

    return line, note_text


# ============================================================
#  STEP 7 — RUN EVERYTHING
# ============================================================

print("=" * 55)
print("  🎹  EMG PIANO + LIVE GRAPH — STARTING")
print("=" * 55)
print("  Scale: C major pentatonic (always sounds musical!)")
print("  Relax your arm  → C3  (low, calm note)")
print("  Squeeze gently  → C4/D4 (middle range)")
print("  Squeeze hard    → A5  (high, bright note)")
print("  Close the graph window to stop.")
print("=" * 55)
print()

# Start the live animation
# interval=50 means update every 50ms → 20 frames per second
ani = animation.FuncAnimation(
    fig,
    update_frame,
    interval=50,       # milliseconds between updates
    blit=False,        # redraw full axes each frame (simpler)
    cache_frame_data=False,
)

plt.tight_layout()
plt.show()   # opens the window — blocks until you close it

# Cleanup when window is closed
print("\n\n✅ Session ended. Goodbye!")
pygame.mixer.quit()
