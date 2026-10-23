/*
 * Tuney -- real-time vocal pitch correction for MPC (3DTHC).
 *
 * Signal path (44.1 kHz, interleaved int16 stereo, 128-frame blocks):
 *
 *   in --> mono sum --> anti-alias low-pass --> 2:1 decimate --> YIN detector (every 128 samples)
 *                                                                     |
 *                       note choice (key/scale/notes, vibrato, humanize, retune, transition)
 *                                                                     |
 *   in --> stereo ring buffer --> TD-PSOLA (pitch-synchronous grains, shared marks) --> out
 *
 * TD-PSOLA keeps the voice's formants, costs a few multiply-adds per sample, and its latency
 * follows the selected voice range (about 12 ms for Soprano up to 25 ms for Baritone).
 * Latency stays the same in bypass, so switching it never shifts the vocal in time.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <new>

extern "C" {
#include "engine.h"
}

static const int SR = 44100;

/* detector (runs on the 2:1 decimated signal, 22050 Hz) */
static const int DSR = SR / 2;
static const int DET_SIZE = 2048;          /* ring of decimated samples */
static const int DET_WIN = 1024;           /* analysis window, 46 ms */
static const int MIN_LAG = 20;             /* 1102 Hz */
static const int MAX_LAG = 340;            /* 65 Hz */
static const int DET_HOP = 128;            /* input samples between detections, 2.9 ms: crisp hard-tune steps */

/* PSOLA buffers (input samples) */
static const int RING = 8192;              /* power of two */
static const int RMASK = RING - 1;
static const int MARKS = 64;               /* power of two */
static const int HANN_N = 4096;

static const char *NOTE_KEYS[12] = {"note_C", "note_Cs", "note_D", "note_Ds", "note_E", "note_F",
                                    "note_Fs", "note_G", "note_Gs", "note_A", "note_As", "note_B"};

/* voice ranges: lowest and highest fundamental accepted (Hz) */
/* lowest notes: Soprano F#3, Alto C#3, Tenor A2, Baritone E2. The lowest note sets the latency (two of its periods),
 * so each range stops just below where that voice really sings. */
static const float VOICE_LO[4] = {184.0f, 138.0f, 110.0f, 82.0f};   /* F#3, C#3, A2, E2 (just under each) */
static const float VOICE_HI[4] = {1100.0f, 800.0f, 550.0f, 400.0f};

/* scales as 12-bit masks, bit n = n semitones above the key; option 6 is User (the hand-tapped set) */
static const int USER = 6;
static const int SCALE_MASK[6] = {
    0xFFF,                                                   /* Chromatic */
    (1 << 0) | (1 << 2) | (1 << 4) | (1 << 5) | (1 << 7) | (1 << 9) | (1 << 11), /* Major */
    (1 << 0) | (1 << 2) | (1 << 3) | (1 << 5) | (1 << 7) | (1 << 8) | (1 << 10), /* Minor */
    (1 << 0) | (1 << 2) | (1 << 3) | (1 << 5) | (1 << 7) | (1 << 8) | (1 << 11), /* Harmonic Minor */
    (1 << 0) | (1 << 2) | (1 << 4) | (1 << 7) | (1 << 9),                       /* Major Pentatonic */
    (1 << 0) | (1 << 3) | (1 << 5) | (1 << 7) | (1 << 10),                      /* Minor Pentatonic */
};

static float hann_table[HANN_N + 1];

struct Biquad {
    float b0, b1, b2, a1, a2, z1, z2;
    void lowpass(float fc, float q) {
        float w = 2.0f * (float)M_PI * fc / SR, c = cosf(w), al = sinf(w) / (2.0f * q), a0 = 1.0f + al;
        b0 = (1.0f - c) * 0.5f / a0; b1 = (1.0f - c) / a0; b2 = b0;
        a1 = -2.0f * c / a0; a2 = (1.0f - al) / a0; z1 = z2 = 0.0f;
    }
    float run(float x) {
        float y = b0 * x + z1;
        z1 = b1 * x - a1 * y + z2;
        z2 = b2 * x - a2 * y;
        return y;
    }
};

