# Measured Performance vs Published Specs (DIY Fixture)

November 3, 2026 | Sources: bring-up Stages 1–3, water Raman `20261103-1629`, tonic gate `20261103-194005`

> **Scope:** Bench LS 55 (`F1`, SN `79787`) on the **unsecured Al square-bore block** (Gate D open — not factory `L2250140`). Published brochure numbers that require a qualified holder remain **open**; DIY baselines below are usefulness checks, not factory claims. Specs: [../reference/instrument-specs.md](../reference/instrument-specs.md). Exploratory residual, peak-fit, and repeatability tables: [../../notebooks/water-raman-tonic-water-analysis.ipynb](../../notebooks/water-raman-tonic-water-analysis.ipynb).

---

## 1. Scorecard

| Domain | Published / expected | Measured on this DUT | Status |
| --- | --- | --- | --- |
| Wavelength accuracy | `±1.0 nm` | Raman tech Δ ≈ `−1.8 nm` (guide `397`); tonic gate Δ ≈ `−3.0 nm` (guide `450`) | **DIY OK / factory open** |
| Wavelength reproducibility | `±0.5 nm` | Raman tech σ ≈ `1.1 nm`; tonic tech σ ≈ `3.1 nm`; reseats worse | **Not met** (seating-limited) |
| Water Raman sensitivity | `500:1` RMS SNR @ Ex `350`, `10 nm` slits, `L2250140` | Absolute-peak SNR ~`123` (~4× below) on DIY block | **Not met** (fixture) |
| Fluorescence path (quinine) | Broad Em ~`450 nm` | Gate peak **447 ± 5 nm**, unclipped at ~`1:450` | **Go** |
| Dynamic range / clip | ASCII ceiling `999999`; avoid `$PT 0107` | Tonic clips at `1:1`/`1:2`/`~1:90`; clear at ~`1:450` (I ~`127k`) | **Behaves as designed** |
| Dark floor | Near-zero with `$ES 1` | Empty/dark \|I\| ≤ `1` (Stage 3); water blank dark max `0` | **Pass** |
| Shutter (`$ES`) | `0`=ON, `1`=OFF; end OFF | Every Raman/tonic/freepath run restored `$ES`=`1` | **Pass** |
| Scan timing | `$SS` `10–1500 nm/min`; flash cycle ~`16 ms` @ 60 Hz | Locked `120 nm/min`, `2 nm` step; Em `400–550` (~76 pts) ≈ **~2.8 min**/arm | **Consistent** |
| Monochromator / slits | `$GM` / `$SX` / `$SM` ranges | Stage 2 readbacks within tolerance; Raman `10 nm`, tonic `5 nm` set OK | **Pass** |
| Mains / flash clock | 50/60 Hz | `$HZ`=`60`; `$ST` cycle `16 ms` | **Pass** |

---

## 2. Wavelength (accuracy & reproducibility)

| Spec (`pp. 17–18`) | Water Raman (`10 nm`, guide `397`) | Tonic (`5 nm`, guide `450`) |
| --- | --- | --- |
| Accuracy `±1.0 nm` | Tech mean peak `395.2` → **Δ −1.8 nm**; cal (n=10) **Δ −2.4 ± 2.7 nm** | Gate (n=6) peak `447.0` → **Δ −3.0 ± 5.2 nm** |
| Repro `±0.5 nm` | Tech σ **1.1 nm** (n=5); reseat σ **3.7 nm** | Tech σ **3.1 nm** (n=3); reseat σ **7.6 nm** |

**Reading:** Both fluorescent and Raman features land a few nm short of literature guides — useful DIY sanity, **not** a closed factory accuracy claim. Repeatability is **seat-dominated**: undisturbed technicals are tighter than reseats; neither series meets brochure `±0.5 nm` on this loose ~17 mm bore.

Evidence: [water-raman-baseline.md](water-raman-baseline.md), [tonic-water-baseline.md](tonic-water-baseline.md).

---

## 3. Intensity & sensitivity

