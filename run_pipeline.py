import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
LOGS = ROOT / "data" / "logs"
STEPS = ["downloader.py", "analyser.py", "comparator.py"]


def main():
    today = date.today().isoformat()
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"pipeline_{today}.log"

    def log(msg):
        from datetime import datetime
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line)
        with open(log_path, "a") as f:
            f.write(line + "\n")

    log("===== Pipeline starting =====")

    for step in STEPS:
        log(f"Running {step}...")
        result = subprocess.run(
            [str(PYTHON), str(ROOT / step)],
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
            with open(log_path, "a") as f:
                f.write(result.stdout)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
            with open(log_path, "a") as f:
                f.write(result.stderr)

        if result.returncode != 0:
            log(f"ERROR: {step} failed (exit {result.returncode}) — aborting")
            sys.exit(1)

        log(f"{step} OK")

    log("===== Pipeline completed successfully =====")


if __name__ == "__main__":
    main()
