#!/usr/bin/env python3
"""Pull induction bias (L vs I) and thermal data from Wuerth REDEXPERT.

BUILD-TIME ONLY.  The tool itself never touches the network -- markers.test.mjs
asserts there is no fetch/XHR/external tag in the page -- so everything this
script fetches is committed under reference/data/ and baked into the HTML by
emit_magparts.py.  A test then pins the baked numbers back against the anchor
file, so a scraped value is a tested claim rather than a copy.

WHY THE BIAS CURVE MATTERS.  The committed WE_*.m loss grids assume the nominal
inductance.  Real cores roll off: on 7443634700 the incremental inductance falls
47 -> 8.65 uH between 6 A and 14 A, so the ripple at 12 A is 6.1 A, not the
1.45 A a nominal-L calculation predicts.  The tool used to only WARN about this.
This script recovers the curve so the ripple can be computed at the actual bias.

THE TRAP THIS SCRIPT GUARDS AGAINST.  Past a certain bias REDEXPERT stops
modelling the core and silently falls back to the nominal inductance -- deltail
snaps back to 1.45 A and L_eff back to 47 uH -- while simultaneously dropping
`warnOnBias` from the response and still reporting a physically meaningless
thermal rise (196 K at 25 A).  A naive scrape records "no saturation at 25 A",
which is optimistic exactly where someone would be designing.  So each response
is tagged with whether warnOnBias is present, and the valid region ends there.

Sweeps, per part:
  A. bias   -- a small fixed volt-second excitation (5 V for D = 0.5 at 100 kHz,
               which is balanced), sweeping DC bias.  dI stays small so the
               recovered L_eff is the incremental inductance at that bias.
  B. thermal-- ripple given directly (option 'ripplecurrent'), on a small
               IL x dI grid at the same frequency, giving dT / maxdT per point.

Run:  python3 reference/redexp_pull.py            # fetch anything missing
      python3 reference/redexp_pull.py --refresh  # re-fetch everything
"""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "redexpert_bias.json")
ANCHORS = os.path.join(HERE, "external", "inductor_anchors.json")

GATEWAY = ("https://redexpert.we-online.com/api/v2/simulations/"
           "dcdc-converters/losses/calculus")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Sweep A excitation: balanced (D*Von + (1-D)*Voff = 0) and small, so deltail is
# an incremental measurement rather than a wide flux swing.
F_REF = 100e3
DUTY = 0.5
V_ON = 5.0
V_OFF = -5.0
BIAS_FRACS = (0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90, 1.05, 1.20, 1.40, 1.60)
# Sweep B: (IL fraction of Isat30, dI fraction of Isat30).  Deliberately weighted
# to LOW bias and small ripple: a real design runs at a fraction of Isat, so a
# grid spread evenly up to Isat30 resolves nothing where it is needed.  (The
# first pass used 0.25/0.5/1.0 of Isat30 and returned "out of grid" for every
# realistic operating point.)
THERM_IL = (0.05, 0.12, 0.25, 0.50, 0.85)
THERM_DI = (0.03, 0.08, 0.18, 0.40)
DELAY_S = 0.35


def _get(pn, params, refresh=False):
    """One cached API call.  Returns (payload, cached)."""
    q = urllib.parse.urlencode(params)
    key = pn + "?" + q
    if not refresh and key in _CACHE:
        return _CACHE[key], True
    url = GATEWAY + "/" + pn + "?" + q
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                              "Accept": "application/json"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read().decode("utf-8"))
            _CACHE[key] = payload
            return payload, False
        except Exception as e:                                # noqa: BLE001
            last = e
            time.sleep(1.0 + attempt)
    raise RuntimeError("REDEXPERT request failed for %s: %s" % (key, last))


def _out(payload):
    L = (payload or {}).get("output", {}).get("L")
    return L or None


def _val(L, key):
    """REDEXPERT wraps most fields as {value, unit}; warnOnBias is raw."""
    if L is None or key not in L:
        return None
    f = L[key]
    if isinstance(f, dict):
        return f.get("value")
    return f


