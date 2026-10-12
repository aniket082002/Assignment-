import argparse, csv, json, logging, re, sys
from pathlib import Path
from datetime import datetime, timezone

REQUIRED = ("id", "name", "email")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_records(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            data = data["records"]
        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
            raise ValueError('JSON must be a list of objects or contain a "records" list.')
        return data
    raise ValueError("Input must be a .csv or .json file.")

def write_records(records, path, fmt=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = (fmt or path.suffix.lstrip(".")).lower()
    if fmt == "json":
        path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif fmt == "csv":
        fields = list(REQUIRED)
        fields += sorted({str(k) for row in records for k in row if str(k) not in fields})
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
    else:
        raise ValueError("Output format must be csv or json.")

def clean(records, log_path):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("data_cli")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    accepted, seen, rejected = [], set(), 0
    for n, original in enumerate(records, 1):
        row = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in original.items()}
        issues = []
        for field in REQUIRED:
            if row.get(field) in (None, ""):
                issues.append(f"missing required field: {field}")
        record_id = None
        try:
            raw_id = row.get("id")
            if isinstance(raw_id, bool) or str(raw_id).strip() == "":
                raise ValueError
            record_id = int(raw_id)
            if record_id <= 0 or (isinstance(raw_id, float) and not raw_id.is_integer()):
                raise ValueError
        except (TypeError, ValueError):
            issues.append("id must be a positive integer")
        email = str(row.get("email", "")).strip().lower()
        if email and not EMAIL.match(email):
            issues.append("invalid email address")
        row["email"] = email
        if record_id is not None and record_id in seen:
            issues.append(f"duplicate id: {record_id}")
        if issues:
            rejected += 1
            logger.error("row %d rejected: %s", n, "; ".join(issues))
        else:
            seen.add(record_id)
            row["id"] = record_id
            accepted.append(row)
    return accepted, {"total": len(records), "accepted": len(accepted), "rejected": rejected}

def cmd_ingest(a):
    records = load_records(a.input)
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"source": a.input, "ingested_at": timestamp(), "records": records},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Ingested {len(records)} record(s) into {out}")
    return 0

def cmd_run(a):
    records = load_records(a.input)
    cleaned, counts = clean(records, a.log)
    fmt = a.format or Path(a.output).suffix.lstrip(".").lower() or "csv"
    write_records(cleaned, a.output, fmt)
    metrics = {"created_at": timestamp(), "input": a.input, "output": a.output, "log": a.log,
               "format": fmt, **counts,
               "acceptance_rate_percent": round(100 * counts["accepted"] / counts["total"], 2) if counts["total"] else 0}
    Path(a.metrics).parent.mkdir(parents=True, exist_ok=True)
    Path(a.metrics).write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"Run complete: {counts['accepted']} accepted, {counts['rejected']} rejected out of {counts['total']}.")
    print(f"Clean output: {a.output}\nError log: {a.log}\nMetrics: {a.metrics}")
    return 0

def cmd_evaluate(a):
    records = load_records(a.input)
    seen, issues, valid = set(), [], 0
    for n, row in enumerate(records, 1):
        problems = []
        for field in REQUIRED:
            if row.get(field) in (None, ""):
                problems.append(f"missing {field}")
        try:
            rid = int(row.get("id"))
            if rid <= 0: raise ValueError
            if rid in seen: problems.append(f"duplicate id {rid}")
            seen.add(rid)
        except (TypeError, ValueError):
            problems.append("id is not a positive integer")
        if not EMAIL.match(str(row.get("email", "")).strip()):
            problems.append("invalid email")
        if problems: issues.append({"row": n, "issues": problems})
        else: valid += 1
    total = len(records)
    result = {"evaluated_at": timestamp(), "input": a.input, "total": total, "valid_records": valid,
              "invalid_records": len(issues),
              "validity_rate_percent": round(100 * valid / total, 2) if total else 0, "issues": issues}
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Evaluation: {valid}/{total} valid ({result['validity_rate_percent']}%). Saved {out}")
    return 0 if not issues else 1

def cmd_report(a):
    metrics = json.loads(Path(a.metrics).read_text(encoding="utf-8"))
    evaluation = json.loads(Path(a.evaluation).read_text(encoding="utf-8")) if a.evaluation else None
    lines = ["# Data Cleaning Report", "", f"- Generated: {timestamp()}",
             f"- Input: `{metrics.get('input', 'unknown')}`",
             f"- Clean output: `{metrics.get('output', 'unknown')}`",
             f"- Total records: {metrics.get('total', 0)}",
             f"- Accepted: {metrics.get('accepted', 0)}",
             f"- Rejected: {metrics.get('rejected', 0)}",
             f"- Acceptance rate: {metrics.get('acceptance_rate_percent', 0)}%",
             f"- Error log: `{metrics.get('log', 'unknown')}`"]
    if evaluation:
        lines += ["", "## Output Evaluation", "",
                  f"- Evaluated file: `{evaluation.get('input', 'unknown')}`",
                  f"- Valid records: {evaluation.get('valid_records', 0)}",
                  f"- Invalid records: {evaluation.get('invalid_records', 0)}",
                  f"- Validity rate: {evaluation.get('validity_rate_percent', 0)}%"]
        if evaluation.get("issues"):
            lines += ["", "### Issues found", ""]
            lines += [f"- Row {item['row']}: {', '.join(item['issues'])}" for item in evaluation["issues"]]
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report saved to {out}")
    return 0

def build_parser():
    p = argparse.ArgumentParser(prog="data-cli", description="Ingest, clean, evaluate, and report on CSV/JSON records.")
    sub = p.add_subparsers(dest="command", required=True)
    x = sub.add_parser("ingest", help="Import CSV/JSON records into an intermediate JSON file")
    x.add_argument("input"); x.add_argument("-o", "--output", default="data/ingested.json"); x.set_defaults(func=cmd_ingest)
    x = sub.add_parser("run", help="Validate, clean, log rejected rows, and write metrics")
    x.add_argument("-i", "--input", default="data/ingested.json"); x.add_argument("-o", "--output", default="output/cleaned.csv")
    x.add_argument("--format", choices=["csv", "json"]); x.add_argument("--log", default="output/errors.log")
    x.add_argument("--metrics", default="output/metrics.json"); x.set_defaults(func=cmd_run)
    x = sub.add_parser("evaluate", help="Evaluate a cleaned CSV/JSON file")
    x.add_argument("-i", "--input", default="output/cleaned.csv"); x.add_argument("-o", "--output", default="output/evaluation.json"); x.set_defaults(func=cmd_evaluate)
    x = sub.add_parser("report", help="Write a Markdown summary")
    x.add_argument("--metrics", default="output/metrics.json"); x.add_argument("--evaluation")
    x.add_argument("-o", "--output", default="output/report.md"); x.set_defaults(func=cmd_report)
    return p

if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        sys.exit(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
