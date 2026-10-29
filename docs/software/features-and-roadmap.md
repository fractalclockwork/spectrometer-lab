# LS 55 Software Features and Roadmap

October 28, 2026 | Post–bring-up software architecture and feature build order

With hardware bring-up and RS-232 verification complete ([../assessment/bringup-report.md](../assessment/bringup-report.md)), this guide defines the software features worth building in Python to replace legacy **FL WinLab** workflows. For hardware specifications and known device constraints, see [../reference/instrument-specs.md](../reference/instrument-specs.md) and [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md).

---

## 1. Priority Recommendations

1. **Blank subtraction and N-scan replicate averaging as first-class pipeline steps.** Store raw, blank, and blank-subtracted spectra together in every run artifact.
2. **Inner-filter effect (IFE) tracking.** Record sample absorbance at excitation and emission wavelengths whenever available. Keep $A(\lambda_{\text{ex}}) < 0.1$ in a 10 mm cell, or apply standard IFE correction to prevent artificial curvature in dilution and quenching series.
3. **Host-side emission spectral correction.** The LS 55 applies internal excitation correction (`$CX 1` via its reference photodiode and rhodamine table), but **emission spectra are uncorrected** for grating and PMT wavelength response. Relative intensities of a single fluorophore need no emission curve, but band-shape comparisons and relative quantum yields across different emission windows require a host emission correction factor.
4. **Structured JSON sidecar metadata on every acquisition.** Record wavelengths, slits, PMT voltage (`$PV`), scan speed, step interval, `$CX` state, filter position (`$FW`), cell geometry, sample metadata, firmware (`F1`), serial (`79787`), and git commit hash.
5. **Quantitative analysis modules.** Implement linear/weighted calibration fits (with LOD/LOQ), Stern–Volmer quenching fits, and standard-addition scripts on top of standard scan and single-point (`$RD`) acquisitions.
6. **Synchronous scanning (`$MX` / `$MQ`) and 3D excitation–emission matrices (EEM).** Native synchronous scanning narrows overlapping bands in multi-component mixtures; stepped emission scans build EEM datasets.

---

## 2. How Hardware Architecture Shapes Software Design

