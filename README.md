# spectrometer-lab

Python RS-232 control and acquisition toolkit for a PerkinElmer LS 55 fluorescence spectrometer (this bench unit, firmware **F1**).

## Status

- **Completed:** Hardware bring-up and RS-232 verification (Stages 1–3 **PASS** on 2026-10-28). Serial framing, monochromator/slit positioning, excitation shutter control, and empty-compartment emission scans are verified. DIY water Raman baseline recorded (peak ~395 nm, SNR ~123 on this fixture — not factory `500:1`).
- **Open:** Gate D sample holder seating/security. DIY tonic-water usefulness gate recorded (peak ~447 nm at ~`1:450` on this mixer — clipped until well diluted). See [Tonic Water Baseline](docs/assessment/tonic-water-baseline.md), [Water Raman Baseline](docs/assessment/water-raman-baseline.md), and [Known Issues](docs/issues/known-issues-and-limitations.md).
- **Next stage:** **Stage 0** — robust bootup / connection handling ([sign-off](docs/software/stage0-operator-signoff.md)), then Stage 1 operator console ([roadmap](docs/software/features-and-roadmap.md); [Stage 1 sign-off](docs/software/stage1-operator-signoff.md)). Launch locally with `uv run python scripts/run_dashboard.py` → http://127.0.0.1:8055/ .

## Installation