| Spec / behavior | Measured |
| --- | --- |
| Water Raman `500:1` RMS SNR (Ex `350`, `10 nm`, `L2250140`) | DIY absolute-peak SNR **~123 ± 25** (cal n=10). Continuum contrast on good seats ~`2.5–3.3k` counts over ~`14–19k` floor — SNR metric is flattering vs true Raman contrast. |
| Quinine emission intensity | Unclipped peak ~`127k` counts at ~`1:450`, `5 nm` slits; max \|I\| ~`147–163k`. |
| Clip ceiling `999999` | Freepath Rayleigh (Ex `350`) clips near `346–354` / `696–706 nm` (Stage 3). Tonic scouts: `1:1`/`1:2` ~66/76 pts clipped; `~1:90` ~20/76; `~1:450` **0** clipped. |
| Dark / shutter-OFF | Stage 3 dark max \|I\| = `1`; tonic blank dark max `0`. |

**Reading:** Sensitivity shortfall vs `500:1` is expected without return mirrors / factory seat. Dynamic range and dark subtraction behave per design — bright samples need dilution or narrower slits, not a broken PMT.

---

## 4. Time, flash rate, scan pacing

| Spec | DUT / measured |
| --- | --- |
| Mains `$HZ` | **`60`** (matches rear plate) |
| Flash cycle (`$ST`) | **`16 ms`** (~62.5 Hz service rate; flashcount `1`) |
| Scan speed range | `10–1500 nm/min`; locked experiments use **`120 nm/min`** |
| Step | **`2.0 nm`** |
| Wall-clock Em scan (tonic `400–550`, 76 pts, dark+ON) | ~**170 s** end-to-end CLI (~2.8 min) — consistent with 150 nm span @ 120 nm/min plus setup/cleanup |

Flash block-averaging still scales with `$SS` as documented; these baselines did not sweep speed for SNR trade studies.

---

## 5. Shutter & source control

| Spec | Measured |
| --- | --- |
| Polarity | `$ES 0` = source ON, `$ES 1` = OFF |
| Power-on | Source defaults **ON** — software must force OFF before opening door |
| Harness cleanup | Freepath / water-Raman / tonic runners end with verified `$ES`=`1` |
| Gate series | All 7 tonic gate acquisitions + Raman series restored shutter OFF |

---

## 6. Motion, slits, identity (bring-up)

Already closed in [bringup-report.md](bringup-report.md); retained here for the scorecard:

| Item | Spec / command | Observed |
| --- | --- | --- |
| Model / FW / SN | LS 55 | `55` / `F1` / `79787` |
| Wavelength move | `$GM` ±0.1 nm setability | Stage 2 readback within **±0.15 nm** test tolerance |
| Slits | Ex `2.5–15`, Em `2.5–20` | `$SX`/`$SM` `5.0` and `10.0` verified |
| PMT | Auto/manual `$PV` | **`775 A`** (auto) |
| NVM | `$ME` | **`0000`** healthy |
| Mode | Fluorescence `$PH 0` | Confirmed |
| Serial | 9600 8N1 prompted | Prolific path preferred (0 Class B in Stage 1 sample) |

---

## 7. What remains open vs brochure

1. **Factory wavelength accuracy `±1.0 nm`** — needs `$XC`/`$MC` or sealed standards after Gate D seat.
2. **Wavelength reproducibility `±0.5 nm`** — blocked by loose cuvette / unsecured block.
3. **Water Raman `500:1`** — requires `L2250140` (or documented DIY geometry claim); current ~`123` is fixture-limited.
4. **Emission spectral correction** — host-side only; not exercised in these baselines.
5. **PMT variant (S5 vs R928)** — not readable over RS-232; Em to `900 nm` accepted in firmware.

---

## 8. Bottom line

Control plane (shutter, monos, slits, scan timing, dark floor, clip behavior) matches the published instrument model. Optical **go** for home-lab fluorescence and Raman pathfinding. Brochure **accuracy / reproducibility / 500:1 sensitivity** are **not** closed on the DIY holder — fix Gate D seating before treating peak nm or SNR as instrument health vs specs.
