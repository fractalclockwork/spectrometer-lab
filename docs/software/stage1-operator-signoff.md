# Stage 1 — Operator Feature Sign-Off Checklist

**Status: OPEN — no operator sign-off recorded.**

Roadmap Stage 1 features are **incomplete until the operator signs each item** (or the stage as a whole). **[Stage 0](stage0-operator-signoff.md) (robust bootup / connection) must be PASS or explicitly waived before Stage 1 gate.** Offline pytest / fixture demos are development evidence only; they do **not** close these checkboxes.

| Field | Value |
| --- | --- |
| Stage | 1 — Operator console + provenance |
| Instrument | LS 55 · firmware `F1` · SN `79787` (when live) |
| Prerequisite | [Stage 0 sign-off](stage0-operator-signoff.md) — [x] PASS · [ ] Waived (notes): ________ |
| Related roadmap | [features-and-roadmap.md](features-and-roadmap.md) §§2, 5, 7–9 |
| Operator | ________________ |
| Sign-off date | ________________ |
| Mode exercised | [ ] Live serial · [ ] Offline fixture only · [ ] Both |

**How to use:** For each feature, run the acceptance check (offline and/or live as noted). Mark **PASS** only when you are satisfied on the bench. Record notes / defects in the Notes column or under §Defects. Stage 1 closes only when **Stage gate** at the bottom is signed.

---

## A. Library / service primitives

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| A1 | **Status snapshot** — `$ST`/`$ME`/`$AF` + optics readbacks; faults/warnings surfaced | After Connect/Refresh, synoptic or status shows Ex/Em/slits/`$ES`/`$ME`; mismatch or fault is obvious | Y | [ ] | [ ] | |
| A2 | **Apply Setup** — `$GM`/`$SX`/`$SM` (and optional `$FW`/`$PH`/`$PV`/`$CX`) with Xe OFF | Apply Setup moves optics; readbacks match staged setpoints within tolerance; shutter stays OFF | Y | [ ] | [ ] | |
| A3 | **Single Read scout** — `$RD` + dark option; `$ES 1` in `finally` | Scout at guide λ returns intensity; gauge useful for clip; Xe restored OFF after scout | Y | [ ] | [ ] | |
| A4 | **Staged Scan** — dark → sample stream; `$AB`; restore Xe + baseline | Live points appear; Abort stops run; Xe OFF and wavelengths/slits restored after run/abort | Y | [ ] | [ ] | |
| A5 | **GLP sidecar schema (§7)** — provenance, optics, path, source, sample, review hooks | Each persisted run has paired `.json` with §7 fields; CSV path recorded; raw-log digest when available | Y | [ ] | [ ] | |
| A6 | **Viewing / Data Calculator** — blank swap, wing residual, dual SNR, optional T/A | Recompute updates peak, Δλ, abs SNR, contrast SNR; blank mismatch badge fires when slits/Ex disagree | Y | [ ] | [ ] | |
| A7 | **ExtensionRegistry hooks** — `pre_acquire` / `post_acquire` / `emergency_stop` | Hooks exist on service; Abort path calls emergency stop; no Stage 4 plugins required yet | Y | [ ] | [ ] | |

---

## B. Web console — optical path & interlocks

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| B1 | **Top status / abort** — state, identity, Xe badge, clip, Abort/Xe OFF | Badges track connect/scan/fault; Abort + Force Xe OFF works under load; fixed on every tab | Y | [ ] | [ ] | |
| B2 | **Setpoint vs readback synoptic** — Src → Ex → Em → Det | Fixed chrome synoptic shows commanded vs verified Ex/Em/slits/`$ES`/`$ME` without reading JSON logs; mismatch warns | Y | [ ] | [ ] | |
| B3 | **Fault / overload cues** — `$PT 0107`, ADC clip ≥900k, `$ME`, busy | Clip/overrange is unmistakable during scout or scan | Y | [ ] | [ ] | |
| B4 | **Tabbed IA (Setup / Acquire / Results)** | Primary workspace is three tabs (WinLab Status/Setup · Scan · Viewing); no page scroll of Connect+Scan+Calculator together | Y | [ ] | [ ] | |

