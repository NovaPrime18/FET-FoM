# Power-Stage Design Workshop

A single-file, offline, MATLAB-free calculator for **power-FET losses**, for
comparing **GaN against silicon** on the same operating point, and for **designing
the power stage around them** — the ripple, the inductance that holds it, the
capacitance that absorbs it, the core it runs in, and the machine on the other end.

Open `fet_fom.html` by double-clicking it. There is no server, no build step, no
network access and no dependency of any kind — the page is one HTML file with the
loss model, the magnetics and machine models, and a library of the fourteen devices
and seven inductors already inside it.

There are two workspaces, switched in the header:

- **Compare FETs** — the original dashboard: loss breakdown, FOM, sweeps and the
  N × f_sw map. Its behaviour and every number in it are unchanged, and a test
  asserts that a workspace round-trip does not disturb them.
- **Design the power stage** — topology-driven. The topology decides what the
  magnetics *are* (see §12): with a 3-phase inverter the winding is the inductance
  and the stator iron is the core; with any DC-DC topology it is a discrete filter
  inductor and its own steel. The **operating point is shared** with the comparator
  and editable from either workspace, so the bus, current and power behind a set of
  numbers is always visible rather than inherited silently. It answers *what
  inductance holds this ripple, what capacitance holds this voltage, what does the
  whole stage lose, and at what carrier frequency* — including a real **interior
  f_sw optimum**, which the FET-only comparator does not have. Both the inductor
  and the capacitor bank have a **custom entry**, because none of the committed
  parts fits the reference current.

```
FET_FOM/
  fet_fom.html                  the tool (engine + UI + seed library in one file)
  README.md                     this file
  reference/reference.py        Python transcription of the MATLAB models -> golden.json
  reference/make_external.py    builds the external anchors from EPC AN030 / AN017 / the datasheets
  reference/emit_magparts.py    writes the inductor library block into the HTML from the anchors
  reference/redexp_pull.py      build-time scrape of REDEXPERT bias + thermal data (cached)
  reference/data/               redexpert_bias.json -- the committed scrape
  reference/golden.json         generated reference values
  reference/external/           an030, an017, datasheet_anchors, ripple_anchors,
                                inductor_anchors, cap_anchors, machine_anchors,
                                bias_anchors
  tests/                        node --test suites + jsdom UI smoke test
```

## How to drive it

The page is a three-column dashboard, and the centre column is the answer.

The page opens on a stored default scenario — 3-phase, 58 V bus, 80 A rms phase, 25 kHz,
**EPC2361 against IAUTN08S7N006ATMA1** at N = 1 each, with a 1 nH commutation loop and a
0.3 nH shared source plane. It is baked into the page as the initial UI state and kept as
`fet_fom_scenario.json` for provenance, and it is a starting point, not a constraint: a URL
hash, an imported scenario, or any edit overrides it ("Reset page" clears the hash, so it does
return here). The engine's own `defaultOp()` (and the reference point in §7) stays the
`DeviceFOM.m` convention at 40 kHz / 165.4 A rms, which is what the golden cases and the test
suite pin.

- **Left — Application.** The operating point, grouped into *Topology & build*, *Switching*,
  *Bus & load*, *Gate drive* and *Ambient*. **Gate drive carries a rail per device**: leave a
  field blank and that device is driven at its own recommended rail (`VgsRec`), so a 10 V Si
  part and a 5 V GaN part are compared each at its own rail rather than one shared one.
  **The parallel count is per device as well** — 4 GaN dice against 2 Si dice is a valid
  build, and the N charts mark both counts. Every
  field that carries an assumption has an
  info marker; hover it rather than reading prose. **Advanced — estimates** keeps the thermal
  model, the Coss basis, the gate-loop model and the charge exponents, collapsed by default.
- **Centre top — the answer at a glance.** A schematic of the selected topology, with the
  switch symbols drawn in device A's technology colour, beside seven headline numbers: the
  winner at this build and by how much (loss **and** the efficiency gap in percentage
  points), both total FET losses, **the load power being switched** (`P_out`), **both
  semiconductor-only efficiencies**, both junction temperatures, both `N_opt`, and the
  N-invariant technology ratio. The two verdicts (winner, technology FOM) and the two
  context numbers (power switched, efficiency) each share one card as two side-by-side
  bubbles, so the strip stays compact instead of running to seven stacked cards.
- **Centre — the comparison.** Three tables: your build for both devices (each at its own chosen
  parallel count), each device at
  its own `N_opt`, and the N-invariant figures of merit. Each loss row puts the number and
  its bar in **separate columns**: the bar lives in a fixed-width track anchored at zero and
  is scaled to the largest component term in that table, so bar lengths are comparable down
  the column and the bar can never run under the numeral. **Hover any underlined term, or any
  bar**, for its definition and its share of the loss budget. Tooltips are a single
  fixed-position layer on `<body>` — **not** native `title` attributes — so a long
  definition wraps in a bounded box next to its trigger and disappears the moment the
  pointer leaves. Native titles cannot be sized or wrapped, and a long one gets clipped
  into a stub floating wherever the cursor happens to be. The longer explanations are
  folded into the "How to read this comparison" disclosure.
- **Centre bottom — the design space.** Loss vs frequency (dual trace, a dashed line at your
  `f_sw`, a log/linear axis toggle, and **no minimum marked** because with FET
  losses alone the curve is monotonic and its lowest point is just the sweep edge), loss vs
  parallel count (your N marked, with a pill behind each optimum label); a second
  chart beneath it plots **junction temperature against N** on its own axis with
  each part's limit dotted in, so the feasibility frontier is visible without a
  runaway point dictating the scale; and the N × f_sw map, where the outlined row is
  your N and a **labelled colour bar** gives the wattage scale. Hover a cell for a tooltip, or **click one to pin** its
  exact value in the readout beneath — which is the touch-device path.
