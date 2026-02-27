from datetime import date, timedelta
from pathlib import Path

from src.core.online_validation import (
    add_matrix_run,
    add_rtt_run,
    load_data,
    matrix_coverage_summary,
    render_matrix_markdown,
    render_rtt_markdown,
    rtt_mode_summary,
    save_data,
    seed_default_matrix_entries,
    write_reports,
)


def test_online_validation_roundtrip(tmp_path: Path) -> None:
    data_path = tmp_path / "online_validation_data.json"
    data = load_data(data_path)

    add_matrix_run(
        data,
        pair_a="Eden",
        pair_b="Ryujinx",
        result="FAIL",
        build_a="v0.0.4-rc3",
        build_b="1.2.3",
        notes="join failed",
        run_date="2026-02-26",
    )
    add_rtt_run(
        data,
        mode="Public",
        runs=5,
        avg_rtt_ms=42.5,
        disconnects=0,
        host_build="v0.0.4-rc3",
        client_build="v0.0.4-rc3",
        notes="stable",
        run_date="2026-02-26",
    )
    save_data(data_path, data)

    loaded = load_data(data_path)
    assert len(loaded["matrix_runs"]) == 1
    assert len(loaded["rtt_runs"]) == 1


def test_online_validation_markdown_rendering(tmp_path: Path) -> None:
    data = {
        "version": 1,
        "matrix_runs": [
            {
                "date": "2026-02-26",
                "pair_a": "Eden",
                "pair_b": "Ryujinx",
                "result": "FAIL",
                "build_a": "v0.0.4-rc3",
                "build_b": "1.2.3",
                "notes": "join failed",
            }
        ],
        "rtt_runs": [
            {
                "date": "2026-02-26",
                "host_build": "v0.0.4-rc3",
                "client_build": "v0.0.4-rc3",
                "mode": "Public",
                "runs": 5,
                "avg_rtt_ms": 42.5,
                "disconnects": 0,
                "notes": "stable",
            }
        ],
    }

    matrix_md = render_matrix_markdown(data)
    rtt_md = render_rtt_markdown(data)
    assert "Eden" in matrix_md
    assert "Ryujinx" in matrix_md
    assert "42.5" in rtt_md

    matrix_report = tmp_path / "matrix.md"
    rtt_report = tmp_path / "rtt.md"
    write_reports(
        data=data,
        matrix_report_path=matrix_report,
        rtt_report_path=rtt_report,
    )
    assert matrix_report.exists()
    assert rtt_report.exists()


def test_seed_default_matrix_entries_is_idempotent() -> None:
    data = {"version": 1, "matrix_runs": [], "rtt_runs": []}
    first = seed_default_matrix_entries(data)
    second = seed_default_matrix_entries(data)

    assert first >= 1
    assert second == 0


def test_matrix_coverage_summary_tracks_pending_and_verified() -> None:
    data = {"version": 1, "matrix_runs": [], "rtt_runs": []}
    seed_default_matrix_entries(data)

    cov = matrix_coverage_summary(data)
    assert cov["expected_pairs"] >= 1
    assert cov["verified_pairs"] == 0
    assert len(cov["pending_pairs"]) == cov["expected_pairs"]
    assert cov["complete"] is False

    add_matrix_run(
        data,
        pair_a="Eden",
        pair_b="Ryujinx",
        result="FAIL",
        run_date=(date.today() + timedelta(days=1)).isoformat(),
    )
    cov2 = matrix_coverage_summary(data)
    assert cov2["verified_pairs"] == 1
    assert len(cov2["pending_pairs"]) == cov["expected_pairs"] - 1


def test_rtt_mode_summary_and_delta() -> None:
    data = {"version": 1, "matrix_runs": [], "rtt_runs": []}
    add_rtt_run(data, mode="Public", runs=2, avg_rtt_ms=40, disconnects=0, run_date="2026-02-26")
    add_rtt_run(data, mode="Public", runs=3, avg_rtt_ms=50, disconnects=1, run_date="2026-02-26")
    add_rtt_run(
        data,
        mode="Unlisted",
        runs=5,
        avg_rtt_ms=30,
        disconnects=0,
        run_date="2026-02-26",
    )

    summary = rtt_mode_summary(data)
    public = summary["modes"]["Public"]
    unlisted = summary["modes"]["Unlisted"]

    # Weighted average: (2*40 + 3*50) / 5 = 46.0
    assert public["weighted_avg_rtt_ms"] == 46.0
    assert public["trials"] == 5
    assert public["disconnects"] == 1
    assert unlisted["weighted_avg_rtt_ms"] == 30.0
    assert summary["public_minus_unlisted_ms"] == 16.0
