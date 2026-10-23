# Testing Tuney

## Offline (Ubuntu, before the device)

From `~/Tuney`, with the toolchain checked out next to it in `~/mpc-vst-plugins`:

```bash
MV=~/mpc-vst-plugins
# wrapper host test (parameters, popups, stepping, save/restore, two instances) -- must print PASSED
$MV/tools/test_port.sh vst/vst.json

# engine: pitch accuracy, scales, Amount, Vibrato, Retune, voice ranges, bypass, clicks -- must end "0 failure(s)"
g++ -O2 -std=gnu++11 -I$MV/wrapper -c src/engine.cpp -o /tmp/tuney_engine.o
gcc -O2 -I$MV/wrapper tests/run_engine.c /tmp/tuney_engine.o -lstdc++ -lm -o /tmp/run_engine
python3 tests/test_engine.py /tmp/run_engine          # needs numpy + scipy

# key/scale -> note keys, taps, save/restore -- must end "0 failure(s)"
gcc -O2 -I$MV/wrapper tests/test_notes.c /tmp/tuney_engine.o -lstdc++ -lm -o /tmp/test_notes && /tmp/test_notes
```

Results on 2026-10-19 (offline, x86): host test PASSED (33 checks), engine 24/24, notes, light, sung key, dial, Transition, arrows, User preset, range strip and Retune conversion 52/52.
CPU on x86: 0.3 % (Soprano) to 1.4 % (Baritone) of one core, against 32 % for the previous phase-vocoder engine.

## Build

```bash
~/mpc-vst-plugins/tools/build_port.sh vst/vst.json
```

The skin artwork is pre-drawn (`vst/artwork`, `vst/images`); `tools/make_skin_art.py` redraws it after a design change.

## On the MPC (numbered so results can be reported back)

| # | Do | Expect |
|---|----|--------|
| 1 | Insert Tuney on an audio track with a vocal | Loads; one page; no empty boxes; dial shows "-" when silent |
| 2 | Play the vocal, Retune 100, Amount 100, Scale Chromatic | Hard "tuned" sound; dial shows the note and cents |
| 3 | Pick Key and Scale (e.g. A Minor) | Note strip lights the scale's 7 notes |
| 4 | Tap a lit note | It turns off, Scale changes to User; the voice no longer lands on that note |
| 4b | Pick Major, then User again | Major relights its notes; User brings your tapped set back |
| 4c | On User, change Key | Your set moves to the new key with the same shape |
| 5 | Lower Retune to 50-0 on a held, wavering note | The note is held less tightly, more natural (Retune 100 = locked, 0 = loosest) |
| 5b | Transition 100, then 0, singing a melody | 100 = instant stepped jumps between notes; 0 = slow slides from note to note (about half a second) |
| 6 | Vibrato 100 vs 0 on a held note with vibrato | 100 keeps the vibrato, 0 flattens it |
| 7 | Humanize 100 with Retune 100 | Short notes still snap, long notes relax |
| 8 | Amount 0, then Bypass | Both sound like the dry vocal, no click when toggling |
| 9 | Voice: Soprano vs Baritone on a low voice | Baritone tracks low notes; Soprano ignores them (uncorrected, and outside the dimmed range on the strip). Lower Voice = more latency |
| 9b | Freq 432 (or Freq 440 + Cents -32) on a vocal sung to a 432 Hz track | Lands in tune with the track; dial cents near 0 |
| 10 | Q-Links (column 1, then the next column) | Retune, Transition, Amount, Vibrato, then Humanize, Freq, Cents |
| 11 | Save project, reload | All settings, hand-tapped notes and the User set come back |
| 12 | Run 2-3 instances while playing | No dropouts |
| 13 | THEME: Grey (purple), Classic, White, Silver | Whole page changes look; values, notes and knobs stay put; saved with the project |
| 14 | Watch the light in the dial while singing, then stop | Soft white with input, bright white when it locks onto a note, dark glass ~0.15 s after silence |
| 15 | Leave it running on a held-note loop for a minute | Screen stays responsive (light, keys and dial only redraw when they change; a held note leaves them still) |
| 16 | PRESET menu: Hard Tune, Tight, Natural, Smooth, Subtle (hardest to softest) | Each sets Retune / Amount / Humanize / Vibrato; Key, Scale, notes and theme stay as they are |
| 16b | PRESET menu: User | Scale = User, all 12 notes on, strong fast tuning: sing, watch which keys light, tap off the ones you don't want |
| 16c | Open the PRESET menu while the vocal plays | The menu stays open and still; the light, keys and dial keep moving behind it |
| 17 | Hard Tune (Retune and Transition 100), Key + Scale of the song (e.g. Minor or Minor Pent.) | The stepped Future / Travis Scott sound: notes snap, held notes flat |
| 18 | Read every label, value and dropdown from where you normally stand | Legible; dropdown lists have big rows; Key opens as a 3 x 4 pad |
| 19 | Voice and Theme arrows (◀ ▶), tapped and held | One tap = exactly one option, wraps around at the ends; holding steps about 3 a second, never skips |
| 19b | Data wheel or a Q-Link on Voice / Key / Scale / Theme | Three clicks per option: you can stop on every one |
| 20 | Sing with a scale set | The key you're singing lights up green on the piano, and its exact key and octave on the range strip above; singing a switched-off note shows a faint dashed green outline on its piano key |
| 20b | Voice: Soprano, Alto, Tenor, Baritone | The range strip dims what's outside each range and outlines the rest; the name and range show at its left (Tenor: A2 – C5) |
| 20c | Tap each piano key, black keys at their edges too | The key you touch toggles; a black key wins where it overlaps a white one |
| 21 | Tap every note off, then sing | Dial still reads the note and cents, light goes bright, the sung key gets the dashed outline; nothing is corrected |
| 22 | Open a project saved with 1.1.0 | Retune comes back converted (old 0 ms = 100 %, old 25 ms = 75 %) |
| 23 | Open a project saved with 1.2.x | Sounds the same as before: Transition is set to match its Retune |
| 24 | **1.4.2 (new wrapper):** track edit → automation, turn the Q-Links | Each Q-Link moves its parameter and stays there (before, they snapped back). Back on the plugin screen, the Voice and Theme arrows, Key / Scale lists and note keys still update |

Latency follows Voice (the minimum this shifter allows: two periods of the range's lowest note): about 12 ms (Soprano, from F#3),
15 (Alto, from C#3), 19 (Tenor, from A2), 25 (Baritone, from E2). Pick the highest Voice whose lowest note your singer stays above.

Preset strength, offline (a sung A3 28 c flat with a slow drift and vibrato, C major; dry: centre -26 c, 34 c rms off the note):
Hard Tune 3 c rms, Tight 6, Natural 12, Smooth 17, Subtle 19 -- every preset puts the centre on the note (within 2 c);
the rest is the vibrato and drift each one keeps on purpose. Notes below the Voice's range (Tenor: A2) are left alone:
pick a lower Voice for a lower singer.