struct Tuney {
    /* parameters */
    int bypass = 0;
    int voice = 2;              /* Tenor */
    int key = 0;                /* C */
    int scale = 0;              /* Chromatic */
    float retune = 85.0f;       /* %: 100 = instant snap (hardest), 0 = slowest glide (100 ms) */
    float amount = 100.0f;      /* % */
    float humanize = 10.0f;     /* % */
    float transition = 65.0f;   /* %: how fast it moves from one note to the next. 100 = instant jump, 0 = 300 ms glide */
    float vibrato = 35.0f;      /* % of natural vibrato kept */
    float freq = 440.0f;        /* A4 reference, Hz */
    float cents = 0.0f;         /* fine tune on top of freq */
    float ref = 440.0f;         /* freq moved by cents: what "in tune" means */
    int theme = 0;              /* skin colourway, kept only so it saves with the project */
    double last_step = -1.0;    /* when a Voice/Theme arrow last stepped (s, monotonic) */
    int voice_changed = 0, theme_changed = 0;   /* an arrow stepped them: report so the screen follows */
    int notes = 0xFFF;          /* bit n: pitch class n is a target */
    int user = 0xFFF;           /* the User scale: the last hand-tapped set (absolute pitch classes); starts with every
                                 * note on, so you sing, see which keys light, and tap off the ones you don't want */
    int changed = 0;            /* notes the engine changed itself, not yet reported (mpc_engine_changed) */
    int scale_changed = 0;      /* the engine moved Scale to User itself, not yet reported */
    int signal = 0;             /* input light: 0 off, 1 hearing input, 2 locked onto a pitch */
    int signal_hold = 0;
    int sung = 0, sung_cand = -1, sung_run = 0, sung_age = 0;  /* the key lit as you sing: 0 none, 1..12 C..B */
    int sung_key = 0;           /* the same note on the range strip: 0 none, 1..49 = C2..C6 (MIDI 36..84) */
    /* the live display (light, sung key, dial note and cents) reaches the screen through the wrapper's display_rev poll
     * (vst.json HAS_DISPLAY_REV + DISPLAY_REV_NO_UPDATE): every ~100 ms, values only, no screen rebuild, so MPC's PRESET
     * menu stays open while you sing. Never through mpc_engine_changed: an option change there rebuilds the screen. */
    unsigned display_rev = 0;
    int dial_note = 0;          /* 0: nothing sung, 1..12: C..B */
    int dial_cents = 0;         /* 0: blank, 1..101: -50..+50 cents */
    int dial_touched = 0, dial_report = 0;   /* a tap on the dial moved the host's copy of a display value (bit 0 note,
                                              * 1 cents): report the engine's again (mpc_engine_changed) */

    /* detector */
    Biquad aa1, aa2;
    float det[DET_SIZE];
    float win[DET_WIN];
    int det_pos = 0, det_fill = 0, decim = 0, hop = 0;
    float energy_acc = 0.0f;

    /* pitch state */
    float period = 220.0f;      /* current period, input samples */
    int voiced = 0, unvoiced_run = 0, octave_run = 0;
    float last_midi = 0.0f;
    float center = 0.0f;        /* slow pitch centre (MIDI), for vibrato */
    int target = -1000;         /* MIDI note being corrected toward */
    float held = 0.0f;          /* seconds the target has been held */
    float shift = 0.0f;         /* applied shift, semitones */
    float shown_cents = 0.0f;
    int in_transition = 0;      /* moving to a new note: Transition sets the speed until it gets there, then Retune */

    /* PSOLA */
    int lim = 678;              /* longest period the voice range allows */
    int max_lag = MAX_LAG;      /* detector search limits and window for the voice range (decimated) */
    int min_lag = MIN_LAG;
    int det_win = DET_WIN;
    int latency = 1950;
    long long w = 0;            /* input samples written */
    double next_mark = 0.0, next_syn = 0.0;
    long long mark_pos[MARKS];
    float mark_per[MARKS];
    int mark_n = 0, mark_head = 0;
    float in_l[RING], in_r[RING], mono[RING];
    float acc_l[RING], acc_r[RING], wsum[RING];
    Biquad mlp;                 /* low-passed mono for pitch-mark placement */
    float byp_mix = 0.0f;       /* 0 = corrected, 1 = bypassed (click-free) */

};

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

static void set_voice(Tuney *p, int v)
{
    p->voice = v;
    p->lim = (int)ceilf((float)SR / VOICE_LO[v]);
    /* the least a pitch-synchronous grain allows: a grain is two periods long and centred one period back, so the
     * output must trail the input by two of the longest periods (and a little headroom) */
    p->latency = 2 * p->lim + 32;
    memset(p->in_l, 0, sizeof p->in_l); memset(p->in_r, 0, sizeof p->in_r); memset(p->mono, 0, sizeof p->mono);
    memset(p->acc_l, 0, sizeof p->acc_l); memset(p->acc_r, 0, sizeof p->acc_r); memset(p->wsum, 0, sizeof p->wsum);
    p->w = 0; p->next_mark = 0.0; p->next_syn = 0.0; p->mark_n = 0; p->mark_head = 0;
    /* the analysis window spans two of the longest periods, so its centre (lim back) lines up with the grain
     * being placed (also lim back): the correction lands on the audio it was measured on */
    p->max_lag = (int)ceilf((float)DSR / VOICE_LO[v]) + 2;
    if (p->max_lag > MAX_LAG) p->max_lag = MAX_LAG;
    p->min_lag = (int)floorf((float)DSR / VOICE_HI[v]) - 1;
    if (p->min_lag < MIN_LAG) p->min_lag = MIN_LAG;
    p->det_win = 2 * p->max_lag + 32;
    if (p->det_win > DET_WIN) p->det_win = DET_WIN;
    p->period = fminf(220.0f, (float)p->lim);
}

