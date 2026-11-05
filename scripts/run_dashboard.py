#!/usr/bin/env python3
"""Launch the LS 55 operator web console (FastAPI + uvicorn)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LS 55 operator console: status, staging, live scan, review."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8055)
    parser.add_argument(
        "--logs-root",
        type=Path,
        default=REPO_ROOT / "logs",
        help="Root for historical run/blank discovery",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help=(
            "Offline fixture name under tests/fixtures (e.g. demo_session). "
            "Pre-connects at startup and opens UI with ?fixture=…"
        ),
    )
    parser.add_argument(
        "--gate-a-pass",
        action="store_true",
        help="Required with --fixture (or for auto-connect)",
    )
    parser.add_argument(
        "--compartment-closed",
        action="store_true",
        help="Mark compartment closed for fixture auto-connect",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload (dev only)",
    )
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn/fastapi required: run `uv sync --all-groups`",
            file=sys.stderr,
        )
        return 2

    from ls55.service import LS55Service
    from ls55.web.app import create_app

    service = LS55Service(log_dir=REPO_ROOT / "logs" / "dashboard")
    query = ""
    if args.fixture:
        fixture_dir = REPO_ROOT / "tests" / "fixtures" / args.fixture
        if not (fixture_dir / "script.json").is_file():
            print(f"fixture not found: {fixture_dir}", file=sys.stderr)
            return 2
        if not args.gate_a_pass:
            print("Refusing: pass --gate-a-pass with --fixture", file=sys.stderr)
            return 2
        result = service.connect(
            fixture_dir=fixture_dir,
            gate_a_pass=True,
            compartment_closed=bool(args.compartment_closed),
        )
        print(
            f"preconnected fixture={args.fixture} ok={result.get('ok')} "
            f"state={service.snapshot().state}",
            file=sys.stderr,
        )
        query = f"?fixture={args.fixture}"

    app = create_app(service=service, logs_root=args.logs_root)

    print(
        f"LS 55 console → http://{args.host}:{args.http_port}/{query}",
        file=sys.stderr,
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.http_port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
