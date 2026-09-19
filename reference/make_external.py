#!/usr/bin/env python3
"""
make_external.py -- generates the EXTERNAL anchors in reference/external/.

The internal oracle (reference.py -> golden.json) is a transcription of the same
text the JS engine is transcribed from, so it cannot catch a physics-level
mistake that both ports share.  These anchors tie the models to sources outside
this repository:

  an030.json               EPC AN030 "Hard Switching Losses Calculation" -- the
                           method the four switching terms implement, with
                           hand-computed expected values.
  an017.json               EPC AN017 hard/soft-switching figures of merit,
                           FOM_HS = (QGD+QGS2)*RDS(on), FOM_SS = (QG+QOSS)*RDS(on).
  datasheet_anchors.json   specification rows read out of the datasheets
                           committed in this repo (EPC2361_datasheet.pdf,
                           ISG3202LA_datasheet.pdf, IAUTN08S7N006_datasheet.pdf,
                           EPC2367_datasheet.pdf), so the seeded device data is
                           checked against a primary source rather than against
                           the .m files it was copied from.

AUTHORING TOOL.  Run it only when reference.py or the seed data changes.
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference as R  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "external")


def _f(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


# ---------------------------------------------------------------------------
# AN030 -- a symmetric half-bridge at a stated point, kSoftOff = 1.0 so that the
# turn-off overlap reproduces AN030's naive triangle rather than motorDriveLoss.m's
# soft-turn-off refinement.
# ---------------------------------------------------------------------------
def an030():
    pn = "EPC2361"
    part = R.PARTS[pn]
    Vbus, I = 48.0, 20.0
    Vdrv, Ron, Roff = 5.0, 2.6, 0.6
    fsw = 100e3
    qch = part["Qgs"] - part["Qgth"]          # = AN030's QGS2
    qgd = part["Qgd"]
    qsw = qch + qgd
    ig_on = (Vdrv - part["Vpt"]) / Ron
    ig_off = part["Vpt"] / Roff
    # AN030 section 2, turn-on: overlap from the current-rise and voltage-fall
    # transition times, driven by QGS2 and QGD respectively.
    e_on_an030 = 0.5 * Vbus * I * (qch / ig_on + qgd / ig_on)
    # AN030 section 2, turn-off: the same triangle on the way out.  The engine
    # DELIBERATELY does not use this: motorDriveLoss.m notes that turn-off is
    # nearly soft in an inductive-load half-bridge, so only the voltage-rise part
    # belongs there, capped by Coss commutation, with kSoftOff anchored to EPC's
    # measured EOFF/EON = 0.06 on the EPC23102.
    e_off_an030_naive = 0.5 * Vbus * I * (qch / ig_off + qgd / ig_off)
    # AN030 section 3: symmetric half-bridge capacitive loss = Vbus * QOSS
    qoss_v = part["Qoss"] * math.sqrt(Vbus / part["QossVref"])
    coss_an030 = Vbus * qoss_v
    eoss_ref = part["QossVref"] * part["Qoss"] / 3.0     # for a V^-0.5 Coss
    eoss_v = eoss_ref * (Vbus / part["QossVref"]) ** 1.5
    t_risev = min(qgd / ig_off, qoss_v / I)
    e_off_soft = 0.5 * Vbus * I * t_risev
    # AN030 2.2.1 current-fall phase (gate-limited) and 2.2.2 voltage rise.
    # The engine now carries BOTH: the current fall is hard (the node is already
    # at the bus) and is not reduced by kSoftOff; kSoftOff scales the soft
    # voltage-rise phase only.
    e_ifall_an030 = 0.5 * Vbus * I * (qch / ig_off)
    e_vrise_an030 = 0.5 * Vbus * I * (qgd / ig_off)
    # AN030 section 4: QRR is removed from the bus on the positive transition
    qrr_an030 = R.PARTS["IRF7759"]["Qrr"] * Vbus
    # AN030 section 5: gate loss = QG*VGS, dissipated outside the device
    gate_an030 = part["Qg"] * Vdrv

    op = dict(topology="buck", Vin=Vbus, Vout=24.0, Pout=24.0 * I, fsw=fsw,
              Tamb=25.0, tauDead=40e-9, Vdrv=Vdrv, Ron=Ron, Roff=Roff,
              gateModel="fom", RthMode="flat", kT=1.0, Lcsi=0.0, L=None)
    r_zero = R.compute_losses(part, dict(op, kSoftOff=0.0), 1, temp_mode="flat", kT=1.0)
    r_hard = R.compute_losses(part, dict(op, kSoftOff=1.0), 1, temp_mode="flat", kT=1.0)
    r_soft = R.compute_losses(part, dict(op, kSoftOff=0.22), 1, temp_mode="flat", kT=1.0)
    r_eoss = R.compute_losses(part, dict(op, kSoftOff=1.0), 1, temp_mode="flat",
                              kT=1.0, coss_basis="Eoss")
    r_2eoss = R.compute_losses(part, dict(op, kSoftOff=1.0), 1, temp_mode="flat",
                               kT=1.0, coss_basis="2Eoss")
    r_si = R.compute_losses(R.PARTS["IRF7759"], dict(op, Vout=24.0), 1,
                            temp_mode="flat", kT=1.0)

    return {
        "source": "EPC AN030, Hard Switching Losses Calculation",
        "url": ("https://epc-co.com/epc/portals/0/epc/documents/application-notes/"
                "AN030%20Hard%20Switching%20Losses%20Calculation.pdf"),
        "why": ("AN030 uses the same four-way split this engine implements and is "
                "applicable to both eGaN and Si MOSFETs. It is the external check "
                "on the switching terms, which the internal oracle cannot provide "
                "because both ports are transcribed from the same text."),
        "statements": {
            "overlap": "Overlap losses take place in Q1; Q2 does not have overlap "
                       "losses. Current rise time from QGS2, voltage fall from QGD, "
                       "gate current from (VDR - VPl)/RG.",
            "coss": "For a symmetrical half-bridge the overall capacitive loss "
                    "simplifies to Vbus * QOSS.",
            "qrr": "Reverse recovery happens during the switch node positive "
                   "voltage transition, where QRR is provided to Q2 from Vbus; "
                   "losses are QRR*Vbus*fsw. GaN FETs do not have these losses.",
            "gate": "PG = QG*VGS*fsw, dissipated in the gate loop resistors, so in "
                    "most cases outside the device.",
        },
        "case": {"part": pn, "Vbus": Vbus, "I": I, "fsw": fsw, "Vdrv": Vdrv,
                 "Ron": Ron, "Roff": Roff, "topology": "buck", "N": 1,
                 "RdsAt25C": True},
        "expected": {
            "Qgs2": qch, "Qgd": qgd, "Qsw": qsw,
            "IgOn": ig_on, "IgOff": ig_off,
            "Eon_AN030": e_on_an030,
            "Eoff_AN030_naive": e_off_an030_naive,
            "Eifall_AN030": e_ifall_an030,
            "Evrise_AN030": e_vrise_an030,
            "Eoff_engine_tRiseV": e_off_soft,
            "Eoff_engine_kSoftOff_1p0": e_off_soft,
            "Eoff_engine_kSoftOff_0p22": 0.22 * e_off_soft,
            "Eoverlap_AN030_naive": e_on_an030 + e_ifall_an030 + e_vrise_an030,
            "Eoverlap_engine_kSoftOff_1p0": e_on_an030 + e_ifall_an030 + e_off_soft,
            "Eoverlap_engine_kSoftOff_0p22": e_on_an030 + e_ifall_an030 + 0.22 * e_off_soft,
            "Ecoss_AN030_VQoss": coss_an030,
            "Eoss_at_Vbus": eoss_v,
            "coss_factor_VQoss_over_Eoss": coss_an030 / eoss_v,
            "coss_factor_Eoss_over_2Eoss": 0.5,
            "Qrr_AN030_per_die": qrr_an030,
            "Pgate_AN030_per_position": gate_an030,
        },
        "deliberate_divergence": {
            "turn_off": ("The engine's turn-off is kSoftOff * 0.5*Vbus*I*"
                         "min(Qgd/IgOff, Qoss/I), not AN030's (Qgs2+Qgd)/IgOff "
                         "triangle. Source: motorDriveLoss.m, which anchors "
                         "kSoftOff = 0.22 to EPC23102's measured EOFF/EON = 0.06."),
            "asserted": ("turn-on must match AN030 exactly; turn-off must match the "
                         "soft-turn-off expression, and must remain strictly below "
                         "AN030's naive value at kSoftOff = 0.22."),
        },
        "engine_check": {
            "Eon_plus_ifall_per_cycle": _f(r_zero["terms"]["overlap"] / fsw),
            "Eon_plus_ifall_expected": e_on_an030 + e_ifall_an030,
            "overlap_kSoftOff_1p0_per_cycle": _f(r_hard["terms"]["overlap"] / fsw),
            "overlap_kSoftOff_1p0_expected": e_on_an030 + e_ifall_an030 + e_off_soft,
            "overlap_kSoftOff_1p0_AN030_naive": e_on_an030 + e_ifall_an030 + e_vrise_an030,
            "overlap_kSoftOff_0p22_per_cycle": _f(r_soft["terms"]["overlap"] / fsw),
            "overlap_kSoftOff_0p22_expected": e_on_an030 + e_ifall_an030 + 0.22 * e_off_soft,
            "Eoff_soft_over_AN030_vrise": e_off_soft / e_vrise_an030,
            "coss_VQoss_per_cycle": _f(r_hard["terms"]["coss"] / fsw),
            "coss_Eoss_per_cycle": _f(r_eoss["terms"]["coss"] / fsw),
            "coss_2Eoss_per_cycle": _f(r_2eoss["terms"]["coss"] / fsw),
            "qrr_GaN_per_cycle_per_leg": _f(r_hard["terms"]["qrr"] / fsw),
            "qrr_Si_N1_per_cycle_per_leg": _f(r_si["terms"]["qrr"] / fsw),
            "gate_per_cycle_per_position": _f(r_hard["terms"]["gate"] / fsw),
            "gate_expected_2QGVdrv": 2.0 * part["Qg"] * Vdrv,
            "die_excludes_gate": _f(r_hard["die"]),
            "die_plus_gate_is_total": _f(r_hard["total"]),
        },
    }


# ---------------------------------------------------------------------------
# AN017 -- the published FOMs
# ---------------------------------------------------------------------------
def an017():
    dev_op = dict(R.THREEPHASE, gateModel="fom", RthMode="flat", kT=1.0)
    rows = {}
    for pn in ("EPC2361", "EPC2218", "EPC2252", "EPC2204", "EPC2044",
               "EPC2065", "IRF7759"):
        p = R.PARTS[pn]
        r1 = p["Rdson25"]                      # kT = 1 for the raw definition
        qch = p["Qgs"] - p["Qgth"]
        rows[pn] = {
            "technology": p["technology"],
            "Rds_on_mOhm": r1 * 1e3,
            "Qgs2_nC": qch * 1e9,
            "Qgd_nC": p["Qgd"] * 1e9,
            "Qg_nC": p["Qg"] * 1e9,
            "Qoss_nC": p["Qoss"] * 1e9,
            "FOM_HS_mOhm_nC": (p["Qgd"] + qch) * r1 * 1e12,
            "FOM_SS_mOhm_nC": (p["Qg"] + p["Qoss"]) * r1 * 1e12,
        }
    gan = [v["FOM_HS_mOhm_nC"] for k, v in rows.items() if v["technology"] == "GaN"
           and k == "EPC2361"][0]
    si = rows["IRF7759"]["FOM_HS_mOhm_nC"]
    return {
        "source": "EPC AN017, Fourth Generation eGaN FETs Widen the Performance Gap",
        "url": ("https://epc-co.com/epc/design-support/application-notes/"
                "an017-fourth-generation-egan-fets-widen-the-performance-gap"),
        "definition": {
            "FOM_HS": "(QGD + QGS2) * RDS(on)",
            "FOM_SS": "(QG + QOSS) * RDS(on)",
            "note": "QGS2 in AN017 is the gate-source charge from threshold to the "
                    "plateau, i.e. Qgs - Qg(th) in the .m files.",
        },
        "rows": rows,
        "direction": {
            "FOM_HS_improvement_Si_over_GaN": si / gan,
            "assert": "FOM_HS(IRF7759) / FOM_HS(EPC2361) must be >> 1 (GaN much better)",
        },
        "epc_published_context": {
            "FOM_HS_reduction_vs_best_Si": {"40V": 3.5, "100V": 6.1, "200V": 8.5},
            "caveat": ("Recorded as context only, NOT asserted: EPC compares against "
                       "best-in-class Si at the same voltage, while IRF7759 here is a "
                       "75 V / 1.8 mOhm part chosen as an available example."),
        },
    }


# ---------------------------------------------------------------------------
# datasheet_anchors -- primary source for the seeded device data
# ---------------------------------------------------------------------------
def datasheets():
    return {
        "why": ("The seed library was transcribed from the .m files. These are the "
                "specification rows read out of the datasheet PDFs committed in this "
                "repo, so a transcription error in the seed -- or in a "
                "datasheet-sourced entry (IAUTN08S7N006ATMA1, EPC2367, EPC2304, "
                "EPC2305) -- shows up as a test failure against the primary source."),
        "extractedWith": "pdftotext -layout <pdf> -",
        "sources": [
            {
                "file": "EPC2361_datasheet.pdf",
                "rows": [
                    "RDS(on) Drain-Source On Resistance  VGS = 5 V, ID = 50 A  0.75  1  mOhm",
                    "QG Total Gate Charge  VDS = 50 V, VGS = 5 V, ID = 50 A  28  34  nC",
                    "QGS Gate-to-Source Charge  8.5  nC",
                    "QGD Gate-to-Drain Charge  VDS = 50 V, ID = 50 A  3.8  nC",
                    "QG(TH) Gate Charge at Threshold  6  nC",
                    "QOSS Output Charge  VDS = 50 V, VGS = 0 V  90  112  nC",
                    "QRR Source-Drain Recovery Charge  0",
                    "RG Gate Resistance  0.4  Ohm",
                ],
            },
            {
                "file": "ISG3202LA_datasheet.pdf",
                "rows": [
                    "Drain-Source On Resistance RDS(ON) 2.4 3.2 mOhm  PWML=5V or PWMH=5V, ID=25A",
                    "Output Charge QOSS 50 nC  PWML=0V or PWMH=0V, VDS=0V to 50V",
                    "Output Capacitance COSS 460 pF  VDS = 50V",
                    "Reverse Transfer Capacitance CRSS 8.2 pF  VDS = 50V",
                    "Energy Related COSS COSS(ER) 700 pF  VDS = 0V to 50V",
                    "Time Related COSS COSS(TR) 1020 pF  VDS = 0V to 50V",
                    "Source-Drain Forward Voltage VSD 1.5 V  IS = 0.5A",
                    "Drain-to-Source Voltage BVDSS 100 V  ID = 400uA",
                ],
            },
            {
                "file": "IAUTN08S7N006_datasheet.pdf",
                "rows": [
                    "Drain-source breakdown voltage V(BR)DSS  VGS = 0 V, ID = 1 mA  80  min  V",
                    "Drain-source on-state resistance RDS(on)  VGS = 10 V, ID = 100 A  – 0.53 0.57 mOhm",
                    "Drain-source on-state resistance RDS(on)  VGS = 7 V, ID = 50 A  – 0.59 0.67 mOhm",
                    "Continuous drain current ID  VGS = 10 V, chip limitation 605 A; DC current 350 A",
                    "Gate source voltage VGS  ±20 V",
                    "Gate threshold voltage VGS(th)  VDS = VGS, ID = 318 uA  2.3 2.8 3.2 V",
                    "Input capacitance Ciss  VGS = 0 V, VDS = 40 V, f = 1 MHz  – 15915 20690 pF",
                    "Output capacitance Coss  VGS = 0 V, VDS = 40 V, f = 1 MHz  – 6404 8325 pF",
                    "Gate to source charge Qgs  VDD = 40 V, ID = 100 A, VGS = 0 to 10 V  – 70 91 nC",
                    "Gate to drain charge Qgd  – 40 60 nC",
                    "Gate charge total Qg  – 229 298 nC",
                    "Gate plateau voltage Vplateau  – 4.4 – V",
                    "Diode forward voltage VSD  VGS = 0 V, IF = 100 A, Tj = 25 C  – 0.85 0.95 V",
                    "Reverse recovery charge Qrr  VR = 40 V, IF = 50 A, diF/dt = 100 A/us  – 69 138 nC",
                    "Thermal resistance junction-case RthJC  – – 0.38 K/W",
                    "Thermal resistance junction-ambient RthJA  – 14.8 – K/W",
                    "Operating temperature Tj  -55 ... +175 C",
                    "(derived) Qoss(50 V) = 2*Coss(40 V)*sqrt(40*50) under the V^-0.5 law, from Coss 6404 pF -> 572.8 nC",
                ],
            },
            {
                "file": "EPC2367_datasheet.pdf",
                "rows": [
                    "Drain-to-Source Voltage BVDSS  VGS = 0 V, ID = 0.5 mA  100  V",
                    "Drain-Source On Resistance RDS(on)  VGS = 5 V, ID = 30 A  1.2 1.5 mOhm",
                    "Drain-to-Source Voltage VDS (Continuous) 100 V; repetitive transient 120 V",
                    "Continuous drain current ID  TJ < 125 C  101 A; pulsed 25 C / 10 us 420 A",
                    "Gate-to-Source Voltage VGS  +6 / -4 V; repetitive transient +7 V",
                    "Gate Threshold Voltage VGS(TH)  VDS = VGS, ID = 10 mA  0.8 1.1 2.5 V",
                    "Total Gate Charge QG  VDS = 50 V, VGS = 5 V, ID = 30 A  17 20 nC",
                    "Gate-to-Source Charge QGS  5.3 nC",
                    "Gate-to-Drain Charge QGD  VDS = 50 V, ID = 30 A  2.4 nC",
                    "Gate Charge at Threshold QG(TH)  3.8 nC",
                    "Output Charge QOSS  VDS = 50 V, VGS = 0 V  54 63 nC",
                    "Source-Drain Recovery Charge QRR  0",
                    "Source-Drain Forward Voltage VSD  IS = 0.5 A, VGS = 0 V  1.4 V",
                    "Thermal Resistance, Junction-to-Case (Case TOP) RthJC  0.5 K/W",
                    "Thermal Resistance, Junction-to-Board (Case BOTTOM) RthJB  2.4 K/W",
                    "Thermal Resistance, Junction-to-Ambient (JEDEC 51-2 PCB) RthJA_JEDEC  50 K/W",
                    "Thermal Resistance, Junction-to-Ambient (EPC90164 EVB) RthJA_EVB  29 K/W",
                    "Operating Temperature TJ  -40 to 150 C",
                ],
            },
            {
                "file": "EPC2304_datasheet.pdf",
                "rows": [
                    "Drain-to-Source Voltage BVDSS  VGS = 0 V, ID = 500 uA  200 V",
                    "Drain-to-Source Voltage VDS (Continuous) 200 V; repetitive transient 220 V",
                    "Continuous drain current ID  TJ <= 125 C  133 A; pulsed 25 C / 300 us 260 A",
                    "Gate-to-Source Voltage VGS  +6 / -4 V; repetitive transient +7 V",
                    "Gate Threshold Voltage VGS(TH)  VDS = VGS, ID = 9 mA  0.8 1.5 2.5 V",
                    "Drain-Source On Resistance RDS(on)  VGS = 5 V, ID = 30 A  3.5 5 mOhm",
                    "Total Gate Charge QG  VDS = 100 V, VGS = 5 V, ID = 30 A  21 26 nC",
                    "Gate-to-Source Charge QGS  7.5 nC",
                    "Gate-to-Drain Charge QGD  VDS = 100 V, ID = 30 A  2 nC",
                    "Gate Charge at Threshold QG(TH)  5.2 nC",
                    "Output Charge QOSS  VDS = 100 V, VGS = 0 V  120 145 nC",
                    "Source-Drain Recovery Charge QRR  0",
                    "Source-Drain Forward Voltage VSD  IS = 0.5 A, VGS = 0 V  1.8 V",
                    "Thermal Resistance, Junction-to-Case RthJC  0.2 K/W",
                    "Thermal Resistance, Junction-to-Board RthJB  1.5 K/W",
                    "Thermal Resistance, Junction-to-Ambient (JEDEC 51-2 PCB) RthJA_JEDEC  45 K/W",
                    "Thermal Resistance, Junction-to-Ambient (EPC90140 EVB) RthJA_EVB  21 K/W",
                    "Operating Temperature TJ  -40 to 150 C",
                ],
            },
            {
                "file": "EPC2305_datasheet.pdf",
                "rows": [
                    "Drain-to-Source Voltage BVDSS  VGS = 0 V, ID = 0.2 mA  150 V",
                    "Drain-to-Source Voltage VDS (Continuous) 150 V; repetitive transient 180 V",
                    "Continuous drain current ID  TJ <= 125 C  133 A; pulsed 25 C / 300 us 329 A",
                    "Gate-to-Source Voltage VGS  +6 / -4 V",
                    "Gate Threshold Voltage VGS(TH)  VDS = VGS, ID = 11 mA  0.8 1.1 2.5 V",
                    "Drain-Source On Resistance RDS(on)  VGS = 5 V, ID = 30 A  2.2 3.0 mOhm",
                    "Total Gate Charge QG  VDS = 75 V, VGS = 5 V, ID = 30 A  22 28.6 nC",
                    "Gate-to-Source Charge QGS  6.6 nC",
                    "Gate-to-Drain Charge QGD  VDS = 75 V, ID = 30 A  2.1 nC",
                    "Gate Charge at Threshold QG(TH)  4.6 nC",
                    "Output Charge QOSS  VDS = 75 V, VGS = 0 V  103 116 nC",
                    "Source-Drain Recovery Charge QRR  0",
                    "Source-Drain Forward Voltage VSD  IS = 0.5 A, VGS = 0 V  1.4 V",
                    "Thermal Resistance, Junction-to-Case (Case TOP) RthJC  0.2 K/W",
                    "Thermal Resistance, Junction-to-Board (Case BOTTOM) RthJB  1.5 K/W",
                    "Thermal Resistance, Junction-to-Ambient (using JEDEC 51-2 PCB) RthJA_JEDEC  45 K/W",
                    "Thermal Resistance, Junction-to-Ambient (using EPC90142 EVB) RthJA_EVB  21 K/W",
                    "Operating Temperature TJ  -40 to 150 C",
                ],
            },
        ],
        "expected": {
            "EPC2361": {"kind": "discrete", "technology": "GaN",
                        "Rdson25": 0.75e-3, "Qg": 28e-9, "Qgs": 8.5e-9,
                        "Qgd": 3.8e-9, "Qgth": 6e-9, "Qoss": 90e-9,
                        "QossVref": 50.0, "Qrr": 0.0, "BVdss": 100.0},
            "ISG3202LA": {"kind": "bridge", "technology": "GaN",
                          "Rdson25": 2.4e-3, "Qoss": 50e-9, "QossVref": 50.0,
                          "Eoss": 0.5 * 700e-12 * 50.0 ** 2, "EossVref": 50.0,
                          "Vsd0": 1.5, "BVdss": 100.0},
            "IAUTN08S7N006ATMA1": {"kind": "discrete", "technology": "Si",
                                   "Rdson25": 0.53e-3, "RdsonMax": 0.57e-3,
                                   "IdcRating": 350.0, "BVdss": 80.0,
                                   "VgsRec": 10.0, "Vth": 2.8, "Vpt": 4.4,
                                   "Qg": 229e-9, "Qgs": 70e-9, "Qgd": 40e-9,
                                   "Qoss": 572.8e-9, "QossVref": 50.0,
                                   "Qrr": 69e-9, "QrrMax": 138e-9,
                                   "Vsd0": 0.85, "RthJC": 0.38, "TjMax": 175},
            "EPC2367": {"kind": "discrete", "technology": "GaN",
                        "Rdson25": 1.2e-3, "RdsonMax": 1.5e-3,
                        "IdcRating": 101.0, "BVdss": 100.0, "VgsRec": 5.0,
                        "Vth": 1.1, "Qg": 17e-9, "Qgs": 5.3e-9, "Qgd": 2.4e-9,
                        "Qgth": 3.8e-9, "Qoss": 54e-9, "QossVref": 50.0,
                        "QossMax": 63e-9, "Qrr": 0.0, "Vsd0": 1.4,
                        "RthJC": 0.5, "TjMax": 150},
            "EPC2304": {"kind": "discrete", "technology": "GaN",
                        "Rdson25": 3.5e-3, "RdsonMax": 5.0e-3,
                        "IdcRating": 133.0, "BVdss": 200.0, "VgsRec": 5.0,
                        "Vth": 1.5, "Qg": 21e-9, "Qgs": 7.5e-9, "Qgd": 2e-9,
                        "Qgth": 5.2e-9, "Qoss": 120e-9, "QossVref": 100.0,
                        "QossMax": 145e-9, "Qrr": 0.0, "Vsd0": 1.8,
                        "RthJC": 0.2, "TjMax": 150},
            "EPC2305": {"kind": "discrete", "technology": "GaN",
                        "Rdson25": 2.2e-3, "RdsonMax": 3.0e-3,
                        "IdcRating": 133.0, "BVdss": 150.0, "VgsRec": 5.0,
                        "Vth": 1.1, "Qg": 22e-9, "Qgs": 6.6e-9, "Qgd": 2.1e-9,
                        "Qgth": 4.6e-9, "Qoss": 103e-9, "QossVref": 75.0,
                        "QossMax": 116e-9, "Qrr": 0.0, "Vsd0": 1.4,
                        "RthJC": 0.2, "TjMax": 150},
        },
    }


# ---------------------------------------------------------------------------
# Ripple: the exact 3-phase SVPWM anchors
# ---------------------------------------------------------------------------
# svpwm_ripple() is a port of motorDriveLoss.m, so a Python transcription of it
# cannot validate it -- the same mistake would be in both.  What CAN be checked
# independently is the closed form the model has to reproduce: the classic
# maximum peak-to-peak phase-current ripple of a three-phase SVPWM inverter in
# the linear region,
#
#     dI_pp,max = Vdc / (6 * Ls * fsw)
#
# plus a second exact datum at M = 1.  Both are stated as k = lamPPmax*fsw/Vdc,
# which is the L-free, dimensionless form of the same statement.
def ripple():
    m_lin = 2.0 / math.sqrt(3.0)
    vdc, fsw = 58.0, 25000.0
    anchors = []
    for name, M, k_expected, why in (
        ("svpwm-linear-limit", m_lin, 1.0 / 6.0,
         "The classic SVPWM linear-region maximum, dI_pp,max = Vdc/(6*Ls*fsw), "
         "attained at the linear limit M = 2/sqrt(3)."),
        ("svpwm-M1", 1.0, 1.0 / (4.0 * math.sqrt(3.0)),
         "A second exact datum at M = 1, where the same normalised constant is "
         "1/(4*sqrt(3)).  Not the classic quote, but it pins the shape of the "
         "ripple-versus-M curve rather than one endpoint of it."),
    ):
        r = R.svpwm_ripple(vdc, M, fsw, 180, 192)
        k = r["lam_pp_max"] * fsw / vdc
        anchors.append(dict(name=name, M=M, Vdc=vdc, fsw=fsw,
                            k_expected=k_expected, k_measured=k,
                            rel_error=(k - k_expected) / k_expected, why=why))

    # Resolution study.  lamPPmax is a peak-to-peak FLUX, so it is exact at any
    # nSub; Vrms is a mean square over binned pulse widths and so carries an
    # O(1/nSub) bias.  Both facts matter downstream: the sizing answer
    # (requiredL = lamPPmax/dI_target) is exact, while the iron ripple eddy term
    # that consumes Vrms is not.
    res = [48, 96, 192, 384, 768]
    lam, vr = [], []
    for ns in res:
        r = R.svpwm_ripple(vdc, 1.0, fsw, 180, ns)
        lam.append(r["lam_pp_max"])
        vr.append(r["v_rms"])
    v_inf = 2.0 * vr[-1] - vr[-2]                    # Richardson: error ~ C/nSub
    resolution = dict(
        nSub=res, lamPPmax=lam, Vrms=vr, Vrms_extrapolated=v_inf,
        lamPPmax_spread=(max(lam) - min(lam)) / max(lam),
        Vrms_at_default_192_rel=(vr[res.index(192)] - v_inf) / v_inf,
        why="lamPPmax is a peak-to-peak flux, so it is resolution independent "
            "(spread ~ 0); Vrms is a mean square over binned pulse widths and "
            "converges as O(1/nSub).",
    )
    return dict(source="closed form, plus a numerical resolution study",
                generatedBy="FET_FOM/reference/make_external.py",
                note="k = lamPPmax * fsw / Vdc is the L-free, dimensionless form "
                     "of dI_pp = k * Vdc / (Ls * fsw).",
                anchors=anchors, resolution=resolution)


# ---------------------------------------------------------------------------
# Inductor data anchors
# ---------------------------------------------------------------------------
# The design workspace seeds seven Wuerth WE-HCF/HCM inductors.  Those numbers
# are NOT invented here: they are parsed straight out of the committed
# Switching_Losses/WE_*.m files, which are themselves REDEXPERT scrapes, and the
# loss fit is recomputed with an independent stdlib least-squares.  The point is
# that the tool's seeded grid is a tested transcription of the repo's data
# rather than a hand copy that can drift.
#
# The .m grids are ordered Idc-major, then f, then dI; that convention is what
# lets the JS side carry only the axis vectors plus 126 Pac values per part.
def _lstsq_loglog(rows):
    """log P = log k + a log f + b log dI + c log Idc, by least squares.

    Solves the normal equations through a Cholesky factorisation.  The design
    matrix is 4 columns and, for a real f x dI x Idc grid, well conditioned; the
    guard exists to catch a degenerate data file (the old 3-point-per-curve
    grids were rank deficient and returned b = -0.215, i.e. "more ripple, less
    core loss"), not to reproduce MATLAB's SVD-based cond() bit for bit.  Hence
    condEst is a Cholesky pivot ratio squared, and the threshold is the same
    1e4 the .m file uses."""
    n = len(rows)
    X = [[1.0, math.log(f), math.log(d), math.log(i)] for f, d, i, _ in rows]
    y = [math.log(p) for _, _, _, p in rows]
    G = [[sum(X[r][a] * X[r][b] for r in range(n)) for b in range(4)] for a in range(4)]
    v = [sum(X[r][a] * y[r] for r in range(n)) for a in range(4)]
    L = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(i + 1):
            s = G[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s <= 0.0:
                    raise ValueError("design matrix is rank deficient")
                L[i][j] = math.sqrt(s)
            else:
                L[i][j] = s / L[j][j]
    diag = [L[i][i] for i in range(4)]
    cond_est = (max(diag) / min(diag)) ** 2
    z = [0.0] * 4
    for i in range(4):
        z[i] = (v[i] - sum(L[i][k] * z[k] for k in range(i))) / L[i][i]
    beta = [0.0] * 4
    for i in range(3, -1, -1):
        beta[i] = (z[i] - sum(L[j][i] * beta[j] for j in range(i + 1, 4))) / L[i][i]
    resid = 0.0
    for r in range(n):
        pred = math.exp(sum(beta[j] * X[r][j] for j in range(4)))
        resid = max(resid, abs(pred / rows[r][3] - 1.0))
    return math.exp(beta[0]), beta[1], beta[2], beta[3], cond_est, resid


def inductors():
    import glob
    import re
    src = os.path.join(HERE, "..", "..", "Switching_Losses")
    parts, axes = {}, None
    for path in sorted(glob.glob(os.path.join(src, "WE_*.m"))):
        pn = os.path.basename(path)[:-2]
        txt = open(path).read()
        m = re.search(r"acGrid\s*=\s*\[(.*?)\];", txt, re.S)
        if not m:
            raise ValueError(pn + ": no acGrid block")
        rows = []
        for ln in m.group(1).replace("...", "").split(";"):
            if ln.strip():
                v = ln.split()
                rows.append((float(v[0]), float(v[1]), float(v[2]), float(v[3])))

        def num(pat):
            mm = re.search(pat, txt, re.M)
            if not mm or mm.group(1) == "n/a":
                return None
            return float(mm.group(1))

        L = num(r"^\s*L\s*=\s*([0-9.eE+-]+);")
        dcr = num(r"ESR_L\s*=\s*([0-9.eE+-]+);")
        i10 = num(r"Isat@10%\s*=\s*([0-9.]+|n/a)")
        i30 = num(r"Isat@30%\s*=\s*([0-9.]+|n/a)")
        ir = num(r"I_rated\s*=\s*([0-9.]+|n/a)")

        ax = (tuple(sorted({r[0] for r in rows})),
              tuple(sorted({r[1] for r in rows})),
              tuple(sorted({r[2] for r in rows})))
        if axes is None:
            axes = ax
        if ax != axes:
            raise ValueError(pn + ": grid axes differ from the other parts")

        k, a, b, c, ce, rmax = _lstsq_loglog(rows)
        dm = re.search(r"^%\s*WE_\w+\s*--\s*(.*)$", txt, re.M)
        parts[pn] = dict(L=L, DCR=dcr, Isat10=i10, Isat30=i30, Irated=ir,
                         desc=(dm.group(1).strip() if dm else ""),
                         Pac=[r[3] for r in rows],
                         fit=dict(k=k, a=a, b=b, c=c, condEst=ce, residMax=rmax),
                         source="Switching_Losses/" + os.path.basename(path))
    return dict(
        source="Switching_Losses/WE_*.m acGrid blocks (Wuerth REDEXPERT scrape)",
        generatedBy="FET_FOM/reference/make_external.py",
        note="Grid rows are ordered Idc-major, then f, then dI, which is the order "
             "the .m files list them in; the JS library carries the axes plus the "
             "126 Pac values per part and re-fits, so the coefficients are "
             "recomputed rather than transcribed.",
        axes=dict(f=list(axes[0]), dI=list(axes[1]), Idc=list(axes[2])),
        rows=len(next(iter(parts.values()))["Pac"]),
        parts=parts,
    )


# ---------------------------------------------------------------------------
# Capacitor node anchors
# ---------------------------------------------------------------------------
# Both capacitor models are closed-form, so the anchors are the textbook
# expressions rather than a second numerical implementation:
#
#   buck  input  node: Irms = Iout*sqrt(D*(1-D)),  dv = Iout*D*(1-D)/(fsw*C)
#   boost output node: Irms = Iout*sqrt(D/(1-D)),  dv = Iout*D/(fsw*C)
#   smooth node:      Irms = dI/sqrt(12),          dv = dI/(8*fsw*C)
#
# plus Parseval.  The harmonic powers of a zero-mean triangle whose PEAK-TO-PEAK
# value is dI must sum to exactly dI^2/12 -- the triangle's mean square.  That
# identity is what catches Capacitor_Losses.m's amplitude error, which writes
# 8*dI/(pi^2*n^2) where the peak-to-peak definition gives 4*dI/(pi^2*n^2), and
# so overstates its ESR losses by 4x.
def capacitors():
    pulsed = []
    for name, vin, vout, pout, fsw, C in (
        ("buck-48-12-100k", 48.0, 12.0, 240.0, 100e3, 100e-6),
        ("buck-24-18-250k", 24.0, 18.0, 100.0, 250e3, 47e-6),
        ("boost-25-55-200k", 25.0, 55.0, 110.0, 200e3, 100e-6),
        ("boost-12-48-300k", 12.0, 48.0, 200.0, 300e3, 220e-6),
    ):
        if name.startswith("buck"):
            D = vout / vin
            iout = pout / vout
            node, duty = "in", D
        else:
            D = 1.0 - vin / vout
            iout = pout / vout
            node, duty = "out", 1.0 - D
        IL = pout / vin if name.startswith("boost") else iout
        # The node's high level is the inductor current; the low level is 0.
        pulsed.append(dict(
            name=name, Vin=vin, Vout=vout, Pout=pout, fsw=fsw, C=C, node=node,
            expected=dict(
                duty=duty, IL_avg=IL,
                Irms=IL * math.sqrt(duty * (1.0 - duty)),
                dvCap=IL * duty * (1.0 - duty) / (fsw * C),
            ),
        ))

    dIL, fsw, C = 1.0, 100e3, 100e-6
    smooth = dict(dIL=dIL, fsw=fsw, C=C,
                  expected=dict(Irms=dIL / math.sqrt(12.0),
                                dvCap=dIL / (8.0 * fsw * C)))

    # Analytic Parseval target for the same triangle.
    parseval = dict(dIL=dIL, expected_sum_mean_square=dIL * dIL / 12.0,
                    why="sum of the harmonic mean squares of a zero-mean triangle "
                        "with peak-to-peak dI equals its mean square dI^2/12; "
                        "Capacitor_Losses.m's 8*dI amplitude is 2x high and "
                        "therefore 4x high in ESR loss.")

    return dict(source="textbook CCM capacitor-current results, plus Parseval",
                generatedBy="FET_FOM/reference/make_external.py",
                note="Capacitor data in this repo is generic only (no datasheets "
                     "are committed), so these anchor the MODEL, not a part.",
                pulsed=pulsed, smooth=smooth, parseval=parseval)


# ---------------------------------------------------------------------------
# Machine anchors
# ---------------------------------------------------------------------------
# The copper and iron models are ports of motorDriveLoss.m, so the anchors are
# the two things that are NOT a transcription:
#
#  1. The iron-loss calibration.  Kh and Ke are derived from the two no-load
#     dyno rows (7050/9: 4.60 A at 60 V, 10699 rpm; 7050/12: 2.70 A at 54 V,
#     7219 rpm), so feeding those rows back through the model must reproduce
#     them.  It is a consistency check of the calibration, not independent
#     validation of the dyno data, and it is labelled as such.
#  2. The analytic limits of the three AC-resistance factors: skinFr -> 1 at dc
#     and -> a/(2*delta) + 1/4 when the skin depth is small; dowellFr -> 1 at dc;
#     lamEddyFactor -> 1 for small xi and xi*F -> 3 for large xi.
_MOTOR_SEED = dict(p=10, lam=3.010e-3, Rph=9.1e-3, Ls=7.45e-6, cabLen=2.0,
                   cabArea=16e-6, Rfix=1.2e-3, fracIron=0.95, beta=2.0, kLm=0.65,
                   dLam=0.20e-3, rhoLam=0.50e-6, muRLam=500,
                   dStrand=1.0e-3, mLayers=4, poros=0.8,
                   cal=dict(fA=10699/60*10, PA=60.0*4.60*0.95,
                            fB=7219/60*10, PB=54.0*2.70*0.95))


def _bessel_j0(z):
    half = z / 2.0
    term = 1.0 + 0j
    s = 1.0 + 0j
    for k in range(1, 200):
        term = -term * half * half / (k * k)
        s += term
        if abs(term) < 1e-17 * abs(s):
            break
    return s


def _bessel_j1(z):
    half = z / 2.0
    term = 1.0 + 0j
    s = 1.0 + 0j
    for k in range(1, 200):
        term = -term * half * half / (k * (k + 1))
        s += term
        if abs(term) < 1e-17 * abs(s):
            break
    return half * s


def _skin_fr(f, d):
    """Skin-effect AC resistance factor of a solid round conductor."""
    rho, mu0 = 1.72e-8, 4 * math.pi * 1e-7
    a, ff = d / 2.0, max(f, 1.0)
    x = a * math.sqrt(2 * math.pi * ff * mu0 / rho / 2.0)
    if x < 1e-6:
        return 1.0
    z = complex(x, -x)
    return max(((z / 2.0) * _bessel_j0(z) / _bessel_j1(z)).real, 1.0)


def _dowell_fr(f, ds, ml, por):
    """Dowell proximity-effect AC resistance factor."""
    rho, mu0 = 1.724e-8, 4 * math.pi * 1e-7
    dl = math.sqrt(rho / (math.pi * max(f, 1.0) * mu0))
    D = (ds / dl) * math.sqrt(math.pi * por / 4.0)
    if D < 1e-6:
        return 1.0
    fr = D * ((math.sinh(2 * D) + math.sin(2 * D)) / (math.cosh(2 * D) - math.cos(2 * D))
              + (2.0 / 3.0) * (ml * ml - 1) * (math.sinh(D) - math.sin(D))
              / (math.cosh(D) + math.cos(D)))
    return max(fr, 1.0)


def _lam_eddy(f, d, rho, mur):
    """1-D lamination eddy-current skin factor."""
    mu0 = 4 * math.pi * 1e-7
    xi = d / math.sqrt(rho / (math.pi * max(f, 1.0) * mu0 * mur))
    if xi < 1e-9:
        return 1.0
    return (3.0 / xi) * (math.sinh(xi) - math.sin(xi)) / (math.cosh(xi) - math.cos(xi))


def machine():
    m = dict(_MOTOR_SEED)
    c = m["cal"]
    m["Rcable"] = 1.72e-8 * m["cabLen"] / m["cabArea"]
    m["cabDia"] = 2 * math.sqrt(m["cabArea"] / math.pi)
    m["Rwind"] = max(m["Rph"] - m["Rcable"] - m["Rfix"], 0.2 * m["Rph"])
    m["KtPk"] = 1.5 * m["p"] * m["lam"]
    ke = (c["PA"] / c["fA"] - c["PB"] / c["fB"]) / (c["fA"] - c["fB"])
    kh = c["PB"] / c["fB"] - ke * c["fB"]
    m["Ke"] = ke / (2 * math.pi ** 2 * m["lam"] ** 2)
    m["Kh"] = kh / (2 * m["lam"]) ** m["beta"]
    m["alphaEquiv"] = math.log(c["PA"] / c["PB"]) / math.log(c["fA"] / c["fB"])
    m["ironSplit"] = [kh * c["fA"] / c["PA"], ke * c["fA"] ** 2 / c["PA"]]

    # Feed the dyno rows back through the iron model.
    cal = []
    for name, f, P in (("7050-9", c["fA"], c["PA"]), ("7050-12", c["fB"], c["PB"])):
        F = _lam_eddy(f, m["dLam"], m["rhoLam"], m["muRLam"])
        model = (m["Ke"] * (m["lam"] * 2 * math.pi * f) ** 2 / 2.0 * F
                 + m["Kh"] * f * (2 * m["lam"]) ** m["beta"])
        cal.append(dict(name=name, f=f, dyno=P, model=model,
                        rel_error=(model - P) / P, lamEddyFactor=F))

    # Analytic limits of the three AC factors.
    mu0 = 4 * math.pi * 1e-7
    d = m["cabDia"]
    skin = []
    # The Bessel power series below is an alternating series, so its accuracy
    # degrades once |ka| gets large: it is good to ~1e-9 relative through about
    # 400 kHz here, and by 3 MHz (|ka| ~ 84) cancellation has cost several
    # digits.  The motor drive is modelled to a few hundred kHz, so the anchors
    # stop there and the limit is stated rather than papered over.
    for f in (50.0, 40e3, 60e3, 300e3):
        delta = math.sqrt(1.72e-8 / (math.pi * f * mu0))
        fr = _skin_fr(f, d)
        skin.append(dict(f=f, Fr=fr, asymptote=d / 2.0 / (2 * delta),
                         difference=fr - d / 2.0 / (2 * delta)))
    factors = dict(
        skinFr_dc=_skin_fr(1e-6, d),
        skin=[dict(s) for s in skin],
        skin_series_valid_through_Hz=400e3,
        dowellFr_dc=_dowell_fr(1e-6, m["dStrand"], m["mLayers"], m["poros"]),
        dowellFr_60k=_dowell_fr(60e3, m["dStrand"], m["mLayers"], m["poros"]),
        lamEddyFactor_small_xi=_lam_eddy(1e-9, m["dLam"], m["rhoLam"], m["muRLam"]),
        lamEddyFactor_xi_times_F=_lam_eddy(1e9, m["dLam"], m["rhoLam"], m["muRLam"])
        * (m["dLam"] / math.sqrt(m["rhoLam"] / (math.pi * 1e9 * mu0 * m["muRLam"]))),
    )
    return dict(
        source="lehner7050Params.m calibration rows + analytic AC-factor limits",
        generatedBy="FET_FOM/reference/make_external.py",
        note="kh and ke are DERIVED from these two dyno rows, so reproducing them "
             "checks the calibration and its port, not the dyno data.  The AC "
             "factor limits are analytic.",
        derived=_clean_dict(m, ("cal",)),
        cal=cal, factors=factors,
    )


def _clean_dict(d, drop=()):
    return {k: v for k, v in d.items() if k not in drop}


# ---------------------------------------------------------------------------
# Inductor bias (L vs I) and thermal anchors, scraped from Wuerth REDEXPERT
# ---------------------------------------------------------------------------
# The committed WE_*.m grids assume the NOMINAL inductance.  Real cores roll
# off, and at the bias a design actually runs at the ripple can be several times
# what a nominal-L calculation predicts.  redexp_pull.py recovers the incremental
# inductance against bias; this turns it into the anchor file the engine bakes in.
#
# THE VALIDITY RULE, which is the whole reason this is not a straight copy.
# REDEXPERT models the roll-off while `warnOnBias` is False.  Once it is True --
# or once the field disappears from the response entirely -- the model has given
# up: deltail reverts to the nominal-inductance value, so L_eff snaps back to
# L_nom and the reported ripple looks better than it is, while a meaningless
# thermal rise keeps climbing.  Measured on 74437636351012: the curve runs down
# to 74.85 uH at 28.6 A, then reads 110.13 uH (exactly nominal) at 32.6 A with
# warnOnBias True.  A naive scrape would record "no saturation at 32 A".
# So the stored curve stops at the last valid point and the rejected points are
# kept separately as evidence.
def inductor_bias():
    import glob
    src = os.path.join(HERE, "data", "redexpert_bias.json")
    if not os.path.exists(src):
        raise SystemExit("missing %s -- run reference/redexp_pull.py first" % src)
    with open(src) as f:
        raw = json.load(f)

    parts = {}
    for pn, rec in raw["parts"].items():
        curve, rejected = [], []
        for b in rec["bias"]:
            # valid only while the vendor model is still modelling the core
            if b.get("biasValid") is False and b.get("Leff"):
                curve.append(dict(I=b["I"], Leff=b["Leff"], dI=b["dI"],
                                  Pac=b.get("Pac"), dT=b.get("dT")))
            else:
                rejected.append(dict(I=b["I"], Leff=b.get("Leff"),
                                     dI=b.get("dI"), biasValid=b.get("biasValid")))
        if len(curve) < 3:
            print("  warn: %s has only %d valid bias points" % (pn, len(curve)))
        curve.sort(key=lambda r: r["I"])
        lnom = rec["Lnom"]
        # Sanity: with almost no bias the incremental inductance IS the nominal
        # one.  If that fails the excitation or the field mapping is wrong, so it
        # is asserted rather than assumed.
        low_ratio = curve[0]["Leff"] / lnom if curve else None
        if low_ratio is not None and not (0.95 <= low_ratio <= 1.05):
            raise SystemExit("%s: low-bias L_eff/L_nom = %.4f, expected ~1 -- "
                             "check the excitation and units" % (pn, low_ratio))
        parts["WE_" + pn] = dict(
            Lnom=lnom, Isat30=rec["Isat30"],
            curve=curve, rejected=rejected,
            IvalidMax=curve[-1]["I"] if curve else None,
            LeffMin=min(r["Leff"] for r in curve) if curve else None,
            lowBiasRatio=low_ratio,
            thermal=[dict(I=t["I"], dI=t["dI"], dT=t.get("dT"),
                          dTmax=t.get("dTmax"), Pac=t.get("Pac")) for t in rec["thermal"]],
        )
    return dict(
        source="reference/data/redexpert_bias.json (Wuerth REDEXPERT, scraped)",
        generatedBy="FET_FOM/reference/make_external.py + redexp_pull.py",
        excitation=raw.get("excitation"),
        caveat=raw.get("caveat"),
        rule="curve[] keeps only rows where warnOnBias was False, i.e. where "
             "REDEXPERT was still modelling the core; rejected[] keeps the rows "
             "past that point, where the ripple reverts to the nominal inductance.",
        parts=parts,
    )


def main():
    os.makedirs(OUT, exist_ok=True)
    files = {"an030.json": an030(), "an017.json": an017(),
             "datasheet_anchors.json": datasheets(),
             "ripple_anchors.json": ripple(),
             "inductor_anchors.json": inductors(),
             "cap_anchors.json": capacitors(),
             "machine_anchors.json": machine(),
             "bias_anchors.json": inductor_bias()}
    for name, obj in files.items():
        p = os.path.join(OUT, name)
        with open(p, "w") as f:
            json.dump(obj, f, indent=1)
            f.write("\n")
        print("wrote %s" % p)

    a = files["an030.json"]["engine_check"]
    print("\nAN030 cross-check (per-cycle energies, EPC2361, 48 V, 20 A):")
    print("  Eon+Ifall mine = %.6e   AN030 = %.6e   ratio %.9f"
          % (a["Eon_plus_ifall_per_cycle"], a["Eon_plus_ifall_expected"],
             a["Eon_plus_ifall_per_cycle"] / a["Eon_plus_ifall_expected"]))
    print("  kSoftOff=1  mine = %.6e   AN030 naive = %.6e   ratio %.9f"
          % (a["overlap_kSoftOff_1p0_per_cycle"], a["overlap_kSoftOff_1p0_AN030_naive"],
             a["overlap_kSoftOff_1p0_per_cycle"] / a["overlap_kSoftOff_1p0_AN030_naive"]))
    print("  overlap mine(k=0.22) = %.6e   expected = %.6e"
          % (a["overlap_kSoftOff_0p22_per_cycle"],
             a["overlap_kSoftOff_0p22_expected"]))
    print("  Eoff_soft / AN030 voltage-rise = %.4f  (kSoftOff refinement)"
          % a["Eoff_soft_over_AN030_vrise"])
    print("  coss  V*Qoss = %.6e   Eoss = %.6e   2Eoss = %.6e"
          % (a["coss_VQoss_per_cycle"], a["coss_Eoss_per_cycle"],
             a["coss_2Eoss_per_cycle"]))
    print("  coss  V*Qoss / Eoss = %.6f  (expect exactly 3 for a V^-0.5 law)"
          % (a["coss_VQoss_per_cycle"] / a["coss_Eoss_per_cycle"]))
    print("  qrr   GaN = %.3e   Si(N=1) = %.3e   AN030 Si = %.3e"
          % (a["qrr_GaN_per_cycle_per_leg"], a["qrr_Si_N1_per_cycle_per_leg"],
             files["an030.json"]["expected"]["Qrr_AN030_per_die"]))
    print("  gate  2*Qg*Vdrv = %.6e   engine = %.6e"
          % (a["gate_expected_2QGVdrv"], a["gate_per_cycle_per_position"]))
    r = files["an017.json"]
    print("\nAN017 FOM_HS / FOM_SS [mOhm*nC]:")
    for k, v in r["rows"].items():
        print("  %-10s %-3s FOM_HS=%8.2f  FOM_SS=%8.2f"
              % (k, v["technology"], v["FOM_HS_mOhm_nC"], v["FOM_SS_mOhm_nC"]))
    print("  IRF7759 / EPC2361 FOM_HS = %.1fx  (GaN better)"
          % r["direction"]["FOM_HS_improvement_Si_over_GaN"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
