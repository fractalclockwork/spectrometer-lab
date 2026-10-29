# Known Issues and Device Limitations

October 28, 2026 | Consolidated reference for LS 55 unit `79787` (firmware `F1`)

This document tracks hardware constraints, firmware quirks, manual discrepancies, and open software/mechanical tasks following bring-up ([../assessment/bringup-report.md](../assessment/bringup-report.md)).

---

## 1. Current Verification State

| Area | Status | Notes |
| --- | --- | --- |
| RS-232 comms, motion, and empty-path scans (Stages 1–3) | **PASS** (2026-10-28) | Verified on both Parallax FTDI and Prolific USB–RS232 adapters |
| Gate D — Sample holder and cuvette seating | **Open** | Compartment contains an unverified square-bore block on a removable platform |
| Wavelength accuracy (`±1.0 nm`) and water Raman SNR (`500:1`) | **Unvalidated** | Requires Gate D holder and reference standards |
| Legacy FL WinLab PC software | **Not used** | Replaced by direct Python RS-232 control in [`ls55/`](../../ls55/) |

---

## 2. Serial Link Anomalies

Two distinct anomaly classes were identified during bring-up. Byte-level evidence and the host parser mitigation map live in [serial-link-glitch-taxonomy.md](serial-link-glitch-taxonomy.md).

- **Class A — Deterministic `0x01` in `$ST` flashcount:** Firmware `F1` emits an ASCII `SOH` (`0x01`) byte at offset 57 of every `$ST` status payload (`"\x01 1"`). [`ls55/protocol.py`](../../ls55/protocol.py) extracts the integer (`1`) cleanly.
- **Class B — Sporadic `0xb5` byte substitution:** Observed on the Parallax FTDI `#28030` + long cable path (~9.4 events per 100 transactions), where `0xb5` replaced an occasional ASCII `0`, comma, digit, or CR. Switching to the **Prolific USB–RS232 adapter + short cable** reduced Class B occurrences to **`0 / 90` transactions**.
- **Residual parser caveats:**
  1. `_coerce_status_code` in [`ls55/protocol.py`](../../ls55/protocol.py) coerces a high-bit byte inside a 4-byte status code to `'0'`. This is safe when the underlying code is `0000`, but could mask a corrupted non-zero error code if Class B recurs on a degraded cable.
  2. `$GM` wavelength readbacks do not yet have a numeric digit sanitizer if a mid-field byte is corrupted.

---

## 3. Manual and Documentation Discrepancies

Full specification cross-references are tabulated in [../reference/instrument-specs.md](../reference/instrument-specs.md).

| Topic | Discrepancy in User's Guide | Resolution on Unit `79787` |
| --- | --- | --- |
| **RS-232 DB25 pinout (p. 125)** | Port is labeled `DCE`, but the explicit pin table assigns Pin 2 = *Data from instrument* and Pin 3 = *Data to instrument* (opposite to standard DB25 DCE). | Wire per the explicit direction table: **DE9 Pin 3 (TX) ↔ DB25 Pin 3**, **DE9 Pin 2 (RX) ↔ DB25 Pin 2**, **DE9 Pin 5 ↔ DB25 Pin 7**. See [../assessment/bringup-report.md](../assessment/bringup-report.md) §2.2. |
| **Emission wavelength upper limit** | Specifications chapter lists `200–650 nm` (standard S5 PMT) and `200–900 nm` (optional R928 PMT); Optical System and `$GM` allow `0` or `200.0–900.0 nm`. | Firmware accepts moves and scans to `900.0 nm`, but installed PMT type (S5 vs. R928) is not readable over RS-232. |
| **Emission filter wheel position 5** | Specifications list cut-off filters `290, 350, 390, 430, 515 nm`; `$FW` command reference lists position 5 as **`530 nm`**. | Record both filter wheel index (`1–8`) and nominal cutoff in measurement metadata. |

---

## 4. Firmware and Non-Volatile Memory Behavior

