#!/usr/bin/env python3
"""Draws Tuney's skin in its four themes and writes the layout that places the live controls on top.

    python3 tools/make_skin_art.py          # needs: pip install playwright && playwright install chromium

Writes, per theme (vst/artwork/bg_<theme>.svg and vst/images/<theme>_*.png): the page background, the 12 note keys
(on/off), the bypass button and the knob filmstrips; then vst/layout.conf, where every themed part is one line per
theme with when=theme:<n>, so MPC swaps them as the THEME selector changes.

All of it is committed, so a normal build (tools/build_port.sh) does not run this; run it after changing the design.
Coordinates are the skin's (1280 x 628); layout.conf's are the same plus 86 on y.
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VST = os.path.join(HERE, "..", "vst")
# Titillium Web from the toolchain checkout next to this repo (as in ~/mpc-vst-plugins and ~/Tuney)
FONT = os.environ.get("TUNEY_FONTS") or os.path.join(HERE, "..", "..", "mpc-vst-plugins", "tools", "html_art", "fonts")
Y = 86   # layout y = skin y + 86

# ---------------------------------------------------------------- geometry (skin coordinates)
DIAL = (640, 250)
BEZEL, DISC = 148, 98
# the note keys: one octave laid out as a piano (tap to switch a note), and above it a 4-octave range strip (display only:
# the Voice's range, and the exact key being sung)
PIANO_X0, WK_W, WK_GAP, WK_Y, WK_H = 32, 172, 2, 500, 112
BK_W, BK_H = 104, 66
STRIP_X0, SK_W, SK_GAP, STRIP_Y, STRIP_H = 148, 37, 1, 436, 48
SBK_W, SBK_H = 22, 29
STRIP_LO, STRIP_HI = 36, 84                       # C2..C6, MIDI; sung_key 1..49
VOICES = [("SOPRANO", 54, 84), ("ALTO", 49, 79), ("TENOR", 45, 72), ("BARITONE", 40, 67)]   # engine VOICE_LO/HI, MIDI
WHITE_PC = (0, 2, 4, 5, 7, 9, 11)
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SEL_Y, SEL_H = 24, 50
HDR_H = 80                                                                          # header height
FIELD_TEXT = 34                                                                     # MPC height of a selector's value (skin_post.py)
# MPC text sizes (ns=, vs=, tsize=) are font heights, ascent + descent: Titillium's letters come out about 1/1.53 of that
TITLE_W = 152                                                                       # TUNEY and PITCH CORRECTION
# label, key, x, width, options, kind: "arrows" (◀ value ▶, few options) or "popup" (a list, many options)
SELECTS = [("VOICE", "voice", 198, 256, "Soprano,Alto,Tenor,Baritone", "arrows"),
           ("KEY", "key", 468, 106, "C,C#,D,D#,E,F,F#,G,G#,A,A#,B", "popup"),
           ("SCALE", "scale", 588, 282, "Chromatic,Major,Minor,Harmonic Minor,Major Pent.,Minor Pent.,User", "popup"),
           ("THEME", "theme", 884, 228, "Grey,Classic,White,Silver", "arrows")]
ARROW_W = 64                                                                       # an arrow's touch area (fingertip wide)
BYPASS = (1196, 49, 136, 50)                                                       # cx, cy, w, h
KNOB_R, KNOB_CY = 48, 236
KNOBS = [("retune", "RETUNE", 80), ("transition", "TRANSITION", 220), ("amount", "AMOUNT", 360),          # CORRECTION
         ("vibrato", "VIBRATO", 980), ("humanize", "HUMANIZE", 1150)]                                       # CHARACTER
KNOB_X = tuple(k[2] for k in KNOBS)
TUNE_R = 26
TUNE_KNOBS = ((466, 324), (814, 324))                                              # freq, cents: the dial's lower corners
TUNES = [("freq", "FREQ", TUNE_KNOBS[0]), ("cents", "CENTS", TUNE_KNOBS[1])]

# ---------------------------------------------------------------- themes
# f0/f1: gradient stops. nat/sharp: (face0, face1, stroke, ink) for a lit and an unlit key. led_*: the lit key's bar.
BASE = dict(amber=("#f2a33a", "#ffc76e", "#1d1407"))
THEMES = [
    ("grey", "Grey", dict(
        bg=("#2c2f34", "#1b1d21"), hdr=("#383c42", "#272a2f"), panel=("#373b41", "#25282c"), line="#4b5159",
        ink="#eef1f4", dim="#9aa3ad", sub="#9d5cff", hint="#7a838d", accent="#9d5cff", accent_hi="#c9a3ff",
        field="#191b1f", field_line="#4b5159", arrow="#9d5cff",
        bezel=("#3a3e44", "#1c1e22"), disc=("#55309a", "#2d1a57", "#150c2b"), ring="#9d5cff", glow=.55,
        tick="#4b5159", tick_major="#727b85", tick_zero="#c9a3ff", tick_label="#9aa3ad",
        note="f7f2ff", cents="c9a3ff", knob_name="eef1f4", knob_value="c9a3ff",
        kface=("#40454c", "#1d2024"), ktrack="#4b5159", karc="#9d5cff", kpointer="#c9a3ff",
        nat_on=("#f6f8fa", "#c8ced5", "#8d959e", "#1b1e22"), nat_off=("#4a4f57", "#3b3f46", "#41464d", "#7f8791"),
        sharp_on=("#2d3137", "#16181b", "#565c64", "#eef1f4"), sharp_off=("#202327", "#17191c", "#2f3338", "#5b626a"),
        led_nat="#9d5cff", led_sharp="#9d5cff", byp_off=("#191b1f", "#4b5159", "#aab3bd"), byp_on=BASE["amber"])),
    ("classic", "Classic", dict(                                                   # MPC-style: grey, black, white and red
        bg=("#4a4d52", "#33363a"), hdr=("#55595e", "#3e4146"), panel=("#1c1d1f", "#101113"), line="#5c6066",
        ink="#ffffff", dim="#b4b8bd", sub="#e3242b", hint="#8e9399", accent="#e3242b", accent_hi="#ff4d52",
        field="#0e0f10", field_line="#26282b", arrow="#e3242b",
        bezel=("#5a5e63", "#2a2c2f"), disc=("#26282b", "#141516", "#09090a"), ring="#e3242b", glow=.45,
        tick="#55595e", tick_major="#c9cdd2", tick_zero="#ff4d52", tick_label="#c9cdd2",
        note="ffffff", cents="ff6a6e", knob_name="ffffff", knob_value="ff6a6e",
        kface=("#2c2e31", "#0b0c0d"), ktrack="#3a3d41", karc="#e3242b", kpointer="#ffffff",
        nat_on=("#ffffff", "#dfe2e5", "#9ba0a6", "#111214"), nat_off=("#55595e", "#45484d", "#4c5055", "#8e9399"),
        sharp_on=("#2a2c2f", "#0b0c0d", "#4a4d52", "#ffffff"), sharp_off=("#1a1b1d", "#111213", "#2a2c2f", "#5f6368"),
        led_nat="#e3242b", led_sharp="#ff4d52", byp_off=("#0e0f10", "#26282b", "#c9cdd2"), byp_on=("#e3242b", "#ff6a6e", "#ffffff"))),
    ("white", "White", dict(                                                       # white, grey and black with orange
        bg=("#eef0f3", "#dde1e5"), hdr=("#fbfcfd", "#e7eaee"), panel=("#f8f9fb", "#e2e6ea"), line="#b9c0c8",
        ink="#121417", dim="#5f6873", sub="#f26b1d", hint="#7f8893", accent="#f26b1d", accent_hi="#ff8a3d",
        field="#15171a", field_line="#15171a", arrow="#ff8a3d",
        bezel=("#d5dae0", "#aab2bb"), disc=("#2b2f34", "#17191c", "#0b0c0e"), ring="#f26b1d", glow=.35,
        tick="#a1a9b2", tick_major="#4a525b", tick_zero="#f26b1d", tick_label="#4a525b",
        note="ffffff", cents="ff8a3d", knob_name="121417", knob_value="d9560f",
        kface=("#2e3237", "#0f1113"), ktrack="#c3c9d0", karc="#f26b1d", kpointer="#ffffff",
        nat_on=("#ffffff", "#e9ecef", "#9aa2ab", "#121417"), nat_off=("#cdd2d8", "#b9bfc6", "#a8afb7", "#7d858f"),
        sharp_on=("#2e3237", "#0f1113", "#0f1113", "#ffffff"), sharp_off=("#90979f", "#7d848c", "#757c84", "#50575f"),
        led_nat="#f26b1d", led_sharp="#ff8a3d", byp_off=("#ffffff", "#b9c0c8", "#121417"), byp_on=("#f26b1d", "#ff8a3d", "#ffffff"))),
    ("silver", "Silver", dict(
        bg=("#cdd2d8", "#9ea6ae"), hdr=("#e3e7eb", "#bcc2c9"), panel=("#dde1e6", "#b5bcc4"), line="#8b939c",
        ink="#14181d", dim="#48505a", sub="#0a6fb0", hint="#5c646e", accent="#0a6fb0", accent_hi="#0a6fb0",
        field="#1b1f24", field_line="#5f6770", arrow="#6fd8ff",
        bezel=("#e4e8ec", "#8e969f"), disc=("#2b5d85", "#173650", "#0c1b29"), ring="#0a6fb0", glow=.35,
        tick="#7a828b", tick_major="#2f363e", tick_zero="#0a6fb0", tick_label="#3a424b",
        note="f2f8ff", cents="9fdcff", knob_name="14181d", knob_value="0a4f80",
        kface=("#3a3e44", "#14171a"), ktrack="#9aa2ab", karc="#0a6fb0", kpointer="#ffffff",
        nat_on=("#ffffff", "#e3e7eb", "#8b939c", "#14181d"), nat_off=("#aeb5bd", "#99a0a8", "#8b939c", "#5f6873"),
        sharp_on=("#2e3237", "#101215", "#101215", "#e9ecef"), sharp_off=("#6f767e", "#5e646b", "#565c63", "#3c4249"),
        led_nat="#0a6fb0", led_sharp="#3fb0ff", byp_off=("#1b1f24", "#5f6770", "#cfd6dd"), byp_on=BASE["amber"])),
]


def _font_css():
    """Titillium Web as embedded @font-face rules: the SVG is drawn as a separate image, which can't load fonts from
    files, so the background and the pictures carry the font themselves."""
    import base64
    rules = []
    for w, f in ((400, "TitilliumWeb-Regular.ttf"), (600, "TitilliumWeb-SemiBold.ttf"), (700, "TitilliumWeb-Bold.ttf")):
        p = os.path.join(FONT, f)
        if not os.path.exists(p):
            raise SystemExit("make_skin_art: %s not found (set TUNEY_FONTS to the Titillium Web folder)" % p)
        rules.append('@font-face{font-family:"Titillium Web";font-weight:%d;src:url(data:font/ttf;base64,%s)}'
                     % (w, base64.b64encode(open(p, "rb").read()).decode()))
    return "".join(rules)


FONT_CSS = _font_css()
TF = "font-family:'Titillium Web',sans-serif"


def piano_key(i):
    """note 0..11 -> (x, y, w, h) of its key on the one-octave piano"""
    if i in WHITE_PC:
        return PIANO_X0 + WHITE_PC.index(i) * (WK_W + WK_GAP), WK_Y, WK_W, WK_H
    edge = PIANO_X0 + (WHITE_PC.index(i - 1) + 1) * (WK_W + WK_GAP) - WK_GAP / 2
    return round(edge - BK_W / 2), WK_Y, BK_W, BK_H


def strip_key(m):
    """MIDI note on the range strip -> (x, y, w, h)"""
    pc, octv = m % 12, m // 12 - STRIP_LO // 12
    if pc in WHITE_PC:
        return STRIP_X0 + (octv * 7 + WHITE_PC.index(pc)) * (SK_W + SK_GAP), STRIP_Y, SK_W, STRIP_H
    edge = STRIP_X0 + (octv * 7 + WHITE_PC.index(pc - 1) + 1) * (SK_W + SK_GAP) - SK_GAP / 2
    return round(edge - SBK_W / 2), STRIP_Y, SBK_W, SBK_H


def strip_svg(t):
    """the range strip's keys, drawn into the background"""
    o = []
    for black in (0, 1):
        for m in range(STRIP_LO, STRIP_HI + 1):
            if (m % 12 in WHITE_PC) == bool(black):
                continue
            x, y, w, h = strip_key(m)
            f0, f1, stroke, _ = t["sharp_on" if black else "nat_on"]
            o.append('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s" stroke="%s"/>' % (
                x + .5, y + .5, w - 1, h - 1, 2 if black else 3, f1 if black else f0, stroke))
            if not black and m % 12 == 0:
                o.append('<text x="%g" y="%g" text-anchor="middle" style="%s;font-weight:700;font-size:11px" fill="%s">C%d</text>' % (
                    x + w / 2, y + h - 5, TF, t["nat_on"][3], m // 12 - 1))
    return "".join(o)


RANGE_BOX = (30, 430, 1224, 62)                  # x, y, w, h: the strip and the label at its left


def range_svg(v):
    """one Voice's range over the strip: the notes outside it dimmed, the range outlined, its name and notes at the left"""
    name, lo, hi = VOICES[v]
    x_end = strip_key(STRIP_HI)[0] + SK_W
    lx = strip_key(lo)[0]
    hx = sum(strip_key(hi)[::2])
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    nm = lambda m: "%s%d" % (names[m % 12], m // 12 - 1)
    bx, by, bw, bh = RANGE_BOX
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="%d %d %d %d">' % (bw, bh, bx, by, bw, bh)]
    for a, b in ((STRIP_X0, lx), (hx, x_end)):
        if b > a:
            o.append('<rect x="%g" y="%d" width="%g" height="%d" rx="3" fill="#000" opacity=".6"/>' % (a, STRIP_Y, b - a, STRIP_H))
    for col, wid in (("#000", 3.5), ("#ffffff", 1.6)):
        o.append('<rect x="%g" y="%g" width="%g" height="%g" rx="4" fill="none" stroke="%s" stroke-width="%g" opacity=".8"/>' % (
            lx - 2, STRIP_Y - 2.5, hx - lx + 4, STRIP_H + 5, col, wid))
    o.append('<text x="34" y="474" style="%s;font-weight:700;font-size:13px;letter-spacing:1.5px" fill="#8e969f">%s</text>' % (TF, name))
    o.append('<text x="34" y="491" style="%s;font-weight:600;font-size:13px" fill="#8e969f">%s – %s</text>' % (TF, nm(lo), nm(hi)))
    o.append("</svg>")
    return "".join(o)


def grad(id_, stops, vertical=True):
    return '<linearGradient id="%s" x2="%d" y2="%d">%s</linearGradient>' % (
        id_, 0 if vertical else 1, 1 if vertical else 0,
        "".join('<stop offset="%g" stop-color="%s"/>' % (i / max(1, len(stops) - 1), c) for i, c in enumerate(stops)))


# ---------------------------------------------------------------- finish (shared by every theme)
# grain: fine noise over the plate; brushed: horizontal brushed-metal streaks; gloss: strength of the top sheen
FINISH = {"grey": dict(grain=.07, brushed=0, gloss=.09), "classic": dict(grain=.08, brushed=0, gloss=.09),
          "white": dict(grain=.035, brushed=0, gloss=.45), "silver": dict(grain=.02, brushed=.20, gloss=.35)}
LED = (640, 180, 40)                                     # input light in the dial: centre and image size
LED_STATES = (("off", None), ("input", .45), ("pitch", 1.0))   # white light: soft while hearing input, full when locked


def common_defs():
    return ('<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".85" '
            'numOctaves="2" seed="7"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .9 -.35"/></filter>'
            '<filter id="brushed" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".004 .9" '
            'numOctaves="3" seed="3"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1.4 -.55"/></filter>'
            '<filter id="drop" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="4" stdDeviation="6" flood-opacity=".45"/></filter>'
            '<filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3.5"/></filter>'
            '<filter id="blur8" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8"/></filter>'
            '<linearGradient id="bevel" x2="0" y2="1"><stop stop-color="#fff" stop-opacity=".22"/><stop offset=".12" stop-color="#fff" stop-opacity="0"/>'
            '<stop offset=".88" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".35"/></linearGradient>'
            '<linearGradient id="chrome" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff" stop-opacity=".55"/>'
            '<stop offset=".45" stop-color="#fff" stop-opacity=".05"/><stop offset=".55" stop-color="#000" stop-opacity=".1"/>'
            '<stop offset="1" stop-color="#000" stop-opacity=".5"/></linearGradient>'
            '<linearGradient id="inset" x2="0" y2="1"><stop stop-color="#000" stop-opacity=".55"/><stop offset=".35" stop-color="#000" stop-opacity="0"/>'
            '<stop offset="1" stop-color="#fff" stop-opacity=".06"/></linearGradient>'
            '<radialGradient id="vignette" cx=".5" cy=".45" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/>'
            '<stop offset="1" stop-color="#000" stop-opacity=".35"/></radialGradient>'
            '<linearGradient id="glass" x2="0" y2="1"><stop stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')


def gloss_grad(g):
    return ('<linearGradient id="gloss" x2="0" y2="1"><stop stop-color="#fff" stop-opacity="%g"/>'
            '<stop offset=".45" stop-color="#fff" stop-opacity="%g"/><stop offset=".46" stop-color="#fff" stop-opacity="0"/></linearGradient>' % (g, g * .35))


def panel(path, t, fin):
    """A raised panel: soft shadow, fill, top sheen, bevelled edge."""
    return ('<path d="%s" fill="url(#pnl)" filter="url(#drop)"/>'
            '<path d="%s" fill="url(#gloss)" opacity=".6"/>'
            '<path d="%s" fill="none" stroke="url(#bevel)" stroke-width="2"/>'
            '<path d="%s" fill="none" stroke="%s"/>' % (path, path, path, path, t["line"]))


# ---------------------------------------------------------------- background
def background(slug, t):
    fin = FINISH[slug]
    cx, cy = DIAL
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="628" viewBox="0 0 1280 628">', "<defs>",
         grad("bg", t["bg"]), grad("hdr", t["hdr"]), grad("pnl", t["panel"]), gloss_grad(fin["gloss"]), common_defs(),
         '<radialGradient id="disc" cx=".5" cy=".38" r=".65"><stop stop-color="%s"/><stop offset=".55" stop-color="%s"/>'
         '<stop offset="1" stop-color="%s"/></radialGradient>' % t["disc"],
         '<radialGradient id="bezel" cx=".5" cy=".3" r=".75"><stop stop-color="%s"/><stop offset="1" stop-color="%s"/></radialGradient>' % t["bezel"],
         '<clipPath id="discclip"><circle cx="%d" cy="%d" r="%d"/></clipPath>' % (cx, cy, DISC),
         "<style>%s</style>" % FONT_CSS, "</defs>",
         '<rect width="1280" height="628" fill="url(#bg)"/>']
    if fin["brushed"]:
        o.append('<rect width="1280" height="628" filter="url(#brushed)" opacity="%g"/>' % fin["brushed"])
    if fin["grain"]:
        o.append('<rect width="1280" height="628" filter="url(#grain)" opacity="%g"/>' % fin["grain"])
    o.append('<rect width="1280" height="628" fill="url(#vignette)"/>')

    # header: a raised strip with a lit top edge
    o.append('<rect width="1280" height="%d" fill="url(#hdr)" filter="url(#drop)"/>' % HDR_H + '')
    o.append('<rect width="1280" height="34" fill="url(#gloss)" opacity=".7"/>')
    o.append('<path d="M0 .5H1280" stroke="#fff" stroke-opacity=".18"/><path d="M0 %gH1280" stroke="#000" stroke-opacity=".45"/>' % (HDR_H - .5))
    # title and subtitle share a left edge and a width (textLength), so PITCH starts under the T and both lines end together
    o.append('<text x="30" y="44" textLength="%d" lengthAdjust="spacing" style="%s;font-weight:700;font-size:36px" fill="%s">TUNEY</text>' % (TITLE_W, TF, t["ink"]))
    o.append('<text x="31" y="66" textLength="%d" lengthAdjust="spacing" style="%s;font-weight:600;font-size:14px" fill="%s">PITCH CORRECTION</text>' % (TITLE_W - 1, TF, t["sub"]))
    for label, _, x, w, _, kind in SELECTS:
        o.append('<text x="%d" y="%d" style="%s;font-weight:600;font-size:15px;letter-spacing:2px" fill="%s">%s</text>' % (x + 2, SEL_Y - 7, TF, t["dim"], label))
        o.append('<rect x="%g" y="%g" width="%d" height="%d" rx="8" fill="%s"/>' % (x, SEL_Y, w, SEL_H, t["field"]))
        o.append('<rect x="%g" y="%g" width="%d" height="%d" rx="8" fill="url(#inset)"/>' % (x, SEL_Y, w, SEL_H))
        o.append('<rect x="%g" y="%g" width="%d" height="%d" rx="8" fill="none" stroke="%s"/>' % (x + .5, SEL_Y + .5, w - 1, SEL_H - 1, t["field_line"]))
        o.append('<path d="M%g %gH%g" stroke="#fff" stroke-opacity=".10"/>' % (x + 8, SEL_Y + SEL_H + .5, x + w - 8))
        ay = SEL_Y + SEL_H / 2
        if kind == "popup":                   # a list: a ▼ at the right
            ax = x + w - 22
            o.append('<path d="M%g %gV%g" stroke="#fff" stroke-opacity=".08"/>' % (x + w - 44, SEL_Y + 7, SEL_Y + SEL_H - 7))
            o.append('<path d="M%g %gL%g %gL%g %gZ" fill="%s"/>' % (ax - 8, ay - 4, ax + 8, ay - 4, ax, ay + 5, t["arrow"]))
        else:                                 # arrows: the ◀ ▶ are live buttons; only their dividers are drawn here
            for dx in (x + ARROW_W, x + w - ARROW_W):
                o.append('<path d="M%g %gV%g" stroke="#fff" stroke-opacity=".08"/>' % (dx, SEL_Y + 7, SEL_Y + SEL_H - 7))

    # stage: two angled side panels around the dial
    o.append(panel("M16 88H446L398 414H16Z", t, fin))
    o.append(panel("M1264 88H834L882 414H1264Z", t, fin))
    for x, anchor, s in ((34, "start", "CORRECTION"), (1246, "end", "CHARACTER")):
        o.append('<text x="%d" y="117" text-anchor="%s" style="%s;font-weight:600;font-size:19px;letter-spacing:3px" fill="%s">%s</text>' % (x, anchor, TF, t["dim"], s))

    # dial: shadowed chrome-edged bezel, cents scale, glowing ring, glass disc
    o.append('<circle cx="%d" cy="%d" r="%d" fill="#000" opacity=".5" filter="url(#blur8)"/>' % (cx, cy + 6, BEZEL))
    o.append('<circle cx="%d" cy="%d" r="%d" fill="url(#bezel)"/>' % (cx, cy, BEZEL))
    if fin["brushed"]:
        o.append('<circle cx="%d" cy="%d" r="%d" filter="url(#brushed)" opacity="%g"/>' % (cx, cy, BEZEL, fin["brushed"] * .8))
    o.append('<circle cx="%d" cy="%d" r="%g" fill="none" stroke="url(#chrome)" stroke-width="3"/>' % (cx, cy, BEZEL - 1.5))
    o.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="#000" stroke-opacity=".35"/>' % (cx, cy, BEZEL + 1))
    for c in range(-100, 101, 10):
        a = math.radians(c * 1.35)
        major = c % 50 == 0
        r0, r1 = (BEZEL - 24, BEZEL - 8) if major else (BEZEL - 18, BEZEL - 10)
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%g" stroke-linecap="round"/>' % (
            cx + r0 * math.sin(a), cy - r0 * math.cos(a), cx + r1 * math.sin(a), cy - r1 * math.cos(a),
            t["tick_zero"] if c == 0 else (t["tick_major"] if major else t["tick"]), 2.5 if major else 1.5))
        if major:
            lr = BEZEL - 35
            o.append('<text x="%.1f" y="%.1f" text-anchor="middle" dominant-baseline="central" style="%s;font-weight:600;font-size:14px" fill="%s">%s</text>' % (
                cx + lr * math.sin(a), cy - lr * math.cos(a), TF, t["tick_label"], ("%+d" % c) if c else "0"))
    if t["glow"]:
        o.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="6" opacity="%g" filter="url(#soft)"/>' % (cx, cy, DISC + 2, t["ring"], t["glow"]))
    o.append('<circle cx="%d" cy="%d" r="%d" fill="#000" opacity=".6"/>' % (cx, cy, DISC + 5))          # recess
    o.append('<circle cx="%d" cy="%d" r="%d" fill="url(#disc)"/>' % (cx, cy, DISC))
    o.append('<g clip-path="url(#discclip)"><circle cx="%d" cy="%d" r="%d" fill="none" stroke="#000" stroke-width="14" opacity=".45" filter="url(#soft)"/>'
             '<ellipse cx="%d" cy="%d" rx="%d" ry="%d" fill="url(#glass)"/></g>' % (
                 cx, cy, DISC + 4, cx, cy - DISC * .52, DISC * .82, DISC * .5))
    o.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="2"/>' % (cx, cy, DISC, t["ring"]))
    o.append('<path d="M%d %dH%d" stroke="#%s" stroke-opacity=".35"/>' % (cx - 46, cy + 38, cx + 46, t["cents"]))
    # socket for the input light (the light itself is a picture that follows the engine)
    lx, ly, _ = LED
    o.append('<circle cx="%d" cy="%d" r="11" fill="#000" opacity=".55"/><circle cx="%d" cy="%d" r="10.5" fill="none" stroke="url(#chrome)" stroke-width="2"/>' % (lx, ly, lx, ly))
    o.append('<radialGradient id="lens" cx=".4" cy=".35" r=".75"><stop stop-color="#000" stop-opacity=".35"/><stop offset="1" stop-color="#000" stop-opacity=".8"/></radialGradient>'
             '<circle cx="%d" cy="%d" r="8" fill="url(#lens)"/><circle cx="%d" cy="%d" r="7.5" fill="none" stroke="#fff" stroke-opacity=".10"/>'
             '<ellipse cx="%d" cy="%g" rx="3.2" ry="1.7" fill="#fff" opacity=".28"/>' % (lx, ly, lx, ly, lx - 2, ly - 3.5))

    # note strip
    o.append(panel("M26.5 428.5H1253.5A10 10 0 0 1 1263.5 438.5V607.5A10 10 0 0 1 1253.5 617.5H26.5A10 10 0 0 1 16.5 607.5V438.5A10 10 0 0 1 26.5 428.5Z", t, fin))
    o.append('<text x="34" y="451" style="%s;font-weight:600;font-size:19px;letter-spacing:3px" fill="%s">NOTES</text>' % (TF, t["dim"]))
    o.append(strip_svg(t))
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------- pictures
def key_svg(slug, t, name, on, w, h):
    sharp = "#" in name
    f0, f1, stroke, ink = t[("sharp" if sharp else "nat") + ("_on" if on else "_off")]
    g = (FINISH[slug]["gloss"] + .2) if not sharp else .14
    if not on:
        g *= .4
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h),
         '<defs>%s%s<filter id="g" x="-50%%" y="-300%%" width="200%%" height="700%%"><feGaussianBlur stdDeviation="3"/></filter>'
         '<filter id="ds" x="-10%%" y="-10%%" width="120%%" height="130%%"><feDropShadow dx="0" dy="2" stdDeviation="1.6" flood-opacity=".5"/></filter></defs>' % (
             grad("f", (f0, f1)), gloss_grad(g)),
         '<rect x="2" y="1.5" width="%d" height="%d" rx="8" fill="url(#f)" filter="url(#ds)"/>' % (w - 4, h - 6),
         '<rect x="2" y="1.5" width="%d" height="%d" rx="8" fill="url(#gloss)"/>' % (w - 4, h - 6),
         '<rect x="2.5" y="2" width="%d" height="%d" rx="7.5" fill="none" stroke="%s"/>' % (w - 5, h - 7, stroke),
         '<path d="M10 3H%d" stroke="#fff" stroke-opacity="%g"/>' % (w - 10, .55 if (on and not sharp) else .12)]
    # on/off reads from the key itself (a lit key is bright, an unlit one greyed), so no indicator bar
    o.append('<text x="%g" y="%d" text-anchor="middle" style="%s;font-weight:700;font-size:%dpx" fill="%s">%s</text>' % (
        w / 2, h - 22 if sharp else h - 10, TF, 27 if sharp else 31, ink, name))
    o.append("</svg>")
    return "\n".join(o)