- **Right — devices, warnings, library.** Warnings render as separate cards, sorted
  critical-first, each with a severity icon, a short bold title and the detail sentence. The
  severity modifier is a namespaced `sev-*` class and the help badge is scoped to `span.info`,
  because a bare `info` on the card collided with the badge rule (`inline-flex`, 15×15,
  `border-radius:50%`) and collapsed that one card into a blob with its text spilling out. A
  warning raised by *both* devices is shown once with an `A/B` badge instead of being
  printed twice, and datasheet provenance sits behind a disclosure so the panel is not a
  wall of grey text. The library panel exports, imports, saves a scenario and copies a
  share link.

The **25 °C / converged-T<sub>j</sub>** switch sits at the top of the loss breakdown, because it
changes every number in the two tables beneath it.


---

## 1. What it computes, and what it deliberately does not

**You give it:** a topology (3-phase inverter, synchronous buck, synchronous
boost, or 4-switch bidirectional buck-boost), the operating point (voltages,
current or power, switching frequency, modulation index, dead time, gate drive),
and one or two devices.

**It gives you:** the FET loss terms, a technology figure of merit, and an A/B
comparison — plus a switching-frequency sweep, a parallel-count optimiser, and an
N × f<sub>sw</sub> design-space map.

**Every loss figure the tool reports is a whole-bridge total for the build
shown** — the hero "Total FET loss" card, every loss-table row, the chart axes
and the N × f<sub>sw</sub> map alike: all legs, both switch positions, all N
dice or ICs in parallel, plus the shared gate drivers and (if set) loop
ringing. It is neither per leg nor per die — the semiconductor-only efficiency
is taken against the converter's whole P<sub>out</sub>, so the loss must be the
whole-converter figure too. The average per-die silicon loss is
`die total / (positions × N)`; the hint line under each loss table prints it
(in the 3-phase case: 3 legs × 2 positions × N dice).

**In scope — the FETs only:**

| Term | What it is |
|---|---|
| Conduction | `I²·Rds(on)(Tj)` across the switch positions |
| V–I overlap | the hard turn-on (and the residual turn-off) overlap |
| Output capacitance | the `V·Qoss` charge burnt at the hard turn-on |
| Dead time | third-quadrant / body-diode conduction while both devices are off |
| Reverse recovery | `Qrr` — the term that separates silicon from GaN |
| Loop ringing | `0.5·L_loop·I_rms²·fsw` at each hard commutation, averaged over the fundamental |
| Gate / driver | gate charge for discrete parts, plus quiescent draw for integrated stages |
| Junction temperature | solved self-consistently against `Rds(on)(Tj)` |

**Out of scope of the comparator, on purpose:** the comparator stops at the
semiconductor. Inductor and core loss, capacitor ESR, machine copper and iron loss
and the DC-link path *are* modelled — but in the **design workspace**, where they
belong to one design rather than being smeared across a device comparison. The
comparator's efficiency therefore stays semiconductor-only and labelled as such;
the design workspace reports a whole-stage figure instead.

**Out of scope of both:** any time-domain or transient simulation, control-loop
design and stability, EMI and EMC spectra, thermal FEA, PCB parasitics beyond the
existing `L_loop`/`L_csi`, and capacitor ESR versus frequency (this repo commits no
capacitor datasheets, so every seeded capacitor is badged generic). L(I) saturation
roll-off **is** modelled — see §12.6 — for the parts a REDEXPERT bias curve covers;
everything else still gets a warning instead. What is left is a closed-form
design-point calculator and Pareto explorer, not a waveform simulator, which is the
layer at which a sizing decision is actually made.

**Also out of scope for now:** asymmetric legs (a GaN high side with a silicon low
side). High and low side are assumed to be the same part. For matched halves the
conduction term is exact for any modulation index and power factor, because
`<i²d> = <i²(1−d)> = ½<i²>` (`DeviceFOM.m`).

---

## 2. Where each formula comes from

The model is a transcription of the MATLAB in `../Switching_Losses/`, with one
substantive addition.

| Term | Source |
|---|---|
| Conduction | `motorDriveLoss.m` (`L.cond`), `boostBridgeLoss.m` (`P.condLS/HS`) |
| V–I overlap | `Mos_switching.m`, `motorDriveLoss.m` (`Eon`/`Eoff`), `DeviceFOM.m` (`eOv`) |
| Coss | `boostBridgeLoss.m` (`P.Ecoss`), `DeviceFOM.m` (`eCos`), EPC AN030 §3 |
| Dead time | `motorDriveLoss.m` (`L.dead`), `boostBridgeLoss.m` (`P.dead`) |
| **Qrr** | `Mos_switching.m` (`LPdrr`) — **added to every topology here**, and scaled with `Tj` |
| **Turn-off current fall** | EPC AN030 §2.2.1 — **added**; see below |
| **Loop ringing** | not in any `.m` file; added because it dominates this current class |
| Gate / driver | `motorDriveLoss.m` (`L.gate`), `boostBridgeLoss.m` (`P.drvDyn/Stat`) |
| FOM, `N_opt`, loss floor | `DeviceFOM.m` |
| `FOM_HS`, `FOM_SS` | EPC AN017 |

**The one substantive addition.** `MotorDriveLoss.m` and `boostBridgeLoss.m` have
no reverse-recovery term; only the older `Mos_switching.m` carried one. GaN's Qrr
is a true zero and silicon's is not (the seeded `IRF7759` is 150 nC), so a tool
built to compare the two technologies would systematically flatter silicon if it
left Qrr out. It is therefore counted in all four topologies as
`nHard · fsw · Qrr · Vsw`, matching EPC AN030 §4.

---

## 3. N-scaling — the table that matters

Every quantity commits to how it scales with the number of dice N per switch
position. N is per device, so A and B may run different counts — the table below
applies to each independently, and the A/B comparison is then a comparison of two
different builds rather than of two devices in the same build. This is written
down explicitly because a factor-of-N error is exactly
the mistake that a cross-port golden test cannot catch: both ports would make the
same wrong choice. Instead, `tests/engine.test.mjs` measures the realised exponent
per term and checks it against this table.

