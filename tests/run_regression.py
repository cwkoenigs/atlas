"""Record one observed red/green step; errors never count as a green result."""
import pathlib
import subprocess
import sys

phase, *names = sys.argv[1:]
cmd = [sys.executable, "-m", "unittest", "-v", *names]
r = subprocess.run(cmd, capture_output=True, text=True)
output = r.stdout + r.stderr
print(output, end="")
passed = r.returncode == 0
expected = phase == "green"
log = pathlib.Path("docs/regression-log.md")
if not log.exists():
    log.write_text("# Regression red/green log\n\nAll commands use the installed atlas-map Python with `PYTHONPATH=$PWD/src`. Fixtures use TemporaryDirectory under TMPDIR; no real inventory checks run.\n\n")
summary = " | ".join(line for line in output.splitlines() if line.startswith(("Ran ", "OK", "FAILED")))
with log.open("a") as f:
    f.write(f"- **{phase.upper()}** `{' '.join(cmd)}` — {summary}; exit {r.returncode}.\n")
if passed != expected:
    sys.exit("unexpected test outcome")
