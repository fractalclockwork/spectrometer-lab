# LS 55 RS-232 Serial Protocol Reference

October 28, 2026 | Framing, transaction pacing, and command reference

Primary authority: PerkinElmer LS 55 User's Guide, release C, March 2007, printed pp. 125–161 (obtain locally per [../vendor/README.md](../vendor/README.md)). For DUT-specific parameter limits and readbacks, see [instrument-specs.md](instrument-specs.md). For serial anomaly analysis, see [../issues/serial-link-glitch-taxonomy.md](../issues/serial-link-glitch-taxonomy.md).

---

## 1. Serial Framing and Flow Control

Verified against the User's Guide (pp. 125–126) and oscilloscope measurements on this bench unit:

- **Framing:** Fixed **9600 baud, 8 data bits, no parity, 1 stop bit (8N1)**.
- **Command format:** Commands start with `$`, followed by a two-letter uppercase mnemonic, an optional space, and comma-separated arguments (e.g., `b"$GM 350.0,450.0\r"`). Maximum length is 128 characters including the terminator.
- **Command terminator:** Single **CR** (`0x0d`) or single **LF** (`0x0a`). This repository uses a single **CR** (`\r`).
- **Prompted output mode (power-on default):** After receiving a command, the instrument holds each response record until the host sends **DC1** (`0x11`, Ctrl-Q). **DC3** (`0x13`, Ctrl-S) pauses transmission during free-running mode.
- **Host serial driver configuration:** Disable host software flow control (`xonxoff=False`) so the OS driver does not consume `DC1`/`DC3` bytes. Disable hardware handshaking (`rtscts=False`, `dsrdtr=False`) when using a 3-wire (`TX`, `RX`, `GND`) cable.
- **Response records:** Every ASCII record ends with **CR+LF** (`\r\n`).
  - **Status/error code records** consist of 4 ASCII digits followed by `\r\n` (e.g., `b"0000\r\n"`).
  - **Data records** begin with a leading **DEL** byte (`0x7f`) followed by the ASCII payload and `\r\n` (e.g., `b"\x7f1\r\n"`). Log raw bytes before stripping `0x7f`.
- **Transaction envelope:**
  - *Action-only commands* (e.g., `$ES 1`, `$SX 5.0`) return a single 4-digit completion code record (`0000` on success).
  - *Data-returning commands* (e.g., `$ST`, `$ES`, `$GM`, `$RD 1`, `$SC 1`) return an **initial 4-digit code** (`0000`), one or more **DEL-prefixed data records**, and a **final 4-digit completion code** (`0000`). An initial `0000` only acknowledges command receipt; the transaction is not complete until the final code arrives.
- **Command serialization:** Issue one command at a time and wait for its final completion code. Sending a new command while an operation is active returns `0110` (*Busy*).

---

## 2. Core Commands

Parameterless queries read back the current setting unless noted otherwise:

| Command | Arguments | Description |
| --- | --- | --- |
| `$ST` | *(none)* | Read full instrument status record (`55.<rev>,<modes>,<ex>,<em>,...`). |
| `$ES` | `0` (ON), `1` (OFF), or *(none)* | Set or query excitation shutter state. **Note polarity: `0` = source ON, `1` = source OFF.** Power-on default is `0` (ON). |
| `$ME` | *(none)* | Query non-volatile memory status (`0000` OK, `0108` recovered from backup, `0106` fatal fault). |
| `$AF` | *(none)* | Query 12 fitted-accessory flags (`0` or `1`, comma-separated). |
| `$SN` | *(none)* | Query instrument serial number (see [instrument-specs.md](instrument-specs.md) `$SN` DUT row). |
| `$HZ` | *(none)* | Query mains frequency (`50` or `60` Hz). |
| `$GM` | `<ex>,<em_nm>` or *(none)* | Move monochromators (`nm`) or read current wavelengths. |
| `$SX` / `$SM` | `<slit_nm>` or *(none)* | Set or read excitation (`2.5–15.0 nm`) / emission (`0–20.0 nm`) slit bandwidths. |
| `$FW` | `1–8` or *(none)* | Set or read emission filter wheel position (`7` = clear). |
| `$PH` | `0` (fluor), `1` (phos), `2` (bio), or *(none)* | Set or read data collection mode. |
| `$CX` | `0` (off), `1` (on), or *(none)* | Enable, disable, or query excitation rhodamine correction (power-on default `1`). |
| `$PV` | `0–999`, `-1` (auto), or *(none)* | Set or query PMT voltage (readback appends `A` in automatic mode). |
| `$PT` | *(none)* | Query and clear latched PMT overload (`0107`) since power-on or prior `$PT`. |
| `$TP` | *(none)* | Query cell temperature (`0100` if temperature sensor accessory is not fitted). |
| `$DT` | `0` (ASCII) or `1` (binary) | Select data transmission format for `$RD`, `$SC`, and `$TD`. |
| `$RD` | `<integration_s>` | Acquire a single-point reading at current wavelengths. |
| `$MX` / `$AL` / `$AH` / `$SI` / `$SS` | Scan setup parameters | Configure scan monochromator (`$MX 1` = Em), low/high limits (`$AL`/`$AH`), step interval (`$SI`), and speed (`$SS`). |
| `$SC` | `1` | Execute configured wavelength scan. Returns scan header record, paired intensity records, `-9999` end sentinel, and final status code. |
| `$AB` | *(none)* | Abort an active scan or motion command (aborted command terminates with `0099`). |
| `$RE` | `0` (free-running) or `1` (prompted) | Switch output pacing mode. |

**Calibration and service commands (`$CR`, `$MC`, `$XC`, `$MS`, `$XS`):** These commands initiate multi-step calibration dialogues (using codes `1000`/`1001`/`1002`) and overwrite stored calibration tables. Do not invoke them during routine operation or automated tests.

---

## 3. Status and Error Codes

| Code | Meaning | Recommended Host Action |
| --- | --- | --- |
| `0000` | No error | Continue (for data commands, keep prompting with DC1 until the final `0000`). |
| `0002` | Unrecognized command or invalid state | Check command syntax and current instrument mode. |
| `0022` | UART framing, parity, or overrun error | Inspect serial cable, adapter, and baud rate. |
| `0099` | Command aborted | Normal completion code after `$AB`. |
| `0100` | Requested accessory not fitted | Expected on `$TP` when no temperature controller is installed. |
| `0106` | Fatal non-volatile memory fault | Abort operation; hardware service required. |
| `0107` | PMT over-range warning | Signal saturated; narrow slits (`$SX`/`$SM`), reduce `$PV`, or dilute sample. |
| `0108` | NVM recovered from backup | Log warning; verify wavelength and slit calibration before quantitative use. |
| `0110` | Instrument busy | Wait for the active command to finish before sending the next command. |
| `0111` | Invalid parameter or missing correction table | Check parameter bounds or `$CX` excitation correction table state. |
| `0112` | Monochromator stepper or fast-filter sync fault | Stop motion commands and inspect mechanics. |

---

## 4. Implementation in `ls55/`

- [`ls55/transport.py`](../../ls55/transport.py) — `SerialTransport` (pySerial 9600 8N1 wrapper with raw TX/RX hex logging) and offline `FixtureTransport`.
- [`ls55/transactions.py`](../../ls55/transactions.py) — Prompted `DC1` transaction state machine (`run_prompted_command`) and CRLF framing.
- [`ls55/protocol.py`](../../ls55/protocol.py) — `Record.parse`, `$ST` payload parser (`parse_status_payload`), `$AF` decoder, and Class A/B glitch sanitizers.
- [`ls55/scan.py`](../../ls55/scan.py) — `$SC 1` scan header and `-9999`-terminated intensity array parser.
