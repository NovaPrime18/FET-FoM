#!/usr/bin/env python3
"""
reference.py -- faithful Python transcription of the MATLAB loss models in
Switching_Losses/ plus the additions agreed in the approved plan.

Provenance, term by term
------------------------
  conduction        motorDriveLoss.m L.cond, boostBridgeLoss.m P.condLS/HS
  V-I overlap       Mos_switching.m calcLoss, motorDriveLoss.m Eon/Eoff,
                    boostBridgeLoss.m P.ov, DeviceFOM.m eOv
  Coss              boostBridgeLoss.m P.Ecoss ("E_diss = Vout*Qoss(Vout)"),
                    DeviceFOM.m eCos, EPC AN030 section 3
  dead time         motorDriveLoss.m L.dead, boostBridgeLoss.m P.dead
  Qrr               Mos_switching.m LPdrr.  PRESENT in Mos_switching.m,
                    ABSENT from motorDriveLoss.m / boostBridgeLoss.m -- added
                    here because GaN is a true 0 and Si is not, so omitting it
                    would flatter silicon.  EPC AN030 section 4.
  gate / driver     motorDriveLoss.m L.gate, DeviceFOM.m eDrv, boostBridgeLoss.m
                    P.drvDyn/P.drvStat
  FOM (R*E, Nopt)   DeviceFOM.m
  FOM_HS / FOM_SS   EPC AN017 (external, independently published)

Deliberate divergences from the .m sources, all documented in README.md:
  * Qrr is carried into every topology (see above).
  * Terms are scaled in N explicitly (NSCALING table) rather than by mutating
    the device struct in a constructor.
  * Thermal uses a three-term model instead of a flat kT multiplier, with the
    flat multiplier retained as a selectable mode so DeviceFOM.m reproduces.
  * qrrExp defaults to 0 (fixed per-die charge -> group Qrr scales as N), which
    is conservative against silicon; a single datasheet point cannot support
    the Qrr(I/N) ~ Qrr(I) cancellation.

AUTHORING TOOL ONLY.  fet_fom.html does not need Python.  This exists to emit
reference/golden.json, which tests/engine.test.mjs asserts the JS engine against.
"""

import json
import math
import os
import sys

SQRT2 = math.sqrt(2.0)
PI = math.pi

# ---------------------------------------------------------------------------
# Device library -- PER-DIE / PER-IC raw values, exactly as they appear in the
# .m constructors BEFORE the MOSparallel scaling those constructors apply.
# ---------------------------------------------------------------------------
# Fields:
#   kind          'discrete' (external gate loop) or 'bridge' (integrated stage)
#   Rdson25       [ohm]  per die / per IC, 25 C
#   IdcRating     [A]    per-die continuous rating, or None if not established
#   Qoss          [C]    output charge at QossVref, per die  (None if absent)
#   Eoss          [J]    output energy at EossVref, per die  (None if absent)
#   Isd/Vsd       2-point reverse-conduction fit, per die     (None if absent)
#   Vsd0          [V]    scalar reverse knee when no two-point fit exists
#   qrrExp        0 => fixed per-die charge
#   est           set of field names whose value is an ESTIMATE, not datasheet
#
# EPC23102 and EPC23104 are seeded from DeviceFOM.m's cfg.eSpec block (the
# datasheet-derived decomposition), NOT from EPC23104.m's "Cheating" Qg = 250 nC
# fudge, which DeviceFOM.m itself documents as wrong.