static int rotate12(int m, int by)
{
    by = ((by % 12) + 12) % 12;
    return ((m << by) | (m >> (12 - by))) & 0xFFF;
}

static void apply_scale(Tuney *p)
{
    int n = 0;
    if (p->scale == USER) n = p->user;
    else
        for (int i = 0; i < 12; ++i)
            if (SCALE_MASK[p->scale] & (1 << i)) n |= 1 << ((i + p->key) % 12);
    p->changed |= n ^ p->notes;
    p->notes = n;
}

/* ---------- pitch detection (YIN with parabolic interpolation) ---------- */

static float detect(Tuney *p, float *clarity)
{
    *clarity = 0.0f;
    const int W = p->det_win, L = p->max_lag;
    if (p->det_fill < W) return 0.0f;
    float *x = p->win;
    for (int i = 0; i < W; ++i) x[i] = p->det[(p->det_pos + DET_SIZE - W + i) % DET_SIZE];

    double e = 0.0;
    for (int i = 0; i < W; ++i) e += (double)x[i] * x[i];
    if (e / W < 1.0e-6) return 0.0f;          /* about -60 dBFS: silence */

    float d[MAX_LAG + 2];
    const int n = W - L - 1;
    double run = 0.0;
    d[0] = 1.0f;
    for (int lag = 1; lag <= L + 1; ++lag) {
        double s = 0.0;
        for (int i = 0; i < n; i += 2) {
            float t = x[i] - x[i + lag];
            s += t * t;
        }
        run += s;
        d[lag] = run > 1.0e-12 ? (float)(s * lag / run) : 1.0f;
    }

    const int L0 = p->min_lag;
    int best = 0;
    for (int lag = L0; lag <= L; ++lag) {
        if (d[lag] < 0.15f) {
            while (lag < L && d[lag + 1] < d[lag]) ++lag;
            best = lag;
            break;
        }
    }
    if (!best) {                                     /* no clear dip: take the global minimum if it is decent */
        float m = 1.0f;
        for (int lag = L0; lag <= L; ++lag)
            if (d[lag] < m) { m = d[lag]; best = lag; }
        if (m > 0.30f) return 0.0f;
    }

    /* octave check: a vowel whose 2nd harmonic sits on a formant dips at half the period too. If the dip at twice
     * the lag is much deeper, the real period is the longer one. */
    for (int k = 0; k < 2 && best * 2 + 1 <= L; ++k) {
        int c2 = best * 2;
        if (d[c2 + 1] < d[c2]) ++c2;
        else if (d[c2 - 1] < d[c2]) --c2;
        if (d[best] > 0.06f && d[c2] < 0.5f * d[best]) best = c2;
        else break;
    }
    if (best <= 1 || best >= L + 1) return 0.0f;

    float a = d[best - 1], b = d[best], c = d[best + 1], frac = 0.0f;
    float den = a - 2.0f * b + c;
    if (den > 1.0e-9f) frac = clampf(0.5f * (a - c) / den, -0.5f, 0.5f);
    *clarity = clampf(1.0f - b, 0.0f, 1.0f);
    return (float)DSR / ((float)best + frac);
}