def bypass_svg(slug, t, on):
    _, _, w, h = BYPASS
    fill, stroke, ink = t["byp_on" if on else "byp_off"]
    rr = (h - 4) // 2
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"><defs>%s<filter id="gl" x="-20%%" y="-50%%" width="140%%" height="200%%">'
            '<feGaussianBlur stdDeviation="3"/></filter></defs>'
            '%s<rect x="2" y="2" width="%d" height="%d" rx="%d" fill="%s"/><rect x="2" y="2" width="%d" height="%d" rx="%d" fill="url(#gloss)"/>'
            '<rect x="2.5" y="2.5" width="%d" height="%d" rx="%d" fill="none" stroke="%s" stroke-width="1.5"/>'
            '<text x="%g" y="%g" text-anchor="middle" dominant-baseline="central" style="%s;font-weight:700;font-size:18px;letter-spacing:3px" fill="%s">BYPASS</text></svg>') % (
        w, h, gloss_grad(.35 if on else .12),
        ('<rect x="4" y="4" width="%d" height="%d" rx="%d" fill="%s" filter="url(#gl)" opacity=".8"/>' % (w - 8, h - 8, rr, fill)) if on else "",
        w - 4, h - 4, rr, fill, w - 4, h - 4, rr, w - 5, h - 5, rr, stroke, w / 2, h / 2 + 1, TF, ink)


