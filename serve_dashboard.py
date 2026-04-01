from __future__ import annotations

import runpy
import sys
from pathlib import Path

# Add common services to Python path
ROOT = Path(__file__).resolve().parent
COMMON = ROOT / "services" / "common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

# Run the dashboard app
runpy.run_path(str(ROOT / "apps" / "dashboard" / "app.py"), run_name="__main__")
