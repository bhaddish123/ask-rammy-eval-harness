#!/usr/bin/env python3
"""
Inspect the benchmark spreadsheet structure.
Prints the first N rows so you can verify column mappings.
"""

import sys
from pathlib import Path
from xlsx_reader import read_xlsx_rows

if __name__ == "__main__":
    script_dir = Path(__file__).parent.parent
    xlsx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else script_dir / "HR_QA_Benchmark_Template_version2.xlsx"

    if not xlsx_path.exists():
        print(f"File not found: {xlsx_path}")
    else:
        print(f"Reading: {xlsx_path}\n")
        rows = read_xlsx_rows(xlsx_path)
        print(f"Total rows: {len(rows)}\n")
        print("First 15 rows:")
        print("=" * 140)
        for i, row in enumerate(rows[:15], 1):
            print(f"Row {i}: {row}")
