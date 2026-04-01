from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
COMMON = ROOT / "services" / "common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

from adobe_influencer.core.config import AppSettings


def main() -> None:
    settings = AppSettings()
    host = os.environ.get("HOST", settings.api_host)
    port = int(os.environ.get("PORT", str(settings.api_port)))
    reload_enabled = os.environ.get("UVICORN_RELOAD", "").strip().lower() in {"1", "true", "yes"}

    uvicorn.run("apps.api.main:app", host=host, port=port, reload=reload_enabled)


if __name__ == "__main__":
    main()
