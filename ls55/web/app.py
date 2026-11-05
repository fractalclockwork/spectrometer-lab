"""FastAPI + WebSocket operator console API."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ls55.review import (
    discover_blank_candidates,
    discover_logged_runs,
    load_spectrum_csv,
    recompute_run_review,
)
from ls55.service import LS55Service

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_LOGS = REPO_ROOT / "logs"


class ConnectBody(BaseModel):
    port: Optional[str] = None
    fixture_dir: Optional[str] = None
    gate_a_pass: bool = False
    compartment_closed: bool = False
    clear_busy: bool = False
    boot_wait_s: float = 90.0


class SetupBody(BaseModel):
    ex_nm: Optional[float] = None
    em_nm: Optional[float] = None
    ex_slit: Optional[float] = None
    em_slit: Optional[float] = None
    fw: Optional[int] = None
    ph: Optional[int] = None
    cx: Optional[int] = None
    pv: Optional[int] = None


class SingleReadBody(BaseModel):
    ex_nm: float = 350.0
    em_nm: float = 450.0
    integration_s: float = 1.0
    dark_correct: bool = True


class ScanBody(BaseModel):
    mx: int = 1
    ex_nm: float = 350.0
    em_lo: float = 400.0
    em_hi: float = 550.0
    interval_nm: float = 2.0
    speed: int = 120
    ex_slit: float = 5.0
    em_slit: float = 5.0
    include_dark: bool = True
    n_accumulate: int = 1
    # Provenance / staging meta (persisted on successful scan)
    experiment: Optional[str] = None
    method_name: Optional[str] = None
    series_id: Optional[str] = None
    replicate_kind: Optional[str] = None
    sample_id: Optional[str] = None
    dilution: Optional[str] = None
    geometry: str = "right_angle_4w"
    role: str = "sample"  # sample | blank
    persist: bool = True


class ReviewBody(BaseModel):
    run_path: Optional[str] = None
    csv_path: Optional[str] = None
    blank_csv: Optional[str] = None
    wavelength_nm: Optional[list[float]] = None
    sample_on: Optional[list[float]] = None
    guide_nm: float = 450.0
    half_window_nm: float = 25.0
    noise_lo_nm: float = 410.0
    noise_hi_nm: float = 420.0
    wing_left: tuple[float, float] = Field(default=(380.0, 386.0))
    wing_right: tuple[float, float] = Field(default=(410.0, 420.0))
    mode: str = "fluorescence"
    sample_settings: Optional[dict[str, Any]] = None
    blank_settings: Optional[dict[str, Any]] = None


class ProbeBody(BaseModel):
    port: Optional[str] = None
    fixture_dir: Optional[str] = None
    boot_wait_s: float = 5.0
    clear_busy: bool = False


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"event": event, "payload": payload})
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


def create_app(
    *,
    service: Optional[LS55Service] = None,
    logs_root: Optional[Path] = None,
) -> FastAPI:
    svc = service or LS55Service(log_dir=REPO_ROOT / "logs" / "dashboard")
    logs = Path(logs_root) if logs_root else DEFAULT_LOGS
    hub = Hub()
    loop_holder: dict[str, Optional[asyncio.AbstractEventLoop]] = {"loop": None}

    def on_service_event(event: str, payload: dict[str, Any]) -> None:
        loop = loop_holder["loop"]
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(hub.broadcast(event, payload), loop)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        loop_holder["loop"] = asyncio.get_running_loop()
        svc.subscribe(on_service_event)
        try:
            yield
        finally:
            svc.unsubscribe(on_service_event)
            svc.close()
            loop_holder["loop"] = None

    app = FastAPI(
        title="LS 55 Operator Console",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.service = svc
    app.state.logs_root = logs
    app.state.hub = hub

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(404, "dashboard static files missing")
        return FileResponse(index_path)

    @app.get("/api/state")
    async def api_state() -> dict[str, Any]:
        # Enumerate USB first — list_ports may unsettle on unplug — then snapshot.
        ports = svc.list_ports()
        snap = svc.snapshot().to_dict()
        snap["ports"] = ports
        fixtures_root = REPO_ROOT / "tests" / "fixtures"
        snap["fixtures"] = sorted(
            p.name
            for p in fixtures_root.iterdir()
            if p.is_dir() and (p / "script.json").is_file()
        ) if fixtures_root.is_dir() else []
        snap["fixtures_root"] = str(fixtures_root)
        return snap

    @app.post("/api/connect")
    async def api_connect(body: ConnectBody) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                svc.connect,
                port=body.port,
                fixture_dir=Path(body.fixture_dir) if body.fixture_dir else None,
                gate_a_pass=body.gate_a_pass,
                compartment_closed=body.compartment_closed,
                clear_busy=body.clear_busy,
                boot_wait_s=body.boot_wait_s,
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/disconnect")
    async def api_disconnect() -> dict[str, Any]:
        return await asyncio.to_thread(svc.disconnect)

    @app.post("/api/status/refresh")
    async def api_status_refresh() -> dict[str, Any]:
        try:
            return await asyncio.to_thread(svc.refresh_status)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/probe")
    async def api_probe(body: ProbeBody) -> dict[str, Any]:
        """Classify adapter / booting / busy / ready without opening a session."""
        try:
            return await asyncio.to_thread(
                svc.probe_link,
                port=body.port,
                fixture_dir=Path(body.fixture_dir) if body.fixture_dir else None,
                boot_wait_s=body.boot_wait_s,
                clear_busy=body.clear_busy,
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/setup")
    async def api_setup(body: SetupBody) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(svc.apply_setup, body.model_dump())
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/single-read")
    async def api_single_read(body: SingleReadBody) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                svc.single_read,
                ex_nm=body.ex_nm,
                em_nm=body.em_nm,
                integration_s=body.integration_s,
                dark_correct=body.dark_correct,
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/scan")
    async def api_scan(body: ScanBody) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(svc.start_scan, body.model_dump())
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/abort")
    async def api_abort() -> dict[str, Any]:
        try:
            return await asyncio.to_thread(svc.abort)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/shutter/off")
    async def api_shutter_off() -> dict[str, Any]:
        try:
            return await asyncio.to_thread(svc.force_shutter_off)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/runs")
    async def api_runs() -> dict[str, Any]:
        return {"runs": discover_logged_runs(logs)}

    @app.get("/api/blanks")
    async def api_blanks() -> dict[str, Any]:
        return {"blanks": discover_blank_candidates(logs)}

    @app.get("/api/runs/{run_id}")
    async def api_run_detail(run_id: str) -> dict[str, Any]:
        for run in discover_logged_runs(logs):
            if run["run_id"] == run_id:
                path = Path(run["path"])
                data = json.loads(path.read_text(encoding="utf-8"))
                spectrum = None
                csv_path = run.get("csv")
                if csv_path and Path(csv_path).is_file():
                    wl, inten = load_spectrum_csv(Path(csv_path))
                    spectrum = {"wavelength_nm": wl, "intensity": inten}
                return {"run": run, "sidecar": data, "spectrum": spectrum}
        raise HTTPException(404, f"run not found: {run_id}")

    @app.post("/api/review/recompute")
    async def api_review_recompute(body: ReviewBody) -> dict[str, Any]:
        try:
            wl = body.wavelength_nm
            sample = body.sample_on
            if (wl is None or sample is None) and body.csv_path:
                wl, sample = load_spectrum_csv(Path(body.csv_path))
            if (wl is None or sample is None) and body.run_path:
                run = json.loads(Path(body.run_path).read_text(encoding="utf-8"))
                csv_path = run.get("csv") or (run.get("artifacts") or {}).get("csv")
                if not csv_path:
                    raise ValueError("run has no csv artifact")
                wl, sample = load_spectrum_csv(Path(csv_path))
            if wl is None or sample is None:
                raise ValueError("provide wavelength_nm/sample_on or csv_path/run_path")

            blank_settings = body.blank_settings
            if body.blank_csv and blank_settings is None:
                sidecar = Path(body.blank_csv).with_suffix(".json")
                if sidecar.is_file():
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                    blank_settings = data.get("settings") or data.get("ls55_optics")

            result = recompute_run_review(
                wavelength_nm=wl,
                sample_on=sample,
                blank_path=Path(body.blank_csv) if body.blank_csv else None,
                guide_nm=body.guide_nm,
                half_window_nm=body.half_window_nm,
                noise_lo_nm=body.noise_lo_nm,
                noise_hi_nm=body.noise_hi_nm,
                left_wing=body.wing_left,
                right_wing=body.wing_right,
                mode=body.mode,
                sample_settings=body.sample_settings,
                blank_settings=blank_settings,
            )
            return result.to_dict()
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.websocket("/ws/telemetry")
    async def ws_telemetry(ws: WebSocket) -> None:
        await hub.connect(ws)
        try:
            await ws.send_text(
                json.dumps({"event": "hello", "payload": svc.snapshot().to_dict()})
            )
            while True:
                # Keep alive; client may send pings.
                await ws.receive_text()
        except WebSocketDisconnect:
            await hub.disconnect(ws)
        except Exception:
            await hub.disconnect(ws)

    return app