| Term | Discrete, shared external driver | Integrated, per-die driver |
|---|---|---|
| Conduction | **N⁻¹** (`Rds(on)/N`) | **N⁻¹** |
| V–I overlap | **N¹** (charge ×N, shared driver current fixed) | **N⁰** (per-IC energy at `Icom/N`, fixed `tsw`) |
| Coss | **N¹** (Qoss ×N) | **N¹** |
| Dead time | **N⁻¹ … N⁰** | **N⁻¹ … N⁰** |
| Qrr | **N¹** by default | **N¹** by default |
| Qrr(Tj) | **N¹** by default, times the temperature factor | **N¹** |
| Loop ringing | **N⁰** — layout inductance, not device | **N⁰** |
| Gate / driver | **N¹** | **N¹** |

Two of these deserve a note.

- **Dead time falls with N.** The group still carries `Icom`, but the reverse drop
  is `Vsd(Icom/N)`, so paralleling dice lowers it. The loss runs from N⁻¹ in the
  linear region to N⁰ once the fit is clamped near zero. (An earlier review
  suggested N⁰…N¹; the sign is the other way.)
- **Qrr scales as N by default.** A datasheet gives one `Qrr` at one test current.
  Each paralleled die brings its own body diode, so `N · Qrr` is the honest
  reading of a single data point. If Qrr were linear in current the group total
  would be N⁰ instead, and reality is between the two. `qrrExp` is exposed so you
  can sweep it; the default is the conservative choice against silicon.

---

## 4. Figures of merit

`R·E` is the technology comparator. With `E` the switching energy per commutated
amp, `R·E` is invariant to die area **and** to paralleling, because `R ~ 1/area`
and `E ~ area`, so `(R/N)·(E·N) = R·E`. That is what makes it a statement about
the technology rather than about one part number.

- `eOv` — overlap energy per commutated amp [µJ/A], the current-invariant
  comparison `DeviceFOM.m` calls the real one.
- `R1/eOv` — how much die you must buy to get there.
- `N_opt = √(A/B)` with `A = Σ R1·I²` and `B = fsw·a + Pstat`. It is the
  continuous minimiser of `A/N + B·N`; the tool rounds to the better neighbour and
  reports the rounding cost, which is small because the optimum is quadratically
  flat: 10 % off costs 0.5 %, a factor of two costs 25 %.
- `FOM_HS = (Qgd + Qgs2)·Rds(on)` and `FOM_SS = (Qg + Qoss)·Rds(on)` — EPC's own
  published figures of merit (AN017), so the tool's numbers can be checked against
  a vendor table rather than only against itself.

**Sanity anchor:** on the Lehner 7050/10 point from `Fsw_Optimum_Lehner7050.m`,
`EPC2361` comes out at `N_opt = 4.10`, i.e. N = 4 — which is exactly the value that
file records as coming out of `Npar_Optimum.m`.

### Comparison is shown three ways

1. **Shared build** — both parts at your N.
2. **Each at its own `N_opt`** — because `N_opt` differs per technology and that
   is the entire point of the FOM section; comparing at a fixed N embeds an
   arbitrary design decision.
3. **N-invariant FOM** — `R·E`, `eOv`, `FOM_HS`, which cannot be gamed by N at all.

---

## 5. Thermal model, and why the junction does not lie

```
P_die_group = cond + overlap + Coss + dead + Qrr          (gate/driver excluded)
Tj = Tamb + RthJC·(P_die_group/N) + RthCA·P_die_group + RthSink·P_die_bridge
Rds(on)(Tj) = Rds(on)@25C · (1 + kTperC·(Tj − 25))
```

`RthJC` is per die; `RthCA` is the case-to-ambient path of one switch position's
copper, shared by its N dice; `RthSink` is an optional whole-bridge sink. This is
the honest middle between two common mistakes: applying `RthJC` per die *only*
under-states the shared-copper rise, while applying `RthJC` to the whole group
loss (forgetting the `/N`) over-states it by roughly N. `tests/engine.test.mjs`
pins both directions.

The fixed point is iterated until it stops moving. **Divergence is a reported
outcome, not a number:** the tool evaluates the loop gain

```
gain = [ (RthJC/N + RthCA)/n_positions + RthSink ] · kTperC · P_cond_at_25C
```

and if it reaches 1 it says *thermal runaway — add copper or parallel dice* and
refuses to print a junction temperature. The gain must be referenced to the
group's conduction, because the per-position paths see `P_group/n_positions`
while the shared sink sees the whole bridge; using the un-divided form overstates
the gain by exactly `n_positions` and invents runaway on builds that converge
fine. That was a real bug, and `tests/engine.test.mjs` now pins both the formula
and the position-count factor.

Warnings are returned as structured objects — `{severity, code, title, detail}` —
so the panel can lead with an icon and a short title, and so a consumer can branch
on `code` instead of pattern-matching prose.

A `simple` mode collapses the model to a single per-position `Rth`, for when you
just want one number, and a flat `kT` multiplier is available so that
`DeviceFOM.m`'s `kT = 1.25` convention reproduces exactly.

`kTperC` defaults from the technology where the datasheet in this repo does not
carry it (GaN ≈ 0.006 /°C, Si ≈ 0.008 /°C) and is flagged as an **estimate** in
the UI and in the library.

---

## 6. The Coss factor, stated plainly

