# Tonic-Water Quinine Emission — Usefulness Gate

November 3, 2026 | Commercial tonic (drink mixer), Ex `350 nm`, `5 nm` slits

> **Gate D note:** The compartment square-bore block is measured but unsecured ([../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §5). This procedure is a **go/no-go optical usefulness check** for quinine fluorescence on the DIY fixture — **not** the full Expt 1 dilution / IFE ladder in [fluorescence-home-lab.md](fluorescence-home-lab.md).

> **Scope:** Confirm a broad emission band near `~450 nm` at a dilute level (`1:80` start), with no overload. Defer quantitative dilution linearity until cuvette seating is fixed.

---

## 1. Goal

Acquire blank-subtracted emission from degassed commercial tonic water in a quartz cuvette, annotate the quinine band near `450 nm`, and after one sanity PASS collect a short usefulness series (3 technical + 3 reseated).

---

## 2. Method (locked)

| Parameter | Value |
| --- | ---: |
| Sample | Degassed commercial tonic; start **`~1:80`–`1:100`**, dilute further until unclipped (this mixer needed **`~1:450`** at `5 nm` slits) |
| Blank | Matched **DI/distilled water** in the **same** cuvette / orientation |
| Excitation (`$GM`) | `350.0 nm` |
| Emission (`$AL` / `$AH`) | `400–550 nm` |
| Slits (`$SX` / `$SM`) | `5.0 nm` |
| Scan speed (`$SS`) | `120 nm/min` |
| Step (`$SI`) | `2.0 nm` |
| Guide peak | `450 nm` (local max within ±`25 nm`) |

If the load clips (`999999` / `$PT 0107` / max \|I\| ≥ `900000`): dilute ~`3–5×` and restart (grocery tonic can still clip near `1:100` at `5 nm` slits). If the band is barely visible: concentrate once, then proceed.

---

## 3. Sample prep

1. Pour a small portion of commercial tonic into a loosely covered vessel and let it go flat (no CO₂ bubbles on cuvette walls).
2. Mark one clear face of the 4-window UV quartz cuvette so orientation is repeatable.
3. Prepare ≥ `~2.5 mL` of `1:80` (e.g. `0.10 mL` tonic + `7.90 mL` water, or scale to volumetricware on hand). Keep a matched water aliquot for the blank.

---

## 4. Matched solvent blank

Acquire a **new** water-in-cuvette blank at the same Ex, slits, speed, and step; Em must cover `400–550`. Seat the water-filled cuvette (marked face), door closed — freepath CSV shape stores the ON spectrum as `empty_on`:

```bash
uv run python scripts/run_freepath_serial.py \
  --port /dev/serial/by-id/<adapter> \
  --stage2-pass --compartment-closed --baud 9600 \
  --em-lo 400 --em-hi 550 --slit 5 \
  --log-dir logs/freepath
```

Pass the resulting `freepath-*.csv` as `--blank` on every tonic run. Do not reuse a blank taken at a different slit width or Em window. Prefer the same cuvette and marked orientation used for the tonic series.

---

## 5. Cuvette seating

1. Close the excitation shutter (`$ES 1`) and confirm readback before opening the compartment.
2. Empty, rinse if needed, and fill with the tonic dilution (≥ `~2 mL`). Wipe exterior faces; remove bubbles.
3. Seat with the marked face on the excitation axis. Close the door fully.
4. After each scan, verify source OFF / `$ES 1` before opening the door.

---

## 6. Sanity criteria (before the series)

One `--replicate-kind sanity` run must:

- Report acquisition `passed` with no overload / `999999` clipping (`clipped: false`)
- Show a local max near `450 nm` with **|Δ| ≤ 15 nm**
- Report a corrected peak intensity clearly above the blank floor

On failure, stop and diagnose (dilution, seat, fill height, bubbles, blank match) before collecting the series.

---

## 7. Usefulness series

Share one `--series-id` (e.g. wall-clock stamp) across all runs after sanity:

1. **Technical ×3** — cuvette undisturbed; `--replicate-kind technical`
2. **Reseat ×3** — between runs: source OFF → open door → lift and reseat (same orientation) → close → `--replicate-kind reseat`

Then:

```bash
uv run python scripts/summarize_tonic_water.py --series-id <stamp>
```

---

## 8. CLI usage

```bash
PORT=/dev/serial/by-id/<adapter>
BLANK=logs/freepath/freepath-<stamp>.csv
SERIES=$(date +%Y%m%d-%H%M%S)

# Sanity
uv run python scripts/run_tonic_water_serial.py \
  --port "$PORT" --stage2-pass --sample-loaded --baud 9600 \
  --blank "$BLANK" --dilution 1:80 \
  --replicate-kind sanity --series-id "$SERIES"

# Technical replicate (repeat ×3)
uv run python scripts/run_tonic_water_serial.py \
  --port "$PORT" --stage2-pass --sample-loaded --baud 9600 \
  --blank "$BLANK" --dilution 1:80 \
  --replicate-kind technical --series-id "$SERIES"

# Reseat replicate (repeat ×3 after reseating)
uv run python scripts/run_tonic_water_serial.py \
  --port "$PORT" --stage2-pass --sample-loaded --baud 9600 \
  --blank "$BLANK" --dilution 1:80 \
  --replicate-kind reseat --series-id "$SERIES"

# Offline dry-run (freepath_happy Em starts at 400 nm; short fixture window)
uv run python scripts/run_tonic_water_serial.py \
  --fixture-dir tests/fixtures/freepath_happy \
  --stage2-pass --sample-loaded \
  --blank /path/to/blank.csv \
  --guide 410 --half-window 15
```

Outputs land in `logs/tonic-water/`: raw serial log, JSON sidecar (settings, blank, peaks, dilution, clip flag, replicate tags), CSV (`wavelength_nm,sample_on,blank,corrected`), and annotated PNG.

---

## 9. Results (series `20261103-194005`)

Bench writeup, go/no-go verdict, aggregates, and overlay:

**[../assessment/tonic-water-baseline.md](../assessment/tonic-water-baseline.md)**

Summary: fluorescence **go**; gate peak ~`447 nm` (Δ ≈ `−3 nm`) at ~`1:450`; unclipped I ~`127k`; `1:1` / `1:2` / `~1:90` scouts clipped. Full Expt 1 dilution ladder remains deferred until Gate D seating is fixed.

---

## 10. Sources

1. PerkinElmer application note, *Determination of Quinine in Tonic Water Using Fluorescence Spectroscopy* — linked from [fluorescence-home-lab.md](fluorescence-home-lab.md).
2. Home-lab Expt 1 parameters (Ex `350 nm`, Em `400–550 nm`, `5 nm` slits) — [fluorescence-home-lab.md](fluorescence-home-lab.md).
3. DIY fixture context — [../assessment/water-raman-baseline.md](../assessment/water-raman-baseline.md).