---

## C. Web console — measurement staging (under tabs)

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| C1 | **Setup — Connect & safe-idle** | Defers to **Stage 0**: Gate A + compartment; busy/boot honesty; discover; Connect forces `$ES 1`; idle_safe with Xe OFF; kill Xe after link loss | Y | [ ] | [ ] | Requires Stage 0 |
| C2 | **Setup — Method & optics** | Presets (freepath / water Raman / tonic / riboflavin / custom); duration preview; Apply Setup | Y | [ ] | [ ] | |
| C3 | **Setup / Results — Blank pairing** | Acquire matched blank from Setup; select/swap Blank CSV on Results; settings-match badge | partial | [ ] | [ ] | |
| C4 | **Acquire — Scout & readiness** | Sample ID / dilution on Setup; replicate kind + scout gauge `0`–`999999` on Acquire | Y | [ ] | [ ] | |
| C5 | **Acquire — Staged scan & replicates** | Run staged scan; dark optional; auto-switch to Results on complete; advance sanity → technical → reseat without losing method | partial | [ ] | [ ] | |
| C6 | **Optical path geometry tag** | Operator can record `right_angle_4w` / `transmission_2w_mirror` / `uv_fiber_probe` / `free_path` into run metadata | partial | [ ] | [ ] | |

---

## D. Web console — plot, review, provenance

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| D1 | **Live spectrum workbench (Acquire)** | Dark + sample traces update during scan on Acquire tab (WS and/or API fallback after return) | Y | [ ] | [ ] | |
| D2 | **Continuum residual display (Results)** | Residual ΔI visible with wing fit on Results; useful for weak bands on slope | Y | [ ] | [ ] | |
| D3 | **Interactive ROI windows** | Peak / noise / wing regions adjustable in Results calculator (controls → recompute) | partial | [ ] | [ ] | |
| D4 | **Run browser (Results)** | Historical runs under `logs/` filterable/selectable; load into review; blank swap applies | Y | [ ] | [ ] | |
| D5 | **Transaction / phase log drawer** | Collapsed-by-default log; Connect, phases, scout, scan, faults appear when expanded | Y | [ ] | [ ] | |
| D6 | **Artifacts on every staged run** | `.csv` + `.json` (+ `.png` when plotting available) written under dashboard/scans (or agreed path) | partial | [ ] | [ ] | |

---

## E. Offline / launch hygiene (dev evidence — not stage close)

| # | Check | PASS | Notes |
| --- | --- | :---: | --- |
| E1 | `uv run pytest` suite green on this checkout | [ ] | |
| E2 | `uv run python scripts/run_dashboard.py --fixture demo_session --gate-a-pass --compartment-closed` boots console | [ ] | |
| E3 | Fixture path: Connect → Setup → Scout → Scan completes without hang | [ ] | |

---

## Stage gate

Stage 1 is **PASS** only when the operator confirms the console is usable as the primary bench workflow for Status/Setup, Single Read scout, Scan with abort, blank-aware review, and run provenance—**on live hardware** unless explicitly waived.

- [ ] **Offline waived / complete** (fixture-only OK for software bring-up; live still required unless waived below)
- [ ] **Live serial PASS** on this DUT
- [ ] **Live waived** (reason): ________________________________

**Operator signature:** ________________________ **Date:** ________

**Stage 1 result:** [ ] PASS · [ ] FAIL · [ ] PARTIAL (list open IDs): ________

---

## Defects / follow-ups found during sign-off

| ID | Feature # | Severity | Description | Status |
| --- | --- | --- | --- | --- |
| | | | | open |

---

## Legend

- **Offline ok?** — Meaningful acceptance possible with `FakeTransport` / `demo_session` (Y), only partial (partial), or live-only (N).
- **PASS** — Operator judgment; leave unchecked until exercised.
- Incomplete UI/backend items stay **OPEN** on the roadmap until this document’s Stage gate is signed.
