#!/usr/bin/env python3
"""Validate CSV/JSON records and write cleaned output. Uses only the Python standard library."""

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
        force=True,
    )


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read CSV or JSON. JSON may be a list of objects or an object with a records list."""
    suffix = path.suffix.lower()

    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames:
                raise ValueError("CSV file is empty or has no header row.")
            return [dict(row) for row in reader]

    if suffix == ".json":
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            data = data["records"]
        if not isinstance(data, list):
            raise ValueError("JSON must contain a list of objects or an object with a 'records' list.")
        if not all(isinstance(item, dict) for item in data):
            raise ValueError("Every JSON record must be an object.")
        return data

    raise ValueError("Unsupported input format. Use a .csv or .json file.")


def validate_record(record: dict[str, Any], row_number: int) -> tuple[dict[str, Any] | None, list[str]]:
    """Example schema: id, name, email. Extend this function for your own data."""
    cleaned = {}
    errors = []

    # Normalize keys and trim string values.
    for key, value in record.items():
        if not isinstance(key, str) or not key.strip():
            errors.append("column name is blank")
            continue
        normalized_key = key.strip().lower()
        if isinstance(value, str):
            value = value.strip()
        cleaned[normalized_key] = value

    required = ("id", "name", "email")
    for field in required:
        if field not in cleaned or cleaned[field] is None or str(cleaned[field]).strip() == "":
            errors.append(f"missing required field: {field}")

    # ID must be a positive integer and is normalized to int.
    if "id" in cleaned and str(cleaned["id"]).strip():
        try:
            record_id = int(str(cleaned["id"]).strip())
            if record_id <= 0:
                errors.append("id must be a positive integer")
            else:
                cleaned["id"] = record_id
        except (TypeError, ValueError):
            errors.append("id must be a positive integer")

    if "name" in cleaned and cleaned["name"] is not None:
        cleaned["name"] = str(cleaned["name"]).strip()
        if not cleaned["name"]:
            errors.append("name cannot be blank")

    if "email" in cleaned and cleaned["email"] is not None:
        cleaned["email"] = str(cleaned["email"]).strip().lower()
        if cleaned["email"] and not EMAIL_RE.fullmatch(cleaned["email"]):
            errors.append("email format is invalid")

    if errors:
        logging.warning("Record %s rejected: %s | record=%r", row_number, "; ".join(errors), record)
        return None, errors

    return cleaned, []


def write_records(records: list[dict[str, Any]], output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(records, file, indent=2, ensure_ascii=False)
            file.write("\n")
        return

    # Build a stable header from the union of keys, preserving first-seen order.
    fieldnames = []
    seen = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        if not fieldnames:
            file.write("")
            return
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and clean CSV or JSON records; invalid rows are logged and skipped."
    )
    parser.add_argument("input", type=Path, help="Input .csv or .json file")
    parser.add_argument("-o", "--output", type=Path, help="Output path (default: cleaned.<input extension>)")
    parser.add_argument("--format", choices=("csv", "json"), help="Output format (default: same as input)")
    parser.add_argument("--log", type=Path, default=Path("errors.log"), help="Log file path (default: errors.log)")
    args = parser.parse_args()

    configure_logging(args.log)

    if not args.input.is_file():
        logging.error("Input file not found: %s", args.input)
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 2

    output_format = args.format or args.input.suffix.lower().lstrip(".")
    if output_format not in ("csv", "json"):
        print("Error: output format must be csv or json.", file=sys.stderr)
        return 2

    output_path = args.output or args.input.with_name(f"cleaned.{output_format}")

    try:
        records = read_records(args.input)
        clean_records = []
        seen_ids = set()
        rejected = 0

        for row_number, record in enumerate(records, start=2 if args.input.suffix.lower() == ".csv" else 1):
            cleaned, errors = validate_record(record, row_number)
            if errors:
                rejected += 1
                continue

            record_id = cleaned["id"]
            if record_id in seen_ids:
                rejected += 1
                logging.warning("Record %s rejected: duplicate id %s", row_number, record_id)
                continue

            seen_ids.add(record_id)
            clean_records.append(cleaned)

        write_records(clean_records, output_path, output_format)
        logging.info(
            "Finished. Total=%s accepted=%s rejected=%s output=%s",
            len(records), len(clean_records), rejected, output_path
        )
        print("Cleaning completed.")
        print(f"Total records: {len(records)}")
        print(f"Clean records: {len(clean_records)}")
        print(f"Rejected records: {rejected}")
        print(f"Output: {output_path}")
        print(f"Log: {args.log}")
        return 0

    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, ValueError) as exc:
        logging.exception("Processing failed: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
