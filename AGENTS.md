# Contributor guide

```
Setup:   python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
Lint:    ruff check .
Test:    pytest            (pythonpath=src is set in pyproject, no install needed)
Smoke:   routedoctor examples/campus-routing.json 10.20.5.9        # exit 0
         routedoctor examples/unresolved-next-hop.json 203.0.113.9 # exit 1
Layout:  src/routedoctor/engine.py  (Route, Diagnosis, parse_routes, diagnose_destination)
         src/routedoctor/cli.py     (argparse, exit codes 0/1/2)
         tests/test_engine.py       (one test per diagnosis rule)
         examples/*.json            (snapshots used by README and CI)
```

Conventions:

- stdlib only; no runtime dependencies.
- Findings are plain strings; a finding starting with "ERROR" flips `Diagnosis.ok` to False and
  makes the CLI exit 1. New rules append to `result.findings` in `diagnose_destination`.
- Every new finding gets a test in `tests/test_engine.py` and, if user-visible, a README line.
- Keep README example output in sync with the real CLI output.
- CI (`.github/workflows/ci.yml`) runs ruff, pytest, and both smoke commands on 3.11, 3.12
  and 3.13.
