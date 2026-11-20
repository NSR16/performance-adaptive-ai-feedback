"""Reconstruct attempt-level records from the CodeWorkout event tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


EXPECTED_ATTEMPT_COUNT = 69_627
GROUP_COLUMNS = ["SubjectID", "AssignmentID", "ProblemID"]
CONTEXT_COLUMNS = GROUP_COLUMNS + ["CodeStateID"]
EVENT_COLUMNS = [
    "Order",
    "SubjectID",
    "ToolInstances",
    "ServerTimestamp",
    "ServerTimezone",
    "CourseID",
    "CourseSectionID",
    "AssignmentID",
    "ProblemID",
    "CodeStateID",
    "IsEventOrderingConsistent",
    "EventType",
    "Score",
    "Compile.Result",
    "CompileMessageType",
    "CompileMessageData",
    "EventID",
    "ParentEventID",
    "SourceLocation",
]


def convert_numpy_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def read_csv(path: Path) -> pd.DataFrame:
    """Read CSV values as strings so identifiers and timestamps stay intact."""
    return pd.read_csv(path, dtype="string", keep_default_na=False)


def require_columns(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def require_nonempty(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    for column in columns:
        if frame[column].isna().any() or frame[column].str.strip().eq("").any():
            raise ValueError(f"{name}.{column} contains missing identifiers")


def assert_context_matches(
    children: pd.DataFrame,
    parents: pd.DataFrame,
    parent_id_column: str,
    relation_name: str,
) -> None:
    parent_context = parents[["EventID", *CONTEXT_COLUMNS]].rename(
        columns={
            "EventID": "_ParentEventID",
            **{column: f"_parent_{column}" for column in CONTEXT_COLUMNS},
        }
    )
    merged = children[["EventID", parent_id_column, *CONTEXT_COLUMNS].copy()].merge(
        parent_context,
        left_on=parent_id_column,
        right_on="_ParentEventID",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if not merged["_merge"].eq("both").all():
        raise ValueError(f"{relation_name} contains an unresolved parent")
    for column in CONTEXT_COLUMNS:
        if not merged[column].eq(merged[f"_parent_{column}"]).all():
            raise ValueError(
                f"{relation_name} parent disagrees on {column}"
            )


def load_and_validate_events(main_path: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    main = read_csv(main_path)
    require_columns(main, EVENT_COLUMNS, "MainTable")
    require_nonempty(
        main,
        ["Order", *GROUP_COLUMNS, "CodeStateID", "EventType", "EventID"],
        "MainTable",
    )

    order_values = pd.to_numeric(main["Order"], errors="raise")
    main["Order"] = order_values.astype("int64")
    score_text = main["Score"].str.strip()
    parsed_scores = pd.to_numeric(score_text.replace("", pd.NA), errors="coerce")
    invalid_scores = score_text.ne("") & parsed_scores.isna()
    if invalid_scores.any():
        raise ValueError("MainTable.Score contains nonnumeric, nonempty values")
    main["Score"] = parsed_scores.astype("float64")

    if main["EventID"].duplicated().any():
        raise ValueError("MainTable.EventID is not unique")
    if main["Order"].duplicated().any():
        raise ValueError("MainTable.Order is not unique")

    event_counts = {
        str(event_type): int(count)
        for event_type, count in main["EventType"].value_counts().items()
    }
    expected_types = {"Run.Program", "Compile", "Compile.Error"}
    if set(event_counts) != expected_types:
        missing_types = sorted(expected_types - set(event_counts))
        unexpected_types = sorted(set(event_counts) - expected_types)
        raise ValueError(
            "MainTable event types mismatch: "
            f"missing={missing_types}, unexpected={unexpected_types}"
        )

    by_id = main.set_index("EventID")["EventType"]
    parented = main.loc[main["ParentEventID"].ne("")]
    unknown_parent = ~parented["ParentEventID"].isin(by_id.index)
    if unknown_parent.any():
        raise ValueError("MainTable contains unresolved ParentEventID values")

    runs = main.loc[main["EventType"].eq("Run.Program")].copy()
    compiles = main.loc[main["EventType"].eq("Compile")].copy()
    diagnostics = main.loc[main["EventType"].eq("Compile.Error")].copy()

    if runs["ParentEventID"].ne("").any():
        raise ValueError("A Run.Program event unexpectedly has a parent")
    if compiles["ParentEventID"].eq("").any():
        raise ValueError("A Compile event has no parent")
    if diagnostics["ParentEventID"].eq("").any():
        raise ValueError("A Compile.Error event has no parent")
    compile_results = set(compiles["Compile.Result"])
    if compile_results != {"Success", "Error"}:
        raise ValueError(f"Unexpected Compile.Result values: {sorted(compile_results)}")

    parent_type = parented["ParentEventID"].map(by_id)
    expected_parent_type = parented["EventType"].map(
        {"Compile": "Run.Program", "Compile.Error": "Compile"}
    )
    if not parent_type.eq(expected_parent_type).all():
        raise ValueError("An event has a parent of an unexpected event type")

    compile_children = compiles.groupby("ParentEventID", sort=False).size()
    if (
        len(compile_children) != len(runs)
        or not compile_children.eq(1).all()
        or set(compile_children.index) != set(runs["EventID"])
    ):
        raise ValueError("Each Run.Program must have exactly one Compile child")

    assert_context_matches(compiles, runs, "ParentEventID", "Compile-to-Run")
    assert_context_matches(
        diagnostics, compiles, "ParentEventID", "Compile.Error-to-Compile"
    )
    diagnostic_compile_ids = set(diagnostics["ParentEventID"])
    failed_compile_ids = set(
        compiles.loc[compiles["Compile.Result"].eq("Error"), "EventID"]
    )
    successful_compile_ids = set(
        compiles.loc[compiles["Compile.Result"].eq("Success"), "EventID"]
    )
    if diagnostic_compile_ids != failed_compile_ids:
        raise ValueError(
            "Compile.Error diagnostics do not correspond exactly to failed Compile events"
        )
    if diagnostic_compile_ids & successful_compile_ids:
        raise ValueError("A successful Compile unexpectedly has diagnostics")

    run_order = runs.set_index("EventID")["Order"]
    compile_order = compiles.set_index("EventID")["Order"]
    if not compiles["Order"].gt(
        compiles["ParentEventID"].map(run_order)
    ).all():
        raise ValueError("Compile order does not follow its Run.Program")
    if not diagnostics["Order"].gt(
        diagnostics["ParentEventID"].map(compile_order)
    ).all():
        raise ValueError("Compile.Error order does not follow its Compile")

    return main, event_counts


def attach_subject_metadata(
    attempts: pd.DataFrame, subject_path: Path
) -> tuple[pd.DataFrame, dict[str, int]]:
    subjects = read_csv(subject_path)
    require_columns(subjects, ["SubjectID"], "Subject")
    require_nonempty(subjects, ["SubjectID"], "Subject")
    metadata_columns = [column for column in subjects.columns if column != "SubjectID"]

    duplicate_rows = subjects.loc[subjects["SubjectID"].duplicated(keep=False)]
    if not duplicate_rows.empty:
        metadata_variation = duplicate_rows.groupby("SubjectID", sort=False)[
            metadata_columns
        ].nunique(dropna=False)
        if metadata_variation.gt(1).any(axis=None):
            raise ValueError(
                "Duplicate SubjectID rows have conflicting metadata; refusing to deduplicate"
            )

    subjects = subjects.drop_duplicates(subset=["SubjectID"], keep="first")
    if subjects["SubjectID"].duplicated().any():
        raise ValueError("Subject metadata is not unique after exact-metadata deduplication")

    merged = attempts.merge(
        subjects,
        on="SubjectID",
        how="left",
        validate="many_to_one",
        indicator="_subject_merge",
    )
    matched = merged["_subject_merge"].eq("both")
    merged["SubjectMetadataMatched"] = matched
    merged = merged.drop(columns="_subject_merge")
    stats = {
        "source_rows": int(
            len(subjects)
            + len(duplicate_rows)
            - duplicate_rows["SubjectID"].nunique()
        ),
        "unique_subjects": int(subjects["SubjectID"].nunique()),
        "duplicate_rows_removed": int(len(duplicate_rows) - duplicate_rows["SubjectID"].nunique()),
        "attempts_with_metadata": int(matched.sum()),
        "attempts_without_metadata": int((~matched).sum()),
        "students_without_metadata": int(
            attempts.loc[~attempts["SubjectID"].isin(subjects["SubjectID"]), "SubjectID"].nunique()
        ),
    }
    return merged, stats


def build_outputs(
    main: pd.DataFrame,
    code_states_path: Path,
    subject_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    runs = main.loc[main["EventType"].eq("Run.Program")].copy()
    compiles = main.loc[main["EventType"].eq("Compile")].copy()
    diagnostics = main.loc[main["EventType"].eq("Compile.Error")].copy()

    if len(runs) != EXPECTED_ATTEMPT_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_ATTEMPT_COUNT:,} operational attempts, found {len(runs):,}"
        )

    compile_columns = {
        column: f"Compile_{column}" for column in compiles.columns
    }
    compile_columns.update(
        {
            "EventID": "CompileEventID",
            "ParentEventID": "CompileParentEventID",
            "Order": "CompileOrder",
            "ServerTimestamp": "CompileTimestamp",
            "CodeStateID": "CompileCodeStateID",
            "Compile.Result": "CompileResult",
        }
    )
    compile_payload = compiles.rename(columns=compile_columns)
    attempts = runs.merge(
        compile_payload,
        left_on="EventID",
        right_on="CompileParentEventID",
        how="left",
        validate="one_to_one",
        indicator="_compile_merge",
    )
    if not attempts["_compile_merge"].eq("both").all():
        raise ValueError("At least one operational attempt has no attached Compile")
    attempts = attempts.drop(columns="_compile_merge")

    diagnostic_links = compiles[["EventID", "ParentEventID"]].rename(
        columns={"EventID": "CompileEventID", "ParentEventID": "AttemptID"}
    )
    attached_diagnostics = diagnostics.merge(
        diagnostic_links,
        left_on="ParentEventID",
        right_on="CompileEventID",
        how="left",
        validate="many_to_one",
        indicator="_diagnostic_merge",
    )
    if not attached_diagnostics["_diagnostic_merge"].eq("both").all():
        raise ValueError("At least one Compile.Error diagnostic has no Compile parent")
    attached_diagnostics = attached_diagnostics.drop(columns="_diagnostic_merge")
    attached_diagnostics = attached_diagnostics[
        ["AttemptID", "CompileEventID", *EVENT_COLUMNS]
    ]

    diagnostic_counts = attached_diagnostics.groupby("AttemptID", sort=False).size()
    attempts["DiagnosticCount"] = (
        attempts["EventID"].map(diagnostic_counts).fillna(0).astype("int64")
    )

    code_states = read_csv(code_states_path)
    require_columns(code_states, ["CodeStateID", "Code"], "CodeStates")
    require_nonempty(code_states, ["CodeStateID"], "CodeStates")
    if code_states["CodeStateID"].duplicated().any():
        raise ValueError("CodeStates.CodeStateID is not unique")
    code_state_ids = set(code_states["CodeStateID"])
    attempt_code_state_ids = set(attempts["CodeStateID"])
    if attempt_code_state_ids != code_state_ids:
        missing = len(attempt_code_state_ids - code_state_ids)
        unused = len(code_state_ids - attempt_code_state_ids)
        raise ValueError(
            f"CodeStates coverage mismatch: {missing} missing, {unused} unreferenced"
        )
    attempts = attempts.merge(
        code_states,
        on="CodeStateID",
        how="left",
        validate="one_to_one",
        indicator="_code_state_merge",
    )
    if not attempts["_code_state_merge"].eq("both").all():
        raise ValueError("CodeStates join did not cover every attempt")
    attempts = attempts.drop(columns="_code_state_merge")

    attempts, subject_stats = attach_subject_metadata(attempts, subject_path)

    attempts = attempts.sort_values(
        [*GROUP_COLUMNS, "Order"], kind="mergesort"
    ).reset_index(drop=True)
    grouped = attempts.groupby(GROUP_COLUMNS, sort=False, dropna=False)
    attempts["AttemptNumber"] = grouped.cumcount() + 1
    attempts["PreviousScore"] = attempts.groupby(
        GROUP_COLUMNS, sort=False, dropna=False
    )["Score"].shift(1)
    attempts["ScoreDelta"] = attempts["Score"] - attempts["PreviousScore"]
    delta = attempts["ScoreDelta"]
    attempts["ProgressClassification"] = np.select(
        [delta.gt(0.05), delta.lt(-0.05)],
        ["IMPROVING", "REGRESSING"],
        default="STAGNANT",
    )
    attempts.loc[delta.isna(), "ProgressClassification"] = "UNCLASSIFIABLE"

    diagnostic_counts_per_attempt = attempts["DiagnosticCount"].value_counts().sort_index()
    compile_outcomes = attempts["CompileResult"].value_counts(dropna=False).sort_index()
    progress_counts = (
        attempts["ProgressClassification"].value_counts().sort_index()
    )
    summary: dict[str, Any] = {
        "expected_attempt_count": EXPECTED_ATTEMPT_COUNT,
        "attempt_count": int(len(attempts)),
        "event_counts": {key: int(value) for key, value in sorted(main["EventType"].value_counts().items())},
        "compile_outcome_counts": {
            str(key): int(value) for key, value in compile_outcomes.items()
        },
        "diagnostic_event_count": int(len(attached_diagnostics)),
        "attempts_with_diagnostics": int(attempts["DiagnosticCount"].gt(0).sum()),
        "diagnostic_count_per_attempt": {
            str(int(key)): int(value)
            for key, value in diagnostic_counts_per_attempt.items()
        },
        "unique_attempt_ids": int(attempts["EventID"].nunique()),
        "code_states": {
            "source_rows": int(len(code_states)),
            "unique_ids": int(code_states["CodeStateID"].nunique()),
            "matched_attempts": int(attempts["Code"].notna().sum()),
            "coverage_complete": bool(attempts["Code"].notna().all()),
        },
        "subject_metadata": subject_stats,
        "score_missing_attempts": int(attempts["Score"].isna().sum()),
        "progress_classification_counts": {
            str(key): int(value) for key, value in progress_counts.items()
        },
        "attempt_groups": int(attempts.groupby(GROUP_COLUMNS, dropna=False).ngroups),
        "order_range": [
            int(attempts["Order"].min()),
            int(attempts["Order"].max()),
        ],
        "attempts_sorted_by_group_and_order": bool(
            attempts.index.equals(
                attempts.sort_values(
                    [*GROUP_COLUMNS, "Order"], kind="mergesort"
                ).index
            )
        ),
        "compile_per_attempt": bool(
            attempts["CompileEventID"].notna().all()
            and attempts["CompileEventID"].nunique() == len(attempts)
        ),
        "diagnostics_attached": int(len(attached_diagnostics)),
    }
    summary["diagnostic_count_per_attempt_total"] = int(
        sum(int(k) * int(v) for k, v in summary["diagnostic_count_per_attempt"].items())
    )
    summary["validation_passed"] = bool(
        summary["attempt_count"] == EXPECTED_ATTEMPT_COUNT
        and summary["unique_attempt_ids"] == summary["attempt_count"]
        and summary["compile_per_attempt"]
        and summary["diagnostic_event_count"] == summary["diagnostics_attached"]
        and summary["diagnostic_count_per_attempt_total"]
        == summary["diagnostic_event_count"]
        and summary["code_states"]["coverage_complete"]
        and summary["attempts_sorted_by_group_and_order"]
    )
    if not summary["validation_passed"]:
        raise ValueError("One or more reconstruction summary validations failed")

    return attempts, attached_diagnostics, summary


def validate_saved_outputs(
    attempts_path: Path, diagnostics_path: Path, summary: dict[str, Any]
) -> dict[str, bool]:
    attempts = pd.read_csv(
        attempts_path,
        dtype={
            "EventID": "string",
            "CompileEventID": "string",
            "CompileParentEventID": "string",
            "CodeStateID": "string",
            "CompileCodeStateID": "string",
        },
    )
    diagnostics = pd.read_csv(
        diagnostics_path,
        dtype={"AttemptID": "string", "CompileEventID": "string", "EventID": "string"},
    )
    checks = {
        "saved_attempt_count_matches": len(attempts) == EXPECTED_ATTEMPT_COUNT,
        "saved_attempt_ids_unique": attempts["EventID"].is_unique,
        "saved_compile_ids_complete_and_unique": (
            attempts["CompileEventID"].notna().all()
            and attempts["CompileEventID"].is_unique
        ),
        "saved_diagnostic_count_matches": (
            len(diagnostics) == summary["diagnostic_event_count"]
            and diagnostics["EventID"].is_unique
        ),
        "saved_code_state_coverage_complete": (
            attempts["Code"].notna().all()
            and attempts["CodeStateID"].notna().all()
        ),
        "saved_compile_parent_ids_match_attempt_ids": (
            attempts["CompileParentEventID"].equals(attempts["EventID"])
        ),
        "saved_compile_code_state_ids_match": (
            attempts["CompileCodeStateID"].equals(attempts["CodeStateID"])
        ),
    }

    stored_counts = diagnostics.groupby("AttemptID", dropna=False).size()
    expected_counts = attempts["EventID"].map(stored_counts).fillna(0).astype("int64")
    actual_counts = pd.to_numeric(attempts["DiagnosticCount"], errors="raise")
    checks["saved_diagnostics_match_attempt_counts"] = bool(
        actual_counts.equals(expected_counts)
    )

    group_values = attempts.groupby(GROUP_COLUMNS, sort=False, dropna=False)
    checks["saved_order_is_monotonic_within_groups"] = bool(
        attempts.groupby(GROUP_COLUMNS, sort=False, dropna=False)["Order"]
        .apply(lambda values: values.is_monotonic_increasing)
        .all()
    )
    expected_attempt_numbers = group_values.cumcount() + 1
    actual_attempt_numbers = pd.to_numeric(
        attempts["AttemptNumber"], errors="raise"
    ).astype("int64")
    checks["saved_attempt_numbers_are_sequential"] = bool(
        actual_attempt_numbers.equals(expected_attempt_numbers)
    )
    saved_score = pd.to_numeric(attempts["Score"], errors="coerce")
    checks["saved_score_missingness_preserved"] = (
        int(saved_score.isna().sum()) == summary["score_missing_attempts"]
    )
    expected_previous = group_values["Score"].shift(1)
    actual_previous = pd.to_numeric(attempts["PreviousScore"], errors="coerce")
    checks["saved_previous_scores_match_adjacent_attempts"] = bool(
        np.allclose(
            actual_previous.to_numpy(dtype="float64", na_value=np.nan),
            expected_previous.to_numpy(dtype="float64", na_value=np.nan),
            equal_nan=True,
        )
    )
    calculated_delta = pd.to_numeric(attempts["Score"], errors="coerce") - actual_previous
    actual_delta = pd.to_numeric(attempts["ScoreDelta"], errors="coerce")
    checks["saved_score_deltas_match"] = bool(
        np.allclose(
            actual_delta.to_numpy(dtype="float64", na_value=np.nan),
            calculated_delta.to_numpy(dtype="float64", na_value=np.nan),
            equal_nan=True,
        )
    )
    first_or_missing = expected_previous.isna() | pd.to_numeric(
        attempts["Score"], errors="coerce"
    ).isna()
    expected_classification = np.select(
        [
            calculated_delta.gt(0.05),
            calculated_delta.lt(-0.05),
        ],
        ["IMPROVING", "REGRESSING"],
        default="STAGNANT",
    )
    expected_classification = pd.Series(
        expected_classification, index=attempts.index
    )
    expected_classification.loc[first_or_missing] = "UNCLASSIFIABLE"
    checks["saved_progress_classifications_match"] = bool(
        attempts["ProgressClassification"].eq(expected_classification).all()
    )

    return checks


def write_summary_outputs(
    output_dir: Path,
    summary: dict[str, Any],
    event_counts: dict[str, int],
) -> None:
    with (output_dir / "reconstruction_summary.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            summary,
            file,
            indent=2,
            sort_keys=True,
            default=convert_numpy_scalar,
        )
        file.write("\n")

    summary_rows = [
        {
            "metric": key,
            "value": json.dumps(
                value, sort_keys=True, default=convert_numpy_scalar
            )
            if isinstance(value, (dict, list))
            else value,
        }
        for key, value in summary.items()
    ]
    pd.DataFrame(summary_rows).to_csv(
        output_dir / "reconstruction_summary.csv", index=False
    )
    pd.DataFrame(
        [{"EventType": key, "EventCount": value} for key, value in event_counts.items()]
    ).to_csv(output_dir / "event_counts.csv", index=False)
    pd.DataFrame(
        [
            {"ProgressClassification": key, "AttemptCount": value}
            for key, value in summary["progress_classification_counts"].items()
        ]
    ).to_csv(output_dir / "progress_classification_counts.csv", index=False)
    pd.DataFrame(
        [
            {"CompileResult": key, "AttemptCount": value}
            for key, value in summary["compile_outcome_counts"].items()
        ]
    ).to_csv(output_dir / "compile_outcome_counts.csv", index=False)


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=repository_root / "dataset",
        help="Dataset directory (default: repository dataset/)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "analysis" / "outputs",
        help="Output directory (default: analysis/outputs/)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = args.dataset_dir / "Data"
    main_path = data_dir / "MainTable.csv"
    code_states_path = data_dir / "CodeStates" / "CodeStates.csv"
    subject_path = data_dir / "LinkTables" / "Subject.csv"
    for input_path in (main_path, code_states_path, subject_path):
        if not input_path.is_file():
            raise FileNotFoundError(f"Required dataset file not found: {input_path}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    main, event_counts = load_and_validate_events(main_path)
    attempts, diagnostics, summary = build_outputs(
        main, code_states_path, subject_path
    )

    attempts_path = args.output_dir / "reconstructed_attempts.csv"
    diagnostics_path = args.output_dir / "attempt_diagnostics.csv"
    attempts.to_csv(attempts_path, index=False, na_rep="")
    diagnostics.to_csv(diagnostics_path, index=False, na_rep="")
    saved_checks = validate_saved_outputs(
        attempts_path, diagnostics_path, summary
    )
    summary["saved_output_validations"] = saved_checks
    summary["validation_passed"] = bool(
        summary["validation_passed"] and all(saved_checks.values())
    )
    if not summary["validation_passed"]:
        raise ValueError(
            f"Saved output validation failed: "
            f"{[key for key, passed in saved_checks.items() if not passed]}"
        )
    write_summary_outputs(args.output_dir, summary, event_counts)
    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            default=convert_numpy_scalar,
        )
    )


if __name__ == "__main__":
    main()
