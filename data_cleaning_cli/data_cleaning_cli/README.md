# Data Cleaning CLI

A dependency-free Python CLI with four commands:

- `ingest`: read CSV/JSON and save records to an intermediate JSON file.
- `run`: trim strings, lowercase emails, validate `id`, `name`, `email`, reject invalid emails and duplicate/non-positive IDs, write clean output, log rejected rows, and save metrics.
- `evaluate`: check an output file for remaining validation issues.
- `report`: create a Markdown summary from run metrics and optional evaluation results.

Python 3.10+ recommended. No pip installs are required.

## Run in VS Code (Windows PowerShell)

Open this folder in VS Code, then open Terminal → New Terminal. Run commands one at a time:

```powershell
python data_cli.py --help
python data_cli.py ingest sample.csv
python data_cli.py run
python data_cli.py evaluate
python data_cli.py report --evaluation output/evaluation.json
```

The sample deliberately contains invalid records. `evaluate` returns exit code `1` if it finds issues; this is expected if the evaluated file still has invalid records.

## JSON example

```powershell
python data_cli.py ingest sample.json
python data_cli.py run --output output/cleaned.json --format json
python data_cli.py evaluate --input output/cleaned.json
python data_cli.py report --evaluation output/evaluation.json
```

JSON input can be a list of objects or an object with a `records` list.

## Files produced

- `data/ingested.json`
- `output/cleaned.csv` or `.json`
- `output/errors.log`
- `output/metrics.json`
- `output/evaluation.json`
- `output/report.md`

The input file is never modified. Required fields: `id`, `name`, and `email`. IDs must be unique positive integers.
