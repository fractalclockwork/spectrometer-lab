# Distilled Water Raman — Wavelength / SNR Baseline

November 3, 2026 | Quartz-cuvette distilled-water Raman (Ex `350 nm`, `10 nm` slits)

> **Gate D note:** The compartment square-bore block is measured but unsecured ([../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §5). Record peak position and RMS SNR as DIY-fixture baselines. Do **not** claim factory `L2250140` equivalence or the published `500:1` sensitivity.

> **Calibration record:** Only quartz-cuvette distilled-water runs from this procedure belong in the calibration set. Prior solid-sample or non-cuvette probing was exploratory and is archived under `logs/_invalid/` — not part of this record.

---

## 1. Goal

Acquire the water O–H stretch Raman band (~`3400 cm⁻¹` → ~`397 nm` at Ex `350 nm`) in a quartz cuvette filled with distilled water, subtract a matched empty-compartment freepath blank, annotate the peak, and log RMS SNR. After one sanity PASS, collect a calibration series (5 technical + 5 reseated).

---

## 2. Method (locked)

| Parameter | Value |
| --- | ---: |
| Excitation (`$GM`) | `350.0 nm` |
| Emission (`$AL` / `$AH`) | `380–420 nm` |
| Slits (`$SX` / `$SM`) | `10.0 nm` |
| Scan speed (`$SS`) | `120 nm/min` |
| Step (`$SI`) | `2.0 nm` |
| Guide peak | `397 nm` |
| Noise band (SNR) | `410–420 nm` (excludes guide ±`8 nm`) |

---

## 3. Matched blank rule

Acquire a **new** freepath blank at the same Ex, slits, speed, and step; Em must cover at least `380–420`. Empty compartment (cuvette removed), door closed:

```bash
python scripts/run_freepath_serial.py \
  --port /dev/serial/by-id/<adapter> \
  --stage2-pass --compartment-closed --baud 9600 \
  --em-lo 380 --em-hi 420 --slit 10 \
  --log-dir logs/freepath
```

Pass the resulting `freepath-*.csv` as `--blank` on every water-Raman run. Do not reuse a blank taken at a different slit width.

---

## 4. Cuvette seating

1. Close the excitation shutter (`$ES 1`) and confirm readback before opening the compartment.
2. Load a 4-window UV quartz cuvette with distilled water (≥ ~`2 mL` so the meniscus clears the ~9 mm beam). Wipe exterior faces; remove bubbles.
3. Seat the cuvette in the square-bore block with clear faces on the excitation and emission axes. Close the door fully.
4. After each scan, verify source OFF / `$ES 1` before opening the door.

---

## 5. Sanity criteria (before the series)

One `--replicate-kind sanity` run must:

- Report acquisition `passed` with no overload / `999999` clipping
- Show a local max near `397 nm` with **|Δ| ≤ 5 nm**
- Report a finite RMS SNR (no hard factory `500:1` gate on this fixture)

On failure, stop and diagnose (seat, fill height, bubbles, stray light, blank match) before collecting calibration scans.

---

## 6. Calibration series (2C)

Share one `--series-id` (e.g. wall-clock stamp) across all runs after sanity:

1. **Technical ×5** — cuvette undisturbed; `--replicate-kind technical`
2. **Reseat ×5** — between runs: source OFF → open door → lift and reseat (same orientation) → close → `--replicate-kind reseat`

Then:

```bash
python scripts/summarize_water_raman.py --series-id <stamp>
```

---

## 7. CLI usage

```bash
PORT=/dev/serial/by-id/<adapter>
BLANK=logs/freepath/freepath-<stamp>.csv
SERIES=$(date +%Y%m%d-%H%M%S)

# Sanity
python scripts/run_water_raman_serial.py \
  --port "$PORT" --stage2-pass --sample-loaded --baud 9600 \
  --blank "$BLANK" --replicate-kind sanity --series-id "$SERIES"

# Technical replicate (repeat ×5)
python scripts/run_water_raman_serial.py \
  --port "$PORT" --stage2-pass --sample-loaded --baud 9600 \
  --blank "$BLANK" --replicate-kind technical --series-id "$SERIES"

# Reseat replicate (repeat ×5 after reseating)
python scripts/run_water_raman_serial.py \
  --port "$PORT" --stage2-pass --sample-loaded --baud 9600 \
  --blank "$BLANK" --replicate-kind reseat --series-id "$SERIES"

# Offline dry-run (fixture Em range must match --em-lo/--em-hi)
python scripts/run_water_raman_serial.py \
  --fixture-dir tests/fixtures/freepath_happy \
  --stage2-pass --sample-loaded \
  --blank /path/to/blank.csv \
  --em-lo 400 --em-hi 550
```

Outputs land in `logs/water-raman/`: raw serial log, JSON sidecar (settings, blank, peaks, SNR, replicate tags), CSV (`wavelength_nm,sample_on,blank,corrected`), and annotated PNG.

---

## 8. Results (series `20261103-1629`)

Bench writeup, go/no-go verdict, aggregate peak/SNR tables, and continuum-residual figures:

**[../assessment/water-raman-baseline.md](../assessment/water-raman-baseline.md)**

Summary: optical path **go**; technical peak ~`395 nm` (Δ ≈ `−2 nm`); absolute-peak SNR ~`123` (~4× below factory `500:1` on this DIY fixture); reseat intensity unstable until the cuvette seat is fixed.

---

## 9. Sources

1. PerkinElmer LS 55 published water Raman sensitivity: `500:1` RMS SNR at Ex `350 nm`, `10 nm` Ex/Em bandpass, distilled water in `L2250140` — see [../reference/instrument-specs.md](../reference/instrument-specs.md).
2. Water O–H Raman (~`3400 cm⁻¹`) appears near **397 nm** under Ex `350 nm` — [../software/features-and-roadmap.md](../software/features-and-roadmap.md).
3. Series analysis: [../assessment/water-raman-baseline.md](../assessment/water-raman-baseline.md).
