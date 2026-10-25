"""Build an offline, compact IEEE MAC assignee snapshot from operator-supplied CSVs.

Run manually on the operator/build machine, NOT during API requests or collection.
Inputs are IEEE public listing CSV files (MA-L, optional MA-M/MA-S).
No network requests, MAC inventory, personal files or DB tables are read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.device_identity import MAX_ENTRIES, MAX_REGISTRY_BYTES, PREFIX_LENGTHS

ASSIGNMENT_COUNTS = {"MA-L": 6, "MA-M": 7, "MA-S": 9}
REGISTRY_BITS = {"MA-L": 24, "MA-M": 28, "MA-S": 36}


def parse_registry(path, kind):
    """Read only assignment/vendor columns; ignore address and private data."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        expected = {"Registry", "Assignment", "Organization Name"}
        if not reader.fieldnames or not expected.issubset(reader.fieldnames):
            raise ValueError(f"{kind}: expected IEEE CSV headers {sorted(expected)}")
        assignments = {}
        for i, item in enumerate(reader, 2):
            if item.get("Registry", "").strip().upper() != kind:
                raise ValueError(f"{kind} row {i}: unexpected registry")
            assignment = (item.get("Assignment") or "").strip().upper()
            vendor = " ".join((item.get("Organization Name") or "").split())
            if len(assignment) != ASSIGNMENT_COUNTS[kind] or any(c not in "0123456789ABCDEF" for c in assignment):
                raise ValueError(f"{kind} row {i}: invalid assignment")
            if not vendor or len(vendor) > 160 or any(ord(char) < 32 for char in vendor):
                raise ValueError(f"{kind} row {i}: invalid vendor")
            key = (REGISTRY_BITS[kind], assignment)
            if key in assignments and assignments[key] != vendor:
                raise ValueError(f"{kind} row {i}: conflicting assignee for same prefix")
            assignments[key] = vendor
        return assignments


def build(inputs):
    entries = {}
    for kind, path in inputs.items():
        for key, vendor in parse_registry(path, kind).items():
            if key in entries and entries[key] != vendor:
                raise ValueError(f"Conflicting IEEE assignee: {key}")
            entries[key] = vendor
    if not entries or len(entries) > MAX_ENTRIES:
        raise ValueError("No assignments / too many assignments")
    rows = "".join(
        f"{bits}\t{prefix}\t{vendor}\n"
        for (bits, prefix), vendor in sorted(entries.items())
    )
    digest = hashlib.sha256(rows.encode("utf-8")).hexdigest()[:16]
    result = f"# version=ieee-public-{digest}\n# source=IEEE public MA-L/MA-M/MA-S registration listings; assignment and vendor only\n" + rows
    if len(result.encode("utf-8")) > MAX_REGISTRY_BYTES:
        raise ValueError("Compact OUI snapshot exceeds runtime size budget")
    return result, len(entries), digest


def save_atomic(path, content, *, replace=False):
    path = Path(path)
    # Destination directory must have been created on the configured volume.
    if not path.parent.is_dir():
        raise ValueError("Output parent must already exist on the selected volume")
    if path.exists() and not replace:
        raise FileExistsError("Dataset exists; use --replace to update intentionally")
    if path.is_symlink():
        raise ValueError("Refusing symlink output destination")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=".oui-import-", suffix=".tmp", delete=False
        ) as out:
            temp_name = out.name
            os.chmod(temp_name, 0o600)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Compile the IEEE public MAC assignment CSVs into one OFFLINE TSV")
    parser.add_argument("--ma-l", type=Path, required=True, help="IEEE MA-L CSV (oui.csv)")
    parser.add_argument("--ma-m", type=Path, help="IEEE MA-M CSV (mam.csv)")
    parser.add_argument("--ma-s", type=Path, help="IEEE MA-S CSV (oui36.csv)")
    parser.add_argument("--output", type=Path, required=True, help="Existing microSD directory/oui-assignments.tsv")
    parser.add_argument("--replace", action="store_true", help="Explicitly update existing OUI snapshot")
    args = parser.parse_args()
    inputs = {"MA-L": args.ma_l}
    if args.ma_m is not None: inputs["MA-M"] = args.ma_m
    if args.ma_s is not None: inputs["MA-S"] = args.ma_s
    content, size, digest = build(inputs)
    save_atomic(args.output, content, replace=args.replace)
    print(f"Compiled {size} public IEEE assignments; version ieee-public-{digest}. No network/device queries.")


if __name__ == "__main__":
    main()
