#!/usr/bin/env python3
"""Emit the MAGPARTS block of fet_fom.html from the parsed inductor anchors.

WHY THIS EXISTS.  The seven seeded inductors carry a 6 x 7 x 3 REDEXPERT loss
grid each -- 882 numbers in total.  Typing those into the HTML by hand is exactly
the kind of transcription that drifts silently, so they are generated here from
reference/external/inductor_anchors.json, which make_external.py in turn parses
out of the committed Switching_Losses/WE_*.m files.

The generated block is not trusted on its own: tests/engine.test.mjs asserts the
embedded values back against the anchor file, including the log-log fit.

    python3 reference/make_external.py    # refresh the anchors
    python3 reference/emit_magparts.py    # rewrite the block in fet_fom.html
    node --test                           # prove the two still agree
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "..", "fet_fom.html")
ANCHORS = os.path.join(HERE, "external", "inductor_anchors.json")

BEGIN = "/* ==== MAGPARTS BEGIN ==== */"
END = "/* ==== MAGPARTS END ==== */"
PLACEHOLDER = "/* MAGPARTS-INSERT */"


def _num(x):
    """repr() of a float round-trips exactly, so the emitted literal is lossless
    while staying short (15e-06 rather than 0.000015)."""
    return repr(float(x))


def _opt(x):
    return "null" if x is None else _num(x)


def build_block(anchors, bias):
    ax = anchors["axes"]
    L = []
    add = L.append
    add(BEGIN)
    add("/* Magnetic library.  Same discipline as PARTS above: raw seeded values,")
    add(" * an `est` list and a provenance note.  GENERATED -- do not hand-edit;")
    add(" * run reference/emit_magparts.py, which reads")
    add(" * reference/external/inductor_anchors.json (itself parsed from the")
    add(" * committed Switching_Losses/WE_*.m files by make_external.py).")
    add(" *")
    add(" * All seven parts share ONE (f, dI, Idc) axis set, so the axes are carried")
    add(" * once and each part carries only its 126 Pac values, ordered Idc-major,")
    add(" * then f, then dI -- the order the .m files list them in.  indGrid[i] is")
    add(" * the (f, dI, Idc) triple for Pac[i]; tests/engine.test.mjs asserts that")
    add(" * pairing, the seeded L/DCR/Isat values and the fitted exponents back")
    add(" * against the anchor file. */")
    add("var MAGPARTS = (function(){")
    add("  var AXF=" + json.dumps(ax["f"]) + ", AXD=" + json.dumps(ax["dI"]) +
        ", AXI=" + json.dumps(ax["Idc"]) + ";")
    add("  var GRID=[];")
    add("  for(var a=0;a<AXI.length;a++) for(var b=0;b<AXF.length;b++) for(var c=0;c<AXD.length;c++)")
    add("    GRID.push([AXF[b],AXD[c],AXI[a]]);")
    add("  var INDUCTORS={")
    for pn, p in anchors["parts"].items():
        add("  %s:{PN:%s,L:%s,DCR:%s,Isat10:%s,Isat30:%s,Irated:%s," % (
            pn, json.dumps(pn), _num(p["L"]), _num(p["DCR"]),
            _opt(p["Isat10"]), _opt(p["Isat30"]), _opt(p["Irated"])))
        add("    desc:%s, source:%s," % (json.dumps(p["desc"]), json.dumps(p["source"])))
        add("    Pac:[" + ",".join(_num(v) for v in p["Pac"]) + "],")
        add("    est:[],")
        add("    notes:%s}," % json.dumps(
            (p["desc"] + ". " if p["desc"] else "") +
            "L, DCR, Isat and I_rated are the .m header values; the AC-loss grid "
            "is that file's REDEXPERT scrape (duty 0.545, single winding). "
            "Missing Isat@10% is not published rather than estimated.")) 
    add("  };")
    # ---- bias (L vs I) and thermal rise, scraped from REDEXPERT -------------
    add("  /* Bias curves and thermal rise, scraped from Wuerth REDEXPERT")
    add("   * (reference/redexp_pull.py -> data/redexpert_bias.json ->")
    add("   * external/bias_anchors.json).  The committed loss grid above assumes")
    add("   * the NOMINAL inductance; this is what the core actually does.")
    add("   *")
    add("   * Curve[] keeps only the region where REDEXPERT was still modelling the")
    add("   * core (warnOnBias false).  Past that point its reported ripple reverts")
    add("   * to the nominal-inductance value -- L_eff snaps back to L_nom -- so the")
    add("   * curve stops there rather than recording a flattering answer.  th[] is")
    add("   * [I, dI, dT] triples: temperature rise at that bias and that ripple. */")
    add("  var SAT={")
    for pn, p in sorted(bias["parts"].items()):
        cur = p["curve"]
        add("  %s:{I:[%s],L:[%s],IvalidMax:%s,LeffMin:%s," % (
            pn,
            ",".join(_num(r["I"]) for r in cur),
            ",".join(_num(r["Leff"]) for r in cur),
            _num(p["IvalidMax"]), _num(p["LeffMin"])))
        th = [t for t in p["thermal"] if t.get("dT") is not None]
        add("    th:[%s]}," % ",".join(
            "[%s,%s,%s]" % (_num(t["I"]), _num(t["dI"]), _num(round(t["dT"], 1)))
            for t in th))
    add("  };")
    add("  return {ind:INDUCTORS, sat:SAT, indGrid:GRID, indAxes:{f:AXF,dI:AXD,Idc:AXI}};")
    add("})();")
    add(END)
    return "\n".join(L)


def main():
    anchors = json.load(open(ANCHORS))
    bias_path = os.path.join(HERE, "external", "bias_anchors.json")
    bias = json.load(open(bias_path)) if os.path.exists(bias_path) else {"parts": {}}
    if not bias["parts"]:
        print("note: no bias anchors yet -- run redexp_pull.py then make_external.py")
    block = build_block(anchors, bias)
    txt = open(HTML).read()

    if BEGIN in txt and END in txt:
        i = txt.index(BEGIN)
        j = txt.index(END) + len(END)
        new = txt[:i] + block + txt[j:]
        what = "replaced the existing MAGPARTS block"
    elif PLACEHOLDER in txt:
        new = txt.replace(PLACEHOLDER, block, 1)
        what = "filled the MAGPARTS placeholder"
    else:
        print("error: neither the MAGPARTS markers nor %s found in %s"
              % (PLACEHOLDER, HTML), file=sys.stderr)
        return 1

    if new == txt:
        print("no change (%s already current)" % HTML)
        return 0
    with open(HTML, "w") as f:
        f.write(new)
    n = len(anchors["parts"])
    print("%s: %d parts, %d grid rows each" % (what, n, anchors["rows"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