Uses [uv](https://docs.astral.sh/uv/) for the virtualenv and lockfile (`uv.lock`).

```bash
# Install uv if needed: https://docs.astral.sh/uv/getting-started/installation/
uv sync --all-groups
uv run pytest -q
```

Run tools with `uv run …` (or `source .venv/bin/activate` after sync). Analysis notebook:

```bash
uv run jupyter notebook notebooks/water-raman-tonic-water-analysis.ipynb
# or rebuild outputs:
uv run jupyter nbconvert --to notebook --execute \
  notebooks/water-raman-tonic-water-analysis.ipynb --inplace
```

## Quick Connect

| Parameter | Setting |
| --- | --- |
| Serial framing | **9600 baud, 8N1** (fixed in firmware) |
| Command terminator | Single **CR** (`\r`) |
| Output pacing | Prompted by default (`0x11` DC1 per record); host XON/XOFF and RTS/CTS disabled |
| Preferred adapter | Prolific USB–RS232 + short DE9–DB25 cable (`9:3↔25:3, 9:2↔25:2, 9:5↔25:7`) |
| Linux device path | `/dev/serial/by-id/...` (close competing serial programs before running scripts) |
| Resting state | **Xe / excitation shutter OFF** (`$ES 1`) — firmware powers on with source ON; host forces OFF when idle to save lamp life and cut noise |

Full protocol specification: [docs/reference/serial-protocol.md](docs/reference/serial-protocol.md).

### Common Commands

```bash
# Kill Xe / excitation shutter now ($ES 1 + verify; auto-finds the adapter)
uv run python scripts/kill_xe.py
# or: --port /dev/serial/by-id/<your-adapter>

# Discover / safe-idle: wait through boot, refuse if busy, force Xe OFF
uv run python scripts/discover_device.py --gate-a-pass
# or: --port /dev/serial/by-id/<your-adapter> --gate-a-pass

# Read-only instrument identity and configuration dump
uv run python scripts/dump_instrument_identity.py \
  --port /dev/serial/by-id/<your-adapter> \
  --gate-a-pass --compartment-closed

# Empty-compartment emission scan (dark + source ON)
uv run python scripts/run_freepath_serial.py \
  --port /dev/serial/by-id/<your-adapter> \
  --stage2-pass --compartment-closed --baud 9600

# Offline serial-glitch corpus analyzer
uv run python scripts/analyze_serial_glitches.py

# Operator web console (status, staging, live scan, review)
uv run python scripts/run_dashboard.py
# Offline DUT demo (fixture power-on → safe idle):
uv run python scripts/run_dashboard.py --fixture demo_session --gate-a-pass --compartment-closed
# open http://127.0.0.1:8055/?fixture=demo_session
```

## Repository Layout

| Path | Description |
| --- | --- |
| [`ls55/`](ls55/) | Core library: serial transport, prompted transactions, record parsers, scan helpers |
| [`scripts/`](scripts/) | CLI tools for identity dumps, Stage 1–3 verification, serial probing, and log analysis |
| [`tests/`](tests/) | Offline unit tests and recorded protocol fixtures |
| [`notebooks/`](notebooks/) | Analysis notebooks (water Raman / tonic-water metrology report) |
| `logs/` | Local bench run logs, JSON summaries, CSVs, and plots (gitignored) |
| [`docs/`](docs/) | Project documentation and vendor manual |
| [`pyproject.toml`](pyproject.toml) / [`uv.lock`](uv.lock) | Project metadata and locked dependencies (uv) |

## Documentation

| Category | Document | Description |
| --- | --- | --- |
| **Reference** | [docs/reference/serial-protocol.md](docs/reference/serial-protocol.md) | RS-232 framing, prompted DC1 flow, command set, and status codes |
| **Reference** | [docs/reference/instrument-specs.md](docs/reference/instrument-specs.md) | Published specifications correlated with RS-232 commands and this bench DUT’s readbacks |
| **Issues** | [docs/issues/known-issues-and-limitations.md](docs/issues/known-issues-and-limitations.md) | Hardware, firmware, and software limitations plus open TODOs for feature work |
| **Issues** | [docs/issues/serial-link-glitch-taxonomy.md](docs/issues/serial-link-glitch-taxonomy.md) | Root-cause analysis of Class A (`0x01`) and Class B (`0xb5`) serial anomalies |
| **Software** | [docs/software/features-and-roadmap.md](docs/software/features-and-roadmap.md) | Post–bring-up software architecture, spectral corrections, and build order |
| **Software** | [docs/software/stage0-operator-signoff.md](docs/software/stage0-operator-signoff.md) | Stage 0 — robust bootup/connection; prerequisite for Stage 1 |
| **Software** | [docs/software/stage1-operator-signoff.md](docs/software/stage1-operator-signoff.md) | Stage 1 feature checklist — incomplete until operator sign-off |
| **Experiments** | [docs/experiments/fluorescence-home-lab.md](docs/experiments/fluorescence-home-lab.md) | Five baseline fluorescence experiments (requires Gate D sample holder) |
| **Experiments** | [docs/experiments/water-raman.md](docs/experiments/water-raman.md) | Distilled-water Raman wavelength/SNR baseline in a quartz cuvette (Ex 350 nm, 10 nm slits) |
| **Experiments** | [docs/experiments/tonic-water.md](docs/experiments/tonic-water.md) | Tonic-water quinine emission usefulness gate (Ex 350 nm, 5 nm slits, Em 400–550 nm) |
| **Assessment** | [docs/assessment/water-raman-baseline.md](docs/assessment/water-raman-baseline.md) | Distilled-water Raman DIY-fixture baseline: go/no-go, peak/SNR, continuum-residual figures |
| **Assessment** | [docs/assessment/tonic-water-baseline.md](docs/assessment/tonic-water-baseline.md) | Tonic-water DIY-fixture usefulness gate: go/no-go near 450 nm, ~1:450 unclipped series |
| **Assessment** | [docs/assessment/measured-vs-specs.md](docs/assessment/measured-vs-specs.md) | DIY measured vs published specs: wavelength, SNR, clip, shutter, timing |
| **Assessment** | [docs/assessment/bringup-report.md](docs/assessment/bringup-report.md) | Completed bring-up report: wiring, adapter comparison, and Stage 1–3 bench records |
| **Assessment** | [docs/assessment/nvm-status-and-impact.md](docs/assessment/nvm-status-and-impact.md) | NVM contents, `$ME` health on this DUT, and impact on intensity/wavelength/slit operation |
| **Assessment** | [docs/assessment/ls55-uv-fiber-assessment.md](docs/assessment/ls55-uv-fiber-assessment.md) | Low-cost DIY UV fiber probe assessment: bare-fiber candidates, coupling to the compartment block, and tip renewal |
| **Vendor** | [docs/vendor/README.md](docs/vendor/README.md) | How to obtain the PerkinElmer LS 55 User's Guide (part 09934436) and place it locally |
