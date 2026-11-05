# Stage 0 — Robust Bootup / Connection Handling

**Status: PASS — operator sign-off recorded 2026-11-03.**

Stage 0 is the **foundation** under the operator console. It is **not** WinLab Status/Scan UI. It is: find the adapter, survive DUT power cycles, classify busy/boot/ready, keep Xe lamp-safe, and recover after every link loss. **Stage 1 must not be signed off until Stage 0 is PASS** (or explicitly waived with notes).

Offline pytest / fixtures are development evidence only; they do **not** close these checkboxes.

| Field | Value |
| --- | --- |
| Stage | 0 — Robust bootup / connection handling |
| Instrument | LS 55 · firmware `F1` · SN `79787` (when live) |
| Related roadmap | [features-and-roadmap.md](features-and-roadmap.md) §§2, 8 |
| CLIs | `scripts/kill_xe.py`, `scripts/discover_device.py` |
| Service | `ls55/discover.py`, `ls55/source.py`, `ls55/service.py` (link + Xe policy) |
| Operator | plastic (chat) |
| Sign-off date | 2026-11-03 |
| Mode exercised | [x] Live serial · [ ] Offline fixture only · [ ] Both |

**How to use:** Exercise each row on the bench (power, USB, busy). Mark **PASS** only when behavior matches acceptance. Stage 0 closes only when the **Stage gate** at the bottom is signed.

---

## A. Adapter and port ownership

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| A1 | **USB–serial discovery** — `/dev/serial/by-id` only (no bare `ttyS*` false adapters) | Unplugged adapter → “USB–serial unplugged”; plug Prolific → by-id path appears; no phantom “adapter up” on platform UARTs | Y | [ ] | [ ] | |
| A2 | **Exclusive open / release** | Dashboard or script holds the port; second opener fails cleanly; Disconnect / process exit frees the port for `kill_xe` / reconnect | Y | [ ] | [ ] | |
| A3 | **Preferred path** | Live Connect uses by-id symlink when present; logs show the chosen path | Y | [ ] | [ ] | |

---

## B. Boot, busy, and classify

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| B1 | **Power-on / boot silence** | During ~60 s homing, Probe shows booting / no `$ST` (not “ready”); does not claim idle_safe | Y | [ ] | [ ] | |
| B2 | **Busy `0110`** | While DUT busy after power-on (Xe often ON), Probe/Connect classify **BUSY**; host does **not** send `$ES` / force OFF mid-busy | Y | [ ] | [ ] | |
| B3 | **Probe vs Connect** | Busy/boot classify leaves `$ES` alone; **ready Probe and Connect both force Xe OFF** (kill-by-default / post-loss policy) | Y | [ ] | [ ] | |
| B4 | **Clear-busy (optional)** | With “clear busy” armed, `$AB` then re-classify; without it, busy stays busy | Y | [ ] | [ ] | |
| B5 | **`discover_device.py`** | CLI waits through boot, refuses busy without aborting jobs unless asked, forces Xe OFF when ready | Y | [ ] | [ ] | |

---

## C. Xe / lamp safety

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| C1 | **Unverified badge** | Xe shows **? (unverified)** until a confirmed `$ES` readback; never show OFF from stale session after disconnect/busy/boot | Y | [ ] | [ ] | |
| C2 | **Confirmed ON/OFF** | After idle Probe/Connect with verified `$ES`, badge matches `0`=ON / `1`=OFF | Y | [ ] | [ ] | |
| C3 | **`kill_xe.py`** | Forces `$ES 1` + verify; works when dashboard is **not** holding the port | Y | [ ] | [ ] | |
| C4 | **Kill Xe after any connection loss** | USB unplug, DUT power loss, or command-link failure → `xe_kill_pending`; next usable Probe/Abort/Connect/ephemeral open forces OFF and clears pending only when verified | partial | [ ] | [ ] | |
| C5 | **Resting idle** | Successful Connect ends in idle_safe with Xe OFF; intentional Disconnect attempts OFF and sets pending if verify fails | Y | [ ] | [ ] | |
| C6 | **Settle after Xe OFF** | Verified `$ES 1` (ready Probe kill, Connect discover OFF, or shutter/ephemeral kill) sets `link_settled`; auto-probe and idle `$ES` heartbeat **stop**; health detail: “Settled — Xe OFF (no poll until a command fails)” | Y | [ ] | [ ] | |

---

## D. Link loss, fault, and recovery

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| D1 | **Command-driven loss** | While settled, serial stays quiet; a later failed command (timeout / I/O / protocol) unsettles (`recovering`), resumes Probe until ready + Xe OFF, then settles again | Y | [ ] | [ ] | |
| D2 | **Replug / power restore** | USB unplug or Disconnect clears settled (Seeking); after adapter or DUT returns, Probe/Connect can open again without restarting the host process | Y | [ ] | [ ] | |
| D3 | **Fault recovery** | After FAULT (timeout / `0022` glitch), Abort or Refresh clears dialogue (`$AB`), forces Xe OFF when possible, returns **idle_safe** — not stuck FAULT | partial | [ ] | [ ] | |
| D4 | **Abort while disconnected** | Abort/Xe OFF with no session opens briefly, `$AB` + `$ES 1`, closes — no HTTP 500 | Y | [ ] | [ ] | |

---

## E. Operator cues (minimal console)

| # | Feature | Acceptance (operator) | Offline ok? | Live | PASS | Notes |
| --- | --- | --- | :---: | :---: | :---: | --- |
| E1 | **Fixed health strip** | Three fixed slots **USB / DUT / Xe** (`USB OK`, `DUT OFF`/`BOOT`/`BUSY`/`OK`, `Xe ?`/`ON`/`OFF`); strip green only when USB OK + DUT OK + Xe OFF; changing Xe `?`→`OFF` or DUT `BUSY`→`OK` does **not** move **Xe OFF** / Probe buttons | Y | [ ] | [ ] | |
| E2 | **Laptop bench copy** | DUT power-off (quiet fan/Xe) shows calm non-nominal detail, not a sticky red wall; reconnect + ready probe drives Xe OFF and settles (no further poll) | Y | [ ] | [ ] | |
| E3 | **Xe OFF primary** | Top **Xe OFF** forces `$ES 1`; Abort remains available for mid-job stop | Y | [ ] | [ ] | |
| E4 | **Future Pico power** | Doc/UI note only: host power/cooling cycles via Pico are later Stage 0+ — not required for this gate | Y | [ ] | [ ] | deferred |

---

## Defects / waivers

| ID | Description | Severity | Disposition |
| --- | --- | --- | --- |
| | | | |

---

## Stage gate

Stage 0 is **PASS** only when the operator confirms the host can be left running across DUT power cycles and USB unplug/replug, never claims ready while busy/booting, never shows Xe OFF without `$ES` confirmation, always drives toward verified Xe OFF after any connection loss, and once Xe OFF is verified **stops polling** until a later command fails (then recovers to ready + Xe OFF again).

| Field | Value |
| --- | --- |
| **Stage 0 result** | [x] PASS · [ ] FAIL · [ ] PARTIAL (list open IDs): ________ |
| Operator signature | plastic (chat: “stage 0 is fine”) |
| Date | 2026-11-03 |
| Waivers (if any) | none |
