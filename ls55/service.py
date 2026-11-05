"""Single-worker LS55Service actor: exclusive serial owner + event bus."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from ls55.acquire import (
    ScanConfig,
    SpectrumScanResult,
    persist_scan_run,
    run_spectrum_scan,
)
from ls55.control import (
    InstrumentStatusSnapshot,
    OpticalSetup,
    SingleReadResult,
    apply_optical_setup,
    capture_status_snapshot,
    run_single_read,
)
from ls55.discover import list_candidate_ports, run_discover
from ls55.source import SOURCE_OFF, SOURCE_ON, ensure_source_off
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport, Transport

REPO_ROOT = Path(__file__).resolve().parents[1]


class ServiceState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    IDLE_SAFE = "idle_safe"
    MOVING = "moving"
    READING = "reading"
    SCANNING = "scanning"
    ABORTING = "aborting"
    FAULT = "fault"


class ExtensionPlugin(Protocol):
    """Optional Stage 4+ auxiliary hardware hook."""

    name: str

    def connect(self) -> None: ...

    def get_state(self) -> dict[str, Any]: ...

    def pre_acquire(self, context: dict[str, Any]) -> None: ...

    def post_acquire(self, context: dict[str, Any]) -> None: ...

    def emergency_stop(self) -> None: ...


class ExtensionRegistry:
    """Named registry for Stage 4+ plugins (stirrer, gantry, laser, …)."""

    def __init__(self) -> None:
        self._plugins: dict[str, ExtensionPlugin] = {}

    def register(self, plugin: ExtensionPlugin) -> None:
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Optional[ExtensionPlugin]:
        return self._plugins.get(name)

    def values(self):
        return self._plugins.values()

    def items(self):
        return self._plugins.items()

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)


EventCallback = Callable[[str, dict[str, Any]], None]


@dataclass
class ServiceSnapshot:
    state: str
    port: Optional[str] = None
    gate_a_pass: bool = False
    compartment_closed: bool = False
    status: Optional[dict[str, Any]] = None
    es_position: Optional[int] = None
    job: Optional[dict[str, Any]] = None
    last_error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    # Last link probe while disconnected (power/USB are dynamic).
    link: Optional[dict[str, Any]] = None
    # After USB/DUT drop: keep trying kill_xe until $ES OFF is verified.
    xe_kill_pending: bool = False
    # Verified Xe OFF — stop auto-probe until a later command fails.
    link_settled: bool = False
    recovering: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LS55Service:
    """
    Thread-safe instrument actor.

    All serial I/O runs on one worker thread. REST/UI threads submit jobs
    via ``submit`` / convenience methods and subscribe to events.
    """

    def __init__(
        self,
        *,
        log_dir: Optional[Path] = None,
        baud: int = 9600,
        timeout_s: float = 5.0,
    ) -> None:
        self._baud = baud
        self._timeout_s = timeout_s
        self._log_dir = Path(log_dir) if log_dir else Path("logs") / "dashboard"
        self._lock = threading.RLock()
        self._state = ServiceState.DISCONNECTED
        self._engine: Optional[TransactionEngine] = None
        self._transport: Optional[Transport] = None
        self._port: Optional[str] = None
        self._gate_a_pass = False
        self._compartment_closed = False
        self._status: Optional[dict[str, Any]] = None
        self._es_position: Optional[int] = None
        self._last_error: Optional[str] = None
        self._warnings: list[str] = []
        self._job: Optional[dict[str, Any]] = None
        self._link: Optional[dict[str, Any]] = None
        self._subscribers: list[EventCallback] = []
        self.extensions = ExtensionRegistry()
        self._worker_q: queue.Queue[tuple[str, dict[str, Any], queue.Queue]] = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, name="ls55-service", daemon=True)
        self._worker_started = False
        self._stop = threading.Event()
        self._heartbeat_s = 3.0
        self._last_heartbeat_mono = 0.0
        # Policy: after any connection loss, force Xe OFF at next usable link.
        self._xe_kill_pending = False
        # Verified Xe OFF ⇒ settled (no poll). Command failure ⇒ recovering.
        self._link_settled = False
        self._recovering = False

    # --- subscription / extensions -------------------------------------------------

    def subscribe(self, callback: EventCallback) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def register_extension(self, plugin: ExtensionPlugin) -> None:
        self.extensions.register(plugin)

    def _emit(self, event: str, payload: Optional[dict[str, Any]] = None) -> None:
        data = dict(payload or {})
        data.setdefault("state", self._state.value)
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event, data)
            except Exception:  # pragma: no cover - UI isolation
                pass

    def snapshot(self) -> ServiceSnapshot:
        with self._lock:
            return ServiceSnapshot(
                state=self._state.value,
                port=self._port,
                gate_a_pass=self._gate_a_pass,
                compartment_closed=self._compartment_closed,
                status=self._status,
                es_position=self._es_position,
                job=dict(self._job) if self._job else None,
                last_error=self._last_error,
                warnings=list(self._warnings),
                link=dict(self._link) if self._link else None,
                xe_kill_pending=self._xe_kill_pending,
                link_settled=self._link_settled,
                recovering=self._recovering,
            )

    def list_ports(self) -> list[str]:
        """Enumerate USB–serial ports and refresh link hints after unplug/replug."""
        ports = list_candidate_ports()
        # Dynamic USB: keep link state coherent with adapter presence even when
        # no session is open (heartbeat may have left a stale powered_off flag).
        if self._state == ServiceState.DISCONNECTED and self._engine is None:
            if not ports:
                last_port = (self._link or {}).get("port") or self._port
                # Offline fixture settle is not USB-backed — empty by-id list is normal.
                if last_port and str(last_port).startswith("fixture:"):
                    pass
                else:
                    was_settled = self._link_settled
                    self._link = {
                        "state": "no_device",
                        "ready": False,
                        "job_running": False,
                        "errors": ["USB–serial unplugged"],
                        "port": None,
                        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                    if was_settled:
                        self._unsettle_link(
                            reason="USB–serial unplugged", recovering=False
                        )
                    else:
                        self._link_settled = False
                        self._recovering = False
            else:
                prev = (self._link or {}).get("state")
                if prev in {
                    None,
                    "no_device",
                    "adapter_lost",
                    "powered_off",
                    "adapter_present",
                }:
                    # Adapter is back (or never probed) — do not claim DUT ready.
                    # Settled + adapter_present: stay quiet (no thrash of probed_at).
                    if self._link_settled and prev == "adapter_present":
                        pass
                    else:
                        self._link = {
                            "state": "adapter_present",
                            "ready": False,
                            "job_running": False,
                            "errors": [],
                            "port": ports[0],
                            "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "note": "USB–serial present — Probe/Connect to verify DUT",
                        }
                        if prev in {"adapter_lost", "powered_off", "no_device"}:
                            self._last_error = None
                            self._link_settled = False
                            self._recovering = False
        return ports

    # --- worker --------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        if not self._worker_started:
            self._worker_started = True
            self._worker.start()

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                op, args, reply = self._worker_q.get(timeout=0.2)
            except queue.Empty:
                self._maybe_heartbeat()
                continue
            try:
                result = self._dispatch(op, args)
                reply.put(("ok", result))
            except Exception as exc:  # noqa: BLE001 - boundary
                self._maybe_unsettle_from_failure(exc)
                reply.put(("err", exc))

    def _maybe_heartbeat(self) -> None:
        """
        Proactive $ES poll is disabled once the link is settled (Xe OFF verified).

        Loss detection is command-driven: a later failed command unsettles and
        the UI/service recovers by probing until Xe OFF again.
        """
        if self._link_settled:
            return
        if self._state != ServiceState.IDLE_SAFE or self._engine is None:
            return
        if str(self._port or "").startswith("fixture:"):
            return
        # Unsettled session: still avoid idle hammering — wait for a real command.
        return

    def _call(self, op: str, **args: Any) -> Any:
        self._ensure_worker()
        reply: queue.Queue = queue.Queue()
        self._worker_q.put((op, args, reply))
        status, payload = reply.get()
        if status == "err":
            raise payload
        return payload

    def _set_state(self, state: ServiceState) -> None:
        with self._lock:
            self._state = state
        self._emit("state_changed", {"state": state.value})

    def _dispatch(self, op: str, args: dict[str, Any]) -> Any:
        if op == "connect":
            return self._do_connect(**args)
        if op == "disconnect":
            return self._do_disconnect()
        if op == "status":
            return self._do_status()
        if op == "setup":
            return self._do_setup(**args)
        if op == "single_read":
            return self._do_single_read(**args)
        if op == "scan":
            return self._do_scan(**args)
        if op == "shutter_off":
            return self._do_shutter_off()
        if op == "abort":
            return self._do_abort()
        if op == "probe":
            return self._do_probe(**args)
        raise ValueError(f"unknown op {op!r}")

    # --- public API (thread-safe) --------------------------------------------------

    def connect(
        self,
        *,
        port: Optional[str] = None,
        fixture_dir: Optional[Path] = None,
        gate_a_pass: bool = False,
        compartment_closed: bool = False,
        clear_busy: bool = False,
        boot_wait_s: float = 90.0,
    ) -> dict[str, Any]:
        return self._call(
            "connect",
            port=port,
            fixture_dir=str(fixture_dir) if fixture_dir else None,
            gate_a_pass=gate_a_pass,
            compartment_closed=compartment_closed,
            clear_busy=clear_busy,
            boot_wait_s=boot_wait_s,
        )

    def disconnect(self) -> dict[str, Any]:
        return self._call("disconnect")

    def refresh_status(self) -> dict[str, Any]:
        return self._call("status")

    def probe_link(
        self,
        *,
        port: Optional[str] = None,
        fixture_dir: Optional[Path] = None,
        boot_wait_s: float = 5.0,
        clear_busy: bool = False,
    ) -> dict[str, Any]:
        """Non-session probe: adapter / booting / busy / ready (dynamic power+USB)."""
        return self._call(
            "probe",
            port=port,
            fixture_dir=str(fixture_dir) if fixture_dir else None,
            boot_wait_s=boot_wait_s,
            clear_busy=clear_busy,
        )

    def apply_setup(self, setup: OpticalSetup | dict[str, Any]) -> dict[str, Any]:
        if isinstance(setup, OpticalSetup):
            payload = asdict(setup)
        else:
            payload = dict(setup)
        return self._call("setup", setup=payload)

    def single_read(
        self,
        *,
        ex_nm: float,
        em_nm: float,
        integration_s: float = 1.0,
        dark_correct: bool = True,
    ) -> dict[str, Any]:
        return self._call(
            "single_read",
            ex_nm=ex_nm,
            em_nm=em_nm,
            integration_s=integration_s,
            dark_correct=dark_correct,
        )

    def start_scan(self, config: ScanConfig | dict[str, Any]) -> dict[str, Any]:
        if isinstance(config, ScanConfig):
            payload = asdict(config)
        else:
            payload = dict(config)
        return self._call("scan", config=payload)

    def force_shutter_off(self) -> dict[str, Any]:
        return self._call("shutter_off")

    def abort(self) -> dict[str, Any]:
        # Abort flag must be set even if worker is blocked in scan.
        with self._lock:
            engine = self._engine
            if engine is not None:
                engine.request_abort()
            if self._state == ServiceState.SCANNING:
                self._set_state(ServiceState.ABORTING)
        return self._call("abort")

    def close(self) -> None:
        # Drain disconnect on the worker before stopping it — otherwise
        # ``_call("disconnect")`` blocks forever on an unserviced reply queue.
        try:
            if self._engine is not None or self._transport is not None:
                self.disconnect()
        except Exception:
            pass
        self._stop.set()

    # --- worker implementations ----------------------------------------------------

    def _require_engine(self) -> TransactionEngine:
        if self._engine is None:
            raise RuntimeError("not connected")
        return self._engine

    def _resolve_live_port(self, port: Optional[str]) -> str:
        if port:
            return port
        candidates = list_candidate_ports()
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise RuntimeError(
                "no USB–serial adapter found under /dev/serial/by-id "
                "(adapter unplugged, or udev not ready — plug in and Refresh)"
            )
        raise RuntimeError(
            f"multiple serial ports; select one explicitly: {candidates}"
        )

    def _open_serial(self, port: str) -> Transport:
        try:
            return SerialTransport(port, baudrate=self._baud, timeout=0.05)
        except Exception as exc:  # noqa: BLE001 - pyserial OSError/SerialException
            raise RuntimeError(
                f"cannot open {port}: {exc}. "
                "Adapter may be unplugged, in use by another process, or permissions denied."
            ) from exc

    @staticmethod
    def _discover_failure_message(discover) -> str:
        state = getattr(discover, "state", None)
        errs = list(getattr(discover, "errors", None) or [])
        detail = "; ".join(errs) if errs else (state or "not ready")
        if state == "busy" or any("0110" in e for e in errs):
            return (
                f"{detail}. Instrument reports a job running (dynamic: may clear after "
                "power-cycle, or Connect with Clear busy / Abort+$AB)."
            )
        if state == "booting" or any("boot" in e.lower() or "timeout" in e.lower() for e in errs):
            return (
                f"{detail}. No idle $ST yet — instrument may be powered off or still "
                "homing after power-on (retry after power-up; boot can take ~1–2 min)."
            )
        return detail

    def _do_connect(
        self,
        *,
        port: Optional[str],
        fixture_dir: Optional[str],
        gate_a_pass: bool,
        compartment_closed: bool,
        clear_busy: bool = False,
        boot_wait_s: float = 90.0,
    ) -> dict[str, Any]:
        if not gate_a_pass:
            raise ValueError("gate_a_pass required")
        self._set_state(ServiceState.CONNECTING)
        self._gate_a_pass = gate_a_pass
        self._compartment_closed = compartment_closed
        self._warnings = []
        self._last_error = None

        if self._transport is not None:
            self._do_disconnect()

        self._log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        raw_log = self._log_dir / f"session-{stamp}.log"

        try:
            if fixture_dir:
                inner: Transport = FakeTransport.from_fixture_dir(Path(fixture_dir))
                chosen = f"fixture:{fixture_dir}"
            else:
                chosen = self._resolve_live_port(port)
                inner = self._open_serial(chosen)
        except Exception as exc:
            self._last_error = str(exc)
            self._set_state(ServiceState.DISCONNECTED)
            raise

        transport: Transport = LoggingTransport(inner, raw_log)
        engine = TransactionEngine(transport, timeout_s=self._timeout_s, prompted=True)
        self._transport = transport
        self._engine = engine
        self._port = chosen

        discover = run_discover(
            engine,
            gate_a_pass=True,
            port=chosen,
            boot_wait_s=float(boot_wait_s),
        )
        if (
            not discover.ready
            and clear_busy
            and (discover.state == "busy" or any("0110" in e for e in discover.errors))
        ):
            try:
                engine.transact("$AB")
            except Exception as exc:  # noqa: BLE001
                self._warnings.append(f"$AB during clear_busy: {exc}")
            time.sleep(0.5)
            discover = run_discover(
                engine,
                gate_a_pass=True,
                port=chosen,
                boot_wait_s=min(15.0, float(boot_wait_s)),
            )

        self._record_link_from_discover(discover, port=chosen)

        if not discover.ready:
            self._last_error = self._discover_failure_message(discover)
            # Never force $ES while busy/booting/error — power/USB are dynamic and
            # busy 0110 must leave the shutter alone (discover policy).
            self._do_disconnect(force_source_off=False)
            raise RuntimeError(self._last_error)

        # Connect discover forces Xe OFF — clears post-loss kill obligation.
        self._clear_xe_kill_pending(es_after=discover.es_position)
        self._es_position = discover.es_position
        snap = capture_status_snapshot(engine)
        self._status = snap.to_dict()
        self._warnings = list(snap.warnings)
        if snap.es_position is not None:
            self._es_position = snap.es_position
        self._last_heartbeat_mono = time.monotonic()
        self._set_state(ServiceState.IDLE_SAFE)
        self._emit(
            "connected",
            {"port": chosen, "discover": discover.to_dict(), "status": self._status},
        )
        return {
            "ok": True,
            "port": chosen,
            "discover": discover.to_dict(),
            "status": self._status,
            "raw_log": str(raw_log),
            "link": self._link,
        }

    def _record_link_from_discover(self, discover, *, port: Optional[str]) -> None:
        # Busy/boot/error never yield a trustworthy $ES — keep badge unverified.
        es = discover.es_position if discover.ready else None
        self._link = {
            "state": discover.state,
            "ready": discover.ready,
            "job_running": discover.job_running,
            "first_power_on": discover.first_power_on if discover.ready else False,
            "lamp_disabled": discover.lamp_disabled if discover.ready else False,
            "es_position": es,
            "boot_attempts": discover.boot_attempts,
            "errors": list(discover.errors),
            "port": port,
            "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def _note_connection_loss(self, *, recovering: bool = True) -> None:
        """Mark that Xe must be forced OFF at the next usable link."""
        self._xe_kill_pending = True
        self._es_position = None
        self._unsettle_link(reason="connection loss", recovering=recovering)

    def _clear_xe_kill_pending(
        self, *, es_after: Optional[int] = None, settle: bool = True
    ) -> None:
        self._xe_kill_pending = False
        if es_after is not None:
            self._es_position = es_after
        if settle and es_after == SOURCE_OFF:
            self._mark_link_settled(es_after=es_after)

    def _mark_link_settled(self, *, es_after: Optional[int] = None) -> None:
        """Verified Xe OFF — assume connected; stop auto-probe/heartbeat."""
        if es_after is not None:
            self._es_position = es_after
        already = self._link_settled and not self._recovering
        self._link_settled = True
        self._recovering = False
        self._xe_kill_pending = False
        if already:
            return
        self._emit(
            "link_settled",
            {
                "link_settled": True,
                "es_position": self._es_position,
                "port": self._port,
            },
        )

    def _unsettle_link(self, *, reason: str = "", recovering: bool = True) -> None:
        """
        Clear settled.

        ``recovering=True`` — later command failed; poll until ready+Xe OFF.
        ``recovering=False`` — Seeking after Disconnect / USB gone.
        """
        changed = self._link_settled or (self._recovering != recovering)
        self._link_settled = False
        self._recovering = recovering
        if not changed:
            return
        self._emit(
            "link_unsettled",
            {
                "link_settled": False,
                "recovering": recovering,
                "reason": reason,
            },
        )

    @staticmethod
    def _is_link_failure_text(text: str) -> bool:
        t = text.lower()
        return any(
            key in t
            for key in (
                "timeout",
                "input/output",
                "errno 5",
                "device disconnected",
                "no such file",
                "not open",
                "protocol",
                "inter-byte",
                "empty read",
                "usb",
                "serial",
            )
        )

    def _maybe_unsettle_from_failure(self, *parts: Any) -> None:
        chunks: list[str] = []
        for part in parts:
            if part is None:
                continue
            if isinstance(part, BaseException):
                chunks.append(str(part))
            elif isinstance(part, (list, tuple)):
                chunks.extend(str(x) for x in part)
            else:
                chunks.append(str(part))
        text = "; ".join(chunks)
        if text and self._is_link_failure_text(text):
            self._unsettle_link(reason=text)

    def _kill_xe_after_loss(self) -> dict[str, Any]:
        """
        Policy: after any connection loss, force Xe OFF when the link works again.

        Uses a brief exclusive open (same as Abort while disconnected). Clears
        ``xe_kill_pending`` only when ``$ES`` readback confirms OFF.
        """
        if not self._xe_kill_pending and self._link_settled:
            return {
                "ok": True,
                "skipped": True,
                "xe_kill_pending": False,
                "link_settled": True,
            }
        if not self._xe_kill_pending:
            return {"ok": True, "skipped": True, "xe_kill_pending": False}
        result = self._ephemeral_clear(also_shutter_off=True)
        shutter = result.get("shutter") or {}
        if shutter.get("ok"):
            self._clear_xe_kill_pending(es_after=shutter.get("es_after"))
            result["xe_kill_pending"] = False
            result["link_settled"] = self._link_settled
            self._emit("xe_killed_after_loss", result)
        else:
            result["xe_kill_pending"] = True
            result["link_settled"] = False
        return result

    def _do_disconnect(self, *, force_source_off: bool = True) -> dict[str, Any]:
        if self._engine is not None and force_source_off:
            try:
                off = ensure_source_off(self._engine)
                if off.ok:
                    # Verified OFF on the way out — clear pending, but do not
                    # settle: Disconnect returns to Seeking (no assumed link).
                    self._clear_xe_kill_pending(es_after=off.es_after, settle=False)
                else:
                    # Could not verify OFF on the way out — retry when link returns.
                    self._note_connection_loss(recovering=False)
            except Exception:
                self._note_connection_loss(recovering=False)
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
        self._engine = None
        self._transport = None
        # Keep last port hint for ephemeral abort / probe preference.
        if self._port and not str(self._port).startswith("fixture:"):
            pass  # retain self._port as last-known
        else:
            self._port = None
        held_port = self._port
        self._status = None
        self._job = None
        # Never keep a stale Xe badge after the session ends — DUT power/USB
        # are dynamic; unknown until the next verified $ES readback.
        self._es_position = None
        self._unsettle_link(reason="disconnect", recovering=False)
        self._set_state(ServiceState.DISCONNECTED)
        self._emit(
            "disconnected",
            {
                "last_port": held_port,
                "xe_kill_pending": self._xe_kill_pending,
                "link_settled": self._link_settled,
            },
        )
        return {
            "ok": True,
            "xe_kill_pending": self._xe_kill_pending,
            "link_settled": self._link_settled,
        }

    def _do_probe(
        self,
        *,
        port: Optional[str] = None,
        fixture_dir: Optional[str] = None,
        boot_wait_s: float = 5.0,
        clear_busy: bool = False,
    ) -> dict[str, Any]:
        """Open briefly, classify link (busy/booting/ready), close — no session."""
        if self._engine is not None:
            # In-session Probe/Refresh: re-verify status (also recovers FAULT).
            if self._state in {ServiceState.IDLE_SAFE, ServiceState.FAULT}:
                status = self._do_status()
                return {
                    "ok": self._state == ServiceState.IDLE_SAFE,
                    "in_session": True,
                    "state": self._state.value,
                    "es_position": self._es_position,
                    "link": self._link,
                    "status": status,
                }
            return {
                "ok": True,
                "in_session": True,
                "state": self._state.value,
                "link": self._link,
            }

        self._log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        raw_log = self._log_dir / f"probe-{stamp}.log"

        try:
            if fixture_dir:
                inner: Transport = FakeTransport.from_fixture_dir(Path(fixture_dir))
                chosen = f"fixture:{fixture_dir}"
            else:
                chosen = self._resolve_live_port(port)
                inner = self._open_serial(chosen)
        except Exception as exc:
            self._link = {
                "state": "no_device",
                "ready": False,
                "errors": [str(exc)],
                "port": port,
                "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            self._last_error = str(exc)
            self._emit("link_probe", self._link)
            return {"ok": False, **self._link, "raw_log": None}

        transport: Transport = LoggingTransport(inner, raw_log)
        engine = TransactionEngine(transport, timeout_s=self._timeout_s, prompted=True)
        try:
            # Classify first without touching $ES (busy 0110 must leave shutter alone).
            discover = run_discover(
                engine,
                gate_a_pass=True,
                port=chosen,
                boot_wait_s=float(boot_wait_s),
                force_idle_source_off=False,
            )
            if (
                not discover.ready
                and clear_busy
                and (discover.state == "busy" or any("0110" in e for e in discover.errors))
            ):
                try:
                    engine.transact("$AB")
                except Exception as exc:  # noqa: BLE001
                    discover.warnings.append(f"$AB: {exc}")
                time.sleep(0.4)
                discover = run_discover(
                    engine,
                    gate_a_pass=True,
                    port=chosen,
                    boot_wait_s=min(10.0, float(boot_wait_s)),
                    force_idle_source_off=False,
                )

            if discover.state in {"busy", "booting"} or discover.job_running:
                # Power-on / link drop in progress — obligate kill_xe when ready returns.
                self._note_connection_loss()
            elif discover.ready:
                # Stage 0: once the DUT is idle enough for $ES, force Xe OFF.
                # Covers connection-loss restore, power-on default ON, and pending kills.
                saw_on = (
                    discover.first_power_on
                    or discover.es_position == SOURCE_ON
                    or discover.es_position_initial == SOURCE_ON
                )
                try:
                    off = ensure_source_off(engine)
                    discover.transactions.extend(off.transactions)
                    if discover.es_position_initial is None:
                        discover.es_position_initial = off.es_before
                    discover.es_position = off.es_after
                    # Classify may have consumed the ON readback; keep that signal.
                    discover.first_power_on = saw_on or off.was_on
                    discover.lamp_disabled = bool((saw_on or off.was_on) and off.ok)
                    if off.ok:
                        self._clear_xe_kill_pending(es_after=off.es_after)
                    else:
                        self._note_connection_loss()
                        discover.errors.extend(off.errors or ["kill_xe after ready probe failed"])
                        if off.busy:
                            discover.state = "busy"
                            discover.job_running = True
                            discover.ready = False
                except Exception as exc:  # noqa: BLE001
                    self._note_connection_loss()
                    discover.errors.append(f"kill_xe after ready probe: {exc}")

            self._record_link_from_discover(discover, port=chosen)
            if not discover.ready:
                self._last_error = self._discover_failure_message(discover)
                # Busy/boot probes do not yield a trustworthy $ES readback.
                self._es_position = None
            else:
                self._last_error = None
                self._es_position = discover.es_position
            payload = {
                "ok": discover.ready,
                **(self._link or {}),
                "raw_log": str(raw_log),
                "xe_kill_pending": self._xe_kill_pending,
                "link_settled": self._link_settled,
                "recovering": self._recovering,
            }
            self._emit("link_probe", payload)
            return payload
        finally:
            try:
                transport.close()
            except Exception:
                pass

    @staticmethod
    def _flush_engine_rx(engine: TransactionEngine) -> None:
        transport = getattr(engine, "_transport", None)
        reset = getattr(transport, "reset_input_buffer", None)
        if callable(reset):
            try:
                reset()
            except Exception:
                pass

    def _do_status(self) -> dict[str, Any]:
        if self._engine is None:
            # Disconnected: treat Refresh as a short link probe (power/USB dynamic).
            return self._do_probe(boot_wait_s=5.0)
        if self._state not in {ServiceState.IDLE_SAFE, ServiceState.FAULT}:
            raise RuntimeError(f"cannot refresh status in state {self._state.value}")
        engine = self._engine
        if self._state == ServiceState.FAULT:
            # Clear leftover framing noise before re-querying after a fault.
            self._flush_engine_rx(engine)
            try:
                engine.transact("$AB")
            except Exception as exc:  # noqa: BLE001
                self._warnings.append(f"$AB during fault status refresh: {exc}")
        try:
            snap: InstrumentStatusSnapshot = capture_status_snapshot(engine)
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            self._set_state(ServiceState.FAULT)
            self._maybe_unsettle_from_failure(exc)
            raise
        self._status = snap.to_dict()
        self._es_position = snap.es_position
        self._warnings = list(snap.warnings)
        if not snap.ok:
            self._last_error = "; ".join(snap.errors)
            self._set_state(ServiceState.FAULT)
            self._maybe_unsettle_from_failure(self._last_error)
        else:
            self._last_error = None
            self._set_state(ServiceState.IDLE_SAFE)
            if snap.es_position == SOURCE_OFF:
                self._mark_link_settled(es_after=snap.es_position)
            self._link = {
                "state": "ready",
                "ready": True,
                "job_running": False,
                "first_power_on": False,
                "lamp_disabled": False,
                "es_position": snap.es_position,
                "boot_attempts": 0,
                "errors": [],
                "port": self._port,
                "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        self._emit("status", {"status": self._status})
        return self._status

    def _do_setup(self, *, setup: dict[str, Any]) -> dict[str, Any]:
        engine = self._require_engine()
        if self._state != ServiceState.IDLE_SAFE:
            raise RuntimeError(f"cannot apply setup in state {self._state.value}")
        self._set_state(ServiceState.MOVING)
        self._job = {"type": "setup", "setup": setup}
        try:
            opt = OpticalSetup(**{
                k: setup.get(k)
                for k in (
                    "ex_nm",
                    "em_nm",
                    "ex_slit",
                    "em_slit",
                    "fw",
                    "ph",
                    "cx",
                    "pv",
                )
            })
            applied = apply_optical_setup(engine, opt)
            if not applied.ok:
                self._last_error = "; ".join(applied.errors)
                self._set_state(ServiceState.FAULT)
                self._maybe_unsettle_from_failure(self._last_error)
            else:
                self._set_state(ServiceState.IDLE_SAFE)
            self._emit("setup_done", applied.to_dict())
            return applied.to_dict()
        finally:
            self._job = None

    def _do_single_read(
        self,
        *,
        ex_nm: float,
        em_nm: float,
        integration_s: float,
        dark_correct: bool,
    ) -> dict[str, Any]:
        engine = self._require_engine()
        if self._state != ServiceState.IDLE_SAFE:
            raise RuntimeError(f"cannot single-read in state {self._state.value}")
        if not self._compartment_closed:
            raise RuntimeError("compartment_closed required for Single Read")
        self._set_state(ServiceState.READING)
        self._job = {
            "type": "single_read",
            "ex_nm": ex_nm,
            "em_nm": em_nm,
            "integration_s": integration_s,
        }
        try:
            for ext in self.extensions.values():
                ext.pre_acquire({"op": "single_read"})
            result: SingleReadResult = run_single_read(
                engine,
                ex_nm=ex_nm,
                em_nm=em_nm,
                integration_s=integration_s,
                dark_correct=dark_correct,
            )
            self._es_position = result.es_after
            payload = result.to_dict()
            self._emit("single_read_done", payload)
            if not result.ok:
                self._last_error = "; ".join(result.errors)
                self._set_state(ServiceState.FAULT)
                self._maybe_unsettle_from_failure(self._last_error)
            else:
                self._set_state(ServiceState.IDLE_SAFE)
                if result.es_after == SOURCE_OFF:
                    self._mark_link_settled(es_after=result.es_after)
            for ext in self.extensions.values():
                ext.post_acquire({"op": "single_read", "result": payload})
            return payload
        finally:
            self._job = None

    def _do_scan(self, *, config: dict[str, Any]) -> dict[str, Any]:
        engine = self._require_engine()
        if self._state != ServiceState.IDLE_SAFE:
            raise RuntimeError(f"cannot scan in state {self._state.value}")
        if not self._compartment_closed:
            raise RuntimeError("compartment_closed required for scan")
        allowed = (
            "mx",
            "ex_nm",
            "em_lo",
            "em_hi",
            "interval_nm",
            "speed",
            "ex_slit",
            "em_slit",
            "include_dark",
            "n_accumulate",
        )
        meta_keys = (
            "experiment",
            "method_name",
            "series_id",
            "replicate_kind",
            "sample_id",
            "dilution",
            "geometry",
            "role",
            "persist",
        )
        cfg = ScanConfig(**{k: config[k] for k in allowed if k in config})
        meta = {k: config[k] for k in meta_keys if k in config}

        self._set_state(ServiceState.SCANNING)
        self._job = {
            "type": "scan",
            "config": asdict(cfg),
            "points": 0,
            "arm": None,
        }
        try:
            for ext in self.extensions.values():
                ext.pre_acquire({"op": "scan", "config": asdict(cfg), "meta": meta})

            def on_point(wl: float, intensity: int, arm: str) -> None:
                with self._lock:
                    if self._job is not None:
                        self._job["points"] = int(self._job.get("points") or 0) + 1
                        self._job["arm"] = arm
                        self._job["last_wl"] = wl
                        self._job["last_intensity"] = intensity
                self._emit(
                    "scan_point",
                    {
                        "wavelength_nm": wl,
                        "intensity": intensity,
                        "arm": arm,
                    },
                )

            def on_phase(name: str, payload: dict[str, Any]) -> None:
                self._emit("scan_phase", {"phase": name, **payload})

            result: SpectrumScanResult = run_spectrum_scan(
                engine,
                cfg,
                compartment_closed=True,
                on_point=on_point,
                on_phase=on_phase,
            )
            self._es_position = result.es_after
            payload = result.to_dict()
            if meta.get("persist", True) and result.sample and result.sample.intensity:
                try:
                    role = str(meta.get("role") or "sample")
                    experiment = str(meta.get("experiment") or (
                        "dashboard-blank" if role == "blank" else "dashboard-scan"
                    ))
                    artifacts = persist_scan_run(
                        result,
                        out_dir=self._log_dir / "scans",
                        experiment=experiment,
                        method_name=meta.get("method_name"),
                        series_id=meta.get("series_id"),
                        replicate_kind=meta.get("replicate_kind"),
                        sample_id=meta.get("sample_id"),
                        dilution=meta.get("dilution"),
                        geometry=str(meta.get("geometry") or "right_angle_4w"),
                        role=role,
                        instrument=(self._status or {}).get("status")
                        if isinstance(self._status, dict)
                        else None,
                        repo_root=REPO_ROOT,
                        write_png=True,
                    )
                    payload["artifacts"] = artifacts
                except Exception as exc:  # noqa: BLE001 - keep scan result
                    payload.setdefault("warnings", []).append(f"persist failed: {exc}")
            self._emit("scan_completed", payload)
            if result.aborted:
                self._set_state(ServiceState.IDLE_SAFE)
                if result.es_after == SOURCE_OFF:
                    self._mark_link_settled(es_after=result.es_after)
            elif not result.passed:
                self._last_error = "; ".join(result.errors) or "scan failed"
                self._set_state(ServiceState.FAULT)
                self._maybe_unsettle_from_failure(self._last_error)
            else:
                self._set_state(ServiceState.IDLE_SAFE)
                if result.es_after == SOURCE_OFF:
                    self._mark_link_settled(es_after=result.es_after)
            for ext in self.extensions.values():
                ext.post_acquire({"op": "scan", "result": payload})
            return payload
        finally:
            self._job = None
            if self._state == ServiceState.ABORTING:
                self._set_state(ServiceState.IDLE_SAFE)

    def _ephemeral_clear(self, *, also_shutter_off: bool) -> dict[str, Any]:
        """
        Open the adapter briefly when not in a session (power/USB are dynamic).

        Sends ``$AB`` and optionally forces Xe OFF, then closes the port so
        Connect can take exclusive ownership next.
        """
        ports = list_candidate_ports()
        preferred = None
        if self._port and not str(self._port).startswith("fixture:"):
            preferred = self._port
        if preferred and preferred in ports:
            chosen = preferred
        elif len(ports) == 1:
            chosen = ports[0]
        elif not ports:
            if also_shutter_off:
                self._note_connection_loss()
            return {
                "ok": False,
                "ephemeral": True,
                "errors": [
                    "no USB–serial adapter present — plug in adapter and/or power the instrument"
                ],
                "xe_kill_pending": self._xe_kill_pending,
            }
        else:
            if also_shutter_off:
                self._note_connection_loss()
            return {
                "ok": False,
                "ephemeral": True,
                "errors": [f"select a port first (candidates: {ports})"],
                "xe_kill_pending": self._xe_kill_pending,
            }

        self._log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        raw_log = self._log_dir / f"abort-{stamp}.log"
        inner = None
        open_errors: list[str] = []
        for attempt in range(2):
            try:
                inner = self._open_serial(chosen)
                break
            except Exception as exc:
                open_errors.append(str(exc))
                if attempt == 0:
                    time.sleep(0.6)
        if inner is None:
            self._note_connection_loss()
            return {
                "ok": False,
                "ephemeral": True,
                "port": chosen,
                "errors": open_errors or ["serial open failed"],
                "xe_kill_pending": self._xe_kill_pending,
            }

        transport: Transport = LoggingTransport(inner, raw_log)
        engine = TransactionEngine(transport, timeout_s=self._timeout_s, prompted=True)
        errors: list[str] = []
        ab_code = None
        off_payload: dict[str, Any] = {}
        try:
            self._flush_engine_rx(engine)
            try:
                ab = engine.transact("$AB")
                ab_code = ab.final_code or ab.initial_code
            except Exception as exc:  # noqa: BLE001
                errors.append(f"$AB: {exc}")
            if also_shutter_off:
                try:
                    off = ensure_source_off(engine)
                    off_payload = off.to_dict()
                    self._es_position = off.es_after
                    if off.ok:
                        self._clear_xe_kill_pending(es_after=off.es_after)
                    else:
                        errors.extend(off.errors or ["ensure_source_off failed"])
                        self._note_connection_loss()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"$ES off: {exc}")
                    self._note_connection_loss()
        finally:
            try:
                transport.close()
            except Exception:
                pass

        ok = not errors and (
            not also_shutter_off or bool(off_payload.get("ok"))
        )
        payload = {
            "ok": ok,
            "ephemeral": True,
            "port": chosen,
            "ab_code": ab_code,
            "shutter": off_payload,
            "errors": errors,
            "raw_log": str(raw_log),
            "state": self._state.value,
            "xe_kill_pending": self._xe_kill_pending,
        }
        self._emit("abort_requested", payload)
        return payload

    def _do_shutter_off(self) -> dict[str, Any]:
        if self._engine is None:
            return self._ephemeral_clear(also_shutter_off=True)
        engine = self._engine
        if self._state == ServiceState.SCANNING:
            engine.request_abort()
            self._set_state(ServiceState.ABORTING)
        try:
            off = ensure_source_off(engine)
        except Exception as exc:
            # Link drop mid-session (adapter unplug / power loss).
            self._last_error = (
                f"shutter_off lost link: {exc}. "
                "Xe OFF required after connection loss — will retry on next usable link."
            )
            self._note_connection_loss()
            self._do_disconnect(force_source_off=False)
            retry = self._kill_xe_after_loss()
            return {
                "ok": bool((retry.get("shutter") or {}).get("ok")),
                "errors": [self._last_error] + list(retry.get("errors") or []),
                "state": self._state.value,
                "xe_kill_pending": self._xe_kill_pending,
                "retry": retry,
            }
        self._es_position = off.es_after
        if off.ok:
            self._clear_xe_kill_pending(es_after=off.es_after)
        if off.ok and self._state in {ServiceState.ABORTING, ServiceState.FAULT}:
            self._set_state(ServiceState.IDLE_SAFE)
        self._emit("shutter_off", off.to_dict())
        return off.to_dict()

    def _do_abort(self) -> dict[str, Any]:
        for ext in self.extensions.values():
            try:
                ext.emergency_stop()
            except Exception:
                pass
        if self._engine is None:
            return self._ephemeral_clear(also_shutter_off=True)
        engine = self._engine
        engine.request_abort()
        if self._state == ServiceState.SCANNING:
            self._set_state(ServiceState.ABORTING)
        # Mid-scan: let the scan worker finish via request_abort → 0099.
        if self._state == ServiceState.ABORTING and self._job is not None:
            payload = {"ok": True, "state": self._state.value, "deferred": True}
            self._emit("abort_requested", payload)
            return payload

        # Idle / FAULT / stuck session: flush, $AB, force Xe OFF, clear fault.
        self._flush_engine_rx(engine)
        errors: list[str] = []
        ab_code = None
        try:
            ab = engine.transact("$AB")
            ab_code = ab.final_code or ab.initial_code
        except Exception as exc:  # noqa: BLE001
            errors.append(f"$AB: {exc}")
        off_payload: dict[str, Any] = {}
        try:
            off = ensure_source_off(engine)
            off_payload = off.to_dict()
            self._es_position = off.es_after
            if not off.ok:
                errors.extend(off.errors or ["ensure_source_off failed"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"$ES off: {exc}")

        if not errors:
            self._last_error = None
            self._set_state(ServiceState.IDLE_SAFE)
            if off_payload.get("ok") and off_payload.get("es_after") == SOURCE_OFF:
                self._clear_xe_kill_pending(es_after=off_payload.get("es_after"))
            self._link = {
                "state": "ready",
                "ready": True,
                "job_running": False,
                "first_power_on": False,
                "lamp_disabled": False,
                "es_position": self._es_position,
                "boot_attempts": 0,
                "errors": [],
                "port": self._port,
                "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        else:
            self._last_error = "; ".join(errors)
            self._set_state(ServiceState.FAULT)
            self._maybe_unsettle_from_failure(self._last_error)

        payload = {
            "ok": not errors,
            "state": self._state.value,
            "ab_code": ab_code,
            "shutter": off_payload,
            "errors": errors,
            "link_settled": self._link_settled,
            "xe_kill_pending": self._xe_kill_pending,
        }
        self._emit("abort_requested", payload)
        return payload
