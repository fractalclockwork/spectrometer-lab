# spectrometer-lab

Python RS-232 control and acquisition tools for a PerkinElmer **LS 55** fluorescence spectrometer (this bench unit, firmware **F1**).

## Status

- **Completed:** Hardware bring-up and RS-232 verification (Stages 1–3 **PASS** on 2026-10-28). Serial framing, monochromator/slit positioning, excitation shutter control, and empty-compartment emission scans are verified.
- **Open:** Gate D sample holder installation and optical performance validation (wavelength accuracy, water Raman SNR). See [Known Issues and Limitations](docs/issues/known-issues-and-limitations.md).
- **Next stage:** Software feature development ([Software Features and Roadmap](docs/software/features-and-roadmap.md)).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Quick Connect

| Parameter | Setting |
| --- | --- |
| Serial framing | **9600 baud, 8N1** (fixed in firmware) |
| Command terminator | Single **CR** (`\r`) |
| Output pacing | Prompted by default (`0x11` DC1 per record); host XON/XOFF and RTS/CTS disabled |
| Preferred adapter | Prolific USB–RS232 + short DE9–DB25 cable (`9:3↔25:3, 9:2↔25:2, 9:5↔25:7`) |
| Linux device path | `/dev/serial/by-id/...` (close competing serial programs before running scripts) |

Full protocol specification: [docs/reference/serial-protocol.md](docs/reference/serial-protocol.md).

### Common Commands

```bash
# Read-only instrument identity and configuration dump
python scripts/dump_instrument_identity.py \
  --port /dev/serial/by-id/<your-adapter> \
  --gate-a-pass --compartment-closed

# Empty-compartment emission scan (dark + source ON)
python scripts/run_freepath_serial.py \
  --port /dev/serial/by-id/<your-adapter> \
  --stage2-pass --compartment-closed --baud 9600

# Offline serial-glitch corpus analyzer
python scripts/analyze_serial_glitches.py
```

## Repository Layout

| Path | Description |
| --- | --- |
| [`ls55/`](ls55/) | Core library: serial transport, prompted transactions, record parsers, scan helpers |
| [`scripts/`](scripts/) | CLI tools for identity dumps, Stage 1–3 verification, serial probing, and log analysis |
| [`tests/`](tests/) | Offline unit tests and recorded protocol fixtures |
| `logs/` | Local bench run logs, JSON summaries, CSVs, and plots (gitignored) |
| [`docs/`](docs/) | Project documentation and vendor manual |

## Documentation

| Category | Document | Description |
| --- | --- | --- |
| **Reference** | [docs/reference/serial-protocol.md](docs/reference/serial-protocol.md) | RS-232 framing, prompted DC1 flow, command set, and status codes |
| **Reference** | [docs/reference/instrument-specs.md](docs/reference/instrument-specs.md) | Published specifications correlated with RS-232 commands and this bench DUT’s readbacks |
| **Issues** | [docs/issues/known-issues-and-limitations.md](docs/issues/known-issues-and-limitations.md) | Hardware, firmware, and software limitations plus open TODOs for feature work |
| **Issues** | [docs/issues/serial-link-glitch-taxonomy.md](docs/issues/serial-link-glitch-taxonomy.md) | Root-cause analysis of Class A (`0x01`) and Class B (`0xb5`) serial anomalies |
| **Software** | [docs/software/features-and-roadmap.md](docs/software/features-and-roadmap.md) | Post–bring-up software architecture, spectral corrections, and build order |
| **Experiments** | [docs/experiments/fluorescence-home-lab.md](docs/experiments/fluorescence-home-lab.md) | Five baseline fluorescence experiments (requires Gate D sample holder) |
| **Assessment** | [docs/assessment/bringup-report.md](docs/assessment/bringup-report.md) | Completed bring-up report: wiring, adapter comparison, and Stage 1–3 bench records |
| **Vendor** | [docs/vendor/README.md](docs/vendor/README.md) | How to obtain the PerkinElmer LS 55 User's Guide (part 09934436) and place it locally |
# spectrometer-lab
