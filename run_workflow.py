from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMON = ROOT / "services" / "common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

from adobe_influencer.pipelines.runner import PipelineRunner


def build_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    pythonpath_parts = [str(COMMON)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def run_dashboard() -> None:
    subprocess.run([sys.executable, "serve_dashboard.py"], check=True, env=build_runtime_env(), cwd=ROOT)


def run_api() -> None:
    subprocess.run([sys.executable, "serve_api.py"], check=True, env=build_runtime_env(), cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Adobe Influencer Intelligence MVP workflow.")
    parser.add_argument("--launch-dashboard", action="store_true")
    parser.add_argument("--launch-api", action="store_true")
    parser.add_argument("--creator-url", action="append", default=[], help="Creator URL to analyze. Repeat for multiple creators.")
    parser.add_argument("--live", action="store_true", help="Force live mode even if USE_MOCK_DATA=true.")
    parser.add_argument("--enable-media-pipeline", action="store_true", help="Download and transcribe creator videos during the run.")
    args = parser.parse_args()

    with PipelineRunner() as runner:
        if args.live:
            runner.settings.use_mock_data = False
        if args.enable_media_pipeline:
            runner.settings.enable_media_pipeline = True
        runner.run(creator_urls=args.creator_url)

    if args.launch_api:
        run_api()
    elif args.launch_dashboard:
        run_dashboard()


if __name__ == "__main__":
    main()
