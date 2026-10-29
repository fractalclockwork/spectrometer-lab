# LS 55 Software Features and Roadmap

October 28, 2026 | Post–bring-up software architecture and staged feature build order

With hardware bring-up and RS-232 verification complete ([../assessment/bringup-report.md](../assessment/bringup-report.md)), this guide defines the software features worth building in Python to replace legacy **FL WinLab** workflows. Features are **staged by usefulness** for this bench LS 55 and the five home-lab experiments in [../experiments/fluorescence-home-lab.md](../experiments/fluorescence-home-lab.md)—not by WinLab chapter order. For hardware specifications and known device constraints, see [../reference/instrument-specs.md](../reference/instrument-specs.md) and [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md).

---

## 1. Staged Priorities (most useful first)

Build **Software Stage 1** before analysis modules. Later stages assume Gate D holder readiness where liquid samples are required.

| Stage | Focus | Unlocks |
| --- | --- | --- |
| **1 — Core acquire + provenance** | Scan, blank/$N$-average, JSON sidecar, Status snapshot, Single Read | Every experiment’s raw workflow |
| **2 — Quantitation, validation, kinetics** | Validation, Concentration, standard addition, TimeDrive, Wavelength Program, Data Calculator | Expts **1**, **2**, **4** |
| **3 — Mixtures and advanced optics** | Sync scan, EEM, emission correction/Φ, Autopol, phosphorescence | Expts **3**, **5**; publishable shapes; polarizers fitted |
| **4 — Deferred accessories** | Plate/TLC/FFA/sipper/ICBC/Ratio/enzyme/WPR | Not on this DUT (`$AF`); mark `[X]`/`[H]` |

Tags used below: **`[S]`** = pure software over RS-232 · **`[H]`** = needs accessory · **`[R]`** = needs optical reference · **`[X]`** = out of scope on this bench unit.

---

## 2. How Hardware Architecture Shapes Software Design