The default capacitive loss is **`Vsw · Qoss(Vsw)`**, which is the expression EPC
AN030 derives for a symmetric half-bridge ("the bus will provide the total energy
`Vbus·QOSS`"). It is not `Eoss`, and it is not `2·Eoss`.

For a GaN-like `Coss ~ V^−0.5`, this equals **`3·Eoss` exactly** when the part is
energy-specified (verified on `EPC23102`: 1.500 µJ = 3 × 0.500 µJ). When a
datasheet specifies both charge and energy the ratio is close but not exact
(`ISG3202LA`: 2.500 µJ vs 0.875 µJ, i.e. **2.857×**). Against the common `2·Eoss`
rule of thumb the ratio is therefore **1.50** for the energy-specified case and
**1.43** for `ISG3202LA`.

So if you are used to budgeting `2·Eoss`, the default here will look 1.4–1.5×
worse on that one line. That is the deliberate, EPC-documented choice, and the
`cossBasis` advanced selector lets you switch to `2·Eoss` or `Eoss` to see the
sensitivity rather than having to take it on trust.

---

## 7. Seeded device library

All fourteen devices are seeded as **per-die / per-IC raw values**, exactly as the
`.m` constructors hold them before their `MOSparallel` scaling, which the engine
now applies explicitly.

| Part | Tech | Kind | Rds(on) | Idc | Qrr | N_opt (this library's FOM) |
|---|---|---|---|---|---|---|
| EPC2361 | GaN | discrete | 0.75 mΩ | 101 A | 0 | 4.10 → **4** |
| EPC2367 | GaN | discrete | 1.2 mΩ | 101 A | 0 | 6.61 → 7 |
| EPC2304 | GaN | discrete | 3.5 mΩ | 133 A | 0 | 10.44 → **10** |
| EPC2305 | GaN | discrete | 2.2 mΩ | 133 A | 0 | 8.44 → **8** |
| EPC2218 | GaN | discrete | 2.4 mΩ | 60 A | 0 | 10.90 → 11 |
| EPC2252 | GaN | discrete | 8.0 mΩ | — | 0 | 36.78 → 37 |
| EPC2204 | GaN | discrete | 4.4 mΩ | — | 0 | 19.60 → 20 |
| EPC2044 | GaN | discrete | 7.0 mΩ | — | 0 | 34.15 → 34 |
| EPC2065 | GaN | discrete | 2.7 mΩ | — | 0 | 12.70 → 13 |
| **IRF7759** | **Si** | discrete | 1.8 mΩ | — | **150 nC** | 2.63 → 3 |
| **IAUTN08S7N006ATMA1** | **Si** | discrete | 0.53 mΩ | 350 A | **69 nC** | 0.59 → 1 |
| EPC23102 | GaN | bridge | 5.2 mΩ | 35 A | 0 | 29.85 → 30 |
| EPC23104 | GaN | bridge | 8.7 mΩ | 15 A | 0 | 47.52 → 48 |
| ISG3202LA | GaN | bridge | 2.4 mΩ | 60 A | 0 | 24.81 → 25 |

(N_opt is the `DeviceFOM.m` convention: 3-phase, N = 4, `kT = 1.25`, continuous
optimum. `EPC23102`/`EPC23104` are seeded from `DeviceFOM.m`'s datasheet-derived
`cfg.eSpec` block, **not** from `EPC23104.m`'s `Qg = 250 nC` shortcut, which that
file itself labels as cheating.)

**`EPC2361`, `EPC2367`, `EPC2304`, `EPC2305`, `ISG3202LA` and
`IAUTN08S7N006ATMA1` were checked
field-for-field against the datasheet PDFs committed in this repo**
(`EPC2361_datasheet.pdf`, `EPC2367_datasheet.pdf`, `EPC2304_datasheet.pdf`,
`EPC2305_datasheet.pdf`, `ISG3202LA_datasheet.pdf`,
`IAUTN08S7N006_datasheet.pdf`) and that check is a
test, not a claim. Fields that are estimates rather than datasheet values —
including `TjMax` and `QrrMax` for the parts whose datasheets are not in this
repo — carry an `est` list and are badged in the UI, for example `ISG3202LA.tsw`,
because that datasheet publishes no `Eon`/`Eoff` at all. The silicon
`IAUTN08S7N006ATMA1` (Infineon OptiMOS 7, 80 V, 0.53 mΩ typ / 0.57 mΩ max in
TOLL) is the mirror case: every static, charge and thermal row it needs is
datasheet-verified, and the model-only fields its datasheet does not publish —
`Qgth` (there is no `Qg(th)` row), `Qoss` (only `Coss` at 40 V is given), plus
`kTperC`, `RthCA` and `CSI` — are all flagged as estimates, so the tool never
presents a derived number as a datasheet one. `EPC2367` (100 V, 1.2 mΩ in a
3.3×3.3 mm QFN) is verified the same way, with only `Vpt`, `kTperC`, `CSI` and
`RthCA` estimated; its datasheet does publish `Qg(th)` and `Qoss`, so those need
no derivation. `EPC2304` (200 V, 3.5 mΩ typ / 5 mΩ max) and `EPC2305` (150 V,
2.2 mΩ typ / 3 mΩ max) — the top-side-cooled 3×5 mm PQFN eGaN parts — are
verified the same way, with only `Vpt`, `kTperC`, `CSI` and `RthCA` estimated;
their datasheets publish `Qg(th)` and `Qoss` (at 100 V and 75 V respectively),
and their `RthJC` is the datasheet's 0.2 K/W junction-to-case-top value.

### The GaN-vs-silicon headline

`EPC2361` vs `IRF7759`, 58 V bus, 40 kHz, 165.4 A rms phase, N = 4, 25 °C.
This reference point keeps the `DeviceFOM.m` convention of one shared 5 V rail
(which the plateau safeguard lifts to 12 V for the silicon part, so it is not
under-driven); the **live tool now defaults to each device's own rail** instead —
see §9.

| Term | EPC2361 (GaN) | IRF7759 (Si) |
|---|---|---|
| Conduction | 19.24 W | 46.17 W |
| V–I overlap | 13.60 W | 50.30 W |
| Coss | 2.70 W | 1.80 W |
| Dead time | 2.99 W | 1.06 W |
| **Qrr** | **0.00 W** | **4.18 W** |
| Loop ringing | 0.00 W (`L_loop` = 0) | 0.00 W |
| Gate / driver | 0.13 W | 2.30 W |
| **Die total at 25 °C** | **38.53 W** | **103.50 W** |

These, like every loss figure in the tool, are whole-bridge totals for the
build — here 3 legs × 2 positions × N = 4 dice = 24 dice — so the per-die
silicon loss is 38.53 / 24 ≈ 1.6 W for the GaN half.

With self-heating at the default `RthCA` = 5 °C/W, the same two parts give
**39.90 W at Tj = 81 °C** (GaN) and **175.76 W at Tj = 267 °C** (silicon). The
silicon figure is flagged **critical — above its 175 °C limit**, and that is the
point: view 2 crowns GaN against a device the tool has just cooked past its
rating, so it now says so instead of quietly reporting the number.

The silicon part wins only on Coss and dead time. Everywhere else — and especially
on the overlap, which is where `FOM_HS` says it should — it pays.

---

## 8. Tests, and how much to trust them

```bash
node --test                 # 137 tests; the UI suite skips cleanly when jsdom is absent
python3 reference/reference.py       # regenerate golden.json
python3 reference/make_external.py   # regenerate the external anchors
python3 reference/redexp_pull.py     # refresh the REDEXPERT bias/thermal scrape (cached)
python3 reference/emit_magparts.py   # rewrite the inductor library block from them
```

The UI tests need a DOM, so they skip cleanly unless jsdom is available:

```bash
npm install --no-save jsdom     # test-only; the tool itself has no dependencies
node --test                     # 92 tests, 0 skipped
```

**The internal oracle cannot validate the physics.** `reference/reference.py` is a
transcription of the same MATLAB text the JavaScript is a port of, so both ports
can share a mistake and still agree. It catches port and transcription errors,
nothing more. There is no MATLAB or Octave on this machine, so the oracle could
not be run against the original.

Physics-level trust therefore comes from three external anchors:

1. **EPC [AN030 Hard Switching Losses Calculation](https://epc-co.com/epc/portals/0/epc/documents/application-notes/AN030%20Hard%20Switching%20Losses%20Calculation.pdf)** —
   the same four-way split. The tests check that the turn-on overlap matches
   AN030's method exactly, that the symmetric-half-bridge Coss loss is
   `Vbus·QOSS`, that Qrr is `QRR·Vbus·fsw` and exactly zero for every GaN part,
   and that gate loss is `QG·VGS` outside the die.
2. **EPC [AN017](https://epc-co.com/epc/design-support/application-notes/an017-fourth-generation-egan-fets-widen-the-performance-gap)** —
   `FOM_HS` and `FOM_SS` reproduced from their published definitions, and the
   direction asserted (the seeded GaN part is **27.8×** better on `FOM_HS`).
3. **The datasheets in this repo** — the seeded values checked against the
   specification rows extracted from the PDFs.

Three UI tests deserve a note. One pins the warning-card geometry and structure for every
severity, so a class collision that collapses a card cannot come back. Another asserts the
tooltip layer is a portal on `<body>`, is
positioned above the page, and that **no native `title` attribute remains anywhere** — so
a clipped native tooltip cannot come back. The other asserts that **no HTML-only tag** (`sub`, `sup`, `b`, …)
appears inside a generated SVG, and that no text is hoisted out of an SVG into its host
element. Browsers close an `<svg>` early at such a tag and push the remainder into the page
as stray text, which renders as floating words sitting on top of unrelated panels — a real
bug this guard was written after finding.

Plus two structural checks that no golden could provide: the per-term N-scaling
exponents are measured and compared against §3, and `N_opt` is verified to
actually minimise `A/N + B·N` over a swept integer range. A jsdom smoke suite
executes the real page: it renders all four topologies, checks that the topology
schematic actually changes per topology and that the hero KPIs and hover
definitions are present, exercises the log-axis toggle and the temperature
toggle, the device switch and the part editor, restores a scenario from the URL
hash, and drives the actual file import path — scenario files, part-library
files, a wrong-`schemaVersion` refusal, and an export-then-reimport round-trip.

---

## 9. Terms added after the first external review

| Term | What it is and why it changed |
|---|---|
| **Turn-off current fall** | AN030 §2.2.1: `0.5·Vsw·Icom·(Qgs−Qgth)/Ig_off`, **not** scaled by `kSoftOff`. When the gate-limited current fall is slower than the Coss commutation the node is already at the bus, so this phase is hard switching. `kSoftOff` now scales only the soft voltage-rise phase, and at `kSoftOff = 1` the engine reproduces AN030's entire turn-off triangle exactly (verified: ratio 1.000000000). On the reference silicon part this was worth **+8.7 W**, on GaN **+1.5 W**. |
| **Loop ringing** | `0.5·L_loop·I_rms²·fsw` per hard-switching leg. Layout inductance, so it does **not** fall as you parallel dice — which is precisely why it flattens the benefit of a large N. It is off by default so the reference numbers stay comparable, and when it is zero the tool *says so and quantifies it at 5 nH* (8.2 W at the reference point) rather than letting the total look complete. |
| **`Qrr(Tj)`** | `Qrr(25)·(1 + k·(Tj − 25))`, `k` = 0.01 /°C by default (doubles over 100 °C), evaluated at the converged junction temperature. A single 25 °C datasheet point badly understates the term on a hot device: 4.18 W → 14.27 W in the example above. |
| **`TjMax` check** | Every part carries a junction limit — verified against the datasheet PDFs committed in this repo for `EPC2361` and `ISG3202LA`, flagged as an estimate elsewhere. Exceeding it raises a **critical** warning, and `Tj` gets its own chart under the N sweep, with each device's limit dotted in, so the feasibility frontier is visible rather than inferred. |
| **typ/max toggle** | One control moves `Rds(on)`, `Qoss` and `Qrr` onto the datasheet maximum where one is recorded, and reports which fields had no maximum to move. Typical is the optimistic number; max is what you should design against. |

### Per-device gate drive, and why a shared rail is wrong

A silicon MOSFET is characterised at `V_GS = 10 V`, while a GaN HEMT is a 5 V
device whose absolute maximum is around 6 V, so one shared gate rail cannot be
right for both. The old shared default also interacted badly with the
"rail within 0.5 V of the plateau" safeguard: `IRF7759` (5 V plateau) was lifted
to the auto-selected 12 V, but the 4.4 V-plateau `IAUTN08S7N006ATMA1` was not and
stayed at 5 V — so the two devices were silently evaluated at different effective
rails, which is exactly the failure a comparator must not have.

Each device now resolves its own rail (`VdrvA` / `VdrvB`) with the precedence

```
per-device override  >  explicit shared op.Vdrv  >  the part's VgsRec  >  5 V
```

so a **blank field means "drive this device at its own recommended rail"**, and
the effective rail is printed in both loss-table column headers and in the device
panel. `Ron`/`Roff` stay shared board-level values, and the plateau safeguard is
applied per device. `gateFor` (`gate_for` in the oracle) implements this in both
ports, `golden.json`'s `gates` section pins the precedence, and a scenario or
share link saved before this change carries one shared `Vdrv` which is migrated
into the two per-device fields on load so it keeps the rail it actually used.

### Two things this tool will not pretend

- **There is no interior `fsw` optimum in the comparator — but there is in the
  design workspace.** With FET losses alone, loss is monotonic in frequency, so the
  lowest point of the comparator's sweep is always its left edge, and its chart says
  so rather than marking a fake minimum. Add the machine and a genuine interior
  minimum appears: raising the carrier costs switching loss and buys lower ripple
  copper and a smaller minor-loop iron loss. The design workspace finds it, and a
  test asserts both neighbours of the reported optimum are worse.

  The **DC-DC** side is where modelling saturation changes the *shape* of the
  answer, and it is pinned by a test. With a fixed **nominal** inductance the
  whole-stage total is monotonic in `fsw` and the optimum sits at the low edge.
  Model the roll-off and it is not monotonic at all: at low `fsw` the ripple is
  large, the peak current is high, the core rolls off, and the ripple grows
  further, so the core loss runs away — 18× the optimum at 5 kHz on the seeded
  build. That feedback pushes the optimum inward, which is something a nominal-L
  model simply cannot show. (The committed `BoostConverter.m` sweeps 50–400 kHz
  for a "peak efficiency frequency" using nominal inductance throughout.)
- **The `M` convention is correct.** An external review flagged `V_ph = M·Vdc/(2√2)`
  as an SPWM formula that overstates power above M = 1. It does not: M = 1
  reproduces exactly the SPWM ceiling `Vdc/(2√2)` = 20.506 V, and M = 2/√3
  reproduces exactly the SVPWM ceiling `Vdc/√6` = 23.678 V, so M is normalised
  with the two linear limits where they belong. Both were checked numerically
  and no change was made.

## 10. Deliberate divergences from the MATLAB, collected

1. **Qrr is counted in all four topologies** (§2), where the newer `.m` functions
   omit it.
2. **N-scaling is explicit** (§3) rather than by mutating the device struct in a
   constructor, so it can be tested and printed.
3. **A three-term thermal model replaces the flat `kT = 1.25`** (§5), with the
   flat multiplier retained as a selectable mode.
4. **`qrrExp = 0` by default** (conservative against silicon) rather than assuming
   a current cancellation a single datasheet point cannot support.
5. **The turn-off voltage rise is the soft refinement** from `motorDriveLoss.m`
   (`kSoftOff = 0.22`, anchored to EPC23102's measured `EOFF/EON = 0.06`), which
   sits below AN030's naive voltage-rise triangle by construction. The current-fall
   phase is separate and **not** reduced (see 9), so at `kSoftOff = 1` the engine
   reproduces AN030's full turn-off exactly.
6. **`V·Qoss` is the default Coss basis** (§6), not `Eoss`.
7. **Matched high/low side only** (§1).
8. **No inductor, motor, capacitor, PCB or shunt losses** (§1).
9. **The turn-off current-fall phase is now counted** (§9), which moves *towards*
   AN030 rather than away from it; `kSoftOff` now scales only the soft voltage-rise
   phase instead of the whole turn-off.
10. **`Qrr` is evaluated at the converged `Tj`**, and every part carries a `TjMax`
    that can veto an operating point outright instead of reporting it silently.
11. **`L_loop` is an input rather than a silent omission.** It defaults to zero so
    the reference numbers stay comparable, but the Warnings panel quantifies what is
    missing at 5 nH and says how to include it. Since a switched-off term would
    otherwise read as a broken calculation, the Loop ringing row prints **off** with
    an explanation on hover rather than `0.00`.
12. **The capacitor harmonic amplitude is corrected** (§12.3).
    `Capacitor_Losses.m` writes `8·ΔI/(π²n²)` while its own comment defines `ΔI` as
    the peak-to-peak ripple, so its harmonic current is 2× high and its ESR loss 4×
    high. This port uses `4·ΔI/(π²n²)` and a Parseval test pins the sum against the
    triangle's mean square `ΔI²/12`.
13. **The inductor library is generated, not hand-copied.** `emit_magparts.py`
    writes the 882 grid values into the HTML from the parsed anchors, and a test
    asserts them back, so the embedded data cannot drift from the committed `.m`
    files. The 126-row factorisation (axes carried once) keeps that block at ~9.6 kB.
14. **The design workspace reports a whole-stage efficiency**, distinct from the
    comparator's semiconductor-only figure, and never presents the latter as the
    former.

## 11. Sharing and data format

Exports carry `schemaVersion: 1`; import refuses a version this build does not
know rather than silently mis-reading fields. "Copy link" puts the whole operating
point and device selection in the URL hash, which works from a `file://` page and
sends nothing anywhere — the tool never makes a network request at all, which is
one of the tests.

The `est` arrays are sorted on load so exported JSON is deterministic.

`schemaVersion` is **2** since the design workspace was added. The importer accepts
**1 and 2**: a v1 file simply carries no design-workspace state, which that
workspace fills from its defaults, so it is still read exactly rather than migrated
lossily. A version this build does not know is refused, as before, instead of being
mis-read. The URL hash keeps its original keys and adds `ws` (workspace) and the
design state, so every link saved before the split still opens on the comparator.

---

## 12. The design workspace — what it models, and what anchors it

The topology decides what the magnetics **are**, so there is no free "load model"
selector. `PROFILES` in the engine declares, per topology, where the ripple comes
from, what the inductive element is, which core model applies, whether a machine
exists, and which capacitor nodes carry which kind of current:

| Topology (and mode) | The inductance | Its core | Node carrying the ripple **triangle** | Node carrying **switched** current |
|---|---|---|---|---|
| 3-phase SVPWM | the **motor winding**, plus an optional series line choke | stator iron (hysteresis + eddy + lamination skin) | — | the **DC-link bank** |
| buck | discrete filter inductor | its own steel | **output** cap | input cap |
| boost | discrete filter inductor | its own steel | **input** cap | **output** cap |
| 4-switch | discrete filter inductor | its own steel | follows the resolved mode: buck → output, boost → input, buck-boost → neither | the other node |

Those two node kinds carry different currents and get different models: a triangle
takes the harmonic sum with current division, a switched node takes the exact
two-level charge balance. `tests/engine.test.mjs` asserts the table itself, so the
capacitor panel cannot contradict the loss model.

**Sources.** `motorDriveLoss.m` supplies `svpwmRipple`, `dowellFr`, `skinFr` and
`lamEddyFactor`; `boostBridgeLoss.m` supplies the inductor `P.Lac`/`P.Lesr` split and
the DC-DC hard-switching convention; `estimate_ac_loss.m` supplies the log-log fit
and its conditioning guard; `lehner7050Params.m` and `Fsw_Optimum_Lehner7050.m`
supply the machine and the system-level tradeoff.

### 12.1 Ripple, and why the sizing answer is exact

`svpwmRipple()` returns **flux-domain** quantities — `lamPP`, `lamRms`, `Vrms`,
`fEff` — which are all independent of the inductance. Only the current depends on
`Ls`, by an exact `1/Ls`. That is not a trick for speed, it is what makes
`requiredL = lamPPmax / ΔI_target` a single division rather than a solve, and what
makes an `(fsw × L)` feasibility map cost one ripple evaluation per frequency
rather than one per cell.

Two properties are pinned as anchors rather than trusted:

- the normalised constant `lamPPmax·fsw/Vdc` is **exactly `1/6`** at the SVPWM
  linear limit `M = 2/√3` — the classic `ΔI_pp,max = Vdc/(6·L·fsw)` — and **exactly
  `1/(4√3)`** at `M = 1`. Both reproduce to ~2e-15 relative;
- `lamPPmax` is resolution-independent (spread ~1e-14 across `nSub` 24…6144), so the
  required inductance is exact at any setting. `Vrms` is *not*: it is a mean square
  over binned pulse widths and converges as `O(1/nSub)`, sitting ~0.9% below the
  converged value at the default 192. That is stated in the code and in the
  Advanced tooltip rather than hidden, because the machine's ripple eddy term
  consumes it.

`M > 2/√3` is clamped and flagged, and `M = 0` correctly yields zero ripple: with no
modulation there is no differential voltage across the winding even though every leg
still switches.

### 12.2 Inductor library and core loss

Seven Würth WE-HCF/HCM inductors are seeded from the committed
`Switching_Losses/WE_*.m` REDEXPERT scrapes. All seven share one `(f, ΔI, Idc)` axis
set, so the axes are carried once and each part carries only its 126 `P_ac` values —
about 9.6 kB in total instead of ~46 kB. The block is **generated** by
`reference/emit_magparts.py` from `reference/external/inductor_anchors.json`, which
`make_external.py` parses straight out of the `.m` files; a test asserts the embedded
values, the grid pairing and the fitted exponents back against that file, so a hand
edit cannot drift.

The fit is `P_ac = k·f^a·ΔI^b·Idc^c` by log-log least squares, solved through a
Cholesky factorisation of the normal equations with the same `1e4` conditioning
threshold as `estimate_ac_loss.m`. That guard exists for a real reason, documented in
that file: the older data swept `f` and `ΔI` along one converter curve, so `log ΔI`
was an affine function of `log f`, the design matrix went rank deficient, and the
solver returned `b = −0.215` — "more ripple, less core loss". The test reproduces
exactly that degenerate grid and demands a refusal.

The fitted bias exponents independently confirm the grid axes are paired
`f`/`ΔI`/`Idc` and not swapped — a cross-port test cannot catch such a swap, because
both ports would make it. The committed `.m` files document `c ≈ −0.05` for
`7443642200` and `c = −3.78` with 29% residual for `7443634700`; the port reproduces
`−0.048` and `−3.781` / 29.2%.

Two limits are stated rather than papered over: the power law is only an
interpolation (a point outside the fitted range raises an extrapolation warning), and
**L(I) roll-off is not modelled** — a part past its saturation current raises a
warning that says the ripple, the required-L answer and the core loss are all
optimistic, rather than silently pretending the inductance is nominal.

That matters immediately here: at the tool's own reference point (58 V, 165.4 A rms,
25 kHz) the required inductance is ~7.2 µH and **none of the seven committed parts
can carry the current** (they saturate between 7.5 A and 27 A). The realistic answer
is a part this repo does not have, which is why the selector has a **custom part**
path taking L, DCR, Isat and its own four exponents.

### 12.3 Capacitors, per node

`Capacitor_Losses.m` is reused exactly where it is valid — a node carrying the
inductor ripple **triangle** — and *not* where it is not. One deliberate divergence:
that script writes the harmonic amplitude as `8·ΔI/(π²n²)` while its own comment
defines `ΔI` as the **peak-to-peak** ripple. For a triangle the peak amplitude of
harmonic `n` is `4·ΔI/(π²n²)`, so the script is 2× high on current and 4× high on
ESR loss. This port uses the peak-to-peak definition consistently, and a Parseval
test pins it: the harmonic powers must sum to exactly `ΔI²/12`, the triangle's mean
square.

The pulsed nodes are exact and closed-form. The DC-link current is built from the
same min/max-injection SVPWM duties as the ripple model, with the pole voltage over
the bus as the switching function; its carrier-averaged value reproduces `P_out/Vdc`
to 1e-9, which is what ties it to the same power convention as the rest of the tool.
`requiredC` removes the bank's ESR step first: when the ESR step alone already
exceeds the voltage target, no capacitance can meet it, and that is reported as a
flag rather than as a negative capacitance.

Every seeded capacitor is **generic** — this repo commits no capacitor datasheets —
so each carries an `est` list and says so. There is a **custom bank** entry beside
them (capacitance and ESR per part, plus the series and parallel string counts),
because the realistic answer for a real design is usually a part this repo does not
have.

### 12.4 Machine

One machine is seeded: the Lehner TorQstar 3 7050/10. `λ`, `R_ph` and `L_s` are
**measured** (VESC 300/75, per-phase); the 5.9% saliency confirms a surface-PM
machine, so `id = 0` is MTPA. Everything else — `fracIron`, `β`, `kLm`, the
lamination and strand geometry, the cable and connector resistances — is in the same
`est` list the FET parts use.

`Kh` and `Ke` are **derived, not stored**: they come from the two no-load dyno rows
(7050/9 at 60 V and 7050/12 at 54 V), so feeding those rows back through the iron
model must reproduce them. It does — 262.18 W against 262.20 W and 138.51 W against
138.51 W, i.e. to 0.01%, which is a check of the calibration and of its port rather
than independent validation of the dyno data, and is labelled as such.

The three AC-resistance factors are anchored on their analytic limits, not on the
series they were computed from: `skinFr → 1` at dc and `→ a/(2δ) + 1/4` when the
skin depth is small (the classic asymptotic term, reproduced to ~0.02 for `a/δ ≥ 3`),
`dowellFr → 1` at dc while four layers give `Fr ≈ 35` at 60 kHz, and `lamEddyFactor
→ 1` for slow flux with `ξ·F → 3` once the flux is skin-limited. The Bessel power
series behind `skinFr` is good to ~1e-9 relative through 400 kHz and loses digits by
a few MHz; that bound is documented and the anchors stop where the model is used.

Two physical results are pinned because they are counter-intuitive. The winding gets
Dowell's proximity factor and the cable only skin effect — which is why `R_ph` is
split three ways at all — and the **iron** ripple loss does *not* fall when you add
inductance, because the flux swing is set by the applied volt-seconds, which are
inductance-free. Only the copper follows the current. Adding inductance is not a free
win for iron loss.

### 12.5 The whole stage

`stageSystem()` builds one budget from whichever terms the profile declares, and the
FET half is the **same** `computeLosses()` the comparator uses — the design workspace
feeds it the ripple-adjusted current rather than re-deriving the semiconductor model.
With zero ripple it lands on the comparator's number to 1e-12, which is a test.

For 3-phase the phase current becomes `√(Irms² + I_rip²)` for conduction and ringing,
while the commutated current for the overlap stays on the fundamental because it is a
per-event quantity. `stageSystem` drives `computeLosses` through `op` and does not
modify it, which is what keeps all 45 comparator golden cases bit-identical.

It reports a whole-stage efficiency, never the semiconductor-only figure, and an
`(fsw × L)` feasibility map in which a cell is usable only if every constraint holds
(ripple target, voltage ripple, junction temperature, saturation), with the reason
each cell failed — a Pareto view rather than a single operating point.

### 12.6 Bias, saturation and self-heating, scraped from REDEXPERT

The inductor loss grid above assumes the **nominal** inductance. A real core does
not: the incremental inductance of `7443634700` falls 47 → 9 µH between 1 A and
13 A, so the ripple at 12 A is 2.2 A rather than the 0.53 A a nominal-L sum
predicts. `reference/redexp_pull.py` recovers that curve, and the thermal rise
with it, from Würth's REDEXPERT DC-DC endpoint
(`/api/v2/simulations/dcdc-converters/losses/calculus/{pn}`).

**This is build-time only.** The page may never make a network request — a test
forbids `fetch`, XHR and external tags — so the pull is committed as
`reference/data/redexpert_bias.json`, turned into
`reference/external/bias_anchors.json`, and baked into `MAGPARTS.sat` by
`emit_magparts.py`. A test asserts the baked table back against the anchor file.
273 requests in total, every one cached, so re-running costs nothing.

Two data facts worth knowing:

- **The committed grids are reproducible from the live API.** Querying one known
  grid row returned `lossesac = 0.0263`, exactly what `WE_7443631500.m` records.
- **A naive scrape would bake in a lie.** Past a certain bias REDEXPERT stops
  modelling the core entirely: `deltail` reverts to the nominal-inductance value,
  `L_eff` snaps back to nominal, `warnOnBias` turns `true` or vanishes from the
  response, and a meaningless thermal rise (196 K at 25 A) is still reported. On
  `74437636351012` the curve runs down to 74.85 µH at 28.6 A and then reads
  **110.13 µH — exactly nominal — at 32.6 A**. So the stored curve keeps only the
  rows where `warnOnBias` was `false`, the rejected rows are kept separately as
  evidence, and a test asserts the curve is monotone (a saturating core never
  *gains* inductance), which is what catches the artefact.

The model built on it is a one-line fixed point: the ripple depends on the
inductance at the **peak** current and the peak depends on the ripple, so ~4
iterations solve it. The result is written into `op.L` (or `op.Ls` for a 3-phase
series choke), so `derive()`, `computeLosses()` and the capacitor nodes all
compute the saturated ripple without knowing saturation exists. Past the last
scraped bias point the inductance is reported as **unknown, not nominal**, with a
critical warning, because that is what it is.

Self-heating comes from the same pull: a rectangular 5 × 4 grid of (I, ΔI) at
100 kHz per part, bilinearly interpolated, and **refused rather than extrapolated**
outside it — a temperature rise is not something to guess from a trend. Every part
with a curve also raises an explicit note when the bias sits past it.

One bug this work exposed, worth recording because it was invisible: `stageSystem`
silently depended on the caller having already bound `op.L` from the selected
inductor. When it had not, `derive()` saw `L = null`, reported **zero ripple**, and
the fixed point had nothing to solve. That also means the earlier conclusion in
§9 that "the DC-DC total is monotonic, so there is no interior optimum" was drawn
at zero ripple and was doubly wrong. Both are now pinned by tests.