def arrow_svg(t, side, pressed):
    """A ◀ or ▶ for an arrows selector, on a transparent square (the field is in the background)."""
    w, h = ARROW_W, SEL_H
    cx, cy = w / 2, h / 2
    d = -1 if side == "prev" else 1
    col = t["arrow"]
    back = ('<rect x="3" y="3" width="%d" height="%d" rx="7" fill="#fff" opacity=".10"/>' % (w - 6, h - 6)) if pressed else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">%s<path d="M%g %gL%g %gL%g %gZ" fill="%s"/></svg>' % (
        w, h, back, cx + 8 * d, cy, cx - 7 * d, cy - 11, cx - 7 * d, cy + 11, col))


GLOW = "#3dff8f"   # the sung key's light: green reads on white and black keys in every theme


def glow_svg(w, h, lit):
    """Over a key while it's sung. A switched-on note: a green rim with a soft inner glow and a wash from the bottom.
    A switched-off note: a faint green outline only, so you still see you're singing it (nothing corrects it)."""
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h)]
    if not lit:
        o.append('<rect x="3" y="2.5" width="%d" height="%d" rx="7.5" fill="none" stroke="%s" stroke-width="2" '
                 'stroke-dasharray="7 5" opacity=".75"/>' % (w - 6, h - 8, GLOW))
    else:
        o.append('<defs><filter id="b" x="-20%%" y="-20%%" width="140%%" height="140%%"><feGaussianBlur stdDeviation="3.2"/></filter>'
                 '<linearGradient id="w" x2="0" y2="1"><stop offset=".25" stop-color="%s" stop-opacity="0"/>'
                 '<stop offset="1" stop-color="%s" stop-opacity=".30"/></linearGradient></defs>' % (GLOW, GLOW))
        o.append('<rect x="2" y="1.5" width="%d" height="%d" rx="8" fill="url(#w)"/>' % (w - 4, h - 6))
        o.append('<rect x="5" y="4.5" width="%d" height="%d" rx="6" fill="none" stroke="%s" stroke-width="5" opacity=".7" filter="url(#b)"/>' % (
            w - 10, h - 12, GLOW))
        o.append('<rect x="3" y="2.5" width="%d" height="%d" rx="7.5" fill="none" stroke="%s" stroke-width="2.5"/>' % (w - 6, h - 8, GLOW))
    o.append("</svg>")
    return "".join(o)


