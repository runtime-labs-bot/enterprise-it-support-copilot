"""Run both Python suites in separate processes and import roots."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from app.agent.meridian import meridian_installation


def main():
    load_dotenv(ROOT / ".env")
    backend, python = meridian_installation()
    if not python.is_file():
        raise SystemExit("Create backend/.venv and install backend/requirements-dev.txt first.")
    for executable, cwd in ((sys.executable, ROOT), (str(python), backend)):
        print(f"Running tests in {cwd}", flush=True)
        result = subprocess.run([executable, "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=cwd)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