- **Live `$ST` formatting shapes:** Firmware `F1` separates model and revision with a period (`55.F1,...`) and joins scan speed and filter response index with a period (`480.019` → speed `480 nm/min`, response `19`). Both are normal firmware conventions handled by `parse_status_payload`.
- **NVM status codes (`$ME`):** Unit `79787` returns `0000`. If `0108` (*NVM recovered from backup*) ever appears, preserve logs and re-verify wavelength/slit calibration before quantitative work. Code `0106` is a fatal NVM fault requiring service.
- **Excitation correction default (`$CX`):** Defaults to `1` (enabled) at power-on using the stored rhodamine correction curve. Scans return error `0111` if `$CX 1` is active without a valid table.

---

## 5. Hardware and Accessory Constraints

- **Sample holder (Gate D):** The standard single-position cell holder (`L2250140`) accepts a `12.5 mm` square exterior cuvette (`10 mm` optical path, ~2 mL minimum fill) and incorporates return mirrors that boost excitation and collection efficiency. The nominal **13.5 mm beam-center height** (~9 mm beam height) is measured from the inside base of a cuvette seated in the standard holder—not from the bare compartment floor. Any temporary fixture using the existing platform and square-bore block must be mechanically secured, verified for door clearance, and treated as non-equivalent to `L2250140` for sensitivity claims.
- **Fitted accessories (`$AF`):** Reports `0,0,1,1,0,0,0,0,0,0,0,0,0` — **excitation and emission polarizers** are fitted (`$PX` / `$PM`). No temperature controller (`$TP` returns `0100`), cell-holder sensor, fast filter accessory (FFA), or plate reader is installed.
- **Unexposed hardware parameters:** Xenon lamp hours and PMT detector variant (modified S5 vs. R928) have no RS-232 query commands.

---

## 6. Measurement and Analytical Limitations

Software features ([../software/features-and-roadmap.md](../software/features-and-roadmap.md)) must account for these instrument characteristics:

1. **No nanosecond fluorescence lifetime or photon counting:** The LS 55 integrates pulsed xenon flashes (<10 µs FWHM at 60 Hz) into a 12-bit auto-ranging ADC. Time-resolved measurements are limited to millisecond phosphorescence decays (`$DP`, minimum cycle 13 ms).
2. **Excitation-only internal spectral correction:** Internal ratioing (`$CX 1`) corrects excitation lamp/monochromator variation via the reference photodiode and rhodamine curve. **Emission spectra are uncorrected** for grating and PMT wavelength response; comparing band shapes or quantum yields across emission windows requires a host-side emission correction curve.
3. **Bandpass and dynamic range:** Calibrated slit widths are `2.5–15.0 nm` (Ex) and `2.5–20.0 nm` (Em). Strong scattering or concentrated fluorophores clip at `999999` (or set the `$PT` `0107` PMT overload latch) unless slits or PMT voltage (`$PV`) are adjusted.

---

## 7. Open TODOs for Next Stage

- [ ] **Gate D holder qualification:** Measure the existing accessory platform and square-bore block (bore depth, aperture height, mounting threads), secure cuvette seating, and verify full door closure with a 4-window UV cuvette.
- [ ] **Scan abort verification:** Exercise `$AB` during an active scan and confirm `0099` completion handling in [`ls55/transactions.py`](../../ls55/transactions.py).
- [ ] **`$GM` readback sanitizer:** Add optional Class B single-byte corruption detection/retry for `$GM` wavelength readbacks in [`ls55/protocol.py`](../../ls55/protocol.py).
- [ ] **Oscilloscope isolation of Class B (`0xb5`):** If the Parallax adapter or long cable is reused, capture DB25 pin 2 on the MSO7104B simultaneously with `ttyUSB` to isolate cable vs. USB–UART bridge framing.
- [ ] **Baseline water Raman check:** Once Gate D is closed, run the standard water Raman scan (Ex `350 nm`, `10 nm` bandpass) to establish a baseline SNR and wavelength peak log.
