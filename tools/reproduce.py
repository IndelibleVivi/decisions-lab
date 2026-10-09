"""Recompute the dated historical evidence from an operator-supplied data ZIP.

No network. Only repository-owned reviewed code is executed. A bundle is data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "research/2026-10-08"


def reproduce(bundle: Path, out: Path):
    if out.exists():
        raise ValueError("Output already exists; choose a new run directory")
    with zipfile.ZipFile(bundle) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        name = "reanalysis/sys1_order_inputs.jsonl"
        if z.getinfo(name).file_size > 10_000_000:
            raise ValueError("Oversized prediction data")
        raw = z.read(name)
    with tempfile.TemporaryDirectory(prefix="decision-reanalysis-") as temp:
        work = Path(temp)
        (work / "sys1_order_inputs.jsonl").write_bytes(raw)
        # Expected aggregates come from this repository, never untrusted bundle code.
        shutil.copyfile(SNAPSHOT / "reanalysis/author_numbers.json", work / "author_numbers.json")
        shutil.copyfile(SNAPSHOT / "reanalysis/recompute_sys1.py", work / "recompute_sys1.py")
        run = subprocess.run([sys.executable, str(work / "recompute_sys1.py")], capture_output=True, text=True, timeout=60)
        if run.returncode:
            raise ValueError("Historical data failed the reviewed reanalysis; " + run.stderr[-1500:])
        result = json.loads((work / "sys1_reanalysis.json").read_text())
        expected = json.loads((SNAPSHOT / "reanalysis/sys1_reanalysis.json").read_text())
        matches = result == expected
        out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(work / "sys1_reanalysis.json", out / "sys1_reanalysis.json")
        receipt = {"schema": "decisions-lab.historical-reproduction/1", "source_cutoff": "2026-10-08",
                   "input_rows": result["input_rows"], "probability_records": result["option_probability_records_checked"],
                   "author_aggregate_checks": len(result["author_summary_checks"]),
                   "author_aggregates_match": result["all_author_summary_checks_match"],
                   "full_result_matches_snapshot": matches, "inference_calls": 0,
                   "scope": "Recalculation of supplied historical projection; no new inference or upstream projection audit."}
        (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    try:
        receipt = reproduce(args.bundle, args.out)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        p.exit(2, f"Reproduction failed: {exc}\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    raise SystemExit(0 if receipt["full_result_matches_snapshot"] else 1)