static void update_pitch(Tuney *p)
{
    const float dt = (float)DET_HOP / SR;
    float rms = sqrtf(p->energy_acc / DET_HOP);
    p->energy_acc = 0.0f;
    float clarity = 0.0f;
    float hz = detect(p, &clarity);
    bool ok = hz > 0.0f && hz >= VOICE_LO[p->voice] && hz <= VOICE_HI[p->voice];

    float want = 0.0f;                               /* desired shift in semitones */
    if (ok && p->voiced) {                           /* a sudden octave jump must repeat before it's believed */
        float jump = fabsf(69.0f + 12.0f * log2f(hz / p->ref) - p->last_midi);
        if (jump > 10.5f && jump < 13.5f && ++p->octave_run < 5) ok = false, hz = 0.0f;
        else p->octave_run = 0;
    }
    if (ok) {
        p->unvoiced_run = 0;
        p->voiced = 1;
        p->period = clampf((float)SR / hz, 20.0f, (float)p->lim);
        float midi = 69.0f + 12.0f * log2f(hz / p->ref);
        p->last_midi = midi;
        {   /* the sung note, for the keys and the range strip: steady for ~6 ms, at most ~20 changes a second */
            int m = (int)lrintf(midi);
            if (m == p->sung_cand) ++p->sung_run; else { p->sung_cand = m; p->sung_run = 1; }
            int pc = (m % 12 + 12) % 12 + 1, key = m >= 36 && m <= 84 ? m - 35 : 0;
            if ((pc != p->sung || key != p->sung_key) && p->sung_run >= 2 && p->sung_age >= 17) {
                p->sung = pc; p->sung_key = key; p->sung_age = 0; ++p->display_rev;
            }
        }

        /* slow centre follows the note, not the vibrato; a jump of a semitone is a new note */
        if (fabsf(midi - p->center) > 1.0f) p->center = midi;
        else p->center += (midi - p->center) * (1.0f - expf(-dt / 0.12f));
        float ref = midi + (p->center - midi) * (p->vibrato / 100.0f);

        /* nearest active note, with a little hysteresis so it doesn't flicker between two */
        int best = -1000;
        float bd = 1.0e9f;
        int base = (int)lrintf(ref);
        for (int k = -12; k <= 12; ++k) {
            int m = base + k;
            if (!(p->notes & (1 << (((m % 12) + 12) % 12)))) continue;
            float dd = fabsf(ref - m);
            if (dd < bd) { bd = dd; best = m; }
        }
        if (best > -1000) {
            bool keep = p->target > -1000 && (p->notes & (1 << (((p->target % 12) + 12) % 12))) &&
                        fabsf(ref - p->target) < bd + 0.15f;
            if (keep) best = p->target;
            if (best != p->target) { p->target = best; p->held = 0.0f; p->in_transition = 1; }
            else p->held += dt;
            want = (best - ref) * (p->amount / 100.0f);
            p->shown_cents = (midi - best) * 100.0f;
        } else {
            p->target = -1000;
        }
    } else if (++p->unvoiced_run >= 6) {             /* ~17 ms of no pitch: let go */
        p->voiced = 0;
        p->target = -1000;
        p->held = 0.0f;
    }

    /* retune: how fast the shift moves to what it wants; humanize relaxes it on held notes */
    float tau;
    if (p->voiced && p->target > -1000) {
        float sustain = clampf((p->held - 0.15f) / 0.25f, 0.0f, 1.0f);
        /* humanize: long notes loosen a little, growing with the knob (100 lets about half a 5-6 Hz wobble through) */
        float hu = p->humanize / 100.0f;
        tau = (100.0f - p->retune) / 1000.0f + 0.022f * hu * sqrtf(hu) * sustain;
        if (p->in_transition) {                      /* a new note: Transition's speed until it lands (or 0.6 s) */
            if (fabsf(want - p->shift) < 0.1f || p->held > 0.6f) p->in_transition = 0;
            else tau = (100.0f - p->transition) * 0.003f;
        }
    } else {
        want = 0.0f;
        tau = 0.03f;
        p->in_transition = 0;
    }
    if (tau < 0.0005f) p->shift = want;
    else p->shift += (want - p->shift) * (1.0f - expf(-dt / tau));

    /* input light: up at once, down only after ~150 ms, so it doesn't flicker between syllables (and the screen
     * redraws only when it actually changes) */
    int want_sig = p->voiced ? 2 : (rms > 0.0032f ? 1 : 0);   /* pitch found (corrected or not) / input / silence */
    if (want_sig > p->signal) { p->signal = want_sig; p->signal_hold = 0; ++p->display_rev; }
    else if (want_sig < p->signal) {
        if (++p->signal_hold >= 52) { p->signal = want_sig; p->signal_hold = 0; ++p->display_rev; }
    } else p->signal_hold = 0;
    if (p->sung_age < 1000) ++p->sung_age;
    if (p->signal < 2 && (p->sung || p->sung_key)) { p->sung = p->sung_key = 0; p->sung_cand = -1; ++p->display_rev; }   /* dark with the light */

    /* the dial: what's being sung -- the note it lands on when a note is switched on near it, else the nearest note (no
     * notes switched on, e.g. an empty User scale: detection only, nothing is corrected). It holds through the short
     * gaps between syllables and clears with the light; the cents move only by 2 or more on the same note, so a held
     * note doesn't repaint the screen all the time (MPC's screen thread pays for every repaint) */
    int dn = p->dial_note, dc = p->dial_cents;
    if (p->voiced) {
        int shown = p->target > -1000 ? p->target : (int)lrintf(p->last_midi);
        float off = p->target > -1000 ? p->shown_cents : (p->last_midi - shown) * 100.0f;
        int n = ((shown % 12) + 12) % 12 + 1;
        int c = (int)clampf((float)lrintf(off), -50, 50) + 51;
        if (n != dn || dc == 0) { dn = n; dc = c; }
        else if (abs(c - dc) >= 2) dc = c;
    } else if (p->signal < 2) dn = 0, dc = 0;
    if (p->dial_touched) { p->dial_report |= p->dial_touched; p->dial_touched = 0; }   /* the host's copy moved: resend */
    if (dn != p->dial_note || dc != p->dial_cents) { p->dial_note = dn; p->dial_cents = dc; ++p->display_rev; }
}

