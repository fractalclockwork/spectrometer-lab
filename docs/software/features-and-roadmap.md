# LS 55 Software Features and Roadmap

November 3, 2026 | FL WinLab–aligned operator workflows, web console, and extensible hardware architecture

With hardware bring-up and RS-232 verification complete ([../assessment/bringup-report.md](../assessment/bringup-report.md)), this guide defines software features that replace legacy **FL WinLab** while keeping the operator’s **instrument status awareness** and **measurement staging** first. Features follow WinLab’s application model, then extend beyond factory `$AF` accessories for custom optics and motion. For hardware specs and device constraints, see [../reference/instrument-specs.md](../reference/instrument-specs.md) and [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md).

---

## 1. Design Philosophy

An instrument console is a **cockpit for the operator at the bench**:

0. **Stay connected safely (Stage 0)** — truthful adapter/DUT link across power and USB cycles; never claim ready while busy/booting; Xe OFF after every connection loss; recover faults without a host restart.
1. **See device state** — commanded setpoints vs verified hardware readbacks; shutter (`$ES`); faults (`$PT 0107`, `$ME`, busy `0110`).
2. **Stage measurements safely** — optical setup → blank pairing → optional Single-Read scout (clip check) → dark/sample scan with live progress and `$AB` abort → guaranteed `$ES 1` idle.
3. **Inspect spectra interactively** — blank swap, wing-baseline continuum residual, dual SNR, without mutating raw counts.

Automation and scripts may use the same service API; the operator retains arming, gate sign-off, and abort authority.

Tags: **`[S]`** = software over RS-232 · **`[H]`** = needs accessory/extension · **`[R]`** = needs optical reference · **`[X]`** = out of scope unless custom hardware appears.

---

## 2. Staged Priorities

| Stage | Focus | Unlocks |
| --- | --- | --- |
| **0 — Robust bootup / connection** | USB by-id discovery; boot silence & busy `0110`; Probe vs Connect; Xe unverified until `$ES`; **kill Xe after any link loss**; heartbeat; fault recovery | Safe host ↔ DUT relationship before any measurement UI |
| **1 — Operator console + provenance** | Status/Setup synoptic, Single Read scout, Scan with live stream/`$AB`, Methods/sidecar, Viewing/Data Calculator (blank, wing residual, SNR), web dashboard | Every experiment’s raw workflow (**requires Stage 0**) |
| **2 — Quantitation, validation, kinetics** | Validation, Concentration, standard addition, TimeDrive, Wavelength Program | Expts **1**, **2**, **4** |
| **3 — Mixtures and advanced optics** | Sync scan, EEM, emission correction/Φ, Autopol, phosphorescence | Expts **3**, **5**; polarizers fitted |
| **4+ — Custom hardware & optical extensions** | 2-window transmission mirror, UV fiber, stirrer, autosampler, gantry, lasers, ns spark-gap | Beyond factory `$AF` |

**Stage 0 is first.** WinLab-shaped Status/Scan (Stage 1) assumes the link layer already survives power cycles, USB unplug/replug, busy-at-power-on, and lamp-safe recovery. Do not treat dashboard polish as a substitute for Stage 0.

---

## 3. How Hardware Architecture Shapes Software Design