PARTS = {
    # -- EPC discrete eGaN ---------------------------------------------------
    "EPC2361": dict(
        PN="EPC2361", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=0.75e-3, RdsonMax=None, IdcRating=101.0,  # DeviceFOM.m cfg.Idc
        BVdss=100.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.1, Vpt=2.1, Qg=28e-9, Qgd=3.8e-9, Qgs=8.5e-9, Qgth=6e-9,
        Qoss=90e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=50e-12, Isd=[50.0, 100.0], Vsd=[2.15, 2.37], Vsd0=None,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-die values from EPC2361.m; datasheet-checked against "
              "EPC2361_datasheet.pdf (Rds(on), Qg, Qgs, Qgd, Qg(th), Qoss, Qrr)",
        est={"kTperC", "RthJC", "RthCA"},
    ),
    "EPC2367": dict(
        PN="EPC2367", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=1.2e-3, RdsonMax=None, IdcRating=101.0,
        BVdss=100.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.1, Vpt=2.1, Qg=17e-9, Qgd=2.4e-9, Qgs=5.3e-9, Qgth=3.8e-9,
        Qoss=54e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=50e-12, Isd=None, Vsd=None, Vsd0=1.4,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=0.5, RthCA=26.6, RthSink=0.0, tauDead=40e-9,
        notes="EPC2367 eGaN FET, 100 V, 1.2 mOhm typ in a 3.3 x 3.3 mm QFN. "
              "Datasheet revised 2026-06-12: Rds(on) 1.2 mOhm typ / 1.5 max "
              "(VGS=5 V, ID=30 A), Qg 17 nC / Qgs 5.3 nC / Qgd 2.4 nC / "
              "Qg(th) 3.8 nC, Qoss 54 nC typ (63 max) at 50 V, Qrr 0, "
              "Vth 1.1 V, VSD 1.4 V at IS=0.5 A, BVDSS 100 V, ID 101 A, "
              "RthJC(top) 0.5 K/W with RthJB 2.4, RthJA_EVB 29, "
              "RthJA_JEDEC 50, TjMax 150 C. ESTIMATES (no datasheet row): "
              "Vpt 2.1 V from the EPC GaN family, kTperC is the GaN default, "
              "CSI is the 3.3x3.3-package default, and RthCA = RthJA_EVB 29 "
              "- RthJB 2.4. The datasheet publishes one VSD point only, so "
              "dead time uses it as a scalar drop.",
        est={"kTperC", "Vpt", "CSI", "RthCA"},
    ),
    "EPC2304": dict(
        PN="EPC2304", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=3.5e-3, RdsonMax=None, IdcRating=133.0,
        BVdss=200.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.5, Vpt=2.1, Qg=21e-9, Qgd=2e-9, Qgs=7.5e-9, Qgth=5.2e-9,
        Qoss=120e-9, QossVref=100.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=50e-12, Isd=None, Vsd=None, Vsd0=1.8,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=0.2, RthCA=19.5, RthSink=0.0, tauDead=40e-9,
        notes="EPC2304 eGaN FET, 200 V, 3.5 mOhm typ / 5 max in a "
              "top-side-cooled 3 x 5 mm PQFN. Datasheet revised 2026-06-19: "
              "Rds(on) 3.5 mOhm typ / 5 max (VGS=5 V, ID=30 A), Qg 21 nC "
              "typ / 26 max, Qgs 7.5 nC, Qgd 2 nC, Qg(th) 5.2 nC, Qoss 120 "
              "nC typ (145 max) at VDS=100 V, Qrr 0, Vth 1.5 V, VSD 1.8 V "
              "at IS=0.5 A, BVDSS 200 V, ID 133 A (TJ <= 125 C), "
              "RthJC(top) 0.2 K/W with RthJB 1.5, RthJA_EVB 21, "
              "RthJA_JEDEC 45, TjMax 150 C. ESTIMATES (no datasheet row): "
              "Vpt 2.1 V from the EPC GaN family, kTperC is the GaN "
              "default, CSI is the PQFN-package default (EPC2367's "
              "convention), and RthCA = RthJA_EVB 21 - RthJB 1.5. The "
              "datasheet publishes one VSD point only, so dead time uses "
              "it as a scalar drop.",
        est={"kTperC", "Vpt", "CSI", "RthCA"},
    ),
    "EPC2305": dict(
        PN="EPC2305", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=2.2e-3, RdsonMax=None, IdcRating=133.0,
        BVdss=150.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.1, Vpt=2.1, Qg=22e-9, Qgd=2.1e-9, Qgs=6.6e-9, Qgth=4.6e-9,
        Qoss=103e-9, QossVref=75.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=50e-12, Isd=None, Vsd=None, Vsd0=1.4,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=0.2, RthCA=19.5, RthSink=0.0, tauDead=40e-9,
        notes="EPC2305 eGaN FET, 150 V, 2.2 mOhm typ / 3.0 max in a "
              "top-side-cooled 3 x 5 mm PQFN 'Thermal-Max'. Datasheet "
              "revised 2026-06-12: Rds(on) 2.2 mOhm typ / 3.0 max "
              "(VGS=5 V, ID=30 A), Qg 22 nC typ / 28.6 max, Qgs 6.6 nC, "
              "Qgd 2.1 nC, Qg(th) 4.6 nC, Qoss 103 nC typ (116 max) at "
              "VDS=75 V, Qrr 0, Vth 1.1 V, VSD 1.4 V at IS=0.5 A, "
              "BVDSS 150 V, ID 133 A (TJ <= 125 C), RthJC(top) 0.2 K/W "
              "with RthJB 1.5, RthJA_EVB 21, RthJA_JEDEC 45, TjMax 150 C. "
              "ESTIMATES (no datasheet row): Vpt 2.1 V from the EPC GaN "
              "family, kTperC is the GaN default, CSI is the PQFN-package "
              "default (EPC2367's convention), and RthCA = RthJA_EVB 21 - "
              "RthJB 1.5. The datasheet publishes one VSD point only, so "
              "dead time uses it as a scalar drop.",
        est={"kTperC", "Vpt", "CSI", "RthCA"},
    ),
    "EPC2218": dict(
        PN="EPC2218", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=2.4e-3, RdsonMax=None, IdcRating=60.0,  # DeviceFOM.m cfg.Idc
        BVdss=100.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.1, Vpt=2.1, Qg=10.5e-9, Qgd=1.5e-9, Qgs=3.2e-9, Qgth=1.9e-9,
        Qoss=46e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=300e-12, Isd=[50.0, 100.0], Vsd=[2.3, 2.65], Vsd0=None,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-die values from EPC2218.m",
        est={"kTperC", "RthJC", "RthCA"},
    ),
    "EPC2252": dict(
        PN="EPC2252", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=8e-3, RdsonMax=None, IdcRating=None,
        BVdss=100.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.2, Vpt=2.1, Qg=3.5e-9, Qgd=0.5e-9, Qgs=1e-9, Qgth=0.7e-9,
        Qoss=15e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=300e-12, Isd=None, Vsd=None, Vsd0=2.2,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="EPC2252.m (note: that file's function is misnamed EPC2044); "
              "scalar Vsd only, so dead time uses a constant drop",
        est={"kTperC", "RthJC", "RthCA"},
    ),
    "EPC2204": dict(
        PN="EPC2204", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=4.4e-3, RdsonMax=None, IdcRating=None,
        BVdss=100.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.1, Vpt=2.1, Qg=5.7e-9, Qgd=0.8e-9, Qgs=1.8e-9, Qgth=1e-9,
        Qoss=25e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=300e-12, Isd=None, Vsd=None, Vsd0=1.7,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-die values from EPC2204.m; scalar Vsd only",
        est={"kTperC", "RthJC", "RthCA"},
    ),
    "EPC2044": dict(
        PN="EPC2044", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=7e-3, RdsonMax=None, IdcRating=None,
        BVdss=100.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.4, Vpt=2.2, Qg=4.3e-9, Qgd=0.5e-9, Qgs=1.3e-9, Qgth=1e-9,
        Qoss=15e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=300e-12, Isd=None, Vsd=None, Vsd0=2.4,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-die values from EPC2044.m; scalar Vsd only",
        est={"kTperC", "RthJC", "RthCA"},
    ),
    "EPC2065": dict(
        PN="EPC2065", vendor="EPC", technology="GaN", kind="discrete",
        Rdson25=2.7e-3, RdsonMax=None, IdcRating=None,
        BVdss=100.0, VgsRec=5.0, kTperC=0.006,
        Vth=1.2, Vpt=2.3, Qg=9.4e-9, Qgd=1.7e-9, Qgs=2.6e-9, Qgth=2.0e-9,
        Qoss=33e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=300e-12, Isd=[5.0, 50.0], Vsd=[2.0, 2.6], Vsd0=None,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-die values from EPC2065.m",
        est={"kTperC", "RthJC", "RthCA"},
    ),
    # -- Silicon discrete ----------------------------------------------------
    "IRF7759": dict(
        PN="IRF7759", vendor="Infineon (IR)", technology="Si", kind="discrete",
        Rdson25=1.8e-3, RdsonMax=None, IdcRating=None,
        BVdss=75.0, VgsRec=10.0, kTperC=0.008,
        Vth=3.0, Vpt=5.0, Qg=200e-9, Qgd=62e-9, Qgs=48e-9, Qgth=37e-9,
        Qoss=60e-9, QossVref=50.0, qossExp=0.5, Qrr=150e-9, qrrExp=0.0,
        CSI=300e-12, Isd=[10.0, 100.0], Vsd=[0.7, 0.83], Vsd0=None,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=1.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-die values from IRF7759.m. Qrr = 150 nC is the whole point "
              "of the GaN-vs-Si comparison. BVdss/VgsRec are estimates: the "
              ".m file carries no ratings.",
        est={"kTperC", "RthJC", "RthCA", "BVdss", "VgsRec"},
    ),
    "IAUTN08S7N006ATMA1": dict(
        PN="IAUTN08S7N006ATMA1", vendor="Infineon", technology="Si",
        kind="discrete",
        Rdson25=0.53e-3, RdsonMax=0.57e-3, IdcRating=350.0,
        BVdss=80.0, VgsRec=10.0, kTperC=0.008,
        Vth=2.8, Vpt=4.4, Qg=229e-9, Qgd=40e-9, Qgs=70e-9, Qgth=44.6e-9,
        Qoss=572.8e-9, QossVref=50.0, qossExp=0.5, Qrr=69e-9, qrrExp=0.0,
        CSI=300e-12, Isd=None, Vsd=None, Vsd0=0.85,
        Eoss=None, EossVref=None, tsw=None, eiRef=None, eiVref=None,
        Qdrv=None, Iq=None, Vcc=None,
        RthJC=0.38, RthCA=14.42, RthSink=0.0, tauDead=40e-9,
        notes="IAUTN08S7N006 (OPN IAUTN08S7N006ATMA1) -- Infineon OptiMOS 7, "
              "80 V automotive Si MOSFET in TOLL (PG-HSOF-8-9). Datasheet "
              "IAUTN08S7N006-Data-Sheet-10-Infineon Rev 1.0, 2026-03-17: "
              "Rds(on) 0.53 mOhm typ / 0.57 max (VGS=10 V, ID=100 A), "
              "Qg 229 nC / Qgs 70 nC / Qgd 40 nC, Vplateau 4.4 V, Vth 2.8 V, "
              "Qrr 69 nC (VR=40 V, IF=50 A), VSD 0.85 V typ at IF=100 A, "
              "RthJC 0.38 K/W, TjMax 175 C. ESTIMATES (no datasheet row): Qgth "
              "from Ciss*Vth (44.6 nC); Qoss from Coss 6404 pF at VDS=40 V via "
              "the V^-0.5 law (572.8 nC at 50 V); kTperC is the Si default; "
              "RthCA = RthJA typ 14.8 - RthJC max 0.38; CSI is the "
              "discrete-package default. The datasheet publishes one VSD point "
              "only, so dead time uses it as a scalar drop.",
        est={"kTperC", "RthCA", "Qgth", "Qoss", "QossMax", "CSI"},
    ),
    # -- Integrated half-bridges (per IC; one IC = one leg) ------------------
    "EPC23102": dict(
        PN="EPC23102", vendor="EPC", technology="GaN", kind="bridge",
        Rdson25=5.2e-3, RdsonMax=6.6e-3, IdcRating=35.0,
        BVdss=100.0, VgsRec=None, kTperC=0.006,
        Vth=None, Vpt=None, Qg=None, Qgd=None, Qgs=None, Qgth=None,
        Qoss=None, QossVref=None, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=None, Isd=[0.0, 10.0], Vsd=[1.7, 1.7 + 10 * 5.2e-3], Vsd0=1.7,
        Eoss=0.5e-6, EossVref=48.0, tsw=8.96e-9, eiRef=0.20e-6, eiVref=48.0,
        Qdrv=34.4e-9, Iq=22.6e-3, Vcc=5.0,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-IC values from DeviceFOM.m cfg.eSpec.EPC23102 and "
              "EPC23102.m; Eoss 0.5 uJ at 48 V, Qdrv 34.4 nC, Iq 22.6 mA",
        est={"kTperC", "RthJC", "RthCA", "RthSink"},
    ),
    "EPC23104": dict(
        PN="EPC23104", vendor="EPC", technology="GaN", kind="bridge",
        Rdson25=8.7e-3, RdsonMax=11e-3, IdcRating=15.0,
        BVdss=100.0, VgsRec=None, kTperC=0.006,
        Vth=None, Vpt=None, Qg=None, Qgd=None, Qgs=None, Qgth=None,
        Qoss=None, QossVref=None, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=None, Isd=None, Vsd=None, Vsd0=1.7,
        Eoss=0.34e-6, EossVref=48.0, tsw=None, eiRef=0.20e-6, eiVref=48.0,
        Qdrv=7.8e-9, Iq=15.2e-3, Vcc=5.0,
        RthJC=2.0, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-IC values from DeviceFOM.m cfg.eSpec.EPC23104 (the 2026 "
              "datasheet decomposition), NOT EPC23104.m's Qg=250 nC fudge; "
              "publishes no Eon/Eoff, so eiRef is carried from the 23102",
        est={"kTperC", "RthJC", "RthCA", "eiRef"},
    ),
    "ISG3202LA": dict(
        PN="ISG3202LA", vendor="Innoscience", technology="GaN", kind="bridge",
        Rdson25=2.4e-3, RdsonMax=3.2e-3, IdcRating=60.0,
        BVdss=100.0, VgsRec=None, kTperC=0.0083,
        Vth=None, Vpt=None, Qg=None, Qgd=None, Qgs=None, Qgth=None,
        Qoss=50e-9, QossVref=50.0, qossExp=0.5, Qrr=0.0, qrrExp=0.0,
        CSI=None, Isd=[20.0, 60.0], Vsd=[1.65, 2.09], Vsd0=1.5,
        Eoss=0.875e-6, EossVref=50.0, tsw=8e-9, eiRef=None, eiVref=None,
        Qdrv=39.9e-9, Iq=75e-6, Vcc=5.0,
        RthJC=4.1, RthCA=10.0, RthSink=0.0, tauDead=40e-9,
        notes="per-IC values from ISG3202LA.m; datasheet-checked against "
              "ISG3202LA_datasheet.pdf (Rds(on), Qoss, Eoss, BVDSS); tsw is an "
              "ESTIMATE: that datasheet publishes no Eon/Eoff",
        est={"tsw", "RthCA"},
    ),
}

# Datasheet LIMITS, kept apart from the electrical model above so that block
# stays a faithful copy of the .m constructors.  TjMax is verified against a
# datasheet PDF committed in this repo for EPC2361, EPC2367, EPC2304, EPC2305
# and ISG3202LA (all 150 C) and for IAUTN08S7N006ATMA1 (175 C); the rest are
# flagged as estimates.
LIMITS = {
    "EPC2361": {"TjMax": 150, "RdsonMax": 1.0e-3, "QossMax": 112e-9},
    "EPC2367": {"TjMax": 150, "RdsonMax": 1.5e-3, "QossMax": 63e-9},
    "EPC2304": {"TjMax": 150, "RdsonMax": 5.0e-3, "QossMax": 145e-9},
    "EPC2305": {"TjMax": 150, "RdsonMax": 3.0e-3, "QossMax": 116e-9},
    "EPC2218": {"TjMax": 150, "estAdd": ["TjMax"]},
    "EPC2252": {"TjMax": 150, "estAdd": ["TjMax"]},
    "EPC2204": {"TjMax": 150, "estAdd": ["TjMax"]},
    "EPC2044": {"TjMax": 150, "estAdd": ["TjMax"]},
    "EPC2065": {"TjMax": 150, "estAdd": ["TjMax"]},
    "IRF7759": {"TjMax": 175, "QrrMax": 225e-9, "estAdd": ["TjMax", "QrrMax"]},
    "IAUTN08S7N006ATMA1": {"TjMax": 175, "QossMax": 744.6e-9,
                           "QrrMax": 138e-9},
    "EPC23102": {"TjMax": 150, "estAdd": ["TjMax"]},
    "EPC23104": {"TjMax": 150, "estAdd": ["TjMax"]},
    "ISG3202LA": {"TjMax": 150},
}
for _pn, _L in LIMITS.items():
    if _pn not in PARTS:
        continue
    _add = _L.get("estAdd", [])
    for _k, _v in _L.items():
        if _k != "estAdd":
            PARTS[_pn][_k] = _v
    if _add:
        PARTS[_pn]["est"] = sorted(set(PARTS[_pn].get("est", [])) | set(_add))


def with_max(part):
    """typ/max: swap the model onto the datasheet maximum where one exists."""
    p = dict(part)
    missing = []
    for typ, mx in (("Rdson25", "RdsonMax"), ("Qoss", "QossMax"), ("Qrr", "QrrMax")):
        if part.get(mx) is not None:
            p[typ] = part[mx]
        elif part.get(typ):
            missing.append(mx)
    return p, missing


TOPOLOGIES = ("threephase", "buck", "boost", "fourswitch")

# ---------------------------------------------------------------------------
# Term x N-scaling -- the authoritative table from the approved plan.
# N = dice per switch position; R1 = Rdson_perdie / N; I_die = I_group / N.
# ---------------------------------------------------------------------------
NSCALING = {
    "cond_discrete":    dict(exp=(-1, -1), note="Rdson/N"),
    "cond_bridge":      dict(exp=(-1, -1), note="Rdson/N"),
    "overlap_discrete": dict(exp=(1, 1),   note="Qch,Qgd x N with a shared driver"),
    "overlap_bridge":   dict(exp=(0, 0),   note="per-IC energy at Icom/N, fixed tsw"),
    "coss":             dict(exp=(1, 1),   note="Qoss x N"),
    # Dead-time loss FALLS with N: the group still carries Icom but the reverse
    # drop is Vsd(Icom/N), so paralleling dice lowers Vsd.  Linear region gives
    # N^-1, and the max(.,0)/knee clamp flattens it toward N^0.  (This corrects
    # the review note, which suggested N^0..N^1 -- the sign is the other way.)
    "dead":             dict(exp=(-1, 0),  note="Vsd(Icom/N)*Icom: N^-1 .. N^0"),
    "qrr":              dict(exp=(1, 1),   note="N*Qrr_ref (qrrExp=0 default)"),
    # Loop ringing uses the LAYOUT inductance, so once the current is fixed it is
    # independent of how many dice share the position.
    "ring":             dict(exp=(0, 0),   note="0.5*L_loop*I^2*fsw: layout L, N-independent"),
    "gate":             dict(exp=(1, 1),   note="Qg x N"),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _qoss_ref(part):
    """Per-die output charge at its reference voltage, from Qoss or from Eoss.

    DeviceFOM.m / boostBridgeLoss.m recover the charge from an energy-specified
    part as Qoss = 3*Eoss/V.  Returns (Qref, Vref) or (None, None).
    """
    if part.get("Qoss"):
        return part["Qoss"], part["QossVref"]
    if part.get("Eoss") and part.get("EossVref"):
        vref = part["EossVref"]
        return 3.0 * part["Eoss"] / vref, vref
    return None, None


def _eoss_ref(part):
    """Per-die stored energy at its reference voltage.  Uses the specified Eoss
    when there is one; otherwise recovers it from the charge as Vref*Qref/3."""
    if part.get("Eoss") and part.get("EossVref"):
        return part["Eoss"], part["EossVref"]
    qref, vref = _qoss_ref(part)
    if qref:
        return vref * qref / 3.0, vref
    return None, None


def _qoss_at(part, v):
    qref, vref = _qoss_ref(part)
    if qref is None:
        return None
    return qref * (v / vref) ** part.get("qossExp", 0.5)


def _eoss_at(part, v):
    eref, vref = _eoss_ref(part)
    if eref is None:
        return None
    return eref * (v / vref) ** 1.5


def mkWarn(severity, code, title, detail):
    """Structured warning, mirroring the JS engine.

    severity: 'critical' | 'caution' | 'info'.  Consumers branch on `code`,
    never parse `detail`.
    """
    return {"severity": severity, "code": code, "title": title, "detail": detail}


def gate_config(part, op):
    """Effective gate rail / loop resistance.

    DeviceFOM.m: if the requested drive is within 0.5 V of the plateau the rail
    is unusable (IgOn -> 0, overlap time -> infinity), so switch to the 12 V
    rail / 1.9 ohm.  That fires for every silicon part with Vpt ~= 5 V driven
    at 5 V.  Returns (Vdrv, Ron, Roff, auto, warning).
    """
    vdrv = op.get("Vdrv", 5.0)
    ron = op.get("Ron", 2.6)
    roff = op.get("Roff", 0.6)
    vpt = part.get("Vpt")
    if part["kind"] == "bridge" or vpt is None:
        return vdrv, ron, roff, False, None
    if vdrv <= vpt + 0.5:
        if op.get("gateRailAuto", True):
            return 12.0, 1.9, 1.9, True, mkWarn(
                "caution", "gate_rail_auto", "Gate drive rail below the plateau",
                "%s has a %.1f V Miller plateau, so a %.1f V rail would drive "
                "Ig_on toward zero and make the overlap time non-physical. The "
                "tool switched to the 12 V rail / 1.9 ohm, following the "
                "DeviceFOM.m rule." % (part["PN"], vpt, vdrv))
        return vdrv, ron, roff, False, mkWarn(
            "critical", "gate_rail_nonphysical", "Gate drive at or below the plateau",
            "%s was asked for %.1f V against a %.1f V plateau, and automatic rail "
            "selection is off. The overlap time is not physical, so the switching "
            "terms are meaningless." % (part["PN"], vdrv, vpt))
    return vdrv, ron, roff, False, None


def gate_for(part, op, slot=None):
    """Resolve the gate-drive rail for ONE device, mirroring gateFor() in the JS.

    A Si MOSFET is quoted at 10 V and a GaN HEMT at 5 V, so forcing one shared
    rail on an A/B comparison either under-drives the silicon part (Ig_on
    collapses, the overlap is inflated) or over-drives the GaN part.  Precedence:
    per-device override > explicit shared op['Vdrv'] > the part's recommended
    rail VgsRec > 5 V.  A blank per-device field (None) means "drive each device
    at its recommended rail".  Ron/Roff stay board-level shared values.
    """
    o = dict(op)
    v = None
    if slot:
        v = o.get("Vdrv" + slot)
    if v is None:
        v = o.get("Vdrv")
    if v is None:
        v = part.get("VgsRec")
    if v is None:
        v = 5.0
    o["Vdrv"] = v
    return o


def rcsi_of(part, dev_qg_group, icom, N, lcsi):
    """Effective series gate resistance from common-source inductance.

    motorDriveLoss.m: Rcsi = (CSI + Lcsi) * Icom / Qg, with dev.CSI already
    divided by N and dev.Qg the N-die total.  So the per-die CSI contribution
    falls as 1/N^2 and the shared source-plane Lcsi only as 1/N.
    """
    csi = part.get("CSI")
    if csi is None:
        csi = 0.0
    if dev_qg_group <= 0:
        return 0.0
    return (csi / N + lcsi) * icom / dev_qg_group


# ---------------------------------------------------------------------------
# operating point -> per-leg groups
# ---------------------------------------------------------------------------
def derive(op, topology=None):
    """Reduce an operating point to the list of switch groups the loss model
    sums over, plus the scalars the FOM needs.

    Each group is a dict:
      Vsw        node swing [V]
      nHard      hard turn-ons per carrier (0 for an idle, dc-clamped leg)
      deadLegs   1 if this group's leg has dead time, else 0
      positions  parallel switch positions in the group (2 for a leg)
      I_rms      rms current through the group   [A]
      I_dc       dc current for an idle leg      [A]
      mode       'switch' | 'idle'
    """
    t = topology or op["topology"]
    fsw = op["fsw"]

    if t == "threephase":
        Vdc = op["Vdc"]
        M = op.get("M", 1.0)
        PF = op.get("PF", 0.9)
        Irms = op["Irms"]
        Ipk = op.get("Ipk", Irms * SQRT2)
        Icom = 2.0 * Ipk / PI
        Vph_rms = M * Vdc / (2.0 * SQRT2)
        Pout = op.get("Pout", 3.0 * Vph_rms * Irms * PF)
        groups = [dict(Vsw=Vdc, nHard=1, deadLegs=1, positions=2,
                       I_rms=Irms, I_dc=0.0, mode="switch") for _ in range(3)]
        return dict(groups=groups, nLegsTotal=3, nSwitchLegs=3, Icom=Icom,
                    Ipk=Ipk, Pout=Pout, D=None, IL_avg=None, IL_rms=None,
                    mode="foc", warnings=[])

    if t in ("buck", "boost"):
        Vin, Vout, Pout = op["Vin"], op["Vout"], op["Pout"]
        L = op.get("L")
        if t == "buck":
            D = Vout / Vin
            Iout = Pout / Vout
            IL_avg = Iout
            dIL = (Vout * (1 - D) / (L * fsw)) if L else 0.0
            Vsw = Vin
        else:
            D = 1.0 - Vin / Vout
            Iout = Pout / Vout
            IL_avg = Pout / Vin
            dIL = (Vin * D / (L * fsw)) if L else 0.0
            Vsw = Vout
        IL_rms = math.sqrt(IL_avg ** 2 + dIL ** 2 / 12.0)
        groups = [dict(Vsw=Vsw, nHard=1, deadLegs=1, positions=2,
                       I_rms=IL_rms, I_dc=0.0, mode="switch")]
        return dict(groups=groups, nLegsTotal=1, nSwitchLegs=1, Icom=IL_avg,
                    Ipk=IL_avg + dIL / 2.0, Pout=Pout, D=D, IL_avg=IL_avg,
                    IL_rms=IL_rms, dIL=dIL, mode=t, warnings=[])

    if t == "fourswitch":
        Vin, Vout, Pout = op["Vin"], op["Vout"], op["Pout"]
        L = op.get("L")
        warn = []
        band = op.get("modeBand", 0.02)
        if Vin > Vout * (1 + band):
            mode = "buck"
        elif Vin < Vout * (1 - band):
            mode = "boost"
        else:
            mode = "buckboost"
            warn.append(mkWarn(
                "caution", "mode_buckboost", "Vin ~= Vout -- both legs switching",
                "Vin = %.1f V and Vout = %.1f V are inside the mode-switch band, so "
                "the 4-switch converter is treated as switching both legs. The "
                "inductor-current model is nominal here (D = 0.5)." % (Vin, Vout)))
        if mode == "buck":
            D = Vout / Vin
            IL_avg = Pout / Vout
            dIL = (Vout * (1 - D) / (L * fsw)) if L else 0.0
            groups = [
                dict(Vsw=Vin, nHard=1, deadLegs=1, positions=2,
                     I_rms=math.sqrt(IL_avg ** 2 + dIL ** 2 / 12), I_dc=0.0,
                     mode="switch"),
                dict(Vsw=0.0, nHard=0, deadLegs=0, positions=1,
                     I_rms=0.0, I_dc=IL_avg, mode="idle"),
            ]
        elif mode == "boost":
            D = 1.0 - Vin / Vout
            IL_avg = Pout / Vin
            dIL = (Vin * D / (L * fsw)) if L else 0.0
            groups = [
                dict(Vsw=0.0, nHard=0, deadLegs=0, positions=1,
                     I_rms=0.0, I_dc=IL_avg, mode="idle"),
                dict(Vsw=Vout, nHard=1, deadLegs=1, positions=2,
                     I_rms=math.sqrt(IL_avg ** 2 + dIL ** 2 / 12), I_dc=0.0,
                     mode="switch"),
            ]
        else:
            D = 0.5
            IL_avg = Pout / max(Vin, Vout)
            dIL = (Vin * D / (L * fsw)) if L else 0.0
            IL_rms = math.sqrt(IL_avg ** 2 + dIL ** 2 / 12)
            groups = [
                dict(Vsw=Vin, nHard=1, deadLegs=1, positions=2,
                     I_rms=IL_rms, I_dc=0.0, mode="switch"),
                dict(Vsw=Vout, nHard=1, deadLegs=1, positions=2,
                     I_rms=IL_rms, I_dc=0.0, mode="switch"),
            ]
        IL_rms = max(g["I_rms"] for g in groups)
        return dict(groups=groups, nLegsTotal=2, nSwitchLegs=2 if mode == "buckboost" else 1,
                    Icom=IL_avg, Ipk=IL_avg + dIL / 2.0, Pout=Pout, D=D,
                    IL_avg=IL_avg, IL_rms=IL_rms, dIL=dIL, mode=mode, warnings=warn)

    raise ValueError("unknown topology %r" % t)


# ---------------------------------------------------------------------------
# loss model
# ---------------------------------------------------------------------------
def _dead_vsd(part, i_die):
    """Reverse-conduction drop at the per-die current.

    Two-point fit when the device has one (motorDriveLoss.m / boostBridgeLoss.m),
    clamped at 0; constant scalar when the .m file only carries a knee.
    """
    isd = part.get("Isd")
    vsd = part.get("Vsd")
    if isd and vsd:
        rsd = (vsd[1] - vsd[0]) / (isd[1] - isd[0])
        v = vsd[1] + (i_die - isd[1]) * rsd
        return max(v, 0.0)
    v0 = part.get("Vsd0")
    return max(v0, 0.0) if v0 is not None else None


def compute_losses(part, op, N, temp_mode="converged", coss_basis="VQoss",
                   kT=None, relax=1.0, max_iter=200, tol=1e-4, slot=None):
    """FET-only loss breakdown.

    temp_mode:
      'converged'  iterate Rds(on) against the three-term thermal model
      'none'       Rds(on) at 25 C (no kT at all)
      'flat'       Rds(on) * kT (the DeviceFOM.m convention)
    coss_basis: 'VQoss' (default, EPC AN030), '2Eoss', 'Eoss'
    slot:       'A'/'B' selects that device's own gate rail (gate_for)
    """
    op = gate_for(part, op, slot)
    d = derive(op, op.get("topology"))
    groups = d["groups"]
    Icom = d["Icom"]
    fsw = op["fsw"]
    lcsi = op.get("Lcsi", 0.0)
    tau = op.get("tauDead", part.get("tauDead", 40e-9))
    warnings = list(d["warnings"])

    # Advanced overrides: op-level qossExp / qrrExp beat the per-part value.
    if op.get("qossExp") is not None or op.get("qrrExp") is not None:
        part = dict(part)
        if op.get("qossExp") is not None:
            part["qossExp"] = op["qossExp"]
        if op.get("qrrExp") is not None:
            part["qrrExp"] = op["qrrExp"]

    vdrv, ron, roff, auto, gw = gate_config(part, op)
    if gw:
        warnings.append(gw)
    # Underdrive is the misleading case for a comparator: it inflates Rds(on)
    # and the overlap time.  Overdrive is checked against the auto-selected rail,
    # which is deliberately 12 V for silicon, so warn on the REQUESTED voltage.
    vgsrec = part.get("VgsRec")
    if vgsrec and vdrv < vgsrec:
        warnings.append(mkWarn(
            "caution", "gate_underdrive", "Gate drive below the recommended level",
            "%s wants about %.0f V of gate drive, but %.1f V was requested. "
            "Rds(on) is quoted at the higher rail, so the conduction and overlap "
            "terms are both overstated." % (part["PN"], vgsrec, vdrv)))
    bv = part.get("BVdss")
    maxvsw = max(g["Vsw"] for g in groups)
    if bv and maxvsw > bv:
        warnings.append(mkWarn(
            "critical", "bvs_exceeded", "Switch node exceeds the device rating",
            "The node swings %.0f V into a %.0f V device. The loss numbers are "
            "computed but the part is being operated outside its rating."
            % (maxvsw, bv)))

    # typ/max: move the whole model onto the datasheet maximum where one exists.
    if op.get("useMax"):
        part, _missing = with_max(part)
        if _missing:
            warnings.append(mkWarn(
                "info", "typ_max_partial", "Typ/max toggle applied only in part",
                "No datasheet maximum is recorded for %s, so those stay on the "
                "typical value. Without a max, the typical figure is the optimistic "
                "one." % ", ".join(_missing)))

    is_bridge = part["kind"] == "bridge"
    N = float(N)
    rdson25 = part["Rdson25"]
    lloop = op.get("Lloop", 0.0) or 0.0
    qrrTjPerC = op.get("qrrTjPerC", 0.01)

    # Half the loop energy is dissipated at each hard commutation.  With L_loop
    # zero the tool silently omits it, so say so rather than let it look complete.
    _hard = [g for g in groups if g["nHard"] > 0]
    if _hard and not (lloop > 0):
        _est = sum(g["nHard"] * fsw * 0.5 * 5e-9 *
                   (g["I_rms"] ** 2 if g["mode"] == "switch" else g["I_dc"] ** 2)
                   for g in _hard)
        warnings.append(mkWarn(
            "info", "lloop_uncounted", "Loop-inductance ringing not counted",
            "L_loop is 0, so the 0.5*L*I^2 ringing at each hard commutation "
            "is omitted. It does not fall with N; at 5 nH it is about %.1f W "
            "here. Set L_loop in Advanced." % _est))

    # --- N-independent geometry (once) -------------------------------------
    if is_bridge:
        qg_group = None
    else:
        qg_group = part["Qg"] * N
        qch_pd = (part["Qgs"] - part["Qgth"])
        qgd_pd = part["Qgd"]
        qsw_pd = qch_pd + qgd_pd
        # DeviceFOM.m's FOM ignores common-source inductance in the gate loop;
        # motorDriveLoss.m includes it.  'fom' keeps the FOM's clean N^1
        # overlap scaling (which is what makes the closed-form N_opt exact);
        # 'detailed' is the physical model and adds a weak sub-N correction.
        rcsi = (rcsi_of(part, qg_group, Icom, N, lcsi)
                if op.get("gateModel", "detailed") == "detailed" else 0.0)
        ig_on = (vdrv - part["Vpt"]) / (ron + rcsi)
        ig_off = part["Vpt"] / (roff + rcsi)

    def switching_terms(rdson):
        cond = 0.0
        ring = 0.0
        for g in groups:
            if g["mode"] == "switch":
                cond += g["I_rms"] ** 2 * rdson
            else:
                cond += g["I_dc"] ** 2 * rdson
        overlap = coss = dead = qrr = 0.0
        for g in groups:
            Vsw = g["Vsw"]
            if g["nHard"] > 0:
                if is_bridge:
                    if part.get("tsw"):
                        e_ov = 0.5 * Vsw * Icom * part["tsw"]
                    elif part.get("eiRef"):
                        e_ov = part["eiRef"] * (Vsw / part["eiVref"]) * Icom
                    else:
                        e_ov = 0.0
                    overlap += g["nHard"] * fsw * e_ov
                else:
                    qch_g = qch_pd * N
                    qgd_g = qgd_pd * N
                    e_on = 0.5 * Vsw * Icom * (qch_g / ig_on + qgd_g / ig_on)
                    qoss_g = None
                    qref, vref = _qoss_ref(part)
                    if qref is not None:
                        qoss_g = qref * N * (Vsw / vref) ** part.get("qossExp", 0.5)
                    t_rv = min(qgd_g / ig_off,
                               (qoss_g / max(Icom, 1e-9)) if qoss_g else float("inf"))
                    kso = op.get("kSoftOff", 0.22)
                    e_off = kso * 0.5 * Vsw * Icom * t_rv
                    # AN030 2.2.1: the gate-limited CURRENT-fall phase.  Whenever
                    # t_ifall exceeds the Coss commutation time the node is already
                    # at the bus while the current falls, so it is hard switching
                    # and is NOT reduced by kSoftOff -- that factor models the soft
                    # voltage rise only.
                    e_fall = 0.5 * Vsw * Icom * (qch_g / ig_off)
                    overlap += g["nHard"] * fsw * (e_on + e_off + e_fall)
                # Coss, on the selected basis
                if coss_basis == "VQoss":
                    q = _qoss_at(part, Vsw)
                    if q is None:
                        warnings.append(mkWarn(
                            "caution", "coss_unknown",
                            "Output charge not specified",
                            "Neither Qoss nor Eoss is in the %s record, so the "
                            "Coss term is reported as unknown rather than as zero."
                            % part["PN"]))
                        e_cos = None
                    else:
                        e_cos = Vsw * q * N
                elif coss_basis == "2Eoss":
                    e = _eoss_at(part, Vsw)
                    e_cos = None if e is None else 2.0 * e * N
                else:
                    e = _eoss_at(part, Vsw)
                    e_cos = None if e is None else e * N
                if e_cos is not None:
                    coss += g["nHard"] * fsw * e_cos
                # Qrr
                qrr_pd = part.get("Qrr") or 0.0
                if qrr_pd:
                    i_die = Icom / N
                    i_ref = (part.get("Isd") or [1.0, 1.0])[-1]
                    qrr_g = N * qrr_pd * ((i_die / i_ref) ** part.get("qrrExp", 0.0))
                    # Qrr rises with junction temperature (roughly doubling
                    # 25 -> 125 C).
                    qrr_g *= (1.0 + qrrTjPerC * ((Tj if math.isfinite(Tj) else tamb) - 25.0))
                    qrr += g["nHard"] * fsw * Vsw * qrr_g
            if g["deadLegs"] > 0:
                v = _dead_vsd(part, Icom / N)
                if v is not None:
                    dead += g["deadLegs"] * fsw * 2.0 * tau * v * Icom
            # Loop-inductance ringing: 0.5*L*i^2 per hard commutation, averaged
            # over the fundamental.  L_loop is layout, so it does not scale with N.
            if g["nHard"] > 0 and lloop > 0:
                _i2 = (g["I_rms"] ** 2 if g["mode"] == "switch" else g["I_dc"] ** 2)
                ring += g["nHard"] * fsw * 0.5 * lloop * _i2
        return cond, overlap, coss, dead, qrr, ring

    # --- gate / driver ------------------------------------------------------
    if is_bridge:
        n_ic = d["nLegsTotal"] * N
        gate = n_ic * (part["Qdrv"] * part["Vcc"] * fsw + part["Iq"] * part["Vcc"])
    else:
        n_pos = 2 * d["nSwitchLegs"] * N
        gate = n_pos * part["Qg"] * vdrv * fsw

    # --- thermal ------------------------------------------------------------
    n_positions = sum(g["positions"] for g in groups)
    rth_jc = part.get("RthJC") or 0.0
    rth_ca = op.get("RthCA", part.get("RthCA") or 0.0)
    rth_sink = op.get("RthSink", part.get("RthSink") or 0.0)
    tamb = op.get("Tamb", 25.0)
    kTperC = op.get("kTperC", part.get("kTperC") or 0.0)
    rth_mode = op.get("RthMode", "detailed")

    def thermal_resistance():
        # junction->ambient for the hottest position
        if rth_mode == "simple":
            return (rth_ca + rth_sink * n_positions)
        return rth_jc / N + rth_ca + rth_sink * n_positions

    i2sum = sum((g["I_rms"] ** 2 if g["mode"] == "switch" else g["I_dc"] ** 2)
                for g in groups)

    def r_group(mult):
        # resistance of ONE switch position: per-die Rdson / N dice, hot-scaled
        return rdson25 / N * mult

    Tj = tamb
    converged = True
    iters = 0
    if temp_mode == "none":
        rgrp = r_group(1.0)
    elif temp_mode == "flat":
        rgrp = r_group(op.get("kT", 1.25) if kT is None else kT)
    elif kTperC <= 0:
        # Rds(on) does not move with temperature, so no iteration is needed --
        # but the junction still rises above ambient and must be reported.
        rgrp = r_group(1.0)
        _s = switching_terms(rgrp)
        _die = _s[0] + _s[1] + _s[2] + _s[3] + _s[4]
        Tj = tamb + thermal_resistance() * (_die / n_positions if n_positions else 0.0)
    else:
        # analytic runaway guard: gain = dTj/dTj evaluated at 25 C, referenced
        # to the GROUP's conduction.  The per-position paths see
        # P_group/n_positions while the shared sink sees the whole bridge, so the
        # effective resistance against P_group is thermal_resistance()/n_positions.
        # Omitting that divide overstates the gain by n_positions and invents
        # runaway on sane builds.
        cond25 = i2sum * rdson25 / N
        gain = (thermal_resistance() * kTperC * (cond25 / n_positions)
                if n_positions else 0.0)
        if gain >= 1.0:
            rgrp = r_group(1 + kTperC * (tamb - 25))
            cond, overlap, coss, dead, qrr, ring = switching_terms(rgrp)
            die = cond + overlap + coss + dead + qrr
            warnings.append(mkWarn(
                "critical", "thermal_runaway", "Thermal runaway",
                "The self-heating loop gain is %.2f (>= 1), from Rth %.2f C/W, a "
                "tempco of %.4f /C and %.1f W of conduction at 25 C. No junction "
                "temperature is reported: add copper or parallel dice."
                % (gain, thermal_resistance(), kTperC, cond25)))
            return dict(terms=dict(cond=cond, overlap=overlap, coss=coss,
                                   dead=dead, qrr=qrr, ring=ring, gate=gate),
                        die=die, loop=ring, driver=gate, total=die + ring + gate,
                        eff=_eff(d, op, die + ring + gate), Tj=float("nan"),
                        converged=False, gain=gain, iterations=0, rdson=rgrp,
                        N=N, warnings=warnings, derived=d)
        for it in range(max_iter):
            iters = it + 1
            rgrp = r_group(1 + kTperC * (Tj - 25))
            cond, overlap, coss, dead, qrr, ring = switching_terms(rgrp)
            die = cond + overlap + coss + dead + qrr
            p_pos = die / n_positions if n_positions else 0.0
            tj_new = tamb + thermal_resistance() * p_pos
            if abs(tj_new - Tj) < tol:
                Tj = tj_new
                break
            Tj = Tj + relax * (tj_new - Tj)
            if not math.isfinite(Tj) or Tj > 1500.0:
                converged = False
                warnings.append(mkWarn(
                    "critical", "thermal_diverged", "Thermal solution diverged",
                    "The fixed-point iteration ran away to %.0f C, so no junction "
                    "temperature is reported." % Tj))
                Tj = float("nan")
                break
        else:
            converged = False
            warnings.append(mkWarn(
                "caution", "thermal_noconverge", "Thermal solution did not converge",
                "The fixed-point iteration had not settled after %d passes, so the "
                "reported loss does not correspond to a self-consistent junction "
                "temperature." % max_iter))
            Tj = float("nan")

    # make the reported losses self-consistent with the converged Tj
    if temp_mode == "converged" and converged and kTperC > 0 and math.isfinite(Tj):
        rgrp = r_group(1 + kTperC * (Tj - 25))

    # Feasibility, not just arithmetic: a converged Tj above the device limit
    # makes the operating point fictional, so say so loudly.
    if part.get("TjMax") and math.isfinite(Tj) and Tj > part["TjMax"]:
        warnings.append(mkWarn(
            "critical", "tj_exceeded", "Junction temperature above the device limit",
            "Converged Tj is %.0f C against a %d C limit for %s. This operating "
            "point is not feasible as a design point, so the loss comparison against "
            "it is not meaningful: add copper, parallel more dice, or reduce the "
            "current." % (Tj, part["TjMax"], part["PN"])))

    cond, overlap, coss, dead, qrr, ring = switching_terms(rgrp)
    die = cond + overlap + coss + dead + qrr
    return dict(terms=dict(cond=cond, overlap=overlap, coss=coss, dead=dead,
                           qrr=qrr, ring=ring, gate=gate),
                die=die, loop=ring, driver=gate, total=die + ring + gate,
                eff=_eff(d, op, die + ring + gate), Tj=Tj, converged=converged,
                gain=((thermal_resistance() * kTperC
                       * (i2sum * rdson25 / N) / n_positions)
                      if (kTperC > 0 and n_positions) else 0.0),
                iterations=iters, rdson=rgrp, N=N, warnings=warnings, derived=d)


def _eff(d, op, loss):
    pout = d["Pout"]
    if not pout or pout <= 0:
        return None
    return pout / (pout + loss)


# ---------------------------------------------------------------------------
# FOM -- DeviceFOM.m plus the externally published EPC metrics
# ---------------------------------------------------------------------------
def fom_metrics(part, op, N=1, kT=1.25, coss_basis="VQoss", slot=None):
    op = gate_for(part, op, slot)
    if op.get("qossExp") is not None or op.get("qrrExp") is not None:
        part = dict(part)
        if op.get("qossExp") is not None:
            part["qossExp"] = op["qossExp"]
        if op.get("qrrExp") is not None:
            part["qrrExp"] = op["qrrExp"]
    d = derive(op, op.get("topology"))
    groups = d["groups"]
    Icom = d["Icom"]
    fsw = op["fsw"]
    lcsi = op.get("Lcsi", 0.0)
    is_bridge = part["kind"] == "bridge"
    r1 = part["Rdson25"] * kT

    A = 0.0
    for g in groups:
        if g["mode"] == "switch":
            A += r1 * g["I_rms"] ** 2
        else:
            A += r1 * g["I_dc"] ** 2

    vdrv, ron, roff, auto, gw = gate_config(part, op)
    qch_pd = (part["Qgs"] - part["Qgth"]) if not is_bridge else None
    qgd_pd = part["Qgd"] if not is_bridge else None
    qsw_pd = (qch_pd + qgd_pd) if not is_bridge else None

    a = 0.0
    b = 0.0
    pstat = 0.0
    eov_rep = None
    if is_bridge:
        for g in groups:
            if g["nHard"] <= 0:
                continue
            Vsw = g["Vsw"]
            if part.get("eiRef"):
                eov = part["eiRef"] * (Vsw / part["eiVref"])
            elif part.get("tsw"):
                eov = 0.5 * Vsw * part["tsw"]
            else:
                eov = 0.0
            if eov_rep is None:
                eov_rep = eov
            b += g["nHard"] * eov * Icom
            if coss_basis == "VQoss":
                e_cos = Vsw * (_qoss_at(part, Vsw) or 0.0)
            elif coss_basis == "2Eoss":
                e_cos = 2.0 * (_eoss_at(part, Vsw) or 0.0)
            else:
                e_cos = (_eoss_at(part, Vsw) or 0.0)
            a += g["nHard"] * e_cos
        a += d["nLegsTotal"] * part["Qdrv"] * vdrv
        pstat = d["nLegsTotal"] * part["Iq"] * vdrv
    else:
        qg_group = part["Qg"] * N
        rcsi = (rcsi_of(part, qg_group, Icom, N, lcsi)
                if op.get("gateModel", "detailed") == "detailed" else 0.0)
        ig_on = (vdrv - part["Vpt"]) / (ron + rcsi)
        ig_off = part["Vpt"] / (roff + rcsi)
        for g in groups:
            if g["nHard"] <= 0:
                continue
            Vsw = g["Vsw"]
            eov = 0.5 * Vsw * qsw_pd * (1.0 / ig_on + 1.0 / ig_off)  # [J/A]
            if eov_rep is None:
                eov_rep = eov
            a += g["nHard"] * (eov * Icom)
            if coss_basis == "VQoss":
                e_cos = Vsw * (_qoss_at(part, Vsw) or 0.0)
            elif coss_basis == "2Eoss":
                e_cos = 2.0 * (_eoss_at(part, Vsw) or 0.0)
            else:
                e_cos = (_eoss_at(part, Vsw) or 0.0)
            a += g["nHard"] * e_cos
        a += 2.0 * d["nSwitchLegs"] * part["Qg"] * vdrv  # gate energy per unit N
        # Qrr at qrrExp = 0 is an N^1 term, so it belongs in a
        if part.get("Qrr"):
            for g in groups:
                if g["nHard"] > 0:
                    a += g["nHard"] * part["Qrr"] * g["Vsw"]

    B = fsw * a + pstat
    Nopt = math.sqrt(A / B) if B > 0 else float("inf")
    cand = sorted(set([max(int(math.floor(Nopt)), 1), max(int(math.ceil(Nopt)), 1)]))
    nint = min(cand, key=lambda n: A / n + B * n)
    penalty = (0.5 * (Nopt / nint + nint / Nopt) - 1.0) * 100.0
    irms_max = max([g["I_rms"] for g in groups if g["mode"] == "switch"] or [0.0])
    nmin = (irms_max / (SQRT2 * part["IdcRating"])) if part.get("IdcRating") else None
    floor = 2.0 * math.sqrt(A * B) + fsw * b

    # P_ab(N) = A/N + N*(fsw*a + Pstat) + fsw*b  -- the closed form that N_opt
    # minimises.  Excludes dead time (not of the form A/N + B*N; DeviceFOM.m
    # excludes it too).
    def p_ab(n):
        return A / n + n * (fsw * a + pstat) + fsw * b

    # external EPC metrics (AN017)
    fom_hs = fom_ss = None
    if not is_bridge:
        fom_hs = (qgd_pd + qch_pd) * r1
        fom_ss = (part["Qg"] + part["Qoss"]) * r1

    return dict(A=A, a=a, b=b, Pstat=pstat, B=B, Nopt=Nopt, Nint=nint,
                penaltyPct=penalty, Nmin=nmin, floor=floor, R1=r1,
                eOv=(eov_rep * 1e6 if eov_rep is not None else None),
                R_E=(r1 * (eov_rep * Icom) if eov_rep is not None else None),
                R_over_e=(r1 / eov_rep if eov_rep else None),
                FOM_HS=fom_hs, FOM_SS=fom_ss,
                P_ab=p_ab(nint), P_ab_Nopt=p_ab(Nopt))


# ---------------------------------------------------------------------------
# reference cases
# ---------------------------------------------------------------------------
# The Lehner 7050/10 GaN motordriver point from DeviceFOM.m / Fsw_Optimum.
THREEPHASE = dict(topology="threephase", Vdc=58.0, fsw=40e3, Irms=165.4,
                  M=1.0, PF=0.9, Tamb=25.0, tauDead=40e-9, Vdrv=5.0,
                  Ron=2.6, Roff=0.6, kSoftOff=0.22, RthMode="flat",
                  kT=1.25, Lcsi=0.0)

# MPPT boost from BoostConverter.m
BOOST = dict(topology="boost", Vin=25.0, Vout=55.0, Pout=110.0, fsw=200e3,
             Tamb=25.0, tauDead=40e-9, Vdrv=5.0, Ron=2.6, Roff=0.6,
             kSoftOff=0.22, RthMode="flat", kT=1.25, Lcsi=0.0, L=None)

BUCK = dict(topology="buck", Vin=48.0, Vout=12.0, Pout=240.0, fsw=200e3,
            Tamb=25.0, tauDead=40e-9, Vdrv=5.0, Ron=2.6, Roff=0.6,
            kSoftOff=0.22, RthMode="flat", kT=1.25, Lcsi=0.0, L=None)

FOURSWITCH = dict(topology="fourswitch", Vin=24.0, Vout=48.0, Pout=240.0,
                  fsw=200e3, Tamb=25.0, tauDead=40e-9, Vdrv=5.0, Ron=2.6,
                  Roff=0.6, kSoftOff=0.22, RthMode="flat", kT=1.25, Lcsi=0.0,
                  L=None)

TERM_KEYS = ("cond", "overlap", "coss", "dead", "qrr", "ring", "gate")


def _clean(x):
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (set, frozenset)):
        return sorted(_clean(v) for v in x)
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


# ---------------------------------------------------------------------------
# 3-phase SVPWM ripple -- port of motorDriveLoss.m's svpwmRipple()
# ---------------------------------------------------------------------------
# Returns FLUX-domain quantities, which do not depend on the inductance; only
# the current does, by an exact 1/Ls.  That is what makes the required
# inductance a single division and an (fsw x L) map cost one evaluation per
# fsw rather than one per cell.  See the JS port's header for the same note.
def svpwm_ripple(vdc, M, fsw, n_theta=180, n_sub=192):
    if not vdc > 0:
        raise ValueError("svpwmRipple: Vdc must be > 0")
    if not fsw > 0:
        raise ValueError("svpwmRipple: fsw must be > 0")
    if not n_theta > 0:
        raise ValueError("svpwmRipple: nTheta must be a positive integer")
    if not n_sub > 0:
        raise ValueError("svpwmRipple: nSub must be a positive integer")
    m_want = 1.0 if M is None else M
    m_max = 2.0 / math.sqrt(3.0)
    mc = min(m_want, m_max)
    ts = 1.0 / fsw
    dt = ts / n_sub
    two3 = 2.0 * math.pi / 3.0
    lam_pp = []
    sum_v2 = 0.0
    sum_l2 = 0.0
    for i in range(n_theta):
        th = 2.0 * math.pi * i / n_theta
        v = [mc * (vdc / 2.0) * math.cos(th - k * two3) for k in range(3)]
        vcm = -(max(v) + min(v)) / 2.0                  # min/max injection == SVPWM
        d = []
        for k in range(3):
            x = 0.5 + (v[k] + vcm) / vdc
            d.append(0.0 if x < 0.0 else (1.0 if x > 1.0 else x))
        pole = []
        for k in range(3):
            hs = (ts / 2.0) * (1.0 - d[k])
            he = (ts / 2.0) * (1.0 + d[k])
            leg = []
            for j in range(n_sub):
                lo = j * dt
                hi = lo + dt
                a = hi if hi < he else he
                b = lo if lo > hs else hs
                ov = a - b
                leg.append(vdc * ov / dt if ov > 0 else 0.0)
            pole.append(leg)
        # phase voltage referred to the floating star point, then strip the
        # period mean so only the ripple-driving component is left
        vrip = []
        for k in range(3):
            row = []
            for j in range(n_sub):
                row.append(pole[k][j] - sum(pole[kk][j] for kk in range(3)) / 3.0)
            vrip.append(row)
        rowmax = -float("inf")
        rowmin = float("inf")
        for k in range(3):
            mean = sum(vrip[k]) / n_sub
            acc = 0.0
            cum = []
            for j in range(n_sub):
                val = vrip[k][j] - mean
                vrip[k][j] = val
                sum_v2 += val * val
                acc += val * dt
                cum.append(acc)
            cm = acc / n_sub                            # mean of the cumulative sum
            for j in range(n_sub):
                lam = cum[j] - cm
                sum_l2 += lam * lam
                if lam > rowmax:
                    rowmax = lam
                if lam < rowmin:
                    rowmin = lam
        lam_pp.append(rowmax - rowmin)
    n_all = n_theta * n_sub * 3
    v_rms = math.sqrt(sum_v2 / n_all)
    lam_rms = math.sqrt(sum_l2 / n_all)
    return dict(v_rms=v_rms, lam_rms=lam_rms, lam_pp=lam_pp, lam_pp_max=max(lam_pp),
                # fEff = Vrms/(2*pi*Ls*Irms) with Irms = lamRms/Ls, so Ls cancels
                f_eff=(v_rms / (2.0 * math.pi * lam_rms)) if lam_rms > 0 else 0.0,
                M=mc, Mclamped=mc < m_want - 1e-15,
                n_theta=n_theta, n_sub=n_sub)


def required_l(op, topology, target_ipp):
    """Closed-form inverse of derive()'s per-topology ripple formula.

    'What inductance holds this peak-to-peak ripple target?'  The 3-phase case
    is deliberately absent: its ripple comes from the winding inductance and is
    answered by the L-free svpwm_ripple() flux instead."""
    t = topology or op["topology"]
    fsw = op["fsw"]
    if not fsw > 0:
        raise ValueError("requiredL: fsw must be > 0")
    if not target_ipp > 0:
        raise ValueError("requiredL: the peak-to-peak ripple target must be > 0")
    if t == "buck":
        D = op["Vout"] / op["Vin"]
        return op["Vout"] * (1 - D) / (target_ipp * fsw)
    if t == "boost":
        D = 1 - op["Vin"] / op["Vout"]
        return op["Vin"] * D / (target_ipp * fsw)
    if t == "fourswitch":
        band = op.get("modeBand", 0.02)
        if op["Vin"] > op["Vout"] * (1 + band):
            D = op["Vout"] / op["Vin"]
            return op["Vout"] * (1 - D) / (target_ipp * fsw)
        if op["Vin"] < op["Vout"] * (1 - band):
            D = 1 - op["Vin"] / op["Vout"]
            return op["Vin"] * D / (target_ipp * fsw)
        return op["Vin"] * 0.5 / (target_ipp * fsw)
    raise ValueError("requiredL: unknown topology " + t)


def build_golden():
    cases = []
    fom = []
    thermal = []

    # --- cross-topology, GaN vs Si -----------------------------------------
    specs = [
        ("3ph-EPC2361-N4", "EPC2361", THREEPHASE, 4),
        ("3ph-EPC2367-N4", "EPC2367", THREEPHASE, 4),
        ("3ph-EPC2304-N4", "EPC2304", THREEPHASE, 4),
        ("3ph-EPC2305-N4", "EPC2305", THREEPHASE, 4),
        ("3ph-IRF7759-N4", "IRF7759", THREEPHASE, 4),
        ("3ph-IAUTN08S7N006ATMA1-N4", "IAUTN08S7N006ATMA1", THREEPHASE, 4),
        ("3ph-EPC2218-N8", "EPC2218", THREEPHASE, 8),
        ("boost-EPC23102-N1", "EPC23102", BOOST, 1),
        ("boost-ISG3202LA-N1", "ISG3202LA", BOOST, 1),
        ("boost-EPC23104-N1", "EPC23104", BOOST, 1),
        ("buck-EPC2361-N2", "EPC2361", BUCK, 2),
        ("buck-IRF7759-N2", "IRF7759", BUCK, 2),
        ("4sw-EPC2361-N2", "EPC2361", FOURSWITCH, 2),
        ("4sw-IRF7759-N2", "IRF7759", FOURSWITCH, 2),
        ("4sw-buckmode-EPC2361-N2", "EPC2361", dict(FOURSWITCH, Vin=48.0, Vout=12.0), 2),
    ]
    for name, pn, op, N in specs:
        part = PARTS[pn]
        for tm in ("none", "flat", "converged"):
            r = compute_losses(part, op, N, temp_mode=tm)
            cases.append(dict(
                name="%s|%s" % (name, tm), part=pn, topology=op["topology"],
                op=_clean({k: v for k, v in op.items()}), N=N, temp_mode=tm,
                expected=_clean(dict(
                    terms=r["terms"], die=r["die"], driver=r["driver"],
                    total=r["total"], eff=r["eff"], Tj=r["Tj"],
                    converged=r["converged"], rdson=r["rdson"],
                )),
                warnings=r["warnings"],
            ))

    # --- FOM at the DeviceFOM.m convention (kT = 1.25) ---------------------
    for name, pn, op, N in specs:
        part = PARTS[pn]
        f = fom_metrics(part, op, N, kT=1.25)
        fom.append(dict(name=name, part=pn, topology=op["topology"],
                        op=_clean({k: v for k, v in op.items()}), N=N,
                        expected=_clean(f)))

    # --- DeviceFOM.m published row values (kT = 1.25, 3-phase) --------------
    # gateModel='fom' reproduces DeviceFOM.m exactly: its FOM omits common-source
    # inductance from the gate loop.  The product defaults to 'detailed'
    # (motorDriveLoss.m), which adds a ~3% correction on these parts.
    devfom = []
    dev_op = dict(THREEPHASE, gateModel="fom")
    for pn in ("EPC2361", "EPC2218", "EPC2252", "EPC2204", "EPC2044",
               "EPC2065", "EPC23102", "EPC23104", "IRF7759",
               "IAUTN08S7N006ATMA1", "EPC2367", "EPC2304", "EPC2305"):
        f = fom_metrics(PARTS[pn], dev_op, 4, kT=1.25)
        devfom.append(dict(part=pn, op=_clean(dev_op),
                           R1_mOhm=PARTS[pn]["Rdson25"] * 1e3,
                           R1_hot_mOhm=f["R1"] * 1e3,
                           eOv_uJ_per_A=f["eOv"], Nopt=f["Nopt"],
                           Nint=f["Nint"], penaltyPct=f["penaltyPct"],
                           Nmin=f["Nmin"], floor=f["floor"],
                           FOM_HS=f["FOM_HS"], FOM_SS=f["FOM_SS"]))

    # --- thermal --------------------------------------------------------------
    op_conv = dict(THREEPHASE, RthMode="detailed", kTperC=0.006,
                   RthCA=1.0, RthSink=0.2, Tamb=25.0)
    thermal.append(dict(name="converges", part="EPC2361", N=4,
                        op=_clean(op_conv),
                        expected=_clean(_thermal_expect("EPC2361", op_conv, 4))))
    op_run = dict(THREEPHASE, RthMode="detailed", kTperC=0.05, RthCA=20.0,
                  RthSink=5.0, Tamb=25.0)
    thermal.append(dict(name="runaway", part="EPC2361", N=1,
                        op=_clean(op_run),
                        expected=_clean(_thermal_expect("EPC2361", op_run, 1))))

    # --- N-scaling exponents actually realised by the engine -----------------
    scaling = []
    for pn, op, kind in (("EPC2361", THREEPHASE, "discrete"),
                         ("EPC23102", THREEPHASE, "bridge"),
                         ("IRF7759", BUCK, "discrete")):
        part = PARTS[pn]
        base_op = dict(op, RthMode="flat", kT=1.0, gateModel="fom", Lloop=5e-9)
        base = compute_losses(part, base_op, 1, temp_mode="flat", kT=1.0)
        n2 = compute_losses(part, base_op, 2, temp_mode="flat", kT=1.0)
        n4 = compute_losses(part, base_op, 4, temp_mode="flat", kT=1.0)
        row = {"part": pn, "kind": kind, "topology": op["topology"],
               "op": _clean(base_op), "N": [1, 2, 4],
               "expected_exp": {
                   "cond": list(NSCALING["cond_discrete" if kind == "discrete"
                                          else "cond_bridge"]["exp"]),
                   "overlap": list(NSCALING["overlap_discrete" if kind == "discrete"
                                            else "overlap_bridge"]["exp"]),
                   "coss": list(NSCALING["coss"]["exp"]),
                   "dead": list(NSCALING["dead"]["exp"]),
                   "qrr": list(NSCALING["qrr"]["exp"]),
                   "ring": list(NSCALING["ring"]["exp"]),
                   "gate": list(NSCALING["gate"]["exp"]),
               }}
        for k in TERM_KEYS:
            a, b_, c = base["terms"][k], n2["terms"][k], n4["terms"][k]
            slope = None
            if a > 0 and c > 0:
                slope = math.log(c / a) / math.log(4.0)
            row[k] = _clean(slope)
            row[k + "_N1"] = a
            row[k + "_N4"] = c
        scaling.append(row)

    # --- per-device gate-rail resolution -------------------------------------
    # A Si part is quoted at 10 V and a GaN part at 5 V, so a single shared rail
    # makes the A/B comparison meaningless.  These pin gate_for()'s precedence.
    gates = []
    for pn, gop, slot, why in (
        ("IRF7759", {}, None, "no override: falls back to the part's VgsRec"),
        ("IRF7759", {}, "A", "slot A with no override: still VgsRec"),
        ("EPC2361", {}, None, "GaN recommended rail is 5 V"),
        ("EPC23102", {}, None, "bridge has no VgsRec, so the 5 V default stands"),
        ("IRF7759", {"Vdrv": 7.0}, "A", "explicit shared op.Vdrv beats VgsRec"),
        ("IRF7759", {"VdrvB": 12.0, "Vdrv": 7.0}, "B",
         "slot override beats the shared op.Vdrv"),
        ("EPC2361", {"VdrvA": 4.0}, "A", "a slot override can also under-drive GaN"),
    ):
        gates.append(dict(part=pn, op=_clean(dict(gop)), slot=slot,
                          recommended=PARTS[pn].get("VgsRec"),
                          expected=gate_for(PARTS[pn], gop, slot)["Vdrv"], why=why))

    # --- 3-phase SVPWM ripple ------------------------------------------------
    # The L-independent flux quantities, plus the current they imply at a given
    # Ls and the inductance that hits a peak-to-peak target.  These are what the
    # design workspace's sizing panel is built from.
    ripple = []
    for vdc, M, fsw, nt, ns, Ls, ipp in (
        (58.0, 1.0, 25000.0, 64, 64, 7.16e-6, 46.8),
        (58.0, 0.5, 25000.0, 64, 64, 10.0e-6, 20.0),
        (58.0, 2.0 / math.sqrt(3.0), 40000.0, 64, 64, 5.0e-6, 30.0),
        (400.0, 1.0, 10000.0, 64, 64, 200.0e-6, 100.0),
        (58.0, 1.0, 25000.0, 180, 192, 7.16e-6, 46.8),   # the model defaults
    ):
        r = svpwm_ripple(vdc, M, fsw, nt, ns)
        ripple.append(dict(
            vdc=vdc, M=M, fsw=fsw, nTheta=nt, nSub=ns, Ls=Ls, ipp_target=ipp,
            expected=_clean(dict(
                Vrms=r["v_rms"], lamRms=r["lam_rms"], lamPPmax=r["lam_pp_max"],
                lamPP=r["lam_pp"], fEff=r["f_eff"], M=r["M"], Mclamped=r["Mclamped"],
                Irip_rms=r["lam_rms"] / Ls,
                Ipp=r["lam_pp_max"] / Ls,
                requiredL=r["lam_pp_max"] / ipp,
            )),
        ))

    # --- DC-DC ripple sizing -------------------------------------------------
    # The closed-form inverse of derive()'s dIL formula, per topology.  Two
    # ports could share a transcription error here, which is why the engine test
    # also feeds each answer back through derive() and checks that it lands
    # exactly on the target -- a check no shared mistake can satisfy.
    dcdc = []
    for t, op in (
        ("buck", dict(topology="buck", Vin=48.0, Vout=12.0, Pout=240.0, fsw=100e3)),
        ("buck", dict(topology="buck", Vin=24.0, Vout=18.0, Pout=100.0, fsw=250e3)),
        ("boost", dict(topology="boost", Vin=25.0, Vout=55.0, Pout=110.0, fsw=200e3)),
        ("fourswitch", dict(topology="fourswitch", Vin=48.0, Vout=12.0, Pout=240.0, fsw=100e3)),
        ("fourswitch", dict(topology="fourswitch", Vin=12.0, Vout=48.0, Pout=240.0, fsw=100e3)),
        ("fourswitch", dict(topology="fourswitch", Vin=30.0, Vout=30.0, Pout=240.0, fsw=100e3)),
    ):
        for ipp in (2.0, 5.0):
            L = required_l(op, t, ipp)
            d = derive(dict(op, L=L), t)
            dcdc.append(dict(
                topology=t, op=_clean(dict(op)), ipp_target=ipp,
                expected=_clean(dict(requiredL=L, dIL_at_required=d["dIL"],
                                     mode_at_required=d["mode"])),
            ))

    return _clean(dict(
        schemaVersion=2,
        generatedBy="FET_FOM/reference/reference.py",
        sourceModels=["Switching_Losses/boostBridgeLoss.m",
                      "Switching_Losses/motorDriveLoss.m",
                      "Switching_Losses/Mos_switching.m",
                      "Switching_Losses/DeviceFOM.m",
                      "EPC AN030 (hard-switching method)",
                      "EPC AN017 (FOM_HS / FOM_SS)"],
        parts={k: _clean(v) for k, v in PARTS.items()},
        nscaling=NSCALING,
        cases=cases, fom=fom, devicefom=devfom, thermal=thermal,
        scaling=scaling, gates=gates, ripple=ripple, dcdc=dcdc,
    ))


def _thermal_expect(pn, op, N):
    r = compute_losses(PARTS[pn], op, N, temp_mode="converged")
    return dict(Tj=r["Tj"], converged=r["converged"], gain=r["gain"],
                rdson=r["rdson"], die=r["die"], total=r["total"])


# ---------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "golden.json")
    g = build_golden()
    with open(out, "w") as f:
        json.dump(g, f, indent=1, sort_keys=False)
        f.write("\n")
    print("wrote %s (%d cases, %d fom rows)" % (out, len(g["cases"]), len(g["fom"])))

    # a human-readable headline for the terminal / README
    for c in g["cases"]:
        if c["name"].endswith("|flat") and c["name"].split("|")[0] in (
                "3ph-EPC2361-N4", "3ph-IRF7759-N4"):
            e = c["expected"]
            print("  %-18s die=%8.2f W  gate=%6.2f W  Tj=%s" % (
                c["name"], e["die"], e["driver"], e["Tj"]))
    print("\n  external AN017 FOM_HS = (Qgd + Qgs2) * Rds(on)   [mOhm*nC]:")
    for row in g["devicefom"]:
        if row["FOM_HS"] is not None:
            print("    %-10s FOM_HS = %8.2f   FOM_SS = %8.2f"
                  % (row["part"], row["FOM_HS"] * 1e12, row["FOM_SS"] * 1e12))
    return 0


if __name__ == "__main__":
    sys.exit(main())