/* ---------- TD-PSOLA ---------- */

static void make_marks(Tuney *p)
{
    for (;;) {
        float T = p->voiced ? p->period : fminf(220.0f, (float)p->lim);
        long long pred = (long long)llround(p->next_mark);
        int span = p->voiced ? (int)(T * 0.25f) : 0;
        if (pred + span >= p->w) return;
        long long at = pred;
        if (span > 0) {                              /* snap to the waveform's peak: pitch-synchronous grains */
            float m = -1.0e9f;
            for (long long q = pred - span; q <= pred + span; ++q) {
                float v = p->mono[q & RMASK];
                if (v > m) { m = v; at = q; }
            }
            if (p->mark_n) {
                long long prev = p->mark_pos[(p->mark_head + MARKS - 1) & (MARKS - 1)];
                if (at - prev < (long long)(T * 0.6f)) at = pred;
            }
        }
        p->mark_pos[p->mark_head] = at;
        p->mark_per[p->mark_head] = T;
        p->mark_head = (p->mark_head + 1) & (MARKS - 1);
        if (p->mark_n < MARKS) ++p->mark_n;
        p->next_mark = (at == pred ? p->next_mark : (double)at) + (double)T;
    }
}

static void place_grains(Tuney *p)
{
    const float ratio = exp2f(clampf(p->shift, -12.0f, 12.0f) / 12.0f);
    while (p->next_syn <= (double)(p->w - p->lim)) {
        long long s = (long long)llround(p->next_syn);
        /* the analysis mark nearest s whose grain is fully written */
        int bi = -1;
        long long bd = 1LL << 60;
        for (int k = 0; k < p->mark_n; ++k) {
            int i = (p->mark_head + MARKS - 1 - k) & (MARKS - 1);
            long long a = p->mark_pos[i];
            if (a + (long long)p->mark_per[i] > p->w) continue;
            long long dd = a > s ? a - s : s - a;
            if (dd < bd) { bd = dd; bi = i; }
            if (a < s - 2 * p->lim) break;
        }
        float T = bi >= 0 ? p->mark_per[bi] : fminf(220.0f, (float)p->lim);
        long long a = bi >= 0 ? p->mark_pos[bi] : s;
        if (bi >= 0 && bi != ((p->mark_head + MARKS - 1) & (MARKS - 1))) {
            /* the real local period is the distance to the next mark (marks sit on waveform peaks), not the
             * detector's figure, which trails the voice during vibrato and slides */
            float sp = (float)(p->mark_pos[(bi + 1) & (MARKS - 1)] - a);
            if (sp > 0.7f * T && sp < 1.4f * T) T = sp;
        }
        int h = (int)T;
        if (h < 8) h = 8;
        float scale = (float)HANN_N / (2.0f * h);
        for (int j = -h; j < h; ++j) {
            float win = hann_table[(int)((j + h) * scale)];
            int src = (int)((a + j) & RMASK), dst = (int)((s + j) & RMASK);
            p->acc_l[dst] += p->in_l[src] * win;
            p->acc_r[dst] += p->in_r[src] * win;
            p->wsum[dst] += win;
        }
        double step = (double)T / ratio;
        if (step < 8.0) step = 8.0;
        /* with (almost) no shift, pull the synthesis marks onto the analysis marks: grains then land where they were
         * taken from and the output is the input exactly (the window sum is normalised away) */
        float c = fabsf(p->shift) * 100.0f;          /* cents */
        if (c < 0.5f && bi >= 0) step -= (p->next_syn - (double)a) * 0.02 * (1.0 - c / 0.5);   /* gentle: no pitch blip */
        p->next_syn += step;
    }
}

/* ---------- engine interface ---------- */