Full bounds: [../reference/instrument-specs.md](../reference/instrument-specs.md); limits: [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §6.

- **Flash block-averaging vs. scan speed:** Xe fires at mains (`$HZ` = `60` on this DUT). Slower `$SS` averages more flashes per step.
- **12-bit ADC / overload:** Flag `999999` clip and `$PT` `0107`; prompt for narrower slits or lower `$PV`. Prefer a Single-Read scout before long scans.
- **Excitation shutter (`$ES`):** Open (`0`) only during acquire; close (`1`) with readback in `finally`. Idle resting state is OFF.
- **Fitted polarizers (`$AF`):** Excitation and emission polarizers present; temperature controller not fitted (`$TP` → `0100`).

---

## 4. Spectral Correction Architecture

- **Excitation correction (firmware):** Rhodamine table via `$CX 1` (default); `$CR` regenerates. Scans return `0111` if `$CX 1` without a valid table.
- **Emission correction (host, Stage 3):** Host curve from SRM glass / calibrated source / published reference spectrum; apply only when requested.
- **In-situ absorbance (Stage 4+, 2-window + fold mirror):** Synchronous $\Delta\lambda = 0$ yields $T = I/I_0$ and $A = -\log_{10}(I/I_0)$ for IFE inputs.

---

## 5. FL WinLab Application Map → Python Modules

Inventory from **FL WinLab Software User’s Guide** (part **0993-4316**, Release A, March 1999) chs. 3, 5–17 and the LS 55 brochure Applications menu.

| Guide | FL WinLab application | Purpose | `spectrometer-lab` approach | Stage | Tag |
| --- | --- | --- | --- | ---: | --- |
| ch.3 | **Status / Setup** | Live optical path, slits, filters | `ls55/control.py` setpoint vs readback; dashboard synoptic | 1 | `[S]` |
| ch.4 | **Methods** | GLP method load/save | Method JSON + run sidecar (`ls55/sidecar.py`) | 1 | `[S]` |
| ch.5–6 | **Viewing / Data Calculator** | Peaks, blank, baseline, report | `ls55/review.py` + Plotly ROI (blank swap, wing residual, dual SNR) | 1 | `[S]` |
| ch.7 | **Single Read** | Fixed-λ intensity / scout | `run_single_read` (`$RD`) with `$ES` safety | 1 | `[S]` |
| ch.8 | **Scan** | Ex / Em / sync / accumulation | `ls55/acquire.py`; live `on_record`; `$AB` | 1 (Ex/Em, $N$-avg); 3 (sync) | `[S]` |
| ch.9 | **TimeDrive** | Intensity vs time | `$TD` / timed `$RD` | 2 | `[S]` |
| ch.10 | **Wavelength Program** | Multi-λ sequence | `$GM` + `$RD` | 2 | `[S]` |
| ch.12 | **Concentration** | Quantitation / curve fit | Weighted fit, LOD/LOQ, IFE flags | 2 | `[S]` |
| — | **Standard addition** | Spike unknowns | Analysis on tonic matrix | 2 | `[S]` |
| ch.17 | **Validation** | SNR + wavelength accuracy | Water Raman method after Gate D | 2 | `[S]` |
| ch.8 / 3D | **Synchronous + EEM** | Constant $\Delta\lambda$/$\Delta\nu$; stacks | `$MX`/`$MQ`; Rayleigh/Raman mask | 3 | `[S]` |
| — | **Emission correction & relative Φ** | True shape / quantum yield | Host curve + slope vs quinine | 3 | `[R]` |
| Brochure | **Autopol** | Polarization / anisotropy | `$PX`/`$PM` (fitted) | 3 | `[S]`/`[H]` |
| Brochure | **Short phosphorescence decay** | ms gated decay | `$PH 1`, `$PD`/`$PG`/`$PF`, `$DP` | 3 | `[S]` |
| ch.13–16 / Brochure | **Plate / TLC / FFA / Ratio / Sipper** | Factory accessories | Replaced by Stage 4+ custom extensions (not grayed-out forever) | 4+ | `[H]` |

---

## 6. Analytical Best Practices to Encode

- **Blank subtraction / water Raman:** Matched solvent blank; O–H Raman near **397 nm** at Ex `350 nm`.
- **Replicates:** Technical vs reseat (`replicate_kind`); ≥3 independent preparations where claimed.
- **IFE:** Flag $A > 0.05$–$0.10$ in 10 mm path; $F_{\text{corr}} \approx F_{\text{obs}} \times 10^{(A_{\text{ex}}+A_{\text{em}})/2}$ when $A$ known.
- **Relative Φ / Stern–Volmer:** Stage 2–3 analysis on Scan / Single Read series.

---

## 7. Standard Data Record (JSON Sidecar Schema)

Every Stage 1+ acquisition emits paired `.json` + `.csv` + `.png`:

- **`provenance`:** UTC, operator, git commit, method/script name, model `55`, firmware `F1`, `$SN`.
- **`ls55_optics`:** `$PH`, `$GM`/`$AL`/`$AH`, `$SX`/`$SM`, `$SS`/`$SI`, `$FW`, `$PX`/`$PM`, `$PV`, `$CX`, `$PD`/`$PG`/`$PF`.
- **`optical_path_config`:** `right_angle_4w` | `transmission_2w_mirror` | `uv_fiber_probe` | `free_path`; holder/cuvette/fiber metadata.
- **`excitation_source_config`:** `internal_xe` | `external_laser` | `ns_spark_gap` (+ interlock/trigger notes).
- **`auxiliary_state`:** stirrer / autosampler / gantry when present.
- **`sample`:** ID, solvent, dilution, temperature.
- **`review_analysis`:** blank path, peak/noise/wing windows, peaks, absolute + contrast SNR, clip/`0107` flags, raw-log SHA-256.

---

## 8. Recommended Build Order

### Stage 0 — Robust bootup / connection (**PASS — 2026-11-03**)

**Prerequisite for Stage 1.** Checklist: [stage0-operator-signoff.md](stage0-operator-signoff.md). Offline tests are not sign-off.

1. **Adapter truth** — enumerate USB–RS232 via `/dev/serial/by-id` only; exclusive open; release on disconnect/loss.
2. **Boot / busy classify** — poll `$ST` through power-on silence; report busy `0110` without touching `$ES`; Probe = read-only classify; Connect = safe-idle when ready.
3. **Xe lamp policy** — badge unverified until confirmed `$ES`; resting OFF on Connect; **`kill_xe` / `$ES 1` after any connection loss** (pending until verified).
4. **Link loss & fault recovery** — heartbeat → drop dead fd; Abort/Refresh recover FAULT with `$AB` + Xe OFF; ephemeral Abort when disconnected.
5. **Operator cues** — link badge (unplugged / silent / busy / booting / ready / Xe kill pending); CLIs `kill_xe.py`, `discover_device.py`.

Library layout: `ls55/discover.py`, `ls55/source.py`, `ls55/transactions.py`, `ls55/transport.py`, `ls55/service.py` (link + Xe policy), `scripts/kill_xe.py`, `scripts/discover_device.py`.

### Stage 1 — Operator console + provenance (**OPEN — awaiting operator sign-off**)

Implementation may be present in-tree, but **Stage 1 features are not complete until signed off**, and **Stage 0 must be PASS (or waived) first**. Checklist: [stage1-operator-signoff.md](stage1-operator-signoff.md). Offline tests are not sign-off.

1. **Status / Setup** — snapshot + apply optical state; setpoint vs readback.
2. **Single Read** — `$RD` scout with dynamic-range / clip gauge.
3. **Scan** — generalize freepath; live streaming; `$AB`; `$ES` in `finally`.
4. **Methods + sidecar** — §7 schema on every run.
5. **Viewing / Data Calculator** — blank swap, wing continuum residual, dual SNR.
6. **Web dashboard** — FastAPI + WebSocket + Plotly; WinLab-aligned tabs **Setup / Acquire / Results** (Connect→Optics→Blank under Setup; Scout/Scan under Acquire; run browser + Data Calculator under Results). Connect **defers** to Stage 0 link behavior. Fixed health strip + setpoint/readback synoptic on every tab.

Library layout: `ls55/control.py`, `ls55/acquire.py`, `ls55/review.py`, `ls55/sidecar.py`, `ls55/service.py`, `ls55/web/`.

### Stage 2 — Quantitation, validation, kinetics

1. Validation / water Raman health tracker (after Gate D).
2. Concentration / calibration + IFE warnings → Expt 1.
3. Standard addition; Stern–Volmer → Expt 2.
4. TimeDrive; Wavelength Program; Data Calculator exports.

### Stage 3 — Mixtures and advanced optics

1. Synchronous Scan; EEM + scatter mask → Expts 3/5.
2. Host emission correction + relative Φ `[R]`.
3. Autopol (`$PX`/`$PM`); phosphorescence when needed.

### Stage 4+ — Custom hardware & optical extensions

Treat the LS 55 as the **spectrometer core** (monochromators + PMT + compartment bench) coordinated with open-hardware plugins (`ExtensionRegistry` on `LS55Service`):

| Extension | Role | Integration notes |
| --- | --- | --- |
| **2-window + fold mirror** | In-compartment $T(\lambda)$, $A(\lambda)$ | $\Delta\lambda=0$ sync / stepped equal λ; `$FW` `1% T` if needed; IFE inputs |
| **UV fiber probe** | Remote launch/collect | Square-bore block ports; see [../assessment/ls55-uv-fiber-assessment.md](../assessment/ls55-uv-fiber-assessment.md) |
| **Stirrer** | Mix / settle before acquire | `pre_acquire` hooks (`stir_rpm`, `mix_s`, `settle_s`) |
| **Autosampler / sipper** | Vial or flow indexing | USB/serial or rear 15-pin / remote-start |
| **XY/XYZ gantry** | Plate / TLC / spatial maps | Replaces WinLab Ch. 13–14; G-code/GRBL |
| **CW / modulated laser** | External excitation | `$PH 2` + `$ES 1` + door interlock |
| **ns spark-gap + digitizer** | Lifetime $I(t)$ | LS 55 selects λ; external HV + scope/TDC |

Factory WinLab accessories that are unfitted on this DUT are **not** permanently `[X]`—they map onto these custom paths when built.

---

## 9. Operator Measurement Staging (Stage 1 UI)

Console chrome is always visible (Stage 0 health, Xe OFF / Abort / Probe, optical synoptic). Work happens in three tabs (FL WinLab Status/Setup · Scan · Viewing):

| Tab | Staging content |
| --- | --- |
| **Setup** | Connect & safe-idle (Stage 0); method/optics; sample meta; acquire matched blank |
| **Acquire** | Scout `$RD` + gauge; staged scan; live Plotly stream |
| **Results** | Run browser + blank swap; Data Calculator ROI/SNR/residual |

Five-step flow maps onto those tabs (not one scrolling column):

1. **Connect & safe-idle (Stage 0)** — adapter/DUT classify; busy/boot honesty; discover; `$ME`; force `$ES 1`; kill Xe after link loss. *(Setup)*
2. **Stage method & optics** — preset or custom; apply `$GM`/`$SX`/`$SM`/`$FW` with shutter OFF; preview duration. *(Setup)*
3. **Stage blank** — pick matched Blank CSV (Results) or acquire blank now (Setup); settings match badge.
4. **Scout & readiness** — door/sample gates; optional `$RD` at guide λ with `0`–`999999` gauge. *(Acquire)*
5. **Execute** — dark → sample stream → restore `$ES 1`; step `sanity` / `technical` / `reseat`; auto-open Results. *(Acquire → Results)*

---

## Sources

1. PerkinElmer LS 55 User's Guide, part 09934436, release C, March 2007 — [../vendor/README.md](../vendor/README.md).
2. **FL WinLab Software User’s Guide**, Perkin-Elmer part **0993-4316**, Release A, March 1999.
3. PerkinElmer LS 45 / LS 55 brochure — https://www.laboratory-equipment.com/media/asset-library/l/s/ls-55ls_45_fluorescence_spectrometer_perkinelmer.pdf
4. Iowa State CIF *LS 55 Training Manual* — https://www.cif.iastate.edu/files/inline-files/LS%2055%20Training%20Manual.pdf
5. UW Chemistry *Perkin Elmer LS-55* — https://chem.washington.edu/instruments/perkin-elmer-ls-55
6. Home-lab experiments — [../experiments/fluorescence-home-lab.md](../experiments/fluorescence-home-lab.md).
