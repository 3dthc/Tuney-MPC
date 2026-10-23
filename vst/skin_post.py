#!/usr/bin/env python3
"""Tuney skin touch-up, run by gen_vst.py after the skin is built (vst.json "skin_post"):

    python3 skin_post.py "<skin dir>"

Raises the selectors' value text (the Voice / Key / Scale / Theme fields MPC writes into) from the builder's fixed
26 to FIELD_TEXT, so it reads from a distance. Fails if no selector field is found, so a builder change can't
silently undo it.
"""
import json
import os
import sys

FIELD_TEXT = 34.0   # MPC font height (ascent + descent: about 22 px letters); tools/make_skin_art.py sizes the fields (50 px) for it

skin = sys.argv[1]
path = os.path.join(skin, "Plugin Skins", "TUI.json") if os.path.isdir(os.path.join(skin, "Plugin Skins")) else os.path.join(skin, "TUI.json")
tui = json.load(open(path))
changed = 0


def walk(o):
    global changed
    if isinstance(o, dict):
        if str(o.get("key", "")).startswith("shPopField"):
            for c in o.get("value", {}).get("componentsData", []):
                cd = c.get("componentData", {})
                if cd.get("type") == "Label" and cd.get("data", {}).get("type") == "Value":
                    cd["data"]["textStyle"]["font"]["height"] = FIELD_TEXT
                    changed += 1
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


walk(tui)
if not changed:
    sys.exit("skin_post.py: no selector fields found in %s" % path)
json.dump(tui, open(path, "w"), indent=1)
print("skin_post.py: %d selector values set to %g" % (changed, FIELD_TEXT))