def strip_glow_svg(w, h):
    """the sung key on the range strip: a solid green key with a bright rim"""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"><rect x="1" y="1" width="%d" height="%d" rx="3" fill="%s" opacity=".85"/>'
            '<rect x="1" y="1" width="%d" height="%d" rx="3" fill="none" stroke="#eafff2" stroke-width="1.5"/></svg>') % (w, h, w - 2, h - 2, GLOW, w - 2, h - 2)


def led_svg(level):
    """The lit lens: white, with a glow that grows with level (the unlit lens is drawn in the background art)."""
    s = LED[2]
    c = s / 2
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"><defs><radialGradient id="l" cx=".42" cy=".38" r=".7">'
            '<stop stop-color="#fff"/><stop offset=".55" stop-color="#f4f8ff" stop-opacity="%g"/><stop offset="1" stop-color="#cfd9e6" stop-opacity="%g"/>'
            '</radialGradient><filter id="b" x="-100%%" y="-100%%" width="300%%" height="300%%"><feGaussianBlur stdDeviation="%g"/></filter></defs>'
            '<circle cx="%g" cy="%g" r="%g" fill="#fff" opacity="%g" filter="url(#b)"/>'
            '<circle cx="%g" cy="%g" r="8" fill="url(#l)" opacity="%g"/><ellipse cx="%g" cy="%g" rx="3.2" ry="1.8" fill="#fff" opacity=".9"/></svg>') % (
        s, s, .55 + .45 * level, .35 + .5 * level, 2.5 + 2.5 * level, c, c, 8 + 4 * level, .35 + .5 * level, c, c, .55 + .45 * level, c - 2, c - 3.5)


