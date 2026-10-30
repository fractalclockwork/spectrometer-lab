# UV Fiber Probe Assessment for the Salvaged LS 55

October 30, 2026 | Low-cost DIY UV fiber assembly assessment for this bench LS 55 (firmware `F1`)

This bench LS 55 is an e-waste salvage unit operating without a dedicated project budget, and its sample compartment is missing the complete factory `L2250140` cuvette holder (leaving an unfastened machined square-bore block; see [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §5). We are not reinventing optical probe principles—established factory and commercial UV probe designs provide the optical baselines—but purchasing commercial fiber bundles is cost-prohibitive. This assessment evaluates building a custom, replaceable-tip two-fiber assembly from bare solarization-resistant silica fiber (`~$12–$30/m`) coupled through the existing compartment fixture.

---

## 1. Technical Summary and Low-Cost DIY Path

For a first replaceable-tip prototype, the most practical starting material is **acrylate-coated, solarization-resistant, step-index multimode silica fiber (`NA 0.22 ± 0.02`, `200 µm` or `400 µm` core)** using separate excitation and collection legs (`FG200AEA` at `$11.89/m` or `FG400AEA` at `$29.00/m`) [1, 2]:

- **Why acrylate first:** Acrylate coating strips and cleaves cleanly with basic hand tools, making repeated tip renewal practical. Polyimide (`UM22-200` / `UM22-400`) is reserved for cases where sample chemistry or high temperature (`>85 °C`) rules out acrylate [1, 2].
- **Core experimental question:** UV transmission is only one requirement. A usable renewable-tip probe must deliver reproducible excitation/collection overlap, an acceptably low blank signal, and stable spectra after each strip-and-cleave renewal. Replacing a cuvette changes the measurement geometry and does not automatically preserve cuvette calibration; collection efficiency depends strongly on inter-fiber arrangement and sample optical properties [6].
- **Scope:** These candidates are prototype bare-fiber selections, not a final bill of materials or a claim of drop-in LS 55 compatibility. Final specifications depend on the target excitation/emission bands and sample interface geometry.

---

## 2. Existing Precedents (Design Benchmarks, Not Purchase Targets)

We borrow proven optical principles from factory and commercial probes rather than inventing a new optical architecture or buying complete assemblies:

- **PerkinElmer `L2250144` external fiber-optic accessory (factory precedent):** Documented in the LS 55 User's Guide (`pp. 87–92`) as a `1 m` bifurcated bundle with two semicircular regions at the sampling tip, `NA ~0.2`, and excitation down to `~260 nm` [5]. It requires optical alignment on both the excitation and emission ports and achieves peak sensitivity `1–2 mm` from the sample (with poor collection on direct contact). That `1–2 mm` standoff is specific to the factory bundle geometry, not a universal rule for an immersed two-fiber probe. Its existence confirms that remote fiber coupling is supported on the LS 55; our DIY path targets a lower-cost, direct-to-sample renewable tip with deeper UV reach.
- **LS 55 monochromator and detector bounds:** The LS 55 excites across `200–800 nm` and collects across `200–650 nm` with the standard S5 PMT or `200–900 nm` with the optional R928 PMT ([../reference/instrument-specs.md](../reference/instrument-specs.md) §2). Selecting a fiber rated to `180 nm` avoids deep-UV fiber roll-off near `200 nm` but does not extend the instrument below `200 nm`. Which PMT variant is fitted to this salvaged unit remains to be verified visually [5].
- **Ocean Optics `SR` / `XSR` reflection probes (commercial geometry benchmark):** Current probe specifications list `200–1100 nm` (`SR`) and `180–900 nm` (`XSR`, with general technical notes citing `180–800 nm` best efficiency) using a six-illumination-around-one-collection (`6-around-1`) bundle [3, 4]. This serves as a reference benchmark, not proof that `6-around-1` is needed for our samples or mates directly to the LS 55 compartment.
- **Polymicro `FDP` (deep-UV material benchmark):** High-OH, low-solarization silica fiber (`NA 0.22 ± 0.02`, polyimide-coated, `100 / 200 / 400 / 600 µm` cores) developed for `190–325 nm` [7]. Useful as a deep-UV reference family if work shifts below `250 nm`; verify full emission-band transmission before selecting it.

---

## 3. Wavelength Bands and Bare-Fiber Candidates

### 3.1 Selecting by Target Wavelength Band

Manufacturer wavelength ranges describe operating efficiency bands rather than flat attenuation guarantees; qualify both excitation and emission paths over the actual wavelengths used:

| Target Work | Fiber Requirement | Practical Implications |
| --- | --- | --- |
| **~350 nm Ex / 450 nm Em** (quinine baseline in [home-lab experiments](../experiments/fluorescence-home-lab.md)) | Standard UV-grade high-OH silica works here, but solarization-resistant silica preserves headroom for shorter wavelengths. | Sensible first test pair. Standard UV/VIS high-OH fibers typically specify `300–1100 nm` best efficiency [3]. |
| **250–300 nm Ex** (including `~280 nm` aromatic/protein excitation) | Require **solarization-resistant** silica, not merely high-OH content or a short-wavelength cutoff spec. | Standard high-OH fibers solarize (darken) under UV exposure below `300 nm` [1–3]. |
| **200–250 nm Ex** (deep UV) | Require deep-UV solarization-resistant fiber with verified attenuation and UV-dose stability at the working wavelength. | Keep fiber lengths short (`<1 m` per leg) and qualify every lens, mirror, adhesive, ferrule, and exposed coating in the optical path [1, 3, 7]. |
| **UV emission + UV excitation** | Qualify the collection fiber over the UV emission band as well. | An excitation-only transmission spec does not guarantee low loss on a UV return path [3]. |

### 3.2 Bare-Fiber Candidates (`0.22 ± 0.02 NA` Step-Index Multimode)

All four Thorlabs candidates use a pure-silica core and fluorine-doped silica cladding (`NA 0.22 ± 0.02`). Dimensions list `core / cladding / coating` outside diameter (`µm`). Bare-fiber prices (checked October 30, 2026) exclude connectors, optics, tools, tax, and shipping, demonstrating that raw fiber material is inexpensive (`~$12–$52/m`) if assembled in-house [1, 2]:

| Candidate | Rated Band | Dimensions (`core / clad / coat`, `µm`) | Coating & Temp Range | Bare-Fiber Price | DIY Assessment |
| --- | --- | --- | --- | ---: | --- |
| **`FG200AEA`** | `180–1200 nm` | `200 ± 4 / 220 ± 2 / 320 ± 12.8` | Acrylate (`-40 to 85 °C`) | **`$11.89/m`** | Lowest-cost starting point; easy mechanical stripping and cleaving (`22 mm` min long-term bend radius) [1]. |
| **`FG400AEA`** | `180–1200 nm` | `400 ± 8 / 440 ± 4 / 550 ± 15` | Acrylate (`-40 to 85 °C`) | **`$29.00/m`** | `4×` core face area vs. `200 µm`; easier alignment tolerances (`44 mm` min long-term bend radius) [1]. |
| **`UM22-200`** | `180–850 nm` | `200 ± 4 / 220 ± 4 / 239 ± 5` | Polyimide (`-65 to 300 °C`) | `$17.41/m` | Solvent/high-temperature fallback; difficult to strip mechanically [2]. |
| **`UM22-400`** | `180–850 nm` | `400 ± 8 / 440 ± 9 / 480 ± 7` | Polyimide (`-65 to 300 °C`) | `$51.80/m` | Larger-core polyimide option; `0.32 dB/m` typical attenuation at `250 nm` [2]. |

> **Core area vs. signal:** A `400 µm` core has `4×` the cross-sectional area of a `200 µm` core ($d^2$ scaling), which relaxes launch alignment in a DIY mount, but does not guarantee `4×` fluorescence intensity—launch image size, sample overlap volume, and emission monochromator slit acceptance can dominate [6]. Also note that a coating's temperature rating does not establish chemical compatibility for a wetted probe tip.

---

## 4. Optical and Mechanical Coupling to This Bench Unit

Instead of purchasing commercial SMA launch assemblies, the DIY design can adapt the **existing machined square-bore metal block** already sitting in the LS 55 sample compartment ([../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §5):

- **Existing compartment block geometry:** `~17 mm` square bore × `42 mm` deep; `24.81 mm (H) × 9.82 mm (V)` optical windows aligned with the LS 55's `~9 mm` vertical beam height; `~8 mm` (left) and `~3 mm` (right) side ports/bores; exterior mounting-screw holes present.

### Key Design Requirements

1. **Couple both ends of each path at the compartment block:** Relay the LS 55 excitation beam into the excitation fiber core within its `0.22 NA` acceptance cone, and image the collection fiber output into the emission entrance optics. The existing square-bore block (`24.81 × 9.82 mm` windows and `~8 mm` / `~3 mm` side ports) provides a candidate mechanical body for mounting turn mirrors, ball/plano-convex UV fused-silica lenses, or direct fiber ferrules once fastened to the accessory platform. Even the factory `L2250144` accessory requires active optical alignment at both ports [5].
2. **Account for NA changes in the sample medium:** For `NA 0.22`, the acceptance half-angle in air is $\theta_{\text{air}} = \arcsin(0.22) \approx 12.7^\circ$ (`25.4°` full cone). In an aqueous sample ($n \approx 1.33$), the half-angle narrows to $\theta_{\text{water}} = \arcsin(0.22 / 1.33) \approx 9.5^\circ$ (`19.0°` full cone) [3, 6]. Immersion alters the excitation/collection overlap volume compared to air standoff.
3. **Separate probe tip geometry from fiber selection:** Start with two independently positioned bare fibers held in a rigid, repeatable 3D-printed or machined jig. Compare parallel vs. angled (`15°–30°`) two-fiber arrangements with fixed inter-fiber spacing, angle, and immersion depth before committing to a potted bundle [6]. (A single-fiber send/return design would require a beamsplitter/dichroic separator and stricter stray-light rejection.)
4. **Keep fiber runs short and fixed (`<0.5–1.0 m` per leg):** Short paths minimize both cost (`<$15–$30` of fiber per prototype) and deep-UV attenuation. Thorlabs specifies `0.32 dB/m` typical at `250 nm` for `UM22-200`/`400` (not guaranteed at `200 nm` or across all emission bands) and minimum long-term bend radii of `22 mm` (`200 µm` core) and `44 mm` (`400 µm` core) [1, 2]. (For comparison, the jacketed factory `L2250144` bundle specifies a `≥10 cm` bend radius [5].)
5. **Qualify sample-contact materials and probe blanks:** Specify solvent, pH, temperature, exposure time, and cleaning steps. Test the stripped silica tip, any exposed coating margin, and the holder material against a matched **probe-in-solvent blank** so that silica Raman/fluorescence, coating autofluorescence, and scattered excitation light are measured and subtracted rather than attributed to the analyte [6].
6. **Maintain spectral flexibility:** Avoid fixed long-pass adhesives or coatings in the optical path that would block broad excitation/emission scans. Rely on the LS 55's built-in emission monochromator and programmable emission filter wheel (`$FW`: `290, 350, 390, 430, 530 nm`, clear, blank, `1% T`) for excitation rejection ([../reference/instrument-specs.md](../reference/instrument-specs.md) §3) [3, 5].

---

## 5. Replaceable Tips and Manual Renewal Protocol

Because bare acrylate fiber (`FG200AEA` / `FG400AEA`) costs `~$0.12–$0.30 per centimeter`, fouling or tip damage at the sample end can be addressed by stripping and cleaving a few millimeters of fiber rather than replacing an expensive probe—provided the mechanical datum restores the optical geometry. Prove this interface **manually** before designing any automated cutter or dresser:

- **Flat, chip-free cleave:** Strip the acrylate buffer cleanly from the wetted tip region without scratching the fluorine-doped cladding, cleave perpendicular to the fiber axis, and inspect the end face under a microscope to confirm no chips cross the active core.
- **Hard mechanical datum:** Seat both cleaved fibers against a repeatable mechanical stop that restores tip axial position, inter-fiber separation, convergence angle, and exposed stripped length after every renewal.
- **UV pre-conditioning (solarization equilibrium):** Solarization is bulk UV-induced attenuation along the illuminated fiber length—clipping a distal tip removes surface fouling but does not reverse bulk darkening. Thorlabs recommends pre-exposing solarization-resistant fibers to UV until initial degradation reaches equilibrium before taking quantitative series [1–3].
- **Post-renewal verification:** Record dark, air, solvent-blank, and fluorescence-standard readings after each cleave to quantify carryover and throughput reproducibility.
- **Sharps containment:** Collect all cleaved silica shards directly into a closed sharps container and keep glass fragments out of sample vials.

Whether manual or automated tip dressing matches the repeatability and cost per measurement of reusable quartz cuvettes is an open experimental question to be answered on the bench.

---

## 6. Baseline Verification Experiment and Open Decisions

### 6.1 Proposed Five-Step Bench Comparison

Once a basic compartment fixture is secured (Gate D), validate the DIY two-fiber assembly against standard cuvette geometry:

1. **Select a stable test pair:** Start at the **350 nm Ex / 450 nm Em** quinine sulfate (tonic water) condition from [../experiments/fluorescence-home-lab.md](../experiments/fluorescence-home-lab.md) with a matched water blank before moving to `250–280 nm` UV tests.
2. **Record the cuvette baseline:** If a cuvette seat is set up in the square-bore block, record reference dark (`$ES 1`), solvent blank, and standard emission scans (`$ES 0`), logging slit widths (`$SX`, `$SM`), filter wheel (`$FW`), PMT voltage (`$PV`), and `$CX` state.
3. **Evaluate the fixed two-fiber geometry:** Mount the excitation and collection fibers in the compartment block, immerse or position the distal tips in the same standard and blank solutions, and measure dark floor, solvent blank (checking for fiber scatter and the `~397 nm` water Raman band), dilution response, and continuous-exposure drift.
4. **Test tip-renewal repeatability:** Strip, cleave, inspect, and re-seat the fiber tips against the mechanical datum at least `3–5` times, comparing blank background, peak intensity, spectral shape, and coefficient of variation across renewals.
5. **Extend to shortest target UV wavelength:** Repeat at the shortest required excitation wavelength (`≤280 nm`) while independently tracking throughput vs. exposure time to separate xenon lamp drift, bulk fiber solarization, and sample photobleaching.

Define pass/fail criteria (signal-to-blank ratio, cleave-to-cleave RSD, carryover limit) based on the target assay once chosen [6].

### 6.2 Open Design Decisions

Answering these five questions turns the bare-fiber candidates above into a concrete build and ordering list (no purchases have been made):

1. **Shortest wavelength:** What is the shortest excitation wavelength needed (`350 nm` home-lab baseline, `280 nm` protein/aromatic UV, or `<250 nm` deep UV), and does the emission band also lie below `300 nm`?
2. **Sample format and contact mode:** Are the primary samples clear aqueous solutions, turbid mixtures, or solid surfaces—and should the two-fiber tip immerse directly or operate at a short air standoff?
3. **Dominant constraint:** Beyond near-zero capital cost, is the primary optimization target sensitivity, cleave-to-cleave repeatability, zero carryover, or microliter sample volume?
4. **Chemical environment:** Will samples stay within aqueous/mild-buffer conditions compatible with stripped silica and nearby acrylate coating (`FG200AEA` / `FG400AEA`), or require aggressive solvents/temperatures (`UM22` polyimide)?
5. **Compartment coupling & detector:** How will we fixture launch/collection optics inside the existing `~17 mm` square-bore block (`24.81 × 9.82 mm` windows, `~8 mm` / `~3 mm` side ports), and which PMT (`S5` vs. `R928`) is installed inside this unit?

---

## Sources

Manufacturer and primary-source specifications checked October 30, 2026. Supplier tolerances and per-meter prices should be rechecked before ordering.

1. Thorlabs, *0.22 NA Solarization-Resistant Step Index Multimode Optical Fibers* (`FG200AEA`, `FG400AEA` dimensions, operating bands, acrylate coating, prices, termination guidance, and UV conditioning) — https://www.thorlabs.com/0.22-na-solarization-resistant-step-index-multimode-optical-fibers
2. Thorlabs, *0.22 NA Polyimide-Coated Step Index Multimode Optical Fibers* (`UM22-200`, `UM22-400` attenuation at `250 nm`, bend radii, high-OH solarization caveat, and stripping notes) — https://www.thorlabs.com/0.22-na-polyimide-coated-step-index-multimode-optical-fibers
3. Ocean Optics, *Optical Fiber Technical Information* (`UV/VIS` vs. `SR`/`XSR` families, NA and immersion-angle relationship, solarization, and assembly notes) — https://www.oceanoptics.com/accessories/fibers-and-probes/optical-fiber-technical-information/
4. Ocean Optics, *Solarization Resistant Reflection/Backscatter Probes* (`SR`/`XSR` wavelength bands and `6-around-1` bundle geometry) — https://www.oceanoptics.com/accessories/fibers-and-probes/reflection-backscatter-probes/extreme-solarization-resistant-reflection-backscatter-probes/
5. PerkinElmer, *LS 55 User's Guide*, part 09934436 (Instrument specifications; *External Fibre Optic Accessory* `L2250144`, printed `pp. 87–92`; see also [../vendor/README.md](../vendor/README.md) and mirror at https://www.wpi.edu/sites/default/files/2025-07/Perkin_Elmer_LS-55-Users-Guide.pdf).
6. G. K. Bhowmick, N. Gautam, and L. M. Gantayet, *Design optimization of fiber optic probes for remote fluorescence spectroscopy*, Optics Communications 282 (2009), 2676–2684 (abstract, introduction, and conclusions reviewed on probe geometry, excitation/collection overlap, dead volume, and sample optical properties) — https://www.sciencedirect.com/science/article/abs/pii/S0030401809003770
7. Laser Components / Polymicro, *FDP-High-OH: Low-solarization Quartz Fibers* technical datasheet (`190–325 nm` deep-UV band, `0.22 NA`, and core diameter options) — https://www.lasercomponents.com/fileadmin/user_upload/home/Datasheets/polymicro/fdp-high-oh.pdf
