# LS 55 Instrument Specifications (Manual vs. RS-232 vs. DUT)

October 28, 2026 | Reference specification and live configuration table

This table correlates the published specifications and system descriptions in the PerkinElmer LS 55 User's Guide (obtain locally per [../vendor/README.md](../vendor/README.md)) with the RS-232 command set ([serial-protocol.md](serial-protocol.md)) and live readbacks from **this bench DUT** (firmware **`F1`**).

- **Committed bring-up records:** [../assessment/bringup-report.md](../assessment/bringup-report.md) (derived from local captures `logs/identity/identity-20261028-212336.json` and `logs/identity_prolific/identity-20261028-220859.json`).
- **Known limitations and discrepancies:** [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md).

Refresh live identity fields at any time with:

```bash
python scripts/dump_instrument_identity.py \
  --port /dev/serial/by-id/<adapter> \
  --gate-a-pass --compartment-closed
```

---

## Citation Convention

- `pp. N` refers to printed page numbers in the local User's Guide PDF (`docs/vendor/PerkinElmer-LS55-Users-Guide.pdf`).
- `txt ~N` refers to approximate line numbers in the optional local text extract (`docs/vendor/LS55-Users-Guide.txt`).
- See [../vendor/README.md](../vendor/README.md) for how to obtain and place those files.

---

## 1. Identity and System State

| Property | Manual Specification | RS-232 Command / Field | DUT Observed | Notes |
| --- | --- | --- | --- | --- |
| Model identifier | LS 55 | `$ST` payload prefix (`pp. 153–154`, `txt ~4276–4288`) | `55` | |
| Firmware revision | Two-character code in `$ST` | `$ST` `<rev>` field | `F1` | Emitted as `55.F1,...` |
| Serial number | Instrument serial number | `$SN` (`p. 156`, `txt ~4371–4375`) | **`79787`** | Matches rear panel label |
| Mains frequency | 50 or 60 Hz (`p. 18`, `txt ~505`) | `$HZ` (`p. 155`, `txt ~4363–4367`) | **`60`** | Matches rear plate (`120 V, 60 Hz`) |
| NVM status | Non-volatile memory check | `$ME` → `0000` / `0108` / `0106` (`p. 152`, `txt ~4239–4244`) | **`0000`** | Healthy |
| Fitted accessories | 12 accessory presence flags | `$AF` (`p. 152`, `txt ~4224–4235`) | `0,0,1,1,0,0,0,0,0,0,0,0,0` | Excitation + emission polarizers fitted |
| Output pacing mode | Prompted (`DC1`) at power-on | `$RE` (`0` = free-running, `1` = prompted, `p. 153`) | **Prompted (`1`)** | Used by all repo harnesses |

### `$AF` Accessory Flag Order

In manual order (`p. 152`): (1) emission mirror, (2) plate reader, (3) **excitation polarizer**, (4) **emission polarizer**, (5) cell holder, (6) well plate reader, (7) stirrer, (8) temperature controller, (9) peristaltic pump, (10) autosampler, (11) fast filter accessory (FFA) excitation, (12) FFA emission.

On this bench unit, only flags 3 and 4 (**excitation and emission polarizers**) are set (`1`).

---

## 2. Optical Architecture

