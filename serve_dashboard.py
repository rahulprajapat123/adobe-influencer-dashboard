from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMON = ROOT / "services" / "common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

from adobe_influencer.core.config import AppSettings


def main() -> None:
    settings = AppSettings()
    host = os.environ.get("HOST", settings.streamlit_host)
    port = os.environ.get("PORT", str(settings.streamlit_port))

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    pythonpath_parts = [str(COMMON)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "apps/dashboard/app.py",
        f"--server.address={host}",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    subprocess.run(command, check=True, env=env, cwd=ROOT)


if __name__ == "__main__":
    main()
