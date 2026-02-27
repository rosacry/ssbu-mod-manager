"""Online empirical validation logging and report rendering utilities."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Literal

MatrixResult = Literal["PASS", "FAIL", "UNVERIFIED"]
RttMode = Literal["Public", "Unlisted"]

DEFAULT_MATRIX_PAIRS: tuple[tuple[str, str], ...] = (
    ("Eden", "Eden"),
    ("Eden", "Ryujinx"),
    ("Eden", "Yuzu-family fork"),
    ("Ryujinx", "Ryujinx"),
    ("Yuzu-family fork", "Yuzu-family fork"),
)


@dataclass
class EmulatorPairRun:
    date: str
    pair_a: str
    pair_b: str
    result: MatrixResult
    build_a: str = ""
    build_b: str = ""
    notes: str = ""


@dataclass
class RttRun:
    date: str
    host_build: str
    client_build: str
    mode: RttMode
    runs: int
    avg_rtt_ms: float
    disconnects: int = 0
    notes: str = ""


def _today() -> str:
    return date.today().isoformat()


def _pair_key(a: str, b: str) -> tuple[str, str]:
    left = (a or "").strip()
    right = (b or "").strip()
    return tuple(sorted((left, right)))


def default_data() -> dict:
    return {
        "version": 1,
        "matrix_runs": [],
        "rtt_runs": [],
    }


def load_data(path: Path) -> dict:
    if not path.exists():
        return default_data()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default_data()
    if not isinstance(payload, dict):
        return default_data()
    payload.setdefault("version", 1)
    payload.setdefault("matrix_runs", [])
    payload.setdefault("rtt_runs", [])
    return payload


def save_data(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_matrix_run(
    data: dict,
    *,
    pair_a: str,
    pair_b: str,
    result: MatrixResult,
    build_a: str = "",
    build_b: str = "",
    notes: str = "",
    run_date: str | None = None,
) -> EmulatorPairRun:
    run = EmulatorPairRun(
        date=run_date or _today(),
        pair_a=pair_a.strip(),
        pair_b=pair_b.strip(),
        result=result,
        build_a=build_a.strip(),
        build_b=build_b.strip(),
        notes=notes.strip(),
    )
    data.setdefault("matrix_runs", []).append(asdict(run))
    return run


def add_rtt_run(
    data: dict,
    *,
    mode: RttMode,
    runs: int,
    avg_rtt_ms: float,
    host_build: str = "",
    client_build: str = "",
    disconnects: int = 0,
    notes: str = "",
    run_date: str | None = None,
) -> RttRun:
    run = RttRun(
        date=run_date or _today(),
        host_build=host_build.strip(),
        client_build=client_build.strip(),
        mode=mode,
        runs=max(1, int(runs)),
        avg_rtt_ms=float(avg_rtt_ms),
        disconnects=max(0, int(disconnects)),
        notes=notes.strip(),
    )
    data.setdefault("rtt_runs", []).append(asdict(run))
    return run


def _latest_matrix_runs(data: dict) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for row in data.get("matrix_runs", []):
        a = str(row.get("pair_a", "")).strip()
        b = str(row.get("pair_b", "")).strip()
        key = _pair_key(a, b)
        existing = latest.get(key)
        if existing is None or str(row.get("date", "")) >= str(existing.get("date", "")):
            latest[key] = row
    rows = list(latest.values())
    rows.sort(key=lambda r: (str(r.get("pair_a", "")), str(r.get("pair_b", ""))))
    return rows


def _latest_matrix_map(data: dict) -> dict[tuple[str, str], dict]:
    latest: dict[tuple[str, str], dict] = {}
    for row in data.get("matrix_runs", []):
        a = str(row.get("pair_a", "")).strip()
        b = str(row.get("pair_b", "")).strip()
        key = _pair_key(a, b)
        existing = latest.get(key)
        if existing is None or str(row.get("date", "")) >= str(existing.get("date", "")):
            latest[key] = row
    return latest


def matrix_coverage_summary(data: dict) -> dict:
    """Return canonical matrix coverage stats based on latest run per pair."""
    latest = _latest_matrix_map(data)
    pending: list[dict] = []
    verified = 0
    expected = len(DEFAULT_MATRIX_PAIRS)
    for pair_a, pair_b in DEFAULT_MATRIX_PAIRS:
        key = _pair_key(pair_a, pair_b)
        row = latest.get(key)
        if row is None:
            pending.append({"pair_a": pair_a, "pair_b": pair_b, "reason": "missing"})
            continue
        result = str(row.get("result", "UNVERIFIED")).upper()
        if result in {"PASS", "FAIL"}:
            verified += 1
        else:
            pending.append({"pair_a": pair_a, "pair_b": pair_b, "reason": "unverified"})
    return {
        "expected_pairs": expected,
        "verified_pairs": verified,
        "pending_pairs": pending,
        "complete": verified == expected,
    }


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rtt_mode_summary(data: dict) -> dict:
    """Return aggregated RTT statistics by mode and cross-mode delta."""
    rows = data.get("rtt_runs", []) or []
    summary: dict[str, dict] = {}
    for mode in ("Public", "Unlisted"):
        mode_rows = [r for r in rows if str(r.get("mode", "")).strip() == mode]
        total_trials = 0
        weighted_sum = 0.0
        total_disconnects = 0
        latest_date = ""
        for row in mode_rows:
            runs = max(1, _coerce_int(row.get("runs", 1), default=1))
            avg_rtt_ms = _coerce_float(row.get("avg_rtt_ms", 0.0), default=0.0)
            disc = max(0, _coerce_int(row.get("disconnects", 0), default=0))
            total_trials += runs
            weighted_sum += avg_rtt_ms * runs
            total_disconnects += disc
            d = str(row.get("date", ""))
            if d >= latest_date:
                latest_date = d
        weighted_avg = (weighted_sum / total_trials) if total_trials else 0.0
        disconnect_rate = (total_disconnects / total_trials) if total_trials else 0.0
        summary[mode] = {
            "entries": len(mode_rows),
            "trials": total_trials,
            "weighted_avg_rtt_ms": round(weighted_avg, 3),
            "disconnects": total_disconnects,
            "disconnect_rate_per_trial": round(disconnect_rate, 6),
            "latest_date": latest_date,
        }
    delta: float | None = None
    if summary["Public"]["trials"] and summary["Unlisted"]["trials"]:
        delta = round(
            summary["Public"]["weighted_avg_rtt_ms"] - summary["Unlisted"]["weighted_avg_rtt_ms"],
            3,
        )
    return {
        "modes": summary,
        "public_minus_unlisted_ms": delta,
    }


def render_matrix_markdown(data: dict) -> str:
    lines: list[str] = []
    lines.append("# Emulator Pair Results")
    lines.append("")
    lines.append("Generated from `docs/online_validation_data.json`.")
    lines.append("")
    lines.append("| Pair A | Pair B | Result | Last Tested | Build A | Build B | Notes |")
    lines.append("|---|---|---|---|---|---|---|")
    rows = _latest_matrix_runs(data)
    if not rows:
        lines.append("| - | - | UNVERIFIED | - | - | - | No runs recorded yet. |")
    else:
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("pair_a", "")) or "-",
                        str(row.get("pair_b", "")) or "-",
                        str(row.get("result", "UNVERIFIED")) or "UNVERIFIED",
                        str(row.get("date", "")) or "-",
                        str(row.get("build_a", "")) or "-",
                        str(row.get("build_b", "")) or "-",
                        str(row.get("notes", "")) or "-",
                    ]
                )
                + " |"
            )
    lines.append("")
    coverage = matrix_coverage_summary(data)
    lines.append("## Coverage Summary")
    lines.append("")
    lines.append(f"- Canonical pairs: {coverage['expected_pairs']}")
    lines.append(f"- Verified outcomes (PASS/FAIL): {coverage['verified_pairs']}")
    lines.append(f"- Pending pairs: {len(coverage['pending_pairs'])}")
    if coverage["pending_pairs"]:
        for pair in coverage["pending_pairs"]:
            reason = str(pair.get("reason", "missing"))
            lines.append(
                f"- Pending: {pair.get('pair_a', '-')} vs {pair.get('pair_b', '-')} ({reason})"
            )
    else:
        lines.append("- All canonical pairs are verified.")
    lines.append("")
    lines.append("## Run History")
    lines.append("")
    lines.append("| Date | Pair A | Pair B | Result | Build A | Build B | Notes |")
    lines.append("|---|---|---|---|---|---|---|")
    history = sorted(
        data.get("matrix_runs", []),
        key=lambda r: str(r.get("date", "")),
    )
    if not history:
        lines.append("| - | - | - | - | - | - | - |")
    else:
        for row in history:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("date", "")) or "-",
                        str(row.get("pair_a", "")) or "-",
                        str(row.get("pair_b", "")) or "-",
                        str(row.get("result", "")) or "-",
                        str(row.get("build_a", "")) or "-",
                        str(row.get("build_b", "")) or "-",
                        str(row.get("notes", "")) or "-",
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def render_rtt_markdown(data: dict) -> str:
    lines: list[str] = []
    lines.append("# Public vs Unlisted RTT Results")
    lines.append("")
    lines.append("Generated from `docs/online_validation_data.json`.")
    lines.append("")
    lines.append("| Date | Host Build | Client Build | Mode | Runs | Avg RTT (ms) | Disconnects | Notes |")
    lines.append("|---|---|---|---|---|---|---|---|")
    rows = sorted(data.get("rtt_runs", []), key=lambda r: str(r.get("date", "")))
    if not rows:
        lines.append("| - | - | - | - | - | - | - | No runs recorded yet. |")
    else:
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("date", "")) or "-",
                        str(row.get("host_build", "")) or "-",
                        str(row.get("client_build", "")) or "-",
                        str(row.get("mode", "")) or "-",
                        str(row.get("runs", "")) or "-",
                        str(row.get("avg_rtt_ms", "")) or "-",
                        str(row.get("disconnects", "")) or "0",
                        str(row.get("notes", "")) or "-",
                    ]
                )
                + " |"
            )
    lines.append("")
    summary = rtt_mode_summary(data)
    lines.append("## Aggregate Summary")
    lines.append("")
    lines.append("| Mode | Entries | Trials | Weighted Avg RTT (ms) | Disconnects | Disconnect/Trial | Last Date |")
    lines.append("|---|---|---|---|---|---|---|")
    for mode in ("Public", "Unlisted"):
        row = summary["modes"][mode]
        lines.append(
            "| "
            + " | ".join(
                [
                    mode,
                    str(row.get("entries", 0)),
                    str(row.get("trials", 0)),
                    str(row.get("weighted_avg_rtt_ms", 0.0)),
                    str(row.get("disconnects", 0)),
                    str(row.get("disconnect_rate_per_trial", 0.0)),
                    str(row.get("latest_date", "")) or "-",
                ]
            )
            + " |"
        )
    delta = summary.get("public_minus_unlisted_ms")
    lines.append("")
    if delta is None:
        lines.append("- Delta (Public - Unlisted): unavailable (need both modes recorded).")
    else:
        lines.append(f"- Delta (Public - Unlisted): {delta} ms")
    lines.append("")
    return "\n".join(lines)


def write_reports(
    *,
    data: dict,
    matrix_report_path: Path,
    rtt_report_path: Path,
) -> None:
    matrix_report_path.parent.mkdir(parents=True, exist_ok=True)
    rtt_report_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_report_path.write_text(render_matrix_markdown(data), encoding="utf-8")
    rtt_report_path.write_text(render_rtt_markdown(data), encoding="utf-8")


def seed_default_matrix_entries(data: dict) -> int:
    """Seed canonical emulator-pair entries as UNVERIFIED if missing.

    Returns the number of entries added.
    """
    existing_keys = {
        _pair_key(str(r.get("pair_a", "")), str(r.get("pair_b", "")))
        for r in data.get("matrix_runs", [])
    }
    added = 0
    for pair_a, pair_b in DEFAULT_MATRIX_PAIRS:
        key = _pair_key(pair_a, pair_b)
        if key in existing_keys:
            continue
        add_matrix_run(
            data,
            pair_a=pair_a,
            pair_b=pair_b,
            result="UNVERIFIED",
            notes="seeded default entry",
        )
        existing_keys.add(key)
        added += 1
    return added