| Subsystem | Manual Specification | RS-232 Control / Readback | DUT Observed | Notes |
| --- | --- | --- | --- | --- |
| Measurement modes | Fluorescence, phosphorescence, chemi-/bioluminescence (`p. 17`, `txt ~456–458`) | `$PH` (`0` = fluor, `1` = phos, `2` = bio, `p. 145`) | `$PH` = **`0`** | Matches `$ST` mode flag `dc=0` |
| Excitation source | Pulsed Xe discharge lamp (~20 kW peak, <10 µs FWHM, `p. 17`, `txt ~460–461`) | `$ES` (`0` = ON, `1` = OFF, `p. 148`) | `$ES` = **`1`** (OFF after init) | Power-on default is `0` (ON) |
| Festoon trigger lamp | Auxiliary lamp near Xe tube (`p. 166`, `txt ~4638–4640`) | Not exposed over RS-232 | Not applicable | Service item only |
| Excitation monochromator | Monk-Gillieson, `200–800 nm` + zero order (`p. 17`, `txt ~469–471`) | `$GM` Ex `0` or `200.0–800.0` (`p. 149`) | `365.0 nm` (default) | |
| Emission monochromator | Specs (`p. 17`): `200–650 nm` (std S5 PMT) / `200–900 nm` (R928). Optical System (`p. 167`): `200–900 nm` + zero order | `$GM` Em `0` or `200.0–900.0` (`p. 149`) | `435.0 nm` (default) | Firmware allows `900.0 nm`; installed PMT variant is not readable over RS-232 |
| Sample detector | Gated PMT: modified S5 (~650 nm) or optional R928 (~900 nm) (`p. 17`, `txt ~463–465`) | `$PV` voltage; PMT variant not exposed | Unknown (requires visual check) | |
| Reference detector | Photodiode (`~900 nm`, `p. 17`, `txt ~467`) | Internal ratio path; `$CX` correction | Not exposed over RS-232 | |
| Excitation correction | Rhodamine quantum-counter table (`p. 167`, `txt ~4648–4651`) | `$CX` (`0`/`1`), `$CR` (`p. 142`, `txt ~3799–3806`) | `$CX` = **`1`** (enabled) | Power-on default `1`; no built-in emission correction |
| Synchronous scan | Constant wavelength (`Δλ`) or constant energy (`ΔE`) (`p. 17`, `txt ~476–477`) | `$MX` / `$MQ` (`pp. 139–140`) | `ms=0, mq=0` | |
| Signal digitization | 12-bit successive-approximation ADC with auto-ranging and dark subtraction (`p. 171`, `txt ~4782–4789`) | `$RD`, `$SC`, `$DT` (`0` = ASCII, `1` = binary) | Verified in Stages 2–3 | |

---

## 3. Controllable Parameter Ranges

| Parameter | Manual Range | RS-232 Command & Limits | DUT Power-On Default | Notes |
| --- | --- | --- | --- | --- |
| Excitation wavelength | `200–800 nm` + zero order | `$GM` Ex: `0` or `200.0–800.0 nm` (`0.1 nm` step) | `365.0 nm` | |
| Emission wavelength | `200–650 nm` (std) / `200–900 nm` (R928 / Optical System) | `$GM` Em: `0` or `200.0–900.0 nm` (`0.1 nm` step) | `435.0 nm` | |
| Excitation slit | Calibrated `2.5–15.0 nm` (`0.1 nm` step); `0` → `<2 nm` uncalibrated (`p. 167`) | `$SX` `2.5–15.0` (`p. 150`, `txt ~4150–4158`) | `10.0 nm` | |
| Emission slit | Calibrated `2.5–20.0 nm` (`0.1 nm` step); `0` → `<2 nm` uncalibrated | `$SM` `0–20.0` (`p. 150`, `txt ~4138–4146`) | `10.0 nm` | |
| Scan speed | `10–1500 nm/min` (`1 nm/min` step, `p. 18`, `txt ~489–490`) | `$SS` `±10` to `±1500` (`p. 133`, `txt ~3514–3519`) | `480 nm/min` | Flash block-averaging scales inversely with speed |
| Emission filter wheel | Specs (`p. 18`): `290, 350, 390, 430, 515 nm`, blank, 1% T, clear | `$FW` `1–8`: `290, 350, 390, 430, 530 nm`, blank, clear, 1% T (`p. 148`, `txt ~4060–4084`) | `7` (clear) | Specs list `515 nm` while `$FW` position 5 specifies `530 nm` |
| PMT voltage | Auto (coupled to Ex slit) or manual (`p. 153`) | `$PV` `0–999` or `-1` (auto); readback appends `A` in auto | **`775 A`** | |
| Phosphorescence delay | `0–9000 ms` (`p. 170`, `txt ~4760–4761`) | `$PD` / `$ST` delay (`0.01 ms` units) | `100` (`1.00 ms`) | |
| Phosphorescence gate | `0.01–500 ms` (`p. 170`, `txt ~4761–4762`) | `$PG` / `$ST` gate (`0.01 ms` units) | `100` (`1.00 ms`) | |
| Flashes per point / cycle | `1–10` flashes; min period `13 ms` @ 50 Hz (`p. 18`, `txt ~486–487`) | `$PF` / `$ST` flashcount and cycle time (`ms`) | Flashcount `1`, cycle `16 ms` | `$ST` flash field emits `\x01 1` (Class A quirk) |
| Filter response index | Coupled to scan speed by default | `$FR` / `$ST` `<response>` | `19` (joined as `480.019`) | |

