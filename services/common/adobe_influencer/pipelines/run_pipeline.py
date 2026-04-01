from __future__ import annotations

import json
from pathlib import Path

from adobe_influencer.pipelines.runner import run_pipeline


def main() -> None:
    recommendations = run_pipeline()
    output = [item.model_dump() for item in recommendations]
    output_path = Path("data/outputs/recommendations.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(output)} recommendations to {output_path}")


if __name__ == "__main__":
    main()
