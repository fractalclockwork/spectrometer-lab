# Baseline Fluorescence Experiments (Home Lab)

October 28, 2026 | Five aqueous fluorescence experiments using common reagents

> **Prerequisite — Gate D Sample Holder:** Although instrument bring-up (Stages 1–3) is complete, these experiments require a mechanically secured sample holder and a 4-window UV-transmitting fluorescence cuvette (**Gate D**). See [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §5 before introducing liquid samples into the compartment.

---

## 1. Experiment Sequence Overview

These five experiments use aqueous solutions of grocery-grade quinine (tonic water), sodium chloride, and vitamin B2 (riboflavin) to exercise emission scanning, dilution linearity, collisional quenching, photodegradation kinetics, and two-component spectral unmixing within the LS 55's standard `200–650 nm` PMT window.

| Order | Experiment | Primary Question | Software Features Exercised |
| --- | --- | --- | --- |
| **1** | Tonic-water emission spectrum & dilution series | Where does fluorescence intensity deviate from linear concentration scaling? | Blank subtraction, replicate averaging, dilution fit, inner-filter effect (IFE) onset |
| **2** | Halide (NaCl) quenching of quinine | How does a collisional quencher reduce intensity at fixed fluorophore concentration? | Stern–Volmer regression ($I_0/I$ vs. $[\text{NaCl}]$), uncertainty estimation |
| **3** | Vitamin B2 (riboflavin) spectral fingerprint | How do excitation and emission maxima separate two fluorophores? | Multi-wavelength excitation/emission scanning, normalized spectral overlay |
| **4** | Riboflavin photostability (light vs. dark control) | How rapidly does visible/UV exposure degrade aqueous riboflavin? | Time-series tracking at fixed $\lambda_{\text{em}}$, shutter management (`$ES`), drift control |
| **5** | Quinine + riboflavin binary mixtures | When does a two-component spectrum equal the linear sum of its parts? | Linear least-squares unmixing, synchronous scanning, energy-transfer/IFE residuals |

---

## 2. Prerequisites, Cuvettes, and Safety

- **Instrument and electrical safety:** Operate only with all covers in place and the sample compartment door fully closed during acquisitions (`$ES 0`). Close the excitation shutter (`$ES 1` and verify readback) before opening the compartment to load or remove cuvettes. Keep liquids in a secondary tray away from the instrument vents and rear power/serial connections.
- **Cuvette requirements:** Standard LS 55 geometry uses a **12.5 mm square exterior, 10 mm optical path** cuvette with **four clear polished windows**. For `350 nm` excitation, use fused quartz or a UV-rated methacrylate/cyclic-olefin polymer cuvette verified to transmit at `350 nm` (standard polystyrene and soda-lime glass absorb strongly below `380 nm`).
- **Fill volume and beam clearance:** In the standard `L2250140` holder, the optical beam is ~9 mm high centered `13.5 mm` above the cuvette base, requiring at least **~2.0 mL** of solution in a standard 10 mm cell so the meniscus sits well above the beam. Wipe exterior optical faces clean and ensure no air bubbles adhere to the walls.
- **Dedicated labware:** Use clean, dedicated volumetricware and containers; never return prepared solutions to food containers.

---

## 3. Standard Acquisition Protocol

Apply a consistent protocol across all five experiments (see [../software/features-and-roadmap.md](../software/features-and-roadmap.md) for planned automation):

1. **Solvent blank first and last:** Measure a matched water (or buffer/salt) blank in the same cuvette and orientation before and after each sample series. Subtract the blank spectrum point-by-point.
2. **Prevent detector saturation:** Start with dilute solutions. If any point approaches the ASCII clip ceiling (`999999`) or sets the `$PT` `0107` overload latch, narrow the excitation/emission slits (`$SX`, `$SM`) or dilute further before collecting the series.
3. **Lock acquisition parameters within a series:** Keep excitation wavelength, slit widths, scan speed (`$SS`), step interval (`$SI`), PMT voltage (`$PV`), filter wheel (`$FW`), and `$CX` state identical across all samples compared in a single plot.
4. **Replicate measurements:** Record at least 3 scans per condition, including removing and reseating the cuvette to capture mechanical positioning variance.

---

## 4. Experiment Procedures

### Experiment 1: Tonic-Water Emission Spectrum and Dilution Curve

- **Reagents:** Commercial tonic water containing quinine, distilled or deionized water.
- **Preparation:** Degas a small portion of tonic water in a loosely covered vessel until flat so $\text{CO}_2$ bubbles do not form on cuvette walls. Prepare a distilled-water blank and a 2-fold serial dilution series (`1:20`, `1:40`, `1:80`, `1:160`, `1:320` tonic-to-total-volume, where `1:20` = 1 part tonic + 19 parts water).
- **Acquisition:** Set excitation to **350 nm** (`5 nm` Ex/Em slits, `120 nm/min` scan speed, `2 nm` step) and scan emission from **400 to 550 nm** [2, 3]. Quinine exhibits a broad blue emission band centered near **450 nm** (check for the weak water Raman peak near `397 nm` in the water blank).
- **Analysis:** Plot blank-subtracted peak (or band-integrated) intensity vs. relative tonic concentration. Identify the low-concentration linear regime, fit a weighted line with residuals, and note the high-concentration roll-off caused by primary/secondary inner-filter absorption and pH shift upon water dilution [2, 5].

### Experiment 2: Chloride Quenching of Quinine (Stern–Volmer Series)

- **Reagents:** Degassed tonic water (`1:10` working stock: 1 part tonic + 9 parts water), high-purity non-iodized NaCl (`0.50 M` stock: `2.92 g` NaCl made up to `100.0 mL` total volume in water), distilled water.
- **Preparation:** Prepare four `10.0 mL` solutions at a constant `1:100` final tonic dilution and varying $[\text{NaCl}]$:

| Sample | `1:10` Tonic Stock | `0.50 M` NaCl Stock | Distilled Water | Total Volume | Final $[\text{NaCl}]$ |
| --- | ---: | ---: | ---: | ---: | ---: |
| **A ($I_0$)** | `1.0 mL` | `0.0 mL` | `9.0 mL` | `10.0 mL` | `0.000 M` |
| **B** | `1.0 mL` | `0.5 mL` | `8.5 mL` | `10.0 mL` | `0.025 M` |
| **C** | `1.0 mL` | `1.0 mL` | `8.0 mL` | `10.0 mL` | `0.050 M` |
| **D** | `1.0 mL` | `2.0 mL` | `7.0 mL` | `10.0 mL` | `0.100 M` |

- **Acquisition:** Using the same settings as Experiment 1 (Ex `350 nm`, Em `400–550 nm`), measure matched salt-in-water blanks and each sample `A–D` [2, 4].
- **Analysis:** Compute blank-subtracted intensity $I$ at `450 nm` and plot the Stern–Volmer ratio $I_0 / I$ against $[\text{NaCl}]$. Fit $I_0 / I = 1 + K_{\text{SV}}[\text{NaCl}]$ and inspect residuals for upward curvature or ionic-strength effects.

### Experiment 3: Vitamin B2 (Riboflavin) Spectral Fingerprint

- **Reagents:** Single-ingredient riboflavin (vitamin B2) tablet or capsule, distilled water.
- **Preparation:** Dissolve/extract a small amount in water, allow insoluble tablet binders to settle (or filter alongside a filtered water blank), and dilute until visually pale yellow and non-saturating.
- **Acquisition:** Set excitation to **445 nm** and scan emission from **480 to 620 nm** [8]. Riboflavin absorbs near `444 nm` and emits a broad green-yellow band centered near **520–530 nm**.
- **Analysis:** Normalize and overlay the quinine (`~450 nm`) and riboflavin (`~525 nm`) emission spectra to compare Stokes shifts and band profiles.

### Experiment 4: Riboflavin Photodegradation vs. Dark Control

- **Preparation:** Split a fresh dilute riboflavin solution into two identical closed vials at the same ambient temperature. Wrap the control vial completely in aluminum foil; expose the test vial to a fixed visible desk lamp or diffuse daylight (avoid heating the solution).
- **Acquisition:** Record the emission spectrum (Ex `445 nm`, Em `480–620 nm`) of both aliquots at $t = 0, 30, 60, \text{and } 120\text{ min}$ (extending if the light source is weak). Keep the LS 55 shutter closed (`$ES 1`) whenever a scan is not actively running.
- **Analysis:** Plot $I(t)/I(0)$ at `525 nm` for the exposed and foil-wrapped samples, and examine the full emission profile for shifts resulting from photoproducts (such as lumichrome/lumiflavin) [8].

### Experiment 5: Two-Component Mixtures (Quinine + Riboflavin)

- **Preparation:** Prepare (1) pure dilute tonic water at concentration $c_Q$, (2) pure dilute riboflavin at concentration $c_R$, and (3) a mixture containing both components at the **exact same final concentrations** ($c_Q$ and $c_R$), plus a water blank.
- **Acquisition:**
  1. *Shared-excitation emission scan:* Excite all three solutions at **350 nm** (where both quinine and riboflavin have UV absorption bands) and scan emission from **400 to 620 nm**.
  2. *Synchronous scan (optional):* Run constant-offset synchronous scans (`$MX` / `$MQ`) to narrow overlapping bands.
- **Analysis:** Test whether the blank-subtracted mixture spectrum $S_{\text{mix}}(\lambda)$ matches the linear sum $S_Q(\lambda) + S_R(\lambda)$, and fit component weights $w_Q, w_R$ by linear least squares. Analyze residuals for inner-filter cross-absorption (riboflavin absorbs near `444 nm`, overlapping quinine's `450 nm` emission band) [5].

---

## 5. Out of Scope for Initial Runs

- Volatile organic solvents, strong mineral acids, or reactive chemiluminescence reagents.
- Fluorophores emitting above `650 nm` (such as chlorophyll *a* near `670–680 nm`) until the installed PMT variant (standard S5 vs. R928) is confirmed.
- Nanosecond excited-state lifetime measurements (not supported by the LS 55's microsecond flash integration hardware).

## Sources

1. PerkinElmer LS 55 User's Guide, release C, March 2007 — obtain locally per [../vendor/README.md](../vendor/README.md).
2. PerkinElmer application note, *Determination of Quinine in Tonic Water Using Fluorescence Spectroscopy* — https://diverdi.colostate.edu/C372/experiments/steady%20state%20fluorescence%20of%20quinine%20and%20quenching%20by%20chloride/references/quinine%20in%20tonic%20water%20Perkin-Elmer.pdf
3. UCAR Center for Science Education, *Detecting Ultraviolet Light Using Tonic Water* — https://scied.ucar.edu/activity/learn/ultraviolet-light-tonic-water
4. Carolina Biological, *Violet Shines Blue* (halide quenching of quinine) — https://www.carolina.com/teacher-resources/Interactive/violet-shines-blue/tr32614.tr
5. Simeonov & Davis, *Interference with Fluorescence and Absorbance*, Assay Guidance Manual (NCBI Bookshelf, 2015) — https://www.ncbi.nlm.nih.gov/books/NBK343429/
6. Vernier, *Fluorescence/UV Quartz Cuvette* specifications — https://www.vernier.com/product/fluorescence-uv-quartz-cuvette/
7. BRAND, *Four-Window UV-Transparent Cuvettes* technical note — https://shop.brand.de/media/import/1/27/32406/42485/42649/42738/Cuvettes_4_windows_EN.pdf
8. Keune, Waitz & Irmer, *Photodegradation of Riboflavin — Model Experiments on Photo Processes in Chemistry Class* — https://conference.pixel-online.net/files/npse/ed0011/FP/0174-CHEM5412-FP-NPSE11.pdf
