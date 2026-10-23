/* Key/Scale -> note toggles, a tap on one note, what the engine reports to the host, and save/restore.
 *   gcc -I<mpc-vst-plugins>/wrapper tests/test_notes.c engine.o -lstdc++ -lm && ./a.out */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
#include "engine.h"

int mpc_engine_changed(void *inst, char *key, int len);
static int fails;
#define CHECK(c, ...) do { int ok_ = (c); printf("%-4s ", ok_ ? "ok" : "FAIL"); printf(__VA_ARGS__); printf("\n"); if (!ok_) fails++; } while (0)

static const char *K[12] = {"note_C", "note_Cs", "note_D", "note_Ds", "note_E", "note_F",
                            "note_Fs", "note_G", "note_Gs", "note_A", "note_As", "note_B"};

static int mask(const mpc_engine_t *e, void *p)
{
    int m = 0; char b[16];
    for (int i = 0; i < 12; ++i) { e->get_param(p, K[i], b, sizeof b); if (b[0] == '1') m |= 1 << i; }
    return m;
}

static int drain(void *p)
{
    char k[32]; int n = 0;
    while (mpc_engine_changed(p, k, sizeof k) > 0) n++;
    return n;
}

int main(void)
{
    const mpc_engine_t *e = mpc_engine();
    void *p = e->create(NULL);
    CHECK(mask(e, p) == 0xFFF, "default: all 12 notes on (Chromatic)");
    {   /* a fresh User scale is a blank slate */
        void *f = e->create(NULL);
        e->set_param(f, "scale", "6");
        CHECK(mask(e, f) == 0xFFF, "picking User on a fresh instance starts with every note on (0x%03X)", mask(e, f));
        e->destroy(f);
    }
    CHECK(drain(p) == 0, "nothing to report at start");

    e->set_param(p, "scale", "1");                      /* C major: C D E F G A B */
    CHECK(mask(e, p) == 0xAB5, "C Major lights C D E F G A B (0x%03X)", mask(e, p));
    CHECK(drain(p) == 5, "the 5 notes that went off are reported to the host");

    e->set_param(p, "key", "9");                        /* A major: A B C# D E F# G# */
    CHECK(mask(e, p) == ((1<<9)|(1<<11)|(1<<1)|(1<<2)|(1<<4)|(1<<6)|(1<<8)), "A Major lights A B C# D E F# G# (0x%03X)", mask(e, p));
    CHECK(drain(p) == 6, "C->A major changes 6 notes");

    char k[32], v[16];
    e->set_param(p, "note_G", "1");                     /* the user adds G by hand */
    CHECK(mask(e, p) & (1 << 7), "a tap on G turns it on");
    CHECK(mpc_engine_changed(p, k, sizeof k) > 0 && !strcmp(k, "scale"), "the tap moves Scale to User, reported to the host (%s)", k);
    e->get_param(p, "scale", v, sizeof v);
    CHECK(!strcmp(v, "6"), "Scale now reads User");
    CHECK(drain(p) == 0, "the tapped note itself is not echoed back");
    int mine = mask(e, p);

    e->set_param(p, "key", "9");                        /* same key again: no rewrite */
    CHECK(mask(e, p) == mine, "re-picking the same key keeps the hand-edited set");

    e->set_param(p, "scale", "1");                      /* Major again ... */
    CHECK(mask(e, p) == ((1<<9)|(1<<11)|(1<<1)|(1<<2)|(1<<4)|(1<<6)|(1<<8)), "picking Major relights A major");
    drain(p);
    e->set_param(p, "scale", "6");                      /* ... and back to User */
    CHECK(mask(e, p) == mine, "picking User brings the hand-edited set back");

    e->set_param(p, "key", "11");                       /* A -> B: User moves up a whole tone */
    int moved = ((mine << 2) | (mine >> 10)) & 0xFFF;
    CHECK(mask(e, p) == moved, "changing Key on User transposes the set (0x%03X)", mask(e, p));
    e->set_param(p, "key", "9");
    CHECK(mask(e, p) == mine, "and back again");

    e->set_param(p, "note_C", "1");                     /* tapping while on User edits User */
    e->set_param(p, "note_C", "0");
    CHECK(mask(e, p) == mine, "taps on User edit it in place");
    drain(p);

    char st[128]; e->get_param(p, "state", st, sizeof st);
    void *q = e->create(NULL);
    e->set_param(q, "state", st);
    CHECK(mask(e, q) == mask(e, p), "save/restore keeps the notes (%s)", st);
    char a[16], b[16];
    e->get_param(q, "scale", a, sizeof a); e->get_param(q, "key", b, sizeof b);
    CHECK(!strcmp(a, "6") && !strcmp(b, "9"), "save/restore keeps key and scale");
    e->set_param(q, "scale", "0"); e->set_param(q, "scale", "6");
    CHECK(mask(e, q) == mine, "the User set survives save/restore");
    e->set_param(q, "state", "garbage");
    CHECK(mask(e, q) == mine, "a bad state string changes nothing");
    void *r = e->create(NULL);
    e->set_param(r, "state", "v1 0 2 0 1 25 100 0 50 2741");
    CHECK(mask(e, r) == 2741, "an older (v1) saved state still loads");
    e->destroy(r);

    /* input light: silence -> off, a sung A3 -> locked (2), noise -> input (1), silence again -> off after a hold */
    {
        void *s = e->create(NULL);
        int16_t in[256], out[256];
        char sv[16];
        double ph = 0.0;
        unsigned rnd = 1;
        int seen_lock = 0, reported = 0;
        for (int blk = 0; blk < 1200; ++blk) {
            for (int i = 0; i < 128; ++i) {
                float v = 0.0f;
                if (blk >= 100 && blk < 500) { ph += 220.0 / 44100.0; double fr = ph - (long)ph; v = fr < .6 ? (float)(sin(3.14159265 * fr / .6) * sin(3.14159265 * fr / .6) - .3) : -.3f; }
                else if (blk >= 500 && blk < 800) { rnd = rnd * 1103515245u + 12345u; v = ((rnd >> 16) & 0x7FFF) / 32768.0f - .5f; v *= .2f; }
                in[2 * i] = in[2 * i + 1] = (int16_t)(v * 20000);
            }
            e->process(s, in, out, 128);
            char kk[32];
            while (mpc_engine_changed(s, kk, sizeof kk) > 0) reported++;
            e->get_param(s, "signal", sv, sizeof sv);
            if (blk == 90) CHECK(!strcmp(sv, "0"), "light off in silence");
            if (blk >= 200 && blk < 500 && !strcmp(sv, "2")) seen_lock = 1;
            if (blk == 790) CHECK(!strcmp(sv, "1"), "light shows input on unpitched noise (%s)", sv);
            if (blk == 1150) CHECK(!strcmp(sv, "0"), "light goes off again in silence (%s)", sv);
        }
        CHECK(seen_lock, "light shows a locked pitch on a sung A3");
        CHECK(reported == 0, "singing never asks MPC for a screen rebuild (it closes the PRESET menu): %d reports", reported);
        e->destroy(s);
    }

    /* sung note: lights the key being sung (1..12 = C..B), dark in silence; reported only on change */
    {
        void *s = e->create(NULL);
        int16_t in[256], out[256];
        char sv[16];
        double ph = 0.0;
        int saw_a = 0, saw_c = 0, reports = 0, polls_moved = 0, held_moved = 0, dial_a = 0;
        char rev[16] = "", last_rev[16] = "";
        for (int blk = 0; blk < 1100; ++blk) {
            double f = blk < 450 ? 220.0 : 261.63;            /* A3, then C4 */
            for (int i = 0; i < 128; ++i) {
                float v = 0.0f;
                if (blk >= 50 && blk < 800) { ph += f / 44100.0; double fr = ph - (long)ph; v = fr < .6 ? (float)(sin(3.14159265 * fr / .6) * sin(3.14159265 * fr / .6) - .3) : -.3f; }
                in[2 * i] = in[2 * i + 1] = (int16_t)(v * 20000);
            }
            e->process(s, in, out, 128);
            char kk[32];
            while (mpc_engine_changed(s, kk, sizeof kk) > 0) reports++;
            e->get_param(s, "sung", sv, sizeof sv);
            if (blk % 34 == 0) {                              /* the wrapper's display_rev poll: every ~100 ms */
                e->get_param(s, "display_rev", rev, sizeof rev);
                if (strcmp(rev, last_rev)) { polls_moved++; if (blk > 250 && blk < 440) held_moved++; }
                snprintf(last_rev, sizeof last_rev, "%s", rev);
            }
            if (blk == 400) {
                char dn[16], dc[16];
                e->get_param(s, "dial_note", dn, sizeof dn); e->get_param(s, "dial_cents", dc, sizeof dc);
                dial_a = !strcmp(dn, "10.3") && abs(atoi(dc) - 51) <= 3;
                CHECK(dial_a, "the dial shows A, about 0 cents, on a sung A3 (note %s, cents %s)", dn, dc);
            }
            if (blk > 200 && blk < 440 && !strcmp(sv, "10")) saw_a = 1;
            if (blk == 400 || blk == 780) {
                char sk[16]; e->get_param(s, "sung_key", sk, sizeof sk);
                CHECK(!strcmp(sk, blk == 400 ? "22" : "25"), "the range strip lights the exact key (%s: %s)", blk == 400 ? "A3 = 22" : "C4 = 25", sk);
            }
            if (blk > 600 && blk < 790 && !strcmp(sv, "1")) saw_c = 1;
            if (blk == 1090) CHECK(!strcmp(sv, "0"), "sung key goes dark after the voice stops (%s)", sv);
        }
        CHECK(saw_a, "singing A3 lights the A key");
        CHECK(saw_c, "moving to C4 lights the C key");
        CHECK(reports == 0, "sung key and dial changes never ask for a screen rebuild (%d reports)", reports);
        CHECK(polls_moved >= 3 && polls_moved <= 10, "the live display moves only when something changes (%d of 32 polls)", polls_moved);
        CHECK(held_moved == 0, "a held note leaves the screen still (%d polls moved)", held_moved);
        e->destroy(s);
    }
    /* detection never depends on the notes switched on: an empty User scale still shows the sung note, the light and the glow */
    {
        void *s = e->create(NULL);
        for (int i = 0; i < 12; ++i) e->set_param(s, K[i], "0");                     /* no notes at all */
        int16_t in[256], out[256];
        char nv[16], sg[16], sv[16];
        double ph = 0.0;
        for (int blk = 0; blk < 400; ++blk) {
            for (int i = 0; i < 128; ++i) { ph += 220.0 / 44100.0; double fr = ph - (long)ph; float v = fr < .6 ? (float)(sin(3.14159265 * fr / .6) * sin(3.14159265 * fr / .6) - .3) : -.3f; in[2 * i] = in[2 * i + 1] = (int16_t)(v * 20000); }
            e->process(s, in, out, 128);
            char kk[32]; while (mpc_engine_changed(s, kk, sizeof kk) > 0) {}
        }
        e->get_param(s, "dial_note", nv, sizeof nv); e->get_param(s, "signal", sg, sizeof sg); e->get_param(s, "sung", sv, sizeof sv);
        char sc[16]; e->get_param(s, "scale", sc, sizeof sc);
        CHECK(!strcmp(nv, "10.3"), "no notes switched on (User %s): the dial still reads the sung note (%s)", sc, nv);
        CHECK(!strcmp(sg, "2"), "no notes switched on: the light still shows a found pitch (%s)", sg);
        CHECK(!strcmp(sv, "10"), "no notes switched on: the A key still glows (%s)", sv);
        /* a tap on the dial's picture moves the host's copy only: the engine reports its own value back */
        e->set_param(s, "dial_note", "3");
        e->process(s, in, out, 128);
        char kk[32] = "", nv2[16];
        int got = mpc_engine_changed(s, kk, sizeof kk);
        e->get_param(s, "dial_note", nv2, sizeof nv2);
        CHECK(got > 0 && !strcmp(kk, "dial_note") && !strcmp(nv2, "10.3"), "a tap on the dial is undone (%s -> %s)", kk, nv2);
        e->destroy(s);
    }
    /* the User preset (scale User, then every note on, in that order) ends on User with all 12, whatever was tapped before */
    {
        void *s = e->create(NULL);
        e->set_param(s, "scale", "1");
        e->set_param(s, "note_D", "0");                                   /* a tapped set: Major without D */
        e->set_param(s, "scale", "0");                                    /* back to Chromatic */
        e->set_param(s, "scale", "6");
        for (int i = 0; i < 12; ++i) e->set_param(s, K[i], "1");
        char sc[16]; e->get_param(s, "scale", sc, sizeof sc);
        CHECK(mask(e, s) == 0xFFF && !strcmp(sc, "6"), "User preset: all 12 notes on, Scale User (0x%03X, %s)", mask(e, s), sc);
        e->set_param(s, "scale", "1"); e->set_param(s, "scale", "6");
        CHECK(mask(e, s) == 0xFFF, "and User keeps all 12 after switching away and back (0x%03X)", mask(e, s));
        e->destroy(s);
    }
    /* Voice / Theme arrows: one step per press, a repeat within 0.3 s is ignored, and the change is reported */
    {
        void *s = e->create(NULL);
        char v[16], k[32];
        e->set_param(s, "voice_next", "1"); e->set_param(s, "voice_next", "0"); e->set_param(s, "voice_next", "1");
        e->get_param(s, "voice", v, sizeof v);
        CHECK(!strcmp(v, "3"), "a fast double press steps Voice once (Tenor -> Baritone: %s)", v);
        int rep = 0; while (mpc_engine_changed(s, k, sizeof k) > 0) if (!strcmp(k, "voice")) rep++;
        CHECK(rep == 1, "the Voice step is reported to the screen (%d)", rep);
        struct timespec ts = {0, 350000000}; nanosleep(&ts, NULL);
        e->set_param(s, "voice_next", "1");
        e->get_param(s, "voice", v, sizeof v);
        CHECK(!strcmp(v, "0"), "a later press steps again and wraps (Baritone -> Soprano: %s)", v);
        nanosleep(&ts, NULL);
        e->set_param(s, "theme_prev", "1");
        e->get_param(s, "theme", v, sizeof v);
        CHECK(!strcmp(v, "3"), "Theme < wraps from Grey to Silver (%s)", v);
        e->destroy(s);
    }
    /* Transition: saved and restored; a project from before it keeps its old note-to-note speed (Retune's) */
    {
        void *s = e->create(NULL);
        char tv[16], st[128];
        e->set_param(s, "state", "v5 0 2 0 0 100 100 0 0 4095 4095 440 0 0");
        e->get_param(s, "transition", tv, sizeof tv);
        CHECK(!strcmp(tv, "100"), "a 1.2.0 project at Retune 100 keeps instant note changes (Transition %s)", tv);
        e->set_param(s, "transition", "35");
        e->get_param(s, "state", st, sizeof st);
        void *t = e->create(NULL);
        e->set_param(t, "state", st);
        e->get_param(t, "transition", tv, sizeof tv);
        CHECK(!strcmp(tv, "35"), "Transition saves and reloads (%s, %s)", tv, st);
        e->destroy(t);
        e->destroy(s);
    }
    /* retune is a percentage now (100 = instant); projects saved with ms (0 = instant) are converted */
    {
        void *s = e->create(NULL);
        char rv[16];
        e->set_param(s, "state", "v4 0 2 0 0 0 100 0 0 4095 4095 440 0 0");
        e->get_param(s, "retune", rv, sizeof rv);
        CHECK(!strcmp(rv, "100"), "an older project's Retune 0 ms (instant) opens as 100 %% (%s)", rv);
        e->set_param(s, "state", "v1 0 2 0 0 25 100 0 50 4095");
        e->get_param(s, "retune", rv, sizeof rv);
        CHECK(!strcmp(rv, "75"), "an older project's Retune 25 ms opens as 75 %% (%s)", rv);
        char st[160]; e->get_param(s, "state", st, sizeof st);
        void *q2 = e->create(NULL); e->set_param(q2, "state", st); e->get_param(q2, "retune", rv, sizeof rv);
        CHECK(!strcmp(rv, "75"), "and saves/reloads as %% from then on (%s)", rv);
        e->destroy(q2); e->destroy(s);
    }

    e->set_param(p, "scale", "0");
    CHECK(mask(e, p) == 0xFFF, "back to Chromatic: all on");
    e->destroy(p); e->destroy(q);
    printf("%d failure(s)\n", fails);
    return fails != 0;
}
