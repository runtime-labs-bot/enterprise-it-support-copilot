"""Compatibility entry point for live knowledge evaluation.

Use app.evaluation.scorecard for offline/backend profiles and baseline comparisons.
"""
from app.evaluation.scorecard import main


if __name__ == "__main__":
    raise SystemExit(main(default_profile="knowledge"))
