#!/usr/bin/env python3
"""Offline checks for Tuney's engine: synthetic vowels in, measured pitch out.

    python3 tests/test_engine.py path/to/run_engine

Each case writes a synthetic voice (glottal-like pulse train through three formant resonators),
runs it through the engine harness, and measures the output's fundamental with an independent
estimator (full-rate normalised autocorrelation with parabolic interpolation). Exit status 1 on any failure.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy.signal import lfilter

SR = 44100
HARNESS = sys.argv[1] if len(sys.argv) > 1 else "tests/run_engine"


def voice(f0_track, formants=((700, 80), (1220, 90), (2600, 120)), level=0.3, seed=1):
    """A vowel-like signal following f0_track (Hz per sample)."""
    phase = np.cumsum(f0_track / SR)
    frac = phase - np.floor(phase)
    src = np.where(frac < 0.6, np.sin(np.pi * frac / 0.6) ** 2, 0.0)          # Rosenberg-ish pulse
    src = np.diff(src, prepend=0.0)
    y = src
    for fc, bw in formants:
        r = np.exp(-np.pi * bw / SR)
        a = [1, -2 * r * np.cos(2 * np.pi * fc / SR), r * r]
        y = lfilter([1 - r], a, y)
    y = level * y / np.max(np.abs(y))
    y += np.random.default_rng(seed).normal(0, 1e-4, len(y))           # a little breath noise, -70 dB
    return y.astype(np.float32)


def run(sig, **params):
    with tempfile.TemporaryDirectory() as d:
        fi, fo = os.path.join(d, "in.f32"), os.path.join(d, "out.s16")
        sig.astype(np.float32).tofile(fi)
        args = [HARNESS, fi, fo] + ["%s=%s" % kv for kv in params.items()]
        lat = int(subprocess.run(args, check=True, capture_output=True, text=True).stdout.split()[-1])
        out = np.fromfile(fo, dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32768.0
    return out[:, 0], out[:, 1], lat


def f0_at(x, centre, lo=60, hi=1200, win=2048, expect=None):
    """Harmonic-sum pitch: the f0 whose first five harmonics carry the most energy (what the ear hears)."""
    if expect:
        lo, hi = expect / 1.4, expect * 1.4
    seg = x[max(0, centre - win // 2): centre + win // 2]
    if len(seg) < win or np.sqrt(np.mean(seg ** 2)) < 1e-3:
        return 0.0
    pad = 16 * win
    mag = np.abs(np.fft.rfft((seg - seg.mean()) * np.hanning(win), pad))
    bins = SR / pad
    cand = np.exp(np.linspace(np.log(lo), np.log(hi), 4000))
    score = np.zeros_like(cand)
    for k in range(1, 6):
        idx = cand * k / bins
        ok = idx < len(mag) - 1
        score[ok] += np.interp(idx[ok], np.arange(len(mag)), mag) / k ** 0.5
    i = int(np.argmax(score))
    if 0 < i < len(cand) - 1:
        a, b, c = np.log(score[i - 1:i + 2] + 1e-12)
        d = a - 2 * b + c
        fr = 0.5 * (a - c) / d if d != 0 else 0.0
        return float(np.exp(np.log(cand[i]) + fr * (np.log(cand[1]) - np.log(cand[0]))))
    return float(cand[i])


def cents(f, ref):
    return 1200 * np.log2(f / ref)


def track(x, t0, t1, hop=1024, expect=None):
    return np.array([f0_at(x, c, expect=expect) for c in range(int(t0 * SR), int(t1 * SR), hop)])


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


failures = []


def check(name, ok, detail):
    print("%-48s %s  %s" % (name, "PASS" if ok else "FAIL", detail))
    if not ok:
        failures.append(name)


def steady(f0, secs=2.0):
    return np.full(int(secs * SR), f0)


# 1. hard tune: A3 sung 35 cents sharp -> A3
f_in = midi_hz(57) * 2 ** (35 / 1200)
l, r, lat = run(voice(steady(f_in)), retune=100, vibrato=0, voice=2)
tr = track(l, 0.6, 1.8, expect=midi_hz(57))
err = cents(np.median(tr), midi_hz(57))
check("hard tune, A3 +35c -> A3", abs(err) < 5, "out %+.1f c (in +35 c), latency %d (%.1f ms)" % (err, lat, 1000 * lat / SR))

# 2. scale: D major-ish; 290 Hz (D4 -21c) in C major -> D4; C#4 +40c in C major -> D4
for name, fin, want, sc in (("C major, 290 Hz -> D4", 290.0, 62, 1), ("C major, C#4+40c -> D4", midi_hz(61) * 2 ** (40 / 1200), 62, 1),
                            ("C minor pent., E4 -> D#4/F4 nearest", midi_hz(64) - 3, 63, 5)):
    l, r, lat = run(voice(steady(fin)), retune=100, vibrato=0, key=0, scale=sc)
    err = cents(np.median(track(l, 0.6, 1.8, expect=midi_hz(want))), midi_hz(want))
    check(name, abs(err) < 6, "out %+.1f c from target" % err)

# 3. amount 50: half the correction
l, r, lat = run(voice(steady(f_in)), retune=100, vibrato=0, amount=50)
err = cents(np.median(track(l, 0.6, 1.8, expect=midi_hz(57))), midi_hz(57))
check("amount 50, +35c -> about +17c", abs(err - 17.5) < 5, "out %+.1f c" % err)

# 4. vibrato: 5.5 Hz, +/-35 c around A3 +10 c (stays nearest A3 throughout)
t = np.arange(int(2.5 * SR)) / SR
vib = midi_hz(57) * 2 ** ((10 + 35 * np.sin(2 * np.pi * 5.5 * t)) / 1200)
for keep, lo, hi in ((100, 22, 42), (0, 0, 12)):
    l, r, lat = run(voice(vib), retune=100, vibrato=keep)
    tr = cents(track(l, 0.8, 2.3, hop=256, expect=midi_hz(57)), midi_hz(57))
    depth = (np.percentile(tr, 95) - np.percentile(tr, 5)) / 2
    check("vibrato %d%%: depth kept %d-%d c" % (keep, lo, hi), lo <= depth <= hi and abs(np.median(tr)) < 8,
          "depth %.1f c, centre %+.1f c" % (depth, np.median(tr)))

# 5. note changes: Transition 100 % jumps, 0 % glides (~300 ms), whatever Retune is (time to get within 10 c of the new note)
glide = np.concatenate([steady(midi_hz(57) * 2 ** (30 / 1200), 1.0), steady(midi_hz(60) * 2 ** (-30 / 1200), 1.0)])
for name, params, lo, hi in (("transition 100, retune 100", dict(retune=100, transition=100), 0.0, 0.06),
                             ("transition 100, retune 0", dict(retune=0, transition=100), 0.0, 0.06),
                             ("transition 0, retune 100", dict(retune=100, transition=0), 0.25, 0.9)):
    l, r, lat = run(voice(glide), vibrato=0, **params)
    x = l[lat:]
    times = np.arange(1.0, 1.9, 0.005)
    tr = np.array([f0_at(x, int(tt * SR), win=1024, expect=midi_hz(59)) for tt in times])
    ok_t = next((tt - 1.0 for tt, f in zip(times, tr) if f > 0 and abs(cents(f, midi_hz(60))) < 10
                 and all(abs(cents(g, midi_hz(60))) < 10 for g in tr[(times >= tt) & (times < tt + 0.1)] if g > 0)), None)
    check("%s settles in %.2f-%.2f s" % (name, lo, hi), ok_t is not None and lo <= ok_t <= hi,
          "settled after %s s" % ("never" if ok_t is None else "%.3f" % ok_t))

# 5b. retune still sets how tightly a held note is pulled in: 0 % lets a slow drift through, 100 % flattens it
t = np.arange(int(2.5 * SR)) / SR
drift = midi_hz(57) * 2 ** ((25 * np.sin(2 * np.pi * 1.5 * t)) / 1200)
depths = {}
for rt in (100, 0):
    l, r, lat = run(voice(drift), retune=rt, transition=100, vibrato=0)
    tr = cents(track(l, 0.8, 2.3, hop=256, expect=midi_hz(57)), midi_hz(57))
    depths[rt] = (np.percentile(tr, 95) - np.percentile(tr, 5)) / 2
check("retune 100 holds a drifting note, retune 0 lets it move", depths[100] < 6 and depths[0] > depths[100] + 3,
      "drift left: %.1f c (100 %%), %.1f c (0 %%)" % (depths[100], depths[0]))

# 5c. humanize loosens long notes step by step (vibrato knob 0, so only humanize lets the wobble through)
hd = {}
for hu in (0, 50, 100):
    l, r, lat = run(voice(vib), retune=100, transition=100, vibrato=0, humanize=hu)
    tr = cents(track(l, 0.8, 2.3, hop=256, expect=midi_hz(57)), midi_hz(57))
    hd[hu] = (np.percentile(tr, 95) - np.percentile(tr, 5)) / 2
check("humanize 0 < 50 < 100, and 100 still corrects", hd[0] < 8 and hd[0] + 3 < hd[50] < hd[100] - 3 and hd[100] < 26,
      "wobble left: %.1f / %.1f / %.1f c of 35" % (hd[0], hd[50], hd[100]))

# 6. voice ranges
for v, m, name in ((0, 79, "Soprano G5"), (1, 67, "Alto G4"), (3, 43, "Baritone G2"), (2, 46, "Tenor A#2")):
    fin = midi_hz(m) * 2 ** (-30 / 1200)
    l, r, lat = run(voice(steady(fin)), retune=100, vibrato=0, voice=v)
    err = cents(np.median(track(l, 0.6, 1.8, expect=midi_hz(m))), midi_hz(m))
    check("%s -30c -> on pitch" % name, abs(err) < 6, "out %+.1f c, latency %.1f ms" % (err, 1000 * lat / SR))

# 6b. tuning reference: A3 at 432 Hz tuning (216 Hz) is in tune with Freq 432, or with Freq 440 and Cents -32
a432 = 216.0
for name, params in (("Freq 432", dict(freq=432)), ("Freq 440 + Cents -32", dict(freq=440, cents=-32))):
    l, r, lat = run(voice(steady(a432 * 2 ** (25 / 1200))), retune=100, vibrato=0, **params)
    err = cents(np.median(track(l, 0.6, 1.8, expect=a432)), a432)
    check("%s: A3 lands on 216 Hz" % name, abs(err) < 5, "out %+.1f c from 216 Hz" % err)

# 7. bypass and amount 0: transparent (delayed copy of the input)
sig = voice(steady(f_in))
for name, params in (("bypass", dict(bypass=1)), ("amount 0", dict(amount=0))):
    l, r, lat = run(sig, **params)
    a, b = sig[SR // 2: SR + SR // 2], l[SR // 2 + lat: SR + SR // 2 + lat]
    q = np.round(a * 32767) / 32768
    snr = 10 * np.log10(np.sum(q ** 2) / max(np.sum((q - b) ** 2), 1e-20))
    check("%s is transparent" % name, snr > (60 if name == "bypass" else 25), "SNR %.1f dB vs input" % snr)

# 8. no clicks, no level jumps across a note change and a consonant (noise burst) and silence
rng = np.random.default_rng(3)
parts = [voice(steady(midi_hz(57) * 1.01, 0.8)), (0.05 * rng.normal(size=int(0.08 * SR))).astype(np.float32),
         voice(steady(midi_hz(62) * 0.985, 0.8), seed=2), np.zeros(int(0.3 * SR), np.float32)]
sig = np.concatenate(parts)
l, r, lat = run(sig, retune=100)
x = l[lat:]
env_in = np.sqrt(np.convolve(sig ** 2, np.ones(441) / 441, "same"))[: len(x)]
env_out = np.sqrt(np.convolve(x ** 2, np.ones(441) / 441, "same"))[: len(env_in)]
mask = env_in > 0.02
ratio_db = 20 * np.log10(env_out[mask] / env_in[mask])
jump = np.max(np.abs(np.diff(x))) / max(np.max(np.abs(np.diff(sig))), 1e-9)
check("level follows input (+/-3 dB)", np.percentile(np.abs(ratio_db), 99) < 3, "99th pct %.2f dB" % np.percentile(np.abs(ratio_db), 99))
check("no clicks (max step <= 1.5x input's)", jump <= 1.5, "max step ratio %.2f" % jump)
check("stereo channels match for mono input", np.max(np.abs(l - r)) < 1e-6, "")
check("silence stays silent", np.max(np.abs(x[-int(0.2 * SR):])) < 1e-3, "")

print("\n%d failure(s)" % len(failures))
sys.exit(1 if failures else 0)
