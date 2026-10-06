"""Around Us - royalty-free soundtrack for the reels, composed in code (numpy). No AI, no licences.

make_track(seconds, events, path) writes a 44.1 kHz stereo WAV:
  * quiet ambient background music: a warm, slow synth pad with a soft sub bass, C major,
    chords Cmaj7 - Am7 - Fmaj7 - Gsus2 changing every 5 s (composed here, not a song anyone owns)
  * no drums, no plucks, no rising lines, no ticks, dings or swooshes (events are accepted but ignored)
  * 1 s fade in, 2 s fade out, peak at about -10 dBFS so it sits under everything

If the repo has assets/music.mp3 (or .m4a / .wav), reel.py uses that as the backing track instead and only
mixes these effects on top. Use a track you have the rights to.
"""
import wave

import numpy as np

SR = 44100
BPM = 72
BEAT = 60 / BPM
# C major, gentle: Cmaj7 - Am7 - Fmaj7 - Gsus2 (root, 3rd/2nd, 5th, 7th), MIDI note numbers, one chord per bar
CHORDS = [(60, 64, 67, 71), (57, 60, 64, 67), (53, 57, 60, 64), (55, 57, 62, 67)]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def env(n, a, d, s_level=0.0, r=None):
    """Attack / decay (to s_level) / optional release envelope, n samples."""
    a, d = int(a * SR), int(d * SR)
    e = np.ones(n) * s_level
    e[:a] = np.linspace(0, 1, min(a, n)) if a else 1
    if d:
        e[a:a + d] = np.linspace(1, s_level, min(d, max(n - a, 0)))
    if r:
        r = int(r * SR)
        if r and r < n:
            e[-r:] *= np.linspace(1, 0, r)
    return e


def tone(freq, n, kind="sine"):
    t = np.arange(n) / SR
    if kind == "tri":
        return 2 * np.abs(2 * ((t * freq) % 1) - 1) - 1
    return np.sin(2 * np.pi * freq * t)


def lowpass(x, cutoff):
    """One-pole low-pass (vectorised with a recursive filter)."""
    rc = 1 / (2 * np.pi * cutoff)
    alpha = (1 / SR) / (rc + 1 / SR)
    y = np.empty_like(x)
    acc = 0.0
    # scipy is not a dependency; a plain loop over ~1M samples takes well under a second
    for i, v in enumerate(x):
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def reverb(x, amount=0.35):
    """Cheap room: a few soft, low-passed echoes."""
    out = x.copy()
    for delay, gain in ((0.089, 0.45), (0.147, 0.32), (0.233, 0.22), (0.361, 0.14)):
        d = int(delay * SR)
        out[d:] += x[:-d] * gain * amount * 2
    return out


def add(buf, start, sig):
    i = int(start * SR)
    j = min(len(buf), i + len(sig))
    if j > i:
        buf[i:j] += sig[:j - i]


def pluck(freq, seconds, vol):
    """Soft electric-piano / music-box note: a few partials, quick attack, long decay."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * freq * t) * 1.0
           + np.sin(2 * np.pi * freq * 2 * t) * 0.25 * np.exp(-t * 3)
           + np.sin(2 * np.pi * freq * 3 * t) * 0.08 * np.exp(-t * 5))
    return sig * np.exp(-t * 2.2) * env(n, 0.006, 0, 1.0) * vol


def backing(seconds):
    """Quiet ambient background: a warm, slow pad only. No drums, no plucks, no effects, nothing that
    rises or rings. Chords change every 5 seconds and cross-fade into each other; a slow, gentle
    swell in volume keeps it breathing."""
    n = int(seconds * SR)
    pad, bass, upper = (np.zeros(n) for _ in range(3))
    bar = 5.0
    nbars = int(np.ceil(seconds / bar)) + 1
    for b in range(nbars):
        chord = CHORDS[b % len(CHORDS)]
        t0 = b * bar
        m = int((bar + 1.5) * SR)                      # 1.5 s overlap = cross-fade between chords
        e = env(m, 1.5, 0.0, 1.0, r=1.5)
        p = np.zeros(m)
        for note in chord:
            for det in (-0.08, 0.08):
                fr = hz(note - 12) * 2 ** (det / 12)
                p += tone(fr, m, "sine") * 0.07 + tone(fr, m, "tri") * 0.03
        add(pad, t0, p * e)
        # sub bass: the root, very soft and steady
        add(bass, t0, tone(hz(chord[0] - 24), m, "sine") * 0.12 * e)
        # one held upper note per chord (the 5th), sine, slow in and out: no attack, no movement
        add(upper, t0 + 0.5, tone(hz(chord[2]), m, "sine") * 0.05 * env(m, 2.5, 0.0, 1.0, r=2.0))
    mix = lowpass(pad, 700) + bass + lowpass(upper, 1200)
    # a slow breathing swell (about one cycle every 8 s), 15% deep
    t = np.arange(n) / SR
    mix = mix[:n] * (0.925 + 0.075 * np.sin(2 * np.pi * t / 8 - np.pi / 2))
    return reverb(mix, 0.2)


def effects(seconds, events):
    """Sound effects are off: the reels use background music only (no ticks, dings or swooshes)."""
    return np.zeros(int(seconds * SR))


def write_wav(path, left, right):
    stereo = np.empty(len(left) * 2)
    stereo[0::2], stereo[1::2] = left, right
    pcm = np.clip(stereo, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())


LEVEL = 0.32   # peak level (about -10 dBFS): background music, well under speech/notification loudness


def finish(mix, seconds):
    n = int(seconds * SR)
    mix = mix[:n]
    fi, fo = int(1.0 * SR), int(2.0 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    peak = np.max(np.abs(mix)) or 1
    return mix / peak * LEVEL


def make_track(seconds, events, path, music=True):
    """Backing loop (unless music=False) + effects -> stereo WAV at path."""
    mix = effects(seconds, events)
    if music:
        mix = mix + backing(seconds)
    mix = finish(mix, seconds)
    write_wav(path, mix, mix * 0.97)
    return path
