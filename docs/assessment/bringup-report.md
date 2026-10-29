# LS 55 Bring-Up and Assessment Report

October 28, 2026 | Completed hardware and RS-232 verification for unit `79787` (firmware `F1`)

This report archives the initial hardware inspection, RS-232 cable pinout verification, and Stage 1–3 bench results. For day-to-day connection settings and protocol reference, see [../../README.md](../../README.md) and [../reference/serial-protocol.md](../reference/serial-protocol.md). For remaining hardware and software limitations, see [../issues/known-issues-and-limitations.md](../issues/known-issues-and-limitations.md).

---

## 1. Summary and Gate Status

Bring-up was executed in four gated stages so that serial communications, monochromator motion, and detector readout were verified with an empty, closed sample compartment before introducing liquids or custom fixtures.

| Gate / Stage | Scope | Status | Evidence Summary |
| --- | --- | --- | --- |
| **Gate A** | Pre-power electrical, mechanical, and shipping-clamp inspection | **PASS** (2026-10-28) | Rear plate verified (`120 V, 60 Hz, 150 VA`); shipping clamps removed; MPU/motor startup normal |
| **Stage 1 (Gate B)** | Prompted RS-232 link, `$ST` status, shutter OFF (`$ES 1`), NVM & accessory check | **PASS** (2026-10-28) | Model `55`, rev `F1`, serial `79787`, `$ME` `0000`, Ex/Em polarizers fitted |
| **Stage 2 (Gate C)** | Bounded wavelength/slit motion (`$GM`, `$SX`, `$SM`) and single-point `$RD 1` | **PASS** (2026-10-28) | Moves to `350/450 nm` and `5.0 nm` slits verified by readback; baseline restored |
| **Stage 3** | Empty-compartment emission scans (dark `$ES 1` vs. source ON `$ES 0`) | **PASS** (2026-10-28) | 400–550 nm and 200–900 nm scans completed; dark floor `\|I\| <= 1`; Rayleigh peaks observed |
| **Gate D** | Secure sample holder, cuvette seating, and optical alignment | **Open** | Loose square-bore block on accessory platform is unverified; see [Known Issues](../issues/known-issues-and-limitations.md) |

**Scope of verification:** Stages 1–3 confirm RS-232 framing, stepper positioning, shutter actuation, and PMT/ADC readout. They do not establish wavelength calibration accuracy (`±1.0 nm`) or water Raman sensitivity (`500:1` RMS), which require a verified cell holder (Gate D) and reference samples.

---

## 2. Hardware Inspection and RS-232 Wiring

### 2.1 Instrument Inspection (Gate A)

- **Rear panel ratings:** Model `LS 55`, serial `79787`, mains rating `120 V, 60 Hz, 150 VA`, fuse marking `2 A Slo Blo`.
- **Rear connectors:** Host control uses the 25-pin female **RS232C Controller** port. The adjacent 15-pin **Autosampler** port and 8-terminal analog/remote-start block are left disconnected.
- **Power-up behavior:** The instrument initializes in ~60 seconds with normal MPU indicator and stepper homing sequences. The excitation shutter defaults to **ON (`$ES` = 0)** at power-on; software must explicitly set `$ES 1` and verify readback before opening the sample compartment.
- **Sample compartment:** Contains side mounting supports, rear optical ports, a removable accessory platform, and an unfastened machined square-bore metal block. Neither a complete factory single-cell holder (`L2250140`, which includes return mirrors) nor a positive cuvette seat is confirmed.

### 2.2 Working DE9-to-DB25 Pinout

 oscilloscope bit-timing on DB25 pin 2 confirmed **9600 baud, 8N1** (`~104 µs/bit`, negative idle mark). The verified working pinout between a standard PC/USB-RS232 male DE9 DTE port and the LS 55 female DB25 port is:

| Host DE9 (DTE) | LS 55 DB25 | Signal Direction | Notes |
| --- | --- | --- | --- |
| **Pin 3 (TXD)** | **Pin 3** | Host to LS 55 | Data to instrument |
| **Pin 2 (RXD)** | **Pin 2** | LS 55 to Host | Data from instrument |
| **Pin 5 (GND)** | **Pin 7** | Signal ground | Do not substitute chassis ground (DB25 pin 1) |

**Manual p. 125 DCE discrepancy:** The User's Guide (p. 125) labels the DB25 port `DCE`, yet its explicit pin table assigns Pin 2 = *Data from instrument* and Pin 3 = *Data to instrument*—the opposite of a conventional DB25 DCE port. An initial bench test using a conventional straight DE9-to-DB25 modem cable (`DE9 3 -> DB25 2`, `DE9 2 -> DB25 3`) produced zero RX bytes. Wiring to the explicit pin-direction table above (`3<->3`, `2<->2`, `5<->7`) resolved communications.

### 2.3 USB–RS232 Adapter Comparison

Two USB–RS232 adapters were evaluated at 9600 8N1:

1. **Parallax `#28030` (FTDI, `/dev/serial/by-id/usb-Parallax_Inc_USBto232_REV_C_DN028C74-if00-port0`) + long gray cable:** Passed Stages 1–3 and identity dumps, but exhibited sporadic **Class B (`0xb5`)** single-byte RX corruptions (~9.4 events per 100 transactions in the baseline identity logs).
2. **Prolific USB-Serial Controller (`/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller-if00-port0`) + short cable:** Recorded **0 Class B events across 90 transactions** (5 identity dumps + 1 Stage 1 run). This is the preferred hardware path.

Both adapters see **Class A (`0x01`)** at byte offset 57 of every `$ST` response, confirming that Class A is a deterministic firmware `F1` formatting quirk rather than link noise. Full analysis: [../issues/serial-link-glitch-taxonomy.md](../issues/serial-link-glitch-taxonomy.md).

---

## 3. Stage 1–3 Bench Results

### 3.1 Stage 1 — Power-On and Serial System Check (Gate B)

- **Runs:** `logs/stage1/stage1-20261028-153747.json` (Parallax FTDI) and `logs/stage1_prolific/stage1-20261028-220916.json` (Prolific).
- **Result:** **PASS** on both adapters.

| Check / Command | Observed Response | Assessment |
| --- | --- | --- |
| `$ST` (status) | `55.F1,0001,365.0,435.0,  480.019,10.0,10.0,  100,   100,\x01 1,   16` | Model `55`, firmware `F1`, modes `0001`, Ex `365.0 nm`, Em `435.0 nm`, speed `480 nm/min`, response code `19`, slits `10.0 nm`, gate/delay `1.00 ms`, flashcount `1` (with Class A `0x01`), cycle `16 ms` |
| `$ES 1` -> `$ES` | `0000` -> `1` (`0000`) | Excitation shutter closed (source OFF confirmed) |
| `$ME` (NVM status) | `0000` | Non-volatile memory healthy (no `0108` backup recovery or `0106` fault) |
| `$AF` (accessories) | `0,0,1,1,0,0,0,0,0,0,0,0,0` | Excitation and emission polarizers fitted; no temperature controller or Sipper/FKA |
| Optional readbacks | `$GM` `365.0,435.0`; `$SX` `10.0`; `$SM` `10.0`; `$FW` `7` (clear); `$PH` `0` (fluorescence) | Clean on Prolific (`$PH` saw a single Class B `0xb5` byte on the earlier Parallax run) |

Correlated identity fields from `scripts/dump_instrument_identity.py` (`$SN` = `79787`, `$HZ` = `60`, `$PV` = `775 A`, `$CX` = `1`, `$PT` = `0000`, `$TP` = `0100`) are tabulated in [../reference/instrument-specs.md](../reference/instrument-specs.md).

### 3.2 Stage 2 — Bounded Motion and Data Transport (Gate C)

- **Run:** `logs/stage2/stage2-20261028-155239.json` (2026-10-28, source OFF).
- **Result:** **PASS** (0 errors, 0 warnings).