static void *create(const char *)
{
    if (hann_table[HANN_N / 2] == 0.0f)
        for (int i = 0; i <= HANN_N; ++i) hann_table[i] = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * i / HANN_N);
    Tuney *p = new (std::nothrow) Tuney();
    if (!p) return NULL;
    memset(p->det, 0, sizeof p->det);
    p->aa1.lowpass(3000.0f, 0.5412f);                /* 4th-order Butterworth before the 2:1 decimation */
    p->aa2.lowpass(3000.0f, 1.3066f);
    p->mlp.lowpass(1200.0f, 0.7071f);
    set_voice(p, p->voice);
    return p;
}

static void destroy(void *inst) { delete static_cast<Tuney *>(inst); }

static int note_index(const char *key)
{
    for (int i = 0; i < 12; ++i)
        if (!strcmp(key, NOTE_KEYS[i])) return i;
    return -1;
}

static void set_param(void *inst, const char *key, const char *val)
{
    Tuney *p = static_cast<Tuney *>(inst);
    if (!p || !key || !val) return;

    if (!strcmp(key, "state")) {
        /* "v6 bypass voice key scale retune amount humanize vibrato notes user freq cents theme transition"
         * (v5: no transition; v4: retune in ms, 0 = instant; v3: no theme, v2: no freq/cents, v1: no user either) */
        int b, v, k, s, n, u = -1, th = 0;
        float r, a, h, vb, fq = 440.0f, ct = 0.0f, tr = -1.0f;
        int got = sscanf(val, "v6 %d %d %d %d %f %f %f %f %d %d %f %f %d %f", &b, &v, &k, &s, &r, &a, &h, &vb, &n, &u, &fq, &ct, &th, &tr);
        if (got == 14) got = 13;
        else { tr = -1.0f; got = sscanf(val, "v5 %d %d %d %d %f %f %f %f %d %d %f %f %d", &b, &v, &k, &s, &r, &a, &h, &vb, &n, &u, &fq, &ct, &th); }
        bool retune_ms = got != 13;
        if (retune_ms) got = sscanf(val, "v4 %d %d %d %d %f %f %f %f %d %d %f %f %d", &b, &v, &k, &s, &r, &a, &h, &vb, &n, &u, &fq, &ct, &th);
        if (got == 13) got = 12;
        else got = sscanf(val, "v3 %d %d %d %d %f %f %f %f %d %d %f %f", &b, &v, &k, &s, &r, &a, &h, &vb, &n, &u, &fq, &ct);
        if (got == 12) got = 10;
        else got = sscanf(val, "v2 %d %d %d %d %f %f %f %f %d %d", &b, &v, &k, &s, &r, &a, &h, &vb, &n, &u);
        if (got != 10) got = sscanf(val, "v1 %d %d %d %d %f %f %f %f %d", &b, &v, &k, &s, &r, &a, &h, &vb, &n) == 9 ? 10 : 0;
        if (got == 10) {
            p->bypass = b ? 1 : 0;
            if (v >= 0 && v <= 3 && v != p->voice) set_voice(p, v);
            p->key = k >= 0 && k <= 11 ? k : 0;
            p->scale = s >= 0 && s <= USER ? s : 0;
            p->user = u >= 0 ? (u & 0xFFF) : (n & 0xFFF);
            p->retune = clampf(retune_ms ? 100.0f - r : r, 0, 100); p->amount = clampf(a, 0, 100);
            /* before Transition, Retune also set the speed between notes: keep that sound */
            p->transition = tr >= 0.0f ? clampf(tr, 0, 100) : 100.0f - (100.0f - p->retune) / 3.0f;
            p->humanize = clampf(h, 0, 100); p->vibrato = clampf(vb, 0, 100);
            p->freq = clampf(fq, 415, 465); p->cents = clampf(ct, -50, 50);
            p->theme = th >= 0 && th <= 3 ? th : 0;
            p->ref = p->freq * exp2f(p->cents / 1200.0f);
            p->changed |= (n & 0xFFF) ^ p->notes;    /* saved notes win over the scale's: they may be hand-edited */
            p->notes = n & 0xFFF;
        }
        return;
    }

    float f = strtof(val, NULL);
    int i = (int)lrintf(f);
    /* the Voice and Theme arrows: one step per press, at most ~3 a second, so a press the screen repeats (or a wheel
     * turn while an arrow has focus) can't race through the list and skip the option you want */
    if (!strncmp(key, "voice_", 6) || !strncmp(key, "theme_", 6)) {
        bool next = !strcmp(key + 6, "next");
        if (!next && strcmp(key + 6, "prev")) return;
        if (f < 0.5f) return;
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        double now = ts.tv_sec + ts.tv_nsec * 1e-9;
        if (p->last_step >= 0.0 && now - p->last_step < 0.3) return;
        p->last_step = now;
        int d = next ? 1 : -1;
        if (key[0] == 'v') { set_voice(p, (p->voice + d + 4) % 4); p->voice_changed = 1; }
        else { p->theme = (p->theme + d + 4) % 4; p->theme_changed = 1; }
        return;
    }
    if (!strcmp(key, "bypass")) p->bypass = i ? 1 : 0;
    else if (!strcmp(key, "theme")) p->theme = (int)clampf((float)i, 0, 3);
    else if (!strcmp(key, "signal") || !strcmp(key, "sung") || !strcmp(key, "sung_key")) {}   /* display only: the engine sets them */
    else if (!strcmp(key, "dial_note")) p->dial_touched |= 1;      /* display only: a tap on the dial; put it back */
    else if (!strcmp(key, "dial_cents")) p->dial_touched |= 2;
    else if (!strcmp(key, "voice")) { i = (int)clampf((float)i, 0, 3); if (i != p->voice) set_voice(p, i); }
    else if (!strcmp(key, "key")) {
        i = (int)clampf((float)i, 0, 11);
        if (i != p->key) {
            if (p->scale == USER) p->user = rotate12(p->user, i - p->key);   /* User keeps its shape in the new key */
            p->key = i;
            apply_scale(p);
        }
    }
    else if (!strcmp(key, "scale")) {
        i = (int)clampf((float)i, 0, USER);
        if (i != p->scale) { p->scale = i; p->scale_changed = 0; apply_scale(p); }
    }
    else if (!strcmp(key, "retune")) p->retune = clampf(f, 0, 100);
    else if (!strcmp(key, "amount")) p->amount = clampf(f, 0, 100);
    else if (!strcmp(key, "humanize")) p->humanize = clampf(f, 0, 100);
    else if (!strcmp(key, "transition")) p->transition = clampf(f, 0, 100);
    else if (!strcmp(key, "vibrato")) p->vibrato = clampf(f, 0, 100);
    else if (!strcmp(key, "freq") || !strcmp(key, "cents")) {
        if (key[0] == 'f') p->freq = clampf(f, 415, 465);
        else p->cents = clampf(f, -50, 50);
        p->ref = p->freq * exp2f(p->cents / 1200.0f);
    }
    else {
        int n = note_index(key);
        if (n >= 0) {
            int was = p->notes;
            if (i) p->notes |= 1 << n;
            else p->notes &= ~(1 << n);
            p->changed &= ~(1 << n);                 /* the host already knows */
            if (p->notes != was) {                   /* a tap makes this set the User scale */
                p->user = p->notes;
                if (p->scale != USER) { p->scale = USER; p->scale_changed = 1; }
            }
        }
    }
}

