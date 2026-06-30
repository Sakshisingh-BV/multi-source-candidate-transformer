"""
Multi-Source Candidate Data Transformer — CLI entry point.

Usage
-----
python main.py --sources <file1> [<file2> ...] [--config <config.json>] --output <out.json>

Arguments
---------
--sources   One or more source files (.csv, .txt).  At least one required.
--config    Runtime output configuration JSON.  Default: config/default_config.json
--output    Path to write the resulting JSON array.

The CLI is intentionally thin: it only handles argument parsing, file I/O,
and top-level error reporting.  All pipeline logic lives in src/pipeline.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from src.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = os.path.join("config", "default_config.json")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Transform candidate data from multiple sources into a single "
            "canonical profile."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --sources data/sample_candidates.csv data/recruiter_notes.txt "
            "--output output/default_output.json\n"
            "  python main.py --sources data/sample_candidates.csv data/recruiter_notes.txt "
            "--config config/custom_config.json --output output/custom_output.json"
        ),
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        required=True,
        metavar="FILE",
        help="Source files to process (.csv for recruiter CSV, .txt for recruiter notes).",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        metavar="CONFIG_JSON",
        help=f"Runtime output configuration (default: {DEFAULT_CONFIG}).",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="OUTPUT_JSON",
        help="Path for the resulting JSON output file.",
    )
    return parser


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _load_config(config_path: str) -> dict:
    """Load and parse the runtime config JSON.  Exits with a clear message on failure."""
    if not os.path.isfile(config_path):
        _die(f"Config file not found: '{config_path}'")
    try:
        with open(config_path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        _die(f"Config file is not valid JSON ('{config_path}'): {exc}")


def _check_sources(source_paths: list[str]) -> None:
    """Warn (but do not abort) if any source file does not exist."""
    for path in source_paths:
        if not os.path.isfile(path):
            _warn(f"Source file not found: '{path}' — it will be skipped by the extractor.")


def _ensure_output_dir(output_path: str) -> None:
    """Create parent directories for the output file if they don't exist."""
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)


# ---------------------------------------------------------------------------
# Messaging helpers
# ---------------------------------------------------------------------------

def _warn(message: str) -> None:
    print(f"[WARN]  {message}", file=sys.stderr)


def _info(message: str) -> None:
    print(f"[INFO]  {message}")


def _die(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ── Load config ──────────────────────────────────────────────────────────
    config = _load_config(args.config)
    _info(f"Using config : {args.config}")

    # ── Validate source paths (non-fatal warnings) ───────────────────────────
    _check_sources(args.sources)
    _info(f"Sources      : {', '.join(args.sources)}")

    # ── Run pipeline ─────────────────────────────────────────────────────────
    try:
        results = run_pipeline(args.sources, config)
    except ValueError as exc:
        # Raised by pipeline for unsupported file extensions.
        _die(str(exc))
    except Exception as exc:
        _die(f"Unexpected pipeline error: {exc}")

    if not results:
        _warn("Pipeline produced no output — check that source files contain valid candidate data.")
        outputs = []
    else:
        outputs = []
        for i, (output_dict, warnings) in enumerate(results, start=1):
            for w in warnings:
                _warn(w)
            outputs.append(output_dict)

    # ── Write output ─────────────────────────────────────────────────────────
    _ensure_output_dir(args.output)
    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(outputs, fh, indent=2, default=str)
    except OSError as exc:
        _die(f"Could not write output file '{args.output}': {exc}")

    # ── Summary ──────────────────────────────────────────────────────────────
    _info(f"Output       : {args.output}")
    _info(f"Candidates   : {len(outputs)}")
    _info("Done.")


if __name__ == "__main__":
    main()