def pull(parts, refresh=False):
    global _CACHE
    stats = {"calls": 0, "cached": 0}
    result = _CACHE.setdefault("parts", {})
    for pn, info in parts.items():
        Lnom, isat = info["L"], info["isat"]
        rec = result.setdefault(pn, {"Lnom": Lnom, "Isat30": isat,
                                     "bias": [], "thermal": []})
        # ---- A: incremental inductance against DC bias -------------------
        have = {round(b["I"], 6) for b in rec["bias"]}
        for frac in BIAS_FRACS:
            I = round(frac * isat, 3)
            if I <= 0 or I in have:
                continue
            params = dict(f=F_REF, dc=DUTY, type="single", il_avg_w1=I,
                          option_w1="inductorvoltage",
                          vl_positive_w1=V_ON, vl_negative_w1=V_OFF)
            payload, cached = _get(pn, params, refresh)
            stats["cached" if cached else "calls"] += 1
            L = _out(payload)
            if L is None:
                break
            di = _val(L, "deltail")
            if not di or di <= 0:
                break
            # dI = Von*D/(L_eff*f)  ->  L_eff = Von*D/(dI*f)
            leff = V_ON * DUTY / (di * F_REF)
            rec["bias"].append(dict(
                I=I, dI=di, ilmax=_val(L, "ilmax"), Leff=leff,
                ratio=(Lnom / leff) if leff else None,
                Pac=_val(L, "lossesac"), Pdc=_val(L, "lossesdc"),
                dT=_val(L, "deltat"), dTmax=_val(L, "maxDeltat"),
                ilEf=_val(L, "ilEf"),
                biasValid=_val(L, "warnOnBias"),
            ))
            if not cached:
                time.sleep(DELAY_S)
            # Once the vendor model stops warning about bias it has also stopped
            # modelling the core, so the curve ends here.
            if _val(L, "warnOnBias") is None:
                break
        # ---- B: thermal and loss against (IL, dI) -------------------------
        # The thermal grid must stay RECTANGULAR, because the engine interpolates
        # it bilinearly and needs all four corners of the bracketing cell.  So
        # the current THERM_* definition is authoritative: stale points from a
        # previous grid shape are dropped rather than unioned in (a union of two
        # grids is not a grid).
        want = {(round(fi * isat, 3), round(fd * isat, 3))
                for fi in THERM_IL for fd in THERM_DI}
        rec["thermal"] = [t for t in rec["thermal"]
                          if (round(t["I"], 6), round(t["dI"], 6)) in want]
        got = {(round(t["I"], 6), round(t["dI"], 6)) for t in rec["thermal"]}
        for fi in THERM_IL:
            for fd in THERM_DI:
                I, dI = round(fi * isat, 3), round(fd * isat, 3)
                if (I, dI) in got:
                    continue
                params = dict(f=F_REF, dc=DUTY, type="single", il_avg_w1=I,
                              option_w1="ripplecurrent", delta_il_w1=dI)
                payload, cached = _get(pn, params, refresh)
                stats["cached" if cached else "calls"] += 1
                L = _out(payload)
                if L is None:
                    continue
                rec["thermal"].append(dict(
                    I=I, dI=dI, f=F_REF,
                    Pac=_val(L, "lossesac"), Pdc=_val(L, "lossesdc"),
                    Pmax=_val(L, "maxLossestot"), dT=_val(L, "deltat"),
                    dTmax=_val(L, "maxDeltat"),
                ))
                if not cached:
                    time.sleep(DELAY_S)
        print("  %-18s bias points %2d, thermal points %2d"
              % (pn, len(rec["bias"]), len(rec["thermal"])))
    _CACHE["requests"] = _CACHE.get("requests", 0) + stats["calls"]
    print("  (%d fetched, %d from cache)" % (stats["calls"], stats["cached"]))
    return _CACHE


def main():
    global _CACHE
    refresh = "--refresh" in sys.argv
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(CACHE) and not refresh:
        with open(CACHE) as f:
            _CACHE = json.load(f)
    else:
        _CACHE = {}

    with open(ANCHORS) as f:
        anchors = json.load(f)
    parts = {}
    for pn, p in anchors["parts"].items():
        isat = p.get("Isat30") or p.get("Isat10")
        if not isat:
            print("  skip %s: no Isat30 in the anchors" % pn)
            continue
        parts[pn.replace("WE_", "")] = {"L": p["L"], "isat": isat}

    print("pulling REDEXPERT bias + thermal data for %d parts" % len(parts))
    data = pull(parts, refresh=refresh)
    data["source"] = GATEWAY
    data["generatedBy"] = "FET_FOM/reference/redexp_pull.py"
    data["excitation"] = dict(f=F_REF, duty=DUTY, vL_on=V_ON, vL_off=V_OFF,
                              note="balanced small-signal excitation for the bias "
                                   "sweep; thermal grid uses a given ripple")
    data["caveat"] = ("Past a certain bias REDEXPERT stops modelling the core: "
                      "deltail reverts to the nominal-inductance value and "
                      "warnOnBias disappears from the response while a nonsense "
                      "thermal rise is still reported.  The bias curve is "
                      "truncated there.")
    with open(CACHE, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")
    n = sum(len(v["bias"]) for v in data["parts"].values())
    m = sum(len(v["thermal"]) for v in data["parts"].values())
    print("wrote %s (%d bias points, %d thermal points)" % (CACHE, n, m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