FRAMES = 128

# the dial's note and cents are pictures (filmstrip meters on dial_note / dial_cents), not MPC text: a text readout
# needs a full screen rebuild for every change, which kept closing MPC's PRESET menu while you sang
DIAL_NOTE = (190, 100, 96)      # frame w, h, text px: frame 0 a dim dash, 1..12 C..B
DIAL_CENTS = (200, 40, 28)      # frame 0 blank, 1..101 -50..+50 cents


def dial_strip_svg(t, labels, w, h, size, weight, colour, dim_first):
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">' % (w, h * len(labels))]
    for k, lab in enumerate(labels):
        if not lab:
            continue
        op = .32 if dim_first and k == 0 else 1
        o.append('<text x="%g" y="%g" text-anchor="middle" dominant-baseline="central" style="%s;font-size:%dpx;font-weight:%d" '
                 'fill="#%s" opacity="%g">%s</text>' % (w / 2, k * h + h / 2, TF, size, weight, colour.lstrip("#"), op, lab))
    o.append("</svg>")
    return "".join(o), w, h * len(labels)


NOTE_LABELS = ["-"] + NOTES
CENTS_LABELS = [""] + ["%+d cents" % c if c else "0 cents" for c in range(-50, 51)]


def knob_strip_svg(slug, t, r):
    """128 knob positions stacked top to bottom, each in a (2r+8)-pixel square (the renderer's knob box): value arc with a
    soft glow, a bevelled rim, a domed face lit from above, and a pointer. The light stays put while the pointer turns."""
    s = 2 * r + 8
    sw = max(2.5, r / 11)
    R = r + 4 - sw / 2 - 1.5
    fr = r - sw - 2.5                                   # rim radius
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (s, s * FRAMES, s, s * FRAMES),
         '<defs><radialGradient id="kf" cx=".42" cy=".3" r=".85"><stop stop-color="%s"/><stop offset="1" stop-color="%s"/></radialGradient>' % t["kface"],
         '<linearGradient id="rim" x2="0" y2="1"><stop stop-color="#fff" stop-opacity=".45"/><stop offset=".5" stop-color="#fff" stop-opacity=".05"/>'
         '<stop offset="1" stop-color="#000" stop-opacity=".5"/></linearGradient>',
         '<radialGradient id="spec" cx=".5" cy=".5" r=".5"><stop stop-color="#fff" stop-opacity=".38"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>',
         '<filter id="sh" x="-30%%" y="-30%%" width="160%%" height="170%%"><feDropShadow dx="0" dy="%g" stdDeviation="%g" flood-opacity=".6"/></filter>' % (max(1.5, r / 20), max(1.5, r / 18)),
         '<filter id="ag" x="-30%%" y="-30%%" width="160%%" height="160%%"><feGaussianBlur stdDeviation="%g"/></filter></defs>' % max(1.2, r / 22)]
    pt = lambda cx, cy, a, rad: (cx + rad * math.sin(math.radians(a)), cy - rad * math.cos(math.radians(a)))
    for k in range(FRAMES):
        cx, cy = s / 2, s / 2 + k * s
        a1 = -135 + 270 * k / (FRAMES - 1)
        sx, sy = pt(cx, cy, -135, R)
        ex, ey = pt(cx, cy, 135, R)
        o.append('<path d="M%.2f %.2fA%g %g 0 1 1 %.2f %.2f" fill="none" stroke="%s" stroke-width="%g" stroke-linecap="round"/>' % (
            sx, sy, R, R, ex, ey, t["ktrack"], sw))
        if k:
            vx, vy = pt(cx, cy, a1, R)
            arc = 'd="M%.2f %.2fA%g %g 0 %d 1 %.2f %.2f" fill="none" stroke="%s" stroke-linecap="round"' % (
                sx, sy, R, R, 1 if a1 + 135 > 180 else 0, vx, vy, t["karc"])
            o.append('<path %s stroke-width="%g" opacity=".55" filter="url(#ag)"/>' % (arc, sw * 1.8))
            o.append('<path %s stroke-width="%g"/>' % (arc, sw))
        o.append('<circle cx="%g" cy="%g" r="%g" fill="url(#kf)" filter="url(#sh)"/>' % (cx, cy, fr))
        o.append('<circle cx="%g" cy="%g" r="%g" fill="none" stroke="url(#rim)" stroke-width="%g"/>' % (cx, cy, fr - max(1, r / 40), max(1.2, r / 28)))
        o.append('<circle cx="%g" cy="%g" r="%g" fill="url(#kf)"/>' % (cx, cy, fr * .78))
        o.append('<ellipse cx="%g" cy="%g" rx="%g" ry="%g" fill="url(#spec)"/>' % (cx - fr * .18, cy - fr * .38, fr * .55, fr * .32))
        p0, p1 = pt(cx, cy, a1, fr * .30), pt(cx, cy, a1, fr * .86)
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="%g" stroke-linecap="round"/>' % (
            p0[0], p0[1], p1[0], p1[1], t["kpointer"], max(2, r / 10)))
    o.append("</svg>")
    return "\n".join(o), s, s * FRAMES


