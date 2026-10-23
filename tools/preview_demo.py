#!/usr/bin/env python3
"""The built skin as it looks in use, one image per theme: MPC's live text filled in with sample values and one
scale's note keys lit. (tools/studio.py preview, which this wraps, leaves live text as outlines and every key off.)

    python3 tools/preview_demo.py <mpc-vst-plugins checkout> out_dir

Offline approximation only: MPC renders the live text itself, in Titillium Web, at the same places.
"""
import os
import sys
import tempfile

MV, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(MV, "tools"))
from PIL import Image, ImageDraw, ImageFont   # noqa: E402
import studio                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_skin_art as A                       # noqa: E402

SKIN = os.path.join(HERE, "..", "vst", "build", "skin", "3DTHC - VST - Tuney", "Plugin Skins")
FONT = os.path.join(MV, "tools", "html_art", "fonts")
LIT = {"C", "D", "E", "F", "G", "A", "B"}                       # C major

orig_rect = ImageDraw.ImageDraw.rectangle
ImageDraw.ImageDraw.rectangle = lambda self, xy, *a, **k: None if k.get("outline") == (70, 110, 160) else orig_rect(self, xy, *a, **k)
f = lambda size, w="SemiBold": ImageFont.truetype(os.path.join(FONT, "TitilliumWeb-%s.ttf" % w), size)
EM = 1 / 1.53   # MPC font heights are ascent + descent; Titillium's letters are about 1/1.53 of that
ImageFont.load_default = lambda size=10: f(max(1, round(size * EM)))   # studio's live names, in Titillium at MPC's size
os.makedirs(OUT, exist_ok=True)

with tempfile.TemporaryDirectory() as tmp:
    import shutil
    rng = Image.open(os.path.join(HERE, "..", "vst", "images", "range_2.png")).convert("RGBA")
    skin = os.path.join(tmp, "skin")                       # the dial's meters drawn blank: their frames go in below
    shutil.copytree(SKIN, skin)
    for m in os.listdir(skin):
        if m.startswith("sh_meter_") or (m.startswith("sh_btn_noop") and Image.open(os.path.join(skin, m)).size == A.RANGE_BOX[2:]):
            Image.new("RGBA", Image.open(os.path.join(skin, m)).size).save(os.path.join(skin, m))
    pages = [p for p, _ in studio.preview(skin, os.path.join(tmp, "p_%d.png")) if "_open" not in p]
    import json
    names = [p["key"] for p in json.load(open(os.path.join(HERE, "..", "vst", "params.json")))["params"]]
    tag = "_mode%d-" % names.index("theme")
    pages = [pages[0]] + sorted(p for p in pages[1:] if tag in p)          # theme 0, then themes 1..3
    for n, ((slug, name, t), page) in enumerate(zip(A.THEMES, pages)):
        im = Image.open(page).convert("RGBA")
        d = ImageDraw.Draw(im)

        def text(cx, cy, s, size, colour, weight="SemiBold", anchor="mm"):
            d.text((cx, cy), s, font=f(size, weight), fill="#" + colour.lstrip("#"), anchor=anchor)

        img = lambda n: Image.open(os.path.join(HERE, "..", "vst", "images", n + ".png")).convert("RGBA")
        im.alpha_composite(rng, A.RANGE_BOX[:2])                            # Tenor's range on the strip
        for black in (0, 1):                                                # the piano: C major lit, singing A3
            for i, note in enumerate(A.NOTES):
                if ("#" in note) != bool(black):
                    continue
                x, y, w, h = A.piano_key(i)
                im.alpha_composite(img("%s_key_%s_%s" % (slug, note.replace("#", "s"), "on" if note in LIT else "off")), (x, y))
                if note == "A":
                    im.alpha_composite(img("glow_nat_on"), (x, y))
        x, y, w, h = A.strip_key(57)                                        # A3 on the range strip
        im.alpha_composite(img("strip_glow_nat"), (x, y))
        for (lab, key, x, w, _, kind), val in zip(A.SELECTS, ("Tenor", "C", "Major", name)):
            if kind == "arrows":
                text(x + w // 2, A.SEL_Y + A.SEL_H // 2, val, round(A.FIELD_TEXT * EM), "eef1f4")
            else:
                text(x + 12, A.SEL_Y + A.SEL_H // 2, val, round(A.FIELD_TEXT * EM), "eef1f4", anchor="lm")
        lx, ly, ls = A.LED                                                  # the input light, locked
        led = Image.open(os.path.join(HERE, "..", "vst", "images", "led_pitch.png")).convert("RGBA")
        im.alpha_composite(led, (lx - ls // 2, ly - ls // 2))
        cx, cy = A.DIAL                                                     # the dial's pictures: A, +18 cents
        for name, frame, (w, h, _), y in (("note", 10, A.DIAL_NOTE, cy - 10), ("cents", 18 + 51, A.DIAL_CENTS, cy + 56)):
            strip = Image.open(os.path.join(HERE, "..", "vst", "images", "%s_dial_%s.png" % (slug, name))).convert("RGBA")
            im.alpha_composite(strip.crop((0, frame * h, w, frame * h + h)), (cx - w // 2, y - h // 2))
        R, KY = A.KNOB_R, A.KNOB_CY
        for x, v in zip(A.KNOB_X, ("75 %", "60 %", "100 %", "50 %", "20 %")):
            text(x, KY - 53 + 148 + 20, v, round(34 * EM), t["knob_value"])
        for (x, y), v in zip(A.TUNE_KNOBS, ("440 HZ", "0 C")):
            text(x, y - 31 + 97 + 17, v, round(28 * EM), t["knob_value"])
        out = os.path.join(OUT, "tuney_%s.png" % slug)
        im.convert("RGB").save(out)
        print(out)