Full parameter bounds are tabulated in [../reference/instrument-specs.md](../reference/instrument-specs.md); measurement constraints are summarized in [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §6. Key implications for software:

- **Flash block-averaging vs. scan speed:** The pulsed xenon source fires at mains frequency (`60 Hz` on unit `79787`). Slower scan speeds (`$SS 10–1500 nm/min`) average more flashes per wavelength step (e.g., ~50 flashes/point at 30 nm/min vs. 1 flash/point at 1500 nm/min), trading acquisition time directly for signal-to-noise ratio.
- **12-bit auto-ranging ADC and overload handling:** Dark current is subtracted digitally each cycle, and the output in fluorescence mode (`$PH 0`) is the sample-to-reference ratio. When a peak saturates (`999999` in ASCII scan data or `$PT` returning `0107`), the software must flag the scan as clipped and prompt for narrower slits (`$SX`, `$SM`) or lower PMT voltage (`$PV`).
- **Excitation shutter management (`$ES`):** To minimize photobleaching (especially in riboflavin and biological samples) and xenon lamp wear, acquisition wrappers should open the shutter (`$ES 0`) immediately before a scan and close it (`$ES 1` with readback verification) in a `finally` block.
- **Fitted polarizers (`$AF`):** Because excitation and emission polarizer wheels are installed on unit `79787`, future scripts can automate fluorescence anisotropy / polarization measurements via `$PX` and `$PM`.

---

## 3. Spectral Correction Architecture

Per the User's Guide (*Optical System* and *Ratioing and Correction*, pp. 166–171; see [../vendor/README.md](../vendor/README.md)):

- **Excitation correction (in firmware):** The reference photodiode response is multiplied by a stored rhodamine quantum-counter curve (`230–630 nm`). `$CX 1` (power-on default) enables this correction; `$CR` regenerates the table when a rhodamine standard is installed. Scans return `0111` if `$CX 1` is active without a valid table.
- **Emission correction (host software feature):** Grating efficiency and PMT sensitivity (modified S5 roll-off near 650 nm, or R928 to 900 nm) vary strongly with wavelength. To build a host-side emission correction curve:
  - Measure a NIST SRM 2940-series fluorescence glass standard, a calibrated tungsten-halogen source with a diffuse reflector, or a reference fluorophore with a published corrected spectrum.
  - Store the correction vector indexed by wavelength, slit width, and PMT voltage, and apply it in post-processing only when explicitly requested.

---

## 4. Mapping FL WinLab Features to Python Modules

FL WinLab capabilities below are compiled from PerkinElmer LS 55 literature and training manuals ([1–4]).

Tags: **`[S]`** = pure software over RS-232 / **`[H]`** = requires hardware accessory / **`[R]`** = requires optical reference standard / **`[X]`** = out of scope.

| FL WinLab Feature | Purpose | Implementation Approach in `spectrometer-lab` | Tag |
| --- | --- | --- | --- |
| **Excitation / Emission Scan** | Scan one monochromator with the other fixed | Implemented for emission in [`ls55/freepath.py`](../../ls55/freepath.py) and [`ls55/scan.py`](../../ls55/scan.py); generalize to arbitrary Ex/Em scans | `[S]` |
| **Accumulation Scan** | Repeat $N$ scans and average | Loop $N$ scans in Python; store per-wavelength mean and standard deviation | `[S]` |
| **Synchronous Scan** | Scan Ex and Em simultaneously at constant $\Delta\lambda$ or $\Delta\nu$ | Drive native `$MX` / `$MQ` commands; useful for resolving mixtures (e.g., quinine + riboflavin with $\Delta\lambda \approx 20\text{–}80\text{ nm}$) | `[S]` |
| **3D / EEM Scan** | Stack of emission scans across stepped excitation wavelengths | Step `$GM` excitation wavelength in a Python loop, mask 1st/2nd-order Rayleigh and Raman scatter bands, export matrix | `[S]` |
| **Time Drive (Kinetics)** | Intensity vs. time at fixed Ex/Em | Implement `$TD` / `$RT` wrapper (or timed `$RD` loop) for photobleaching and quenching kinetics | `[S]` |
| **Concentration / Calibration** | Linear or nonlinear fit of standards + unknowns | Python analysis script: weighted linear regression, residual plot, $\text{LOD} = 3.3\sigma/m$, $\text{LOQ} = 10\sigma/m$ | `[S]` |
| **Standard Addition** | Spike unknown matrix with known standard increments | Python analysis script; ideal for tonic-water quinine in a complex matrix | `[S]` |
| **Wavelength Program** | Read intensity at discrete $(\lambda_{\text{ex}}, \lambda_{\text{em}})$ pairs | Python sequence over `$GM` + `$RD` | `[S]` |
| **Autopol / Anisotropy** | Polarization / anisotropy via `$PX` and `$PM` | Supported by hardware on unit `79787` (polarizers fitted per `$AF`) | `[S]`/`[H]` |
| **Phosphorescence Delay / Gate & Decay** | Millisecond gated integration (`$PH 1`, `$PD`, `$PG`, `$DP`) | Supported in firmware (`13 ms` min cycle); build wrapper when phosphorescent samples are tested | `[S]` |
| **Water Raman Validation** | Routine SNR (`500:1` RMS) and wavelength drift check | Automated script (Ex `350 nm`, Em `380–420 nm`, `10 nm` slits) once Gate D holder is ready | `[S]` |
| **GLP Result Files & Audit Trail** | Provenance and settings archive | JSON sidecar + CSV + PNG plot per measurement (see §5) | `[S]` |
| **Emission Correction & Quantum Yield** | True spectral shape and relative $\Phi_F$ | Host-side correction vector + relative $\Phi_F$ slope method against quinine sulfate (`[R]`) | `[R]` |
| **Temperature Logging (`$TP`)** | Cell temperature readout | Unit `79787` has no temperature controller (`$TP` → `0100`); log external probe temperature manually in metadata | `[H]` |
| **Fast Kinetics (FKA), Plate Reader, Sipper** | Specialized accessory modes | Accessories not fitted on unit `79787` per `$AF` | `[X]` |

---

## 5. Analytical Best Practices to Encode in Software

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
- **Stern–Volmer quenching:** Fit $F_0 / F = 1 + K_{\text{SV}}[Q]$ (or the combined static/dynamic form $(1 + K_D[Q])(1 + K_S[Q])$ when upward curvature occurs), correcting for dilution and IFE.

---

## 6. Standard Data Record (JSON Sidecar Schema)

Every acquisition script should emit a paired `.json` metadata file alongside `.csv` and `.png` outputs containing:

- **Provenance:** UTC timestamp, operator, git commit hash, script name, instrument model (`55`), firmware (`F1`), serial (`79787`).
- **Optical & electronic settings:** Mode (`$PH`), excitation/emission wavelengths (`$GM` / `$AL` / `$AH`), slits (`$SX`, `$SM`), scan speed (`$SS`), step interval (`$SI`), filter wheel (`$FW`), polarizer positions (`$PX`, `$PM`), PMT voltage (`$PV`), excitation correction (`$CX`), phosphorescence delay/gate/flashes (`$PD`, `$PG`, `$PF`).
- **Sample & cell metadata:** Sample ID, solvent, concentration/dilution factor, cuvette material and path length, holder ID, ambient or external probe temperature, optional $A_{\text{ex}}$ and $A_{\text{em}}$.
- **Processing & integrity:** Reference to blank file, applied corrections (blank subtraction, IFE, emission curve), SHA-256 hash of raw log, and any warning/status codes (`0107` overload, Class B repairs).

---

## 7. Recommended Build Order

1. **General scan CLI and library module** — configurable Ex/Em/Synchronous scan with JSON sidecar, blank subtraction, and $N$-replicate averaging.
2. **Water Raman performance check script** — automated SNR and peak-position tracker (once Gate D sample holder is ready).
3. **Dilution series & calibration module** — linear range finder, residual plot, LOD/LOQ, and IFE warning flags (supports Experiment 1 in [../experiments/fluorescence-home-lab.md](../experiments/fluorescence-home-lab.md)).
4. **Stern–Volmer quenching module** — $F_0/F$ regression with dilution correction (supports Experiment 2).
5. **Time-drive (`$TD` / timed `$RD`) module** — photostability and bleaching tracker (supports Experiment 4).
6. **Synchronous scan & EEM builder** — 2D/3D mixture acquisition and scatter-masking tools (supports Experiment 5).
7. **Host emission correction & relative quantum yield** — once a reference standard or calibrated source is acquired.

## Sources

1. PerkinElmer LS 55 User's Guide, release C, March 2007 — obtain locally per [../vendor/README.md](../vendor/README.md).
2. PerkinElmer LS 45 / LS 55 Fluorescence Spectrometers brochure — https://www.laboratory-equipment.com/media/asset-library/l/s/ls-55ls_45_fluorescence_spectrometer_perkinelmer.pdf
3. Iowa State University Chemical Instrumentation Facility, *LS 55 Training Manual* — https://www.cif.iastate.edu/files/inline-files/LS%2055%20Training%20Manual.pdf
4. University of Washington Chemistry, *Perkin Elmer LS-55* overview — https://chem.washington.edu/instruments/perkin-elmer-ls-55