def render_pngs(items):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        for path, svg, w, h in items:
            pg.set_viewport_size({"width": w, "height": min(h, 16384)})
            pg.set_content("<html><head><style>%s html,body{margin:0;background:transparent}</style></head><body>%s</body></html>" % (FONT_CSS, svg))
            pg.wait_for_timeout(50)
            pg.screenshot(path=path, omit_background=True, full_page=True)
        b.close()


# ---------------------------------------------------------------- layout.conf
def layout():
    L = ["# Tuney -- 3DTHC. Written by tools/make_skin_art.py: edit the design there and rerun it, not this file.",
         "# One page: selectors and bypass on top, the pitch dial with two knobs either side and the small tuning pair in",
         "# its lower corners, the 12-note strip below. Every themed part is one line per theme (when=theme:<n>).",
         "# Coordinates are layout space (skin y + 86).", "", "art_css=popup.css",
         "theme_ink=e6eef6", "theme_ink_dim=7d8b9a", "theme_accent=d7dce2", "theme_accent_hi=ffffff", "theme_line=2b3746",
         "theme_box=10151b", "theme_lcd=0a0e13", "theme_seg_active=d7dce2", "theme_seg_inactive=121820", "theme_seg_active_tx=06121c",
         "", "[tab TUNEY]"]
    for n, (slug, name, _) in enumerate(THEMES):
        L.append('art file="artwork/bg_%s.svg" when=theme:%d' % (slug, n))
    L += ["", "# selectors: the artwork draws the fields (dark in every theme), MPC writes the value in them"]
    for label, key, x, w, opts, kind in SELECTS:
        cy = SEL_Y + SEL_H // 2 + Y
        if kind == "popup":
            cols = " cols=3" if key == "key" else ""                              # the 12 keys as a 3 x 4 pad
            L.append('popup cx=%d cy=%d w=%d h=%d label="%s" key=%s field=none accent=eef1f4%s options="%s"' % (
                x + w // 2, cy, w, SEL_H, label, key, cols, opts))
        else:                                                                      # value between the arrows
            L.append('readout cx=%d cy=%d w=%d h=%d box=0 tsize=%d tcolor=eef1f4 label="%s" key=%s' % (
                x + w // 2, cy, w - 2 * ARROW_W - 8, SEL_H, FIELD_TEXT, label, key))
    bx, by, bw, bh = BYPASS
    for n, (slug, _, t) in enumerate(THEMES):
        L += ["", "# ---- theme %d: %s" % (n, slug)]
        L.append('toggle cx=%d cy=%d key=bypass label="BYPASS" img=images/%s_bypass_off.png img_on=images/%s_bypass_on.png w=%d h=%d ns=0 when=theme:%d' % (
            bx, by + Y, slug, slug, bw, bh, n))
        for key, lab, x in KNOBS:
            L.append('knob cx=%d cy=%d r=%d bw=%d ns=36 vs=34 ink=%s ink_dim=%s strip=images/%s_knob_r%d.png frames=%d label="%s" key=%s when=theme:%d' % (
                x, KNOB_CY + Y, KNOB_R, 130 if key == "amount" else 140, t["knob_name"], t["knob_value"], slug, KNOB_R, FRAMES, lab, key, n))
        for key, lab, (x, y) in TUNES:
            L.append('knob cx=%d cy=%d r=%d bw=84 ns=30 vs=28 ink=%s ink_dim=%s strip=images/%s_knob_r%d.png frames=%d label="%s" key=%s when=theme:%d' % (
                x, y + Y, TUNE_R, t["knob_name"], t["knob_value"], slug, TUNE_R, FRAMES, lab, key, n))
        for label, key, x, w, opts, kind in SELECTS:
            if kind == "arrows":
                for side, ax in (("prev", x + ARROW_W // 2), ("next", x + w - ARROW_W // 2)):
                    L.append('button cx=%d cy=%d w=%d h=%d key=%s_%s label="" img=images/%s_arrow_%s.png img_on=images/%s_arrow_%s_on.png when=theme:%d' % (
                        ax, SEL_Y + SEL_H // 2 + Y, ARROW_W, SEL_H, key, side, slug, side, slug, side, n))
        cx, cy = DIAL
        L.append('meter cx=%d cy=%d w=%d h=%d key=dial_note strip=images/%s_dial_note.png frames=%d when=theme:%d' % (
            cx, cy - 10 + Y, DIAL_NOTE[0], DIAL_NOTE[1], slug, len(NOTE_LABELS), n))
        L.append('meter cx=%d cy=%d w=%d h=%d key=dial_cents strip=images/%s_dial_cents.png frames=%d when=theme:%d' % (
            cx, cy + 56 + Y, DIAL_CENTS[0], DIAL_CENTS[1], slug, len(CENTS_LABELS), n))
    L += ["", "# the voice's range on the strip (dimmed outside it), one drawing per Voice"]
    bx, by, bw, bh = RANGE_BOX
    for v in range(len(VOICES)):
        L.append('button cx=%d cy=%d w=%d h=%d key=noop label="" img=images/range_%d.png img_on=images/range_%d.png when=voice:%d' % (
            bx + bw // 2, by + bh // 2 + Y, bw, bh, v, v, v))
    L += ["", "# the piano: white keys, their sung-note glow, then black keys and theirs (MPC draws and hit-tests in layout order,",
          "# so a black key sits over the white keys' corners). The sung key lights green; a switched-off note sung: dashed",
          "# outline. A tap on the glow toggles the note, as the key does."]
    for black in (0, 1):
        for n, (slug, _, t) in enumerate(THEMES):
            for i, note in enumerate(NOTES):
                if ("#" in note) != bool(black):
                    continue
                x, y, w, h = piano_key(i)
                ns = note.replace("#", "s")
                L.append('toggle cx=%d cy=%d key=note_%s label="%s" img=images/%s_key_%s_off.png img_on=images/%s_key_%s_on.png w=%d h=%d ns=0 when=theme:%d' % (
                    x + w // 2, y + h // 2 + Y, ns, note, slug, ns, slug, ns, w, h, n))
        for i, note in enumerate(NOTES):
            if ("#" in note) != bool(black):
                continue
            x, y, w, h = piano_key(i)
            kind = "sharp" if black else "nat"
            L.append('button cx=%d cy=%d w=%d h=%d key=note_%s label="" img=images/glow_%s_off.png img_on=images/glow_%s_on.png when=sung:%d' % (
                x + w // 2, y + h // 2 + Y, w, h, note.replace("#", "s"), kind, kind, i + 1))
    L += ["", "# the exact key being sung, on the range strip (display only: a tap does nothing)"]
    for m in range(STRIP_LO, STRIP_HI + 1):
        x, y, w, h = strip_key(m)
        kind = "nat" if m % 12 in WHITE_PC else "sharp"
        L.append('button cx=%d cy=%d w=%d h=%d key=noop label="" img=images/strip_glow_%s.png img_on=images/strip_glow_%s.png when=sung_key:%d' % (
            x + w // 2, y + h // 2 + Y, w, h, kind, kind, m - STRIP_LO + 1))
    lx, ly, ls = LED
    L += ["", "# input light in the dial: the unlit lens is in the artwork; a see-through lit lens shows over it while the",
          "# engine reports input (soft white) or a locked pitch (bright white). Badges on the no-op key, so a tap does nothing."]
    for i, (st, colour) in enumerate(LED_STATES):
        if colour:
            L.append('button cx=%d cy=%d w=%d h=%d key=noop label="" img=images/led_%s.png img_on=images/led_%s.png when=signal:%d' % (
                lx, ly + Y, ls, ls, st, st, i))
    L += ["", "# Q-Links: four per column (MPC Live II: one press per column) -- the speeds and amount first, then the rest",
          'qlinks "TUNEY" = retune,transition,amount,vibrato,humanize,freq,cents', ""]
    return "\n".join(L)


def main():
    os.makedirs(os.path.join(VST, "artwork"), exist_ok=True)
    img = os.path.join(VST, "images")
    os.makedirs(img, exist_ok=True)
    items = []
    for slug, _, t in THEMES:
        with open(os.path.join(VST, "artwork", "bg_%s.svg" % slug), "w") as f:
            f.write(background(slug, t) + "\n")
        for i, n in enumerate(NOTES):
            _, _, w, h = piano_key(i)
            for on in (0, 1):
                items.append((os.path.join(img, "%s_key_%s_%s.png" % (slug, n.replace("#", "s"), "on" if on else "off")),
                              key_svg(slug, t, n, on, w, h), w, h))
        for on in (0, 1):
            items.append((os.path.join(img, "%s_bypass_%s.png" % (slug, "on" if on else "off")), bypass_svg(slug, t, on), BYPASS[2], BYPASS[3]))
        for r in (KNOB_R, TUNE_R):
            svg, w, h = knob_strip_svg(slug, t, r)
            items.append((os.path.join(img, "%s_knob_r%d.png" % (slug, r)), svg, w, h))
        for name, labels, (w, h, size), weight, colour in (("note", NOTE_LABELS, DIAL_NOTE, 700, t["note"]),
                                                           ("cents", CENTS_LABELS, DIAL_CENTS, 600, t["cents"])):
            svg, sw, sh = dial_strip_svg(t, labels, w, h, size, weight, colour, name == "note")
            items.append((os.path.join(img, "%s_dial_%s.png" % (slug, name)), svg, sw, sh))
        for side in ("prev", "next"):
            for pressed in (0, 1):
                items.append((os.path.join(img, "%s_arrow_%s%s.png" % (slug, side, "_on" if pressed else "")),
                              arrow_svg(t, side, pressed), ARROW_W, SEL_H))
    for kind, (w, h) in (("nat", (WK_W, WK_H)), ("sharp", (BK_W, BK_H))):
        for lit in (0, 1):
            items.append((os.path.join(img, "glow_%s_%s.png" % (kind, "on" if lit else "off")), glow_svg(w, h, lit), w, h))
    for v in range(len(VOICES)):
        items.append((os.path.join(img, "range_%d.png" % v), range_svg(v), RANGE_BOX[2], RANGE_BOX[3]))
    for kind, (w, h) in (("nat", (SK_W, STRIP_H)), ("sharp", (SBK_W, SBK_H))):
        items.append((os.path.join(img, "strip_glow_%s.png" % kind), strip_glow_svg(w, h), w, h))
    for state, colour in LED_STATES[1:]:
        items.append((os.path.join(img, "led_%s.png" % state), led_svg(colour), LED[2], LED[2]))
    render_pngs(items)
    with open(os.path.join(VST, "layout.conf"), "w") as f:
        f.write(layout())
    print("wrote %d themes: backgrounds, %d images, layout.conf" % (len(THEMES), len(items)))


if __name__ == "__main__":
    main()