---

## 4. Live Configuration Fingerprint (`$ST` and Status Queries)

Captured via `scripts/dump_instrument_identity.py`:

| Field / Query | RS-232 Source | DUT Value | Meaning |
| --- | --- | --- | --- |
| Raw `$ST` payload | `$ST` | `55.F1,0001,365.0,435.0,  480.019,10.0,10.0,  100,   100,\x01 1,   16` | Full status record (after leading DEL `0x7f`) |
| Mode flags (`0001`) | `$ST` `<ms><mq><dc><fl>` | `0001` | `ms=0` (monochromator scan mode), `mq=0` (synchronous mode off), `dc=0` (fluorescence data collection), `fl=1` (flash lamp active) |
| Wavelengths | `$ST` / `$GM` | `365.0 nm` (Ex), `435.0 nm` (Em) | Power-on defaults |
| Scan speed & response | `$ST` | `480 nm/min`, response index `19` | Emitted as `480.019` |
| Slit widths | `$ST` / `$SX` / `$SM` | `10.0 nm` (Ex), `10.0 nm` (Em) | Power-on defaults |
| PMT overload latch | `$PT` (`p. 152`) | `0000` | No latched `0107` PMT overload |
| Cell temperature | `$TP` (`p. 156`) | `0100` (*Accessory not fitted*) | Consistent with `$AF` temperature-controller bit `0` |

---

## 5. Electrical, Mechanical, and Optical Geometry

| Property | Manual Specification | DUT / Notes |
| --- | --- | --- |
| Mains supply | `100 / 120 / 220 / 230 V AC`, `50 / 60 Hz`, `150 VA` (`p. 18`) | Rear plate: **`120 V, 60 Hz, 150 VA`**, `2 A Slo Blo` fuse marking; `$HZ` = `60` |
| Instrument mass | `~49 kg` net (`~59 kg` packaged, `p. 25`) | Two-person lift required |
| Ambient operating range | `15–35 °C`, `≤75% RH` non-condensing (`p. 23`) | Leave ~200 mm clearance at left-side power switch |
| Standard cell holder | Part `L2250140`: `12.5 mm` square exterior cuvette, `10 mm` path, integral return mirrors (`pp. 38, 55`) | Gate D open; see [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md) §5 |
| Beam geometry in cuvette | Beam ~9 mm high; beam center **13.5 mm above inside base of cuvette in standard holder** (`pp. 47, 51`), ~2 mL min volume | Datum is inside the seated cell, not the bare compartment floor |

---

## 6. Published Performance Specifications (Unvalidated on DUT)

These factory specifications cannot be read from RS-232 status registers and require optical validation after Gate D is completed:

| Parameter | Published Specification (`pp. 17–18`) | Validation Method | Status on this bench unit |
| --- | --- | --- | --- |
| Wavelength accuracy | `±1.0 nm` | Excitation/emission calibration peaks (`$XC`, `$MC`) or reference standards | Not yet measured |
| Wavelength reproducibility | `±0.5 nm` | Repeated peak scans | Not yet measured |
| Sensitivity (Water Raman) | `500:1` RMS SNR (Ex `350 nm`, `10 nm` Ex/Em bandpass) | Distilled water scan in `L2250140` holder | Not yet measured |