static int get_param(void *inst, const char *key, char *buf, int len)
{
    Tuney *p = static_cast<Tuney *>(inst);
    if (!p || !key || !buf || len <= 0) return 0;
    if (!strcmp(key, "display_rev")) return snprintf(buf, (size_t)len, "%u", p->display_rev);
    /* the dial's pictures (filmstrip meters): a third of a step over the frame, so it lands on that frame whether MPC
     * rounds or truncates value x (frames - 1) */
    if (!strcmp(key, "dial_note")) return snprintf(buf, (size_t)len, "%d.3", p->dial_note);
    if (!strcmp(key, "dial_cents")) return snprintf(buf, (size_t)len, "%d.3", p->dial_cents);
    if (!strcmp(key, "state"))
        return snprintf(buf, (size_t)len, "v6 %d %d %d %d %g %g %g %g %d %d %g %g %d %g", p->bypass, p->voice, p->key, p->scale,
                        p->retune, p->amount, p->humanize, p->vibrato, p->notes, p->user, p->freq, p->cents, p->theme,
                        p->transition);
    if (!strcmp(key, "latency")) return snprintf(buf, (size_t)len, "%d", p->latency);

    float v;
    if (!strcmp(key, "bypass")) v = (float)p->bypass;
    else if (!strcmp(key, "theme")) v = (float)p->theme;
    else if (!strcmp(key, "signal")) v = (float)p->signal;
    else if (!strcmp(key, "sung")) v = (float)p->sung;
    else if (!strcmp(key, "sung_key")) v = (float)p->sung_key;
    else if (!strcmp(key, "voice")) v = (float)p->voice;
    else if (!strcmp(key, "key")) v = (float)p->key;
    else if (!strcmp(key, "scale")) v = (float)p->scale;
    else if (!strcmp(key, "retune")) v = p->retune;
    else if (!strcmp(key, "amount")) v = p->amount;
    else if (!strcmp(key, "humanize")) v = p->humanize;
    else if (!strcmp(key, "transition")) v = p->transition;
    else if (!strcmp(key, "vibrato")) v = p->vibrato;
    else if (!strcmp(key, "freq")) v = p->freq;
    else if (!strcmp(key, "cents")) v = p->cents;
    else {
        int n = note_index(key);
        if (n < 0) return 0;
        v = (p->notes >> n) & 1 ? 1.0f : 0.0f;
    }
    return snprintf(buf, (size_t)len, "%g", v);
}