Full parameter bounds are tabulated in [../reference/instrument-specs.md](../reference/instrument-specs.md); measurement constraints are summarized in [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §6. Key implications for software:

- **Flash block-averaging vs. scan speed:** The pulsed xenon source fires at mains frequency (`60 Hz` on this bench unit per `$HZ`). Slower scan speeds (`$SS 10–1500 nm/min`) average more flashes per wavelength step (e.g., ~50 flashes/point at 30 nm/min vs. 1 flash/point at 1500 nm/min), trading acquisition time directly for signal-to-noise ratio.
- **12-bit auto-ranging ADC and overload handling:** Dark current is subtracted digitally each cycle, and the output in fluorescence mode (`$PH 0`) is the sample-to-reference ratio. When a peak saturates (`999999` in ASCII scan data or `$PT` returning `0107`), the software must flag the scan as clipped and prompt for narrower slits (`$SX`, `$SM`) or lower PMT voltage (`$PV`).
- **Excitation shutter management (`$ES`):** To minimize photobleaching (especially in riboflavin and biological samples) and xenon lamp wear, acquisition wrappers should open the shutter (`$ES 0`) immediately before a scan and close it (`$ES 1` with readback verification) in a `finally` block.
- **Fitted polarizers (`$AF`):** Because excitation and emission polarizer wheels are installed on this bench unit, Stage 3 can automate fluorescence anisotropy / polarization via `$PX` and `$PM`. Temperature sensor is **not** fitted (`$TP` → `0100`); log an external probe in the sidecar when needed.

---

## 3. Spectral Correction Architecture

Per the User's Guide (*Optical System* and *Ratioing and Correction*, pp. 166–171; see [../vendor/README.md](../vendor/README.md)):

- **Excitation correction (in firmware):** The reference photodiode response is multiplied by a stored rhodamine quantum-counter curve (`230–630 nm`). `$CX 1` (power-on default) enables this correction; `$CR` regenerates the table when a rhodamine standard is installed. Scans return `0111` if `$CX 1` is active without a valid table.
- **Emission correction (host software feature, Stage 3):** Grating efficiency and PMT sensitivity (modified S5 roll-off near 650 nm, or R928 to 900 nm) vary strongly with wavelength. FL WinLab does not replace a host emission curve. To build one:
  - Measure a NIST SRM 2940-series fluorescence glass standard, a calibrated tungsten-halogen source with a diffuse reflector, or a reference fluorophore with a published corrected spectrum.
  - Store the correction vector indexed by wavelength, slit width, and PMT voltage, and apply it in post-processing only when explicitly requested.

---

## 4. FL WinLab Application Map → Python Modules

Application inventory follows the **FL WinLab Software User’s Guide** (part **0993-4316**, Release A, March 1999 — WinLab 3.0 / LS-50B-family software book) chapters 3 and 5–17, cross-checked against the LS 55 brochure Applications menu and plug-ins ([1–2]). The LS 55–bundled WinLab PDF is not in this repo; the same application surface applies, with accessory modules gated by hardware.

| Guide | FL WinLab application | Purpose | `spectrometer-lab` approach | Stage | Tag |
| --- | --- | --- | --- | ---: | --- |
| ch.3 | **Status / Setup** | Live optical path, slits, filters, accessories | Status snapshot into sidecar (`$ST`, `$AF`, `$PV`, `$CX`, `$FW`); reuse identity parsers | 1 | `[S]` |
| ch.4–6 | **Methods / Viewing / Data Handling** | GLP methods, peak labels, calculator, smooth, report, 3D view | JSON sidecar + CSV/PNG (§6); Stage 2 Data Calculator subset | 1–2 | `[S]` |
| ch.7 | **Single Read** | Fixed-λ intensity (polarization / anisotropy options) | `$RD` wrapper at fixed `$GM` | 1 | `[S]` |
| ch.8 | **Scan** | Ex / Em / sync / accumulation; fluor / phos / bio | Generalize [`ls55/freepath.py`](../../ls55/freepath.py) / [`ls55/scan.py`](../../ls55/scan.py); `$ES` in `finally` | 1 (Ex/Em, $N$-avg); 3 (sync) | `[S]` |
| ch.9 | **TimeDrive** | Intensity vs time at fixed λ | `$TD` / `$RT` or timed `$RD`; shutter-aware | 2 | `[S]` |
| ch.10 | **Wavelength Program** | Multi-λ (and multi-cell) program | `$GM` + `$RD` sequence (single cell on this DUT) | 2 | `[S]` |
| ch.12 | **Concentration** | Quantitation / curve fit | Weighted linear fit, residuals, LOD/LOQ; IFE flags | 2 | `[S]` |
| — | **Standard addition** | Spike unknowns (Concentration-adjacent; not a separate 1999 chapter) | Analysis script for tonic matrix | 2 | `[S]` |
| ch.17 | **Validation** | SNR + wavelength accuracy report | Water Raman script (Ex `350 nm`, Em `380–420 nm`, `10 nm` slits) after Gate D | 2 | `[S]` |
| ch.8 / 3D | **Synchronous + EEM** | Constant $\Delta\lambda$/$\Delta\nu$; stacked Em scans | `$MX`/`$MQ`; Em loop + Rayleigh/Raman mask | 3 | `[S]` |
| — | **Emission correction & relative Φ** | True spectral shape / quantum yield | Host curve + slope method vs quinine sulfate | 3 | `[R]` |
| Brochure | **Autopol** | Intensity / polarization / anisotropy vs temperature | `$PX`/`$PM` (wheels fitted); external temp in metadata | 3 | `[S]`/`[H]` |
| Brochure / Scan | **Short phosphorescence decay** | ms gated decay | `$PH 1`, `$PD`/`$PG`/`$PF`, `$DP` when needed | 3 | `[S]` |
| ch.11 | **ICBC Calibration** | Intracellular ion post-process | Deferred — needs Ratio/FFA/biokinetics workflow | 4 | `[X]` |
| ch.13 | **TLC Scan** | Flat-sample 2D/3D via plate reader | Not fitted | 4 | `[X]` |
| ch.14 | **Plate Reader** | Microplate end-point / kinetics | Not fitted (`$AF`) | 4 | `[X]` |
| ch.15 | **Fast Filter** | Rapid multi-channel via FFA | Not fitted | 4 | `[X]` |
| ch.16 | **Ratio Data** | Intracellular True/Quick Ratio | Not fitted; optional later: software two-λ ratio from two TimeDrives (not WinLab Ratio) | 4 | `[X]` |
| Brochure | **Enzyme activity / WPR Scan** | Niche plug-ins | Skip unless accessory + use case appear | 4 | `[X]` |
| Brochure | **Sipper / autosampler paths** | Concentration automation | Not fitted | 4 | `[X]` |

---

## 5. Analytical Best Practices to Encode in Software

Encode these in Stage 1–2 pipelines (see also experiment protocols):

- **Blank subtraction and water Raman awareness:** Subtract a matched-cuvette solvent blank acquired with identical slits, speed, and PMT voltage. In aqueous samples excited at `350 nm`, the water O–H stretch Raman band ($\sim 3400\text{ cm}^{-1}$ shift) appears near **397 nm**—blank subtraction removes it and prevents misidentifying Raman scatter as sample emission.
- **Independent replicates:** Distinguish between technical scan repeats on one fill and $\ge 3$ independent sample preparations.
- **Inner-filter effect (IFE) flagging:** When sample absorbance exceeds $0.05\text{–}0.10$ in a $10\text{ mm}$ cell, primary attenuation of the excitation beam and secondary reabsorption of emission distort linearity. Where $A_{\text{ex}}$ and $A_{\text{em}}$ are known (and moderate), apply the standard geometry approximation:
  \[
  F_{\text{corr}} \approx F_{\text{obs}} \times 10^{(A_{\text{ex}} + A_{\text{em}}) / 2}
  \]
- **Relative quantum yield ($\Phi_x$):** Compare integrated, emission-corrected spectra across a dilution series ($A < 0.1$) against a reference standard such as quinine sulfate in $0.1\text{ M }\text{HClO}_4$ ($\Phi_{\text{ref}} \approx 0.60$) or $0.1\text{ M }\text{H}_2\text{SO}_4$ ($\Phi_{\text{ref}} \approx 0.54\text{–}0.55$):
  \[
  \Phi_x = \Phi_{\text{ref}} \left(\frac{\text{slope}_x}{\text{slope}_{\text{ref}}}\right) \left(\frac{n_x^2}{n_{\text{ref}}^2}\right)
  \]
- **Stern–Volmer quenching:** Fit $F_0 / F = 1 + K_{\text{SV}}[Q]$ (or the combined static/dynamic form $(1 + K_D[Q])(1 + K_S[Q])$ when upward curvature occurs), correcting for dilution and IFE — Stage 2 analysis on top of Scan / Single Read (Expt 2).

---

## 6. Standard Data Record (JSON Sidecar Schema)

Every Stage 1+ acquisition script should emit a paired `.json` metadata file alongside `.csv` and `.png` outputs containing:

- **Provenance:** UTC timestamp, operator, git commit hash, script name, instrument model (`55`), firmware (`F1`), serial (from `$SN`).
- **Optical & electronic settings:** Mode (`$PH`), excitation/emission wavelengths (`$GM` / `$AL` / `$AH`), slits (`$SX`, `$SM`), scan speed (`$SS`), step interval (`$SI`), filter wheel (`$FW`), polarizer positions (`$PX`, `$PM`), PMT voltage (`$PV`), excitation correction (`$CX`), phosphorescence delay/gate/flashes (`$PD`, `$PG`, `$PF`).
- **Sample & cell metadata:** Sample ID, solvent, concentration/dilution factor, cuvette material and path length, holder ID, ambient or external probe temperature, optional $A_{\text{ex}}$ and $A_{\text{em}}$.
- **Processing & integrity:** Reference to blank file, applied corrections (blank subtraction, IFE, emission curve), SHA-256 hash of raw log, and any warning/status codes (`0107` overload, Class B repairs — see [../issues/serial-link-glitch-taxonomy.md](../issues/serial-link-glitch-taxonomy.md)).

---

## 7. Recommended Build Order (Software Stages 1–4)

### Stage 1 — Core acquire + provenance

Unlocks blank/replicate workflow for **all** [home-lab experiments](../experiments/fluorescence-home-lab.md).

1. **General Scan CLI** (WinLab Scan ch.8) — configurable Ex and Em scans; generalize beyond freepath; `$ES 0` before acquire, `$ES 1` in `finally`.
2. **JSON sidecar + CSV/PNG** (methods / viewing ch.4–6) — §6 schema on every run.
3. **Blank subtraction + $N$-accumulation** (Scan accumulation + Data Handling) — store raw, blank, blank-subtracted; per-λ mean and SD.
4. **Status snapshot helper** (Status ch.3) — `$ST` / `$AF` / `$PV` / `$CX` / `$FW` into sidecar.
5. **Single Read** (ch.7) — `$RD` at fixed Ex/Em for quick peak checks.

### Stage 2 — Quantitation, validation, kinetics

1. **Validation / water Raman** (ch.17) — SNR + peak-position tracker after Gate D holder (routine health; supports Expt 1 blank awareness).
2. **Concentration / calibration** (ch.12) — weighted fit, residual plot, LOD/LOQ, IFE warnings → **Expt 1**.
3. **Standard-addition analysis** — Concentration-adjacent script for tonic matrix → **Expt 1/2**.
4. **Stern–Volmer module** — $F_0/F$ regression with dilution/IFE correction → **Expt 2**.
5. **TimeDrive** (ch.9) — `$TD` / timed `$RD`, shutter-aware photobleaching → **Expt 4**.
6. **Wavelength Program** (ch.10) — discrete λ list via `$GM`+`$RD` without full scans.
7. **Data Calculator basics** (ch.6) — smooth, peak pick, export for lab plots.

### Stage 3 — Mixtures and advanced optics

1. **Synchronous Scan** (Scan sync) — `$MX` / `$MQ`; mixture band narrowing → **Expt 5**.
2. **EEM builder + scatter mask** (3D / multi-scan) — stepped Ex, Em stacks; Rayleigh/Raman masks → **Expt 3/5** unmixing input.
3. **Host emission correction + relative Φ** `[R]` — once a reference standard or calibrated source is available.
4. **Autopol / anisotropy** — `$PX` / `$PM` on fitted wheels; after Expts 1–5 unless binding work jumps the queue.
5. **Phosphorescence / short decay** — `$PH 1` / `$DP` when a phosphorescent sample appears.

### Stage 4 — Deferred / not on this DUT

Do **not** schedule implementation until hardware appears:

- Plate Reader, TLC Scan, Fast Filter, Sipper/autosampler Concentration paths, ICBC, Ratio Data (True/Quick), Enzyme-activity plug-in, WPR Scan — `[X]` / unfitted `[H]`.
- Optional substitute (document only): software two-λ ratio from two TimeDrives — **not** the WinLab Ratio application.

---

## Sources

1. PerkinElmer LS 55 User's Guide, part 09934436, release C, March 2007 — obtain locally per [../vendor/README.md](../vendor/README.md).
2. **FL WinLab Software User’s Guide**, Perkin-Elmer part **0993-4316**, Release A, March 1999 (WinLab 3.0 online-help book / LS-50B-family). Used here as the application inventory (chs. 3, 5–17) when the LS 55–bundled WinLab PDF is not in-repo. Mirror commonly indexed as the “FL WinLab software User’s Guide” on documentation aggregators.
3. PerkinElmer LS 45 / LS 55 Fluorescence Spectrometers brochure (Applications menu, Autopol, short phosphorescence decay, enzyme, WPR Scan, 3D) — https://www.laboratory-equipment.com/media/asset-library/l/s/ls-55ls_45_fluorescence_spectrometer_perkinelmer.pdf
4. Iowa State University Chemical Instrumentation Facility, *LS 55 Training Manual* — https://www.cif.iastate.edu/files/inline-files/LS%2055%20Training%20Manual.pdf
5. University of Washington Chemistry, *Perkin Elmer LS-55* overview — https://chem.washington.edu/instruments/perkin-elmer-ls-55
6. Home-lab experiment sequence — [../experiments/fluorescence-home-lab.md](../experiments/fluorescence-home-lab.md).