| Step | Command | Observed Readback / Payload | Status Code |
| --- | --- | --- | --- |
| 1. Confirm shutter OFF | `$ES` | `1` (source OFF) | `0000` |
| 2. Baseline readback | `$GM`, `$SX`, `$SM` | `350.0,450.0` nm; Ex slit `10.0` nm; Em slit `10.0` nm | `0000` |
| 3. Wavelength move | `$GM 350.0,450.0` -> `$GM` | `350.0,450.0` nm (within `±0.15 nm` tolerance) | `0000` |
| 4. Excitation slit move | `$SX 5.0` -> `$SX` | ` 5.0` nm | `0000` |
| 5. Emission slit move | `$SM 5.0` -> `$SM` | ` 5.0` nm | `0000` |
| 6. ASCII single-point read | `$DT 0` -> `$RD 1` | `350.0,450.0,******,        0` (dark intensity `0`) | `0000` |
| 7. Restore baseline | `$GM 350.0,450.0`, `$SX 10.0`, `$SM 10.0` | Baseline restored (`restored: true`) | `0000` |

### 3.3 Stage 3 — Empty-Compartment Emission Scans

Two back-to-back dark (`$ES 1`) and source-ON (`$ES 0`) emission scan pairs were executed with the sample compartment empty and closed (`$DT 0`, `$MX 1`, Ex `350.0 nm`, step `2.0 nm`, speed `120 nm/min`, slits `5.0 nm`):

| Run Artifact | Emission Range | Points | Dark (`$ES 1`) Intensity | Source ON (`$ES 0`) Intensity | Post-Scan State |
| --- | --- | --- | --- | --- | --- |
| `freepath-20261028-161945.json` | `400.0–550.0 nm` | 76 | `0` to `-1` (`max \|I\| = 1`) | `3624` to `6092` (stray light floor; no saturation) | `$ES` = `1`, baseline restored (`PASS`) |
| `freepath-20261028-204514.json` | `200.0–900.0 nm` | 351 | `0` to `1` (`max \|I\| = 1`) | Clips at `999999` across `346–354 nm` (1st-order Rayleigh at Ex `350 nm`) and `696–706 nm` (2nd-order diffraction); decays to `68` at `900 nm` | `$ES` = `1`, baseline restored (`PASS`) |

Both runs confirmed intact multi-record `$SC 1` scan headers (`55.F1,1001,350.0,...`), `-9999` end-of-scan sentinel padding, dark-current subtraction, and optical path continuity from the xenon flash lamp through both monochromators to the PMT.

---

## 4. Re-Running Verification Harnesses

All bring-up harnesses support offline fixture execution (`pytest`) as well as live serial execution:

```bash
# Offline test suite and fixture dry-runs
pytest -q
python scripts/run_stage1_serial.py --fixture-dir tests/fixtures/happy_path --gate-a-pass
python scripts/run_stage2_serial.py --fixture-dir tests/fixtures/stage2_happy --stage1-pass
python scripts/run_freepath_serial.py --fixture-dir tests/fixtures/freepath_happy --stage2-pass --compartment-closed

# Live bench execution (close competing serial programs first)
python scripts/run_stage1_serial.py --port /dev/serial/by-id/<adapter> --gate-a-pass --baud 9600
python scripts/run_stage2_serial.py --port /dev/serial/by-id/<adapter> --stage1-pass --baud 9600
python scripts/run_freepath_serial.py --port /dev/serial/by-id/<adapter> --stage2-pass --compartment-closed --baud 9600
```

## Sources

1. PerkinElmer LS 55 User's Guide, part 09934436, release C, March 2007 — obtain locally per [../vendor/README.md](../vendor/README.md).
2. Protocol and command reference — [../reference/serial-protocol.md](../reference/serial-protocol.md).
3. Correlated DUT specifications — [../reference/instrument-specs.md](../reference/instrument-specs.md).
4. Serial anomaly taxonomy — [../issues/serial-link-glitch-taxonomy.md](../issues/serial-link-glitch-taxonomy.md).