/* What the engine switched itself, so the screen follows: notes (a Key or Scale change), Scale (a tap -> User), and the
 * dial's values after a tap on them. The live display goes through display_rev instead (see Tuney::display_rev). */
extern "C" int mpc_engine_changed(void *inst, char *key, int len)
{
    Tuney *p = static_cast<Tuney *>(inst);
    if (!p) return 0;
    if (p->dial_report) {                            /* numbers, not options: reported without a screen rebuild */
        int b = p->dial_report & 1 ? 1 : 2;
        p->dial_report &= ~b;
        snprintf(key, (size_t)len, b == 1 ? "dial_note" : "dial_cents");
        return 1;
    }
    if (p->voice_changed || p->theme_changed) {
        bool v = p->voice_changed;
        if (v) p->voice_changed = 0; else p->theme_changed = 0;
        snprintf(key, (size_t)len, v ? "voice" : "theme");
        return 1;
    }
    if (p->scale_changed) {
        p->scale_changed = 0;
        snprintf(key, (size_t)len, "scale");
        return 1;
    }
    if (!p->changed) return 0;
    for (int i = 0; i < 12; ++i)
        if (p->changed & (1 << i)) {
            p->changed &= ~(1 << i);
            snprintf(key, (size_t)len, "%s", NOTE_KEYS[i]);
            return 1;
        }
    return 0;
}

static void midi(void *, const uint8_t *, int) {}

static void render(void *, int16_t *out_lr, int frames)
{
    if (out_lr && frames > 0) memset(out_lr, 0, (size_t)frames * 2 * sizeof(int16_t));
}

static int16_t to_s16(float x)
{
    x *= 32768.0f;
    return x >= 32767.0f ? 32767 : x <= -32768.0f ? -32768 : (int16_t)lrintf(x);
}

static void process(void *inst, const int16_t *in_lr, int16_t *out_lr, int frames)
{
    Tuney *p = static_cast<Tuney *>(inst);
    if (!p || !in_lr || !out_lr || frames <= 0) return;

    for (int i = 0; i < frames; ++i) {
        float l = in_lr[2 * i] / 32768.0f, r = in_lr[2 * i + 1] / 32768.0f, m = 0.5f * (l + r);
        p->energy_acc += m * m;
        int wi = (int)(p->w & RMASK);
        p->in_l[wi] = l;
        p->in_r[wi] = r;
        p->mono[wi] = p->mlp.run(m);
        float a = p->aa2.run(p->aa1.run(m));
        if ((p->decim ^= 1) == 0) {
            p->det[p->det_pos] = a;
            p->det_pos = (p->det_pos + 1) % DET_SIZE;
            if (p->det_fill < DET_SIZE) ++p->det_fill;
        }
        ++p->w;
        if (++p->hop >= DET_HOP) { p->hop = 0; update_pitch(p); }
    }

    make_marks(p);
    place_grains(p);

    /* read the finished output, `latency` samples behind the input */
    const float byp_target = p->bypass ? 1.0f : 0.0f, byp_step = 1.0f / 441.0f;   /* 10 ms crossfade */
    for (int i = 0; i < frames; ++i) {
        long long t = p->w - frames + i - p->latency;
        int ri = (int)(t & RMASK);
        float ws = p->wsum[ri];
        float g = ws > 0.25f ? 1.0f / ws : 1.0f;
        float wl = p->acc_l[ri] * g, wr = p->acc_r[ri] * g;
        p->acc_l[ri] = p->acc_r[ri] = p->wsum[ri] = 0.0f;
        if (t < 0) wl = wr = 0.0f;
        if (p->byp_mix != byp_target)
            p->byp_mix = byp_target > p->byp_mix ? fminf(byp_target, p->byp_mix + byp_step)
                                                 : fmaxf(byp_target, p->byp_mix - byp_step);
        float dl = t < 0 ? 0.0f : p->in_l[ri], dr = t < 0 ? 0.0f : p->in_r[ri];
        out_lr[2 * i] = to_s16(wl + (dl - wl) * p->byp_mix);
        out_lr[2 * i + 1] = to_s16(wr + (dr - wr) * p->byp_mix);
    }
}

static const mpc_engine_t engine = {create, destroy, midi, set_param, get_param, render, process};

extern "C" const mpc_engine_t *mpc_engine(void) { return &engine; }
