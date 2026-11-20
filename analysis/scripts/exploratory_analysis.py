"""Explore the approved CodeWorkout operational-attempt reconstruction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


EXPECTED_ATTEMPTS = 69_627
GROUP_COLUMNS = ["SubjectID", "AssignmentID", "ProblemID"]
PROGRESS_CLASSES = ["IMPROVING", "STAGNANT", "REGRESSING"]
CLASS_COLORS = {
    "IMPROVING": "#2a7f62",
    "STAGNANT": "#64748b",
    "REGRESSING": "#b54747",
}
BASELINE_COLORS = ["#3973ac", "#d18b27", "#7a5798"]
ATTEMPT_COLUMNS = [
    "EventID",
    "CompileEventID",
    "SubjectID",
    "AssignmentID",
    "ProblemID",
    "Order",
    "Score",
    "AttemptNumber",
    "PreviousScore",
    "ScoreDelta",
    "ProgressClassification",
    "CompileResult",
    "DiagnosticCount",
]


def json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return json_safe(value.item())
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def parse_numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    raw = frame[column].astype("string").str.strip()
    parsed = pd.to_numeric(raw.replace("", pd.NA), errors="coerce")
    invalid = raw.ne("") & parsed.isna()
    if invalid.any():
        raise ValueError(f"{column} contains nonnumeric, nonempty values")
    return parsed.astype("float64")


def distribution_stats(values: pd.Series | np.ndarray) -> dict[str, Any]:
    numeric = pd.Series(values, dtype="float64").dropna()
    if numeric.empty:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "std": None,
            "min": None,
            "q1": None,
            "q3": None,
            "max": None,
        }
    return {
        "count": int(numeric.count()),
        "mean": float(numeric.mean()),
        "median": float(numeric.median()),
        "std": float(numeric.std(ddof=1)) if len(numeric) > 1 else None,
        "min": float(numeric.min()),
        "q1": float(numeric.quantile(0.25)),
        "q3": float(numeric.quantile(0.75)),
        "max": float(numeric.max()),
    }


def load_approved_outputs(
    output_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    reconstruction_summary_path = output_dir / "reconstruction_summary.json"
    attempts_path = output_dir / "reconstructed_attempts.csv"
    diagnostics_path = output_dir / "attempt_diagnostics.csv"
    for path in (reconstruction_summary_path, attempts_path, diagnostics_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required approved reconstruction output missing: {path}")

    reconstruction_summary = json.loads(
        reconstruction_summary_path.read_text(encoding="utf-8")
    )
    saved_checks = reconstruction_summary.get("saved_output_validations", {})
    if reconstruction_summary.get("validation_passed") is not True or not saved_checks:
        raise ValueError("Reconstruction summary does not report successful validation")
    if not all(saved_checks.values()):
        raise ValueError("One or more saved reconstruction validations failed")
    if reconstruction_summary.get("attempt_count") != EXPECTED_ATTEMPTS:
        raise ValueError(
            "Reconstruction summary does not report the expected 69,627 attempts"
        )

    attempts = pd.read_csv(
        attempts_path,
        usecols=ATTEMPT_COLUMNS,
        dtype={
            "EventID": "string",
            "CompileEventID": "string",
            "SubjectID": "string",
            "AssignmentID": "string",
            "ProblemID": "string",
        },
        keep_default_na=False,
    )
    if len(attempts) != EXPECTED_ATTEMPTS:
        raise ValueError(
            f"Expected {EXPECTED_ATTEMPTS:,} attempts in approved output, found {len(attempts):,}"
        )
    if attempts["EventID"].isna().any() or attempts["EventID"].str.strip().eq("").any():
        raise ValueError("Reconstructed attempts contain missing EventID values")
    if attempts["EventID"].duplicated().any():
        raise ValueError("Reconstructed attempts contain duplicate EventID values")
    for column in GROUP_COLUMNS:
        if attempts[column].isna().any() or attempts[column].str.strip().eq("").any():
            raise ValueError(f"Reconstructed attempts contain missing {column} values")

    for column in ("Order", "AttemptNumber", "DiagnosticCount"):
        attempts[column] = pd.to_numeric(attempts[column], errors="raise").astype("int64")
    for column in ("Score", "PreviousScore", "ScoreDelta"):
        attempts[column] = parse_numeric_column(attempts, column)

    if attempts["Score"].isna().sum() != reconstruction_summary.get(
        "score_missing_attempts"
    ):
        raise ValueError("Score missingness differs from the approved reconstruction summary")
    if attempts["CompileResult"].isin(["Success", "Error"]).sum() != len(attempts):
        raise ValueError("Unexpected or missing CompileResult in reconstructed attempts")
    if set(attempts["ProgressClassification"]) - {
        "IMPROVING",
        "STAGNANT",
        "REGRESSING",
        "UNCLASSIFIABLE",
    }:
        raise ValueError("Unexpected progress classification in reconstructed attempts")

    group_sizes = attempts.groupby(GROUP_COLUMNS, sort=False, dropna=False).size()
    expected_numbers = (
        attempts.groupby(GROUP_COLUMNS, sort=False, dropna=False).cumcount() + 1
    )
    if not attempts["AttemptNumber"].equals(expected_numbers):
        raise ValueError("AttemptNumber is not sequential within student-problem groups")
    order_checks = attempts.groupby(GROUP_COLUMNS, sort=False, dropna=False)[
        "Order"
    ].apply(lambda values: values.is_monotonic_increasing)
    if not order_checks.all():
        raise ValueError("Attempts are not ordered by Order within every group")

    grouped = attempts.groupby(GROUP_COLUMNS, sort=False, dropna=False)
    expected_previous = grouped["Score"].shift(1)
    expected_delta = attempts["Score"] - expected_previous
    if not np.allclose(
        attempts["PreviousScore"].to_numpy(dtype="float64", na_value=np.nan),
        expected_previous.to_numpy(dtype="float64", na_value=np.nan),
        equal_nan=True,
    ):
        raise ValueError("PreviousScore does not match the preceding attempt")
    if not np.allclose(
        attempts["ScoreDelta"].to_numpy(dtype="float64", na_value=np.nan),
        expected_delta.to_numpy(dtype="float64", na_value=np.nan),
        equal_nan=True,
    ):
        raise ValueError("ScoreDelta does not match adjacent scores")
    expected_classes = np.select(
        [expected_delta.gt(0.05), expected_delta.lt(-0.05)],
        ["IMPROVING", "REGRESSING"],
        default="STAGNANT",
    )
    expected_classes = pd.Series(expected_classes, index=attempts.index)
    expected_classes.loc[expected_delta.isna()] = "UNCLASSIFIABLE"
    if not attempts["ProgressClassification"].eq(expected_classes).all():
        raise ValueError("Progress classifications do not match the approved threshold")
    if len(group_sizes) != reconstruction_summary.get("attempt_groups"):
        raise ValueError("Attempt group count differs from the approved reconstruction")

    diagnostics = pd.read_csv(
        diagnostics_path,
        usecols=["EventID", "ParentEventID", "AttemptID", "CompileEventID"],
        dtype={
            "EventID": "string",
            "ParentEventID": "string",
            "AttemptID": "string",
            "CompileEventID": "string",
        },
        keep_default_na=False,
    )
    if len(diagnostics) != reconstruction_summary.get("diagnostic_event_count"):
        raise ValueError("Diagnostic row count differs from the approved reconstruction")
    if diagnostics["EventID"].duplicated().any():
        raise ValueError("Duplicate diagnostic EventID in approved output")
    if not diagnostics["ParentEventID"].equals(diagnostics["CompileEventID"]):
        raise ValueError("A diagnostic is not attached to its recorded Compile event")
    attempt_to_compile = attempts.set_index("EventID")["CompileEventID"]
    if not diagnostics["AttemptID"].isin(attempts["EventID"]).all():
        raise ValueError("A diagnostic references an unknown operational attempt")
    if not diagnostics["CompileEventID"].equals(
        diagnostics["AttemptID"].map(attempt_to_compile)
    ):
        raise ValueError("Diagnostic attempt and Compile links do not agree")
    diagnostic_counts = diagnostics.groupby("AttemptID", sort=False).size()
    expected_diagnostic_counts = (
        attempts["EventID"].map(diagnostic_counts).fillna(0).astype("int64")
    )
    if not attempts["DiagnosticCount"].equals(expected_diagnostic_counts):
        raise ValueError("DiagnosticCount does not match the linked diagnostic records")

    return attempts, diagnostics, reconstruction_summary


def summarize_score(attempts: pd.DataFrame) -> dict[str, Any]:
    stats = distribution_stats(attempts["Score"])
    stats.update(
        {
            "attempt_rows": int(len(attempts)),
            "missing_score_rows": int(attempts["Score"].isna().sum()),
            "standard_deviation_definition": "sample standard deviation (ddof=1)",
            "quartile_definition": "linear empirical quantiles",
        }
    )
    return stats


def summarize_compilation(
    attempts: pd.DataFrame, diagnostics: pd.DataFrame
) -> pd.DataFrame:
    counts = attempts["CompileResult"].value_counts().reindex(
        ["Success", "Error"], fill_value=0
    )
    if int(counts.sum()) != len(attempts):
        raise ValueError("Compilation outcome denominator does not cover all attempts")
    diagnostic_counts = attempts.groupby("CompileResult")["DiagnosticCount"].sum()
    if int(diagnostic_counts.get("Success", 0)) != 0:
        raise ValueError("Successful compilations unexpectedly have diagnostics")
    if int(diagnostic_counts.get("Error", 0)) != len(diagnostics):
        raise ValueError("Failed-compilation diagnostic count does not match diagnostic rows")

    return pd.DataFrame(
        [
            {
                "CompileResult": outcome,
                "AttemptCount": int(counts[outcome]),
                "AttemptDenominator": int(len(attempts)),
                "AttemptPercent": float(counts[outcome] / len(attempts) * 100),
                "DiagnosticEventCount": int(diagnostic_counts.get(outcome, 0)),
            }
            for outcome in ("Success", "Error")
        ]
    )


def summarize_submissions(
    attempts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    student_attempts = attempts.groupby("SubjectID", sort=True).agg(
        AttemptCount=("EventID", "size"),
        ProblemCount=("ProblemID", "nunique"),
    )
    student_groups = (
        attempts[["SubjectID", "AssignmentID", "ProblemID"]]
        .drop_duplicates()
        .groupby("SubjectID", sort=True)
        .size()
        .rename("StudentProblemGroupCount")
    )
    student_attempts = student_attempts.join(student_groups).reset_index()

    problem_attempts = attempts.groupby("ProblemID", sort=True).agg(
        AttemptCount=("EventID", "size"),
        StudentCount=("SubjectID", "nunique"),
    )
    problem_attempts = problem_attempts["AttemptCount"]
    student_stats = distribution_stats(student_attempts["AttemptCount"])
    problem_stats = distribution_stats(problem_attempts)
    behavior_summary = pd.DataFrame(
        [
            {
                "Measure": "Operational attempts per student",
                "UnitCount": int(len(student_attempts)),
                **student_stats,
            },
            {
                "Measure": "Operational attempts per ProblemID",
                "UnitCount": int(len(problem_attempts)),
                **problem_stats,
            },
        ]
    )

    per_problem = attempts.groupby("ProblemID", sort=True).agg(
        AttemptCount=("EventID", "size"),
        ScoredAttemptCount=("Score", "count"),
        StudentCount=("SubjectID", "nunique"),
        MeanScore=("Score", "mean"),
        MedianScore=("Score", "median"),
        ScoreStd=("Score", "std"),
    )
    quartiles = attempts.groupby("ProblemID", sort=True)["Score"].quantile(
        [0.25, 0.75]
    ).unstack()
    quartiles.columns = ["ScoreQ1", "ScoreQ3"]
    per_problem = per_problem.join(quartiles).reset_index()
    per_problem["MissingScoreCount"] = (
        per_problem["AttemptCount"] - per_problem["ScoredAttemptCount"]
    )
    return behavior_summary, student_attempts, per_problem


def summarize_attempt_positions(attempts: pd.DataFrame) -> pd.DataFrame:
    position = attempts.groupby("AttemptNumber", sort=True).agg(
        AttemptCount=("EventID", "size"),
        ScoredAttemptCount=("Score", "count"),
        MeanScore=("Score", "mean"),
        MedianScore=("Score", "median"),
        ScoreStd=("Score", "std"),
        StudentCount=("SubjectID", "nunique"),
    )
    position["MissingScoreCount"] = (
        position["AttemptCount"] - position["ScoredAttemptCount"]
    )
    position["ProblemGroupCount"] = (
        attempts.drop_duplicates([*GROUP_COLUMNS, "AttemptNumber"])
        .groupby("AttemptNumber", sort=True)
        .size()
    )
    return position.reset_index()


def summarize_progress(
    attempts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    first_mask = attempts["AttemptNumber"].eq(1)
    nonfirst = attempts.loc[~first_mask]
    classifiable = nonfirst.loc[
        nonfirst["ScoreDelta"].notna()
        & nonfirst["ProgressClassification"].isin(PROGRESS_CLASSES)
    ]
    unclassifiable_nonfirst = nonfirst.loc[
        nonfirst["ProgressClassification"].eq("UNCLASSIFIABLE")
    ]
    counts = classifiable["ProgressClassification"].value_counts().reindex(
        PROGRESS_CLASSES, fill_value=0
    )
    denominator = int(counts.sum())
    if denominator == 0:
        raise ValueError("No classifiable adjacent-attempt transitions")
    transition_summary = pd.DataFrame(
        [
            {
                "ProgressClassification": label,
                "TransitionCount": int(counts[label]),
                "TransitionDenominator": denominator,
                "TransitionPercent": float(counts[label] / denominator * 100),
            }
            for label in PROGRESS_CLASSES
        ]
    )

    all_students = pd.Index(
        attempts["SubjectID"].drop_duplicates(), name="SubjectID"
    )
    per_student_counts = (
        classifiable.groupby(["SubjectID", "ProgressClassification"], sort=False)
        .size()
        .unstack(fill_value=0)
        .reindex(index=all_students, columns=PROGRESS_CLASSES, fill_value=0)
        .astype("int64")
    )
    per_student_counts["TransitionCount"] = per_student_counts[PROGRESS_CLASSES].sum(
        axis=1
    )
    per_student = (
        attempts.groupby("SubjectID", sort=False)
        .agg(
            AttemptCount=("EventID", "size"),
            ProblemGroupCount=("ProblemID", "nunique"),
        )
        .join(
            attempts[["SubjectID", *GROUP_COLUMNS[1:]]]
            .drop_duplicates()
            .groupby("SubjectID", sort=False)
            .size()
            .rename("StudentProblemGroupCount")
        )
        .join(per_student_counts)
    )
    per_student = per_student.reset_index()
    for label in PROGRESS_CLASSES:
        per_student[f"{label}Share"] = (
            per_student[label]
            / per_student["TransitionCount"].replace(0, np.nan)
        )

    share_rows = []
    students_with_transitions = per_student.loc[
        per_student["TransitionCount"].gt(0)
    ]
    for label in PROGRESS_CLASSES:
        shares = students_with_transitions[f"{label}Share"]
        share_rows.append(
            {
                "ProgressClassification": label,
                "StudentsWithTransitions": int(len(students_with_transitions)),
                "MeanStudentShare": float(shares.mean()),
                "MedianStudentShare": float(shares.median()),
                "Q1StudentShare": float(shares.quantile(0.25)),
                "Q3StudentShare": float(shares.quantile(0.75)),
                "StudentsOverHalfTransitions": int(shares.gt(0.5).sum()),
                "StudentsOverHalfPercent": float(shares.gt(0.5).mean() * 100),
            }
        )
    student_share_summary = pd.DataFrame(share_rows)

    details = {
        "attempt_rows": int(len(attempts)),
        "first_attempt_rows_excluded_from_transition_percentages": int(
            first_mask.sum()
        ),
        "nonfirst_unclassifiable_rows": int(len(unclassifiable_nonfirst)),
        "classifiable_transition_count": denominator,
        "student_count": int(attempts["SubjectID"].nunique()),
        "students_with_classifiable_transitions": int(
            students_with_transitions["SubjectID"].nunique()
        ),
        "students_without_classifiable_transitions": int(
            attempts["SubjectID"].nunique()
            - students_with_transitions["SubjectID"].nunique()
        ),
        "per_student_share_statistics_use_student_as_unit": True,
    }
    return transition_summary, per_student, student_share_summary, details


def summarize_initial_score_groups(
    attempts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    first_attempts = attempts.loc[attempts["AttemptNumber"].eq(1)]
    first_per_group = first_attempts.groupby(
        GROUP_COLUMNS, sort=False, dropna=False
    ).agg(
        FirstAttemptScore=("Score", "first"),
        FirstAttemptScoreCount=("Score", "count"),
    )
    if len(first_per_group) != attempts.groupby(GROUP_COLUMNS, dropna=False).ngroups:
        raise ValueError("Expected one first-attempt row per student-problem group")
    baseline = first_per_group.reset_index().groupby("SubjectID", sort=True).agg(
        MeanInitialProblemScore=("FirstAttemptScore", "mean"),
        InitialProblemGroupCount=("FirstAttemptScore", "size"),
        InitialScoreCount=("FirstAttemptScore", "count"),
    )
    available = baseline["MeanInitialProblemScore"].dropna()
    if available.nunique() < 2:
        raise ValueError("Initial-score cohorts are not meaningful: fewer than two values")

    quantile_codes, bin_edges = pd.qcut(
        available,
        q=3,
        labels=False,
        retbins=True,
        duplicates="drop",
    )
    quantile_codes = pd.Series(quantile_codes, index=available.index).astype("Int64")
    bin_count = len(bin_edges) - 1
    if bin_count < 2:
        raise ValueError("Initial-score grouping produced fewer than two bins")
    labels = (
        ["Low", "Middle", "High"][:bin_count]
        if bin_count == 3
        else [f"Quantile {index + 1}" for index in range(bin_count)]
    )
    code_to_label = dict(enumerate(labels))
    baseline["InitialScoreGroup"] = "UNCLASSIFIABLE"
    baseline.loc[quantile_codes.index, "InitialScoreGroup"] = (
        quantile_codes.map(code_to_label).astype("string")
    )
    baseline = baseline.reset_index()

    group_rows = []
    for index, label in enumerate(labels):
        selected = baseline.loc[baseline["InitialScoreGroup"].eq(label)]
        group_rows.append(
            {
                "InitialScoreGroup": label,
                "StudentCount": int(len(selected)),
                "MinStudentBaseline": float(
                    selected["MeanInitialProblemScore"].min()
                ),
                "MaxStudentBaseline": float(
                    selected["MeanInitialProblemScore"].max()
                ),
                "LowerBinEdge": float(bin_edges[index]),
                "UpperBinEdge": float(bin_edges[index + 1]),
                "LowerEdgeInclusive": bool(index == 0),
                "UpperEdgeInclusive": True,
            }
        )
    group_summary = pd.DataFrame(group_rows)

    student_positions = attempts.groupby(
        ["SubjectID", "AttemptNumber"], sort=False, dropna=False
    ).agg(
        StudentMeanScore=("Score", "mean"),
        ProblemGroupsAtPosition=("EventID", "size"),
        ScoredAttemptsAtPosition=("Score", "count"),
    )
    student_positions = student_positions.reset_index().merge(
        baseline[["SubjectID", "InitialScoreGroup"]],
        on="SubjectID",
        how="left",
        validate="many_to_one",
    )
    progression = (
        student_positions.groupby(
            ["InitialScoreGroup", "AttemptNumber"], sort=True, observed=True
        )
        .agg(
            StudentCount=("SubjectID", "nunique"),
            StudentsWithScore=("StudentMeanScore", "count"),
            MeanStudentScore=("StudentMeanScore", "mean"),
            MedianStudentScore=("StudentMeanScore", "median"),
            MedianProblemGroups=("ProblemGroupsAtPosition", "median"),
        )
        .reset_index()
    )
    info = {
        "baseline_definition": (
            "Per student, mean of first-attempt scores across that student's "
            "student-assignment-problem groups"
        ),
        "progression_unit": (
            "Each student contributes one mean score per attempt position, "
            "averaged across their problem groups at that position"
        ),
        "grouping_method": "tertiles of student baseline means using pandas qcut",
        "baseline_student_count": int(len(baseline)),
        "baseline_students_with_score": int(available.count()),
        "baseline_students_without_score": int(baseline["MeanInitialProblemScore"].isna().sum()),
        "bin_count": int(bin_count),
    }
    return baseline, group_summary, progression, info


def save_figures(
    output_dir: Path,
    attempts: pd.DataFrame,
    score_summary: dict[str, Any],
    compilation: pd.DataFrame,
    position: pd.DataFrame,
    transitions: pd.DataFrame,
    per_student_progress: pd.DataFrame,
    problem_summary: pd.DataFrame,
    baseline_groups: pd.DataFrame,
    initial_progression: pd.DataFrame,
    progress_details: dict[str, Any],
) -> list[str]:
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    plt.rcParams.update(
        {
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 8,
            "legend.fontsize": 9,
            "figure.dpi": 120,
        }
    )

    values = attempts["Score"].dropna()
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.hist(
        values,
        bins=np.linspace(0, 1, 26),
        color="#4c78a8",
        edgecolor="white",
        linewidth=0.6,
    )
    ax.axvline(
        score_summary["mean"],
        color="#b54747",
        linestyle="--",
        linewidth=1.8,
        label=f"Mean {score_summary['mean']:.3f}",
    )
    ax.axvline(
        score_summary["median"],
        color="#d18b27",
        linestyle=":",
        linewidth=2,
        label=f"Median {score_summary['median']:.3f}",
    )
    ax.set(
        xlim=(0, 1),
        xlabel="Observed score",
        ylabel="Operational attempts",
        title=(
            "Overall score distribution "
            f"(n={int(values.count()):,}; missing={score_summary['missing_score_rows']:,})"
        ),
    )
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    path = plot_dir / "score_distribution.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    paths.append(path.name)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        compilation["CompileResult"],
        compilation["AttemptCount"],
        color=["#2a7f62", "#b54747"],
        width=0.62,
    )
    for bar, row in zip(bars, compilation.itertuples(index=False)):
        ax.annotate(
            f"{row.AttemptCount:,}\n{row.AttemptPercent:.1f}%",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set(
        ylabel="Operational attempts",
        title=(
            f"Compilation outcomes per attempt (n={len(attempts):,})\n"
            f"{int(compilation['DiagnosticEventCount'].sum()):,} diagnostic events "
            "are separate from compilation outcomes"
        ),
    )
    ax.set_ylim(0, float(compilation["AttemptCount"].max()) * 1.18)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    path = plot_dir / "compilation_outcomes.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    paths.append(path.name)

    fig, (score_ax, count_ax) = plt.subplots(
        2,
        1,
        figsize=(10, 7.5),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    score_ax.plot(
        position["AttemptNumber"],
        position["MeanScore"],
        color="#4c78a8",
        marker="o",
        markersize=3,
        linewidth=1.5,
        label="Mean score",
    )
    score_ax.plot(
        position["AttemptNumber"],
        position["MedianScore"],
        color="#e08b36",
        marker="s",
        markersize=3,
        linewidth=1.3,
        label="Median score",
    )
    score_ax.set(
        ylabel="Score",
        ylim=(0, 1),
        title="Observed scores by attempt position within a problem group",
    )
    score_ax.legend(frameon=False)
    score_ax.grid(alpha=0.2)
    count_ax.bar(
        position["AttemptNumber"],
        position["AttemptCount"],
        color="#9bb7d4",
        width=0.8,
    )
    count_ax.set(
        xlabel="Attempt number within SubjectID-AssignmentID-ProblemID",
        ylabel="Attempts",
    )
    count_ax.grid(axis="y", alpha=0.2)
    count_ax.set_xticks(
        np.arange(1, int(position["AttemptNumber"].max()) + 1, 5)
    )
    fig.suptitle(
        "Attempt-position summaries (attempt-weighted; lower panel shows support)",
        y=1.01,
    )
    fig.tight_layout()
    path = plot_dir / "score_by_attempt_number.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    paths.append(path.name)

    fig, (overall_ax, student_ax) = plt.subplots(
        1, 2, figsize=(12, 5.5), gridspec_kw={"width_ratios": [1, 1.35]}
    )
    bars = overall_ax.barh(
        transitions["ProgressClassification"],
        transitions["TransitionPercent"],
        color=[CLASS_COLORS[label] for label in transitions["ProgressClassification"]],
    )
    for bar, row in zip(bars, transitions.itertuples(index=False)):
        overall_ax.annotate(
            f"{row.TransitionPercent:.1f}% ({row.TransitionCount:,})",
            (bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
        )
    overall_ax.set(
        xlabel=f"Share of classifiable transitions (n={int(transitions['TransitionDenominator'].iloc[0]):,})",
        title="Transition outcomes\n(first attempts excluded)",
    )
    overall_ax.set_xlim(0, max(60, float(transitions["TransitionPercent"].max()) * 1.35))
    overall_ax.grid(axis="x", alpha=0.2)

    share_columns = [f"{label}Share" for label in PROGRESS_CLASSES]
    student_values = [
        per_student_progress.loc[
            per_student_progress["TransitionCount"].gt(0), column
        ].dropna()
        for column in share_columns
    ]
    student_labels = [
        f"{label}\n(n={len(values):,})"
        for label, values in zip(PROGRESS_CLASSES, student_values)
    ]
    student_ax.boxplot(
        student_values,
        tick_labels=student_labels,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#111827", "linewidth": 1.5},
        boxprops={"facecolor": "#dbe6f0", "edgecolor": "#55718b"},
        whiskerprops={"color": "#55718b"},
        capprops={"color": "#55718b"},
    )
    student_ax.axhline(0.5, color="#b54747", linestyle="--", linewidth=1)
    student_ax.set(
        ylabel="Per-student share of transitions",
        ylim=(0, 1),
        title=(
            "Distribution across students\n"
            f"(n={progress_details['students_with_classifiable_transitions']:,}; "
            "one share per student)"
        ),
    )
    student_ax.grid(axis="y", alpha=0.2)
    fig.suptitle("Adjacent-attempt progress patterns", y=1.02)
    fig.tight_layout()
    path = plot_dir / "progress_transitions.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    paths.append(path.name)

    plot_problem = problem_summary.sort_values(
        ["MedianScore", "MeanScore", "ProblemID"],
        ascending=[True, True, True],
        kind="mergesort",
    )
    problem_values = [
        attempts.loc[attempts["ProblemID"].eq(problem_id), "Score"].dropna().to_numpy()
        for problem_id in plot_problem["ProblemID"]
    ]
    problem_labels = [
        f"Problem {row.ProblemID} (n={row.AttemptCount:,})"
        for row in plot_problem.itertuples(index=False)
    ]
    fig, ax = plt.subplots(figsize=(10, 15))
    ax.boxplot(
        problem_values,
        orientation="horizontal",
        tick_labels=problem_labels,
        patch_artist=True,
        showfliers=False,
        whis=1.5,
        medianprops={"color": "#111827", "linewidth": 1.2},
        boxprops={"facecolor": "#c9d9e8", "edgecolor": "#55718b"},
        whiskerprops={"color": "#55718b"},
        capprops={"color": "#55718b"},
    )
    ax.set(
        xlabel="Observed score",
        xlim=(0, 1),
        title=(
            "Score distributions by ProblemID\n"
            "Boxes show IQR; whiskers use 1.5×IQR; outlier markers suppressed"
        ),
    )
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    path = plot_dir / "problem_score_distributions.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    paths.append(path.name)

    fig, (cohort_ax, support_ax) = plt.subplots(
        2,
        1,
        figsize=(10, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    group_labels = baseline_groups["InitialScoreGroup"].tolist()
    color_by_group = {
        label: BASELINE_COLORS[index % len(BASELINE_COLORS)]
        for index, label in enumerate(group_labels)
    }
    for row in baseline_groups.itertuples(index=False):
        label = row.InitialScoreGroup
        cohort = initial_progression.loc[
            initial_progression["InitialScoreGroup"].eq(label)
        ]
        cohort_ax.plot(
            cohort["AttemptNumber"],
            cohort["MeanStudentScore"],
            marker="o",
            markersize=3,
            linewidth=1.4,
            color=color_by_group[label],
            label=f"{label} baseline (n={row.StudentCount} students)",
        )
        support_ax.plot(
            cohort["AttemptNumber"],
            cohort["StudentCount"],
            color=color_by_group[label],
            linewidth=1.4,
            label=label,
        )
    cohort_ax.set(
        ylabel="Mean of student-level mean scores",
        ylim=(0, 1),
        title="Progression by tertile of students' initial mean scores",
    )
    cohort_ax.legend(frameon=False)
    cohort_ax.grid(alpha=0.2)
    support_ax.set(
        xlabel="Attempt number within SubjectID-AssignmentID-ProblemID",
        ylabel="Students",
    )
    support_ax.grid(axis="y", alpha=0.2)
    support_ax.set_xticks(
        np.arange(
            1,
            int(initial_progression["AttemptNumber"].max()) + 1,
            5,
        )
    )
    fig.suptitle(
        "Student-level cohort summaries (lower panel shows changing support)",
        y=1.01,
    )
    fig.tight_layout()
    path = plot_dir / "initial_score_group_progression.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    paths.append(path.name)

    if len(paths) < 4 or len(paths) > 6:
        raise ValueError(f"Expected 4–6 figures, generated {len(paths)}")
    return paths


def write_outputs(
    output_dir: Path,
    attempts: pd.DataFrame,
    diagnostics: pd.DataFrame,
    reconstruction_summary: dict[str, Any],
) -> dict[str, Any]:
    score_summary = summarize_score(attempts)
    compilation = summarize_compilation(attempts, diagnostics)
    behavior, student_attempts, problem_summary = summarize_submissions(attempts)
    position = summarize_attempt_positions(attempts)
    (
        transitions,
        per_student_progress,
        student_share_summary,
        progress_details,
    ) = summarize_progress(attempts)
    (
        baseline_students,
        baseline_groups,
        initial_progression,
        baseline_details,
    ) = summarize_initial_score_groups(attempts)

    validation_checks = {
        "score_rows_cover_attempts": (
            score_summary["count"] + score_summary["missing_score_rows"]
            == len(attempts)
        ),
        "compilation_outcomes_cover_attempts": (
            int(compilation["AttemptCount"].sum()) == len(attempts)
            and bool(
                np.isclose(compilation["AttemptPercent"].sum(), 100.0)
            )
        ),
        "diagnostic_events_match_attempt_diagnostic_counts": (
            int(attempts["DiagnosticCount"].sum()) == len(diagnostics)
        ),
        "student_attempt_counts_cover_attempts": (
            int(student_attempts["AttemptCount"].sum()) == len(attempts)
            and len(student_attempts) == attempts["SubjectID"].nunique()
        ),
        "problem_attempt_counts_cover_attempts": (
            int(problem_summary["AttemptCount"].sum()) == len(attempts)
            and len(problem_summary) == attempts["ProblemID"].nunique()
        ),
        "attempt_position_counts_cover_attempts": (
            int(position["AttemptCount"].sum()) == len(attempts)
        ),
        "progress_denominator_and_percentages_are_consistent": (
            int(transitions["TransitionCount"].sum())
            == progress_details["classifiable_transition_count"]
            and bool(np.isclose(transitions["TransitionPercent"].sum(), 100.0))
            and int(
                per_student_progress["TransitionCount"].sum()
            )
            == progress_details["classifiable_transition_count"]
        ),
        "baseline_groups_cover_scored_students": (
            int(baseline_groups["StudentCount"].sum())
            == baseline_details["baseline_students_with_score"]
        ),
    }
    if not all(validation_checks.values()):
        failed = [key for key, passed in validation_checks.items() if not passed]
        raise ValueError(f"EDA summary validation failed: {failed}")

    output_dir.mkdir(parents=True, exist_ok=True)
    score_frame = pd.DataFrame([score_summary])
    score_frame.to_csv(output_dir / "score_summary.csv", index=False)
    compilation.to_csv(output_dir / "compilation_outcomes.csv", index=False)
    behavior.to_csv(output_dir / "submission_behavior_summary.csv", index=False)
    student_attempts.to_csv(output_dir / "student_attempt_counts.csv", index=False)
    problem_summary.to_csv(output_dir / "problem_performance_summary.csv", index=False)
    position.to_csv(output_dir / "attempt_number_summary.csv", index=False)
    transitions.to_csv(output_dir / "progress_transition_summary.csv", index=False)
    per_student_progress.to_csv(
        output_dir / "per_student_progress_summary.csv", index=False, na_rep=""
    )
    student_share_summary.to_csv(
        output_dir / "per_student_share_summary.csv", index=False
    )
    baseline_students.to_csv(
        output_dir / "initial_score_student_groups.csv", index=False, na_rep=""
    )
    baseline_groups.to_csv(
        output_dir / "initial_score_group_summary.csv", index=False
    )
    initial_progression.to_csv(
        output_dir / "initial_score_group_progression.csv", index=False, na_rep=""
    )

    figures = save_figures(
        output_dir,
        attempts,
        score_summary,
        compilation,
        position,
        transitions,
        per_student_progress,
        problem_summary,
        baseline_groups,
        initial_progression,
        progress_details,
    )

    low_problems = problem_summary.sort_values(
        ["MeanScore", "MedianScore"], kind="mergesort"
    ).head(5)
    high_problems = problem_summary.sort_values(
        ["MeanScore", "MedianScore"], ascending=False, kind="mergesort"
    ).head(5)
    summary = {
        "attempt_count": int(len(attempts)),
        "student_count": int(attempts["SubjectID"].nunique()),
        "problem_count": int(attempts["ProblemID"].nunique()),
        "attempt_group_count": int(
            attempts.groupby(GROUP_COLUMNS, dropna=False).ngroups
        ),
        "score_distribution": score_summary,
        "compilation_outcomes": {
            row.CompileResult: {
                "attempt_count": int(row.AttemptCount),
                "attempt_denominator": int(row.AttemptDenominator),
                "attempt_percent": float(row.AttemptPercent),
                "diagnostic_event_count": int(row.DiagnosticEventCount),
            }
            for row in compilation.itertuples(index=False)
        },
        "diagnostic_event_count": int(len(diagnostics)),
        "attempts_with_diagnostics": int(attempts["DiagnosticCount"].gt(0).sum()),
        "total_diagnostic_count_from_attempts": int(
            attempts["DiagnosticCount"].sum()
        ),
        "attempts_per_student": distribution_stats(
            student_attempts["AttemptCount"]
        ),
        "attempts_per_problem": distribution_stats(
            problem_summary["AttemptCount"]
        ),
        "highest_attempt_count_problems": problem_summary.nlargest(
            5, "AttemptCount"
        )[["ProblemID", "AttemptCount", "StudentCount"]].to_dict(
            orient="records"
        ),
        "attempt_position_count": int(len(position)),
        "maximum_attempt_number": int(position["AttemptNumber"].max()),
        "attempt_position_1": position.iloc[0].to_dict(),
        "attempt_position_2": position.loc[
            position["AttemptNumber"].eq(2)
        ].iloc[0].to_dict(),
        "attempt_position_10": position.loc[
            position["AttemptNumber"].eq(10)
        ].iloc[0].to_dict(),
        "attempt_position_20": position.loc[
            position["AttemptNumber"].eq(20)
        ].iloc[0].to_dict(),
        "attempt_position_last": position.iloc[-1].to_dict(),
        "transition_analysis": {
            **progress_details,
            "classifiable_transition_counts": {
                row.ProgressClassification: int(row.TransitionCount)
                for row in transitions.itertuples(index=False)
            },
            "classifiable_transition_percentages": {
                row.ProgressClassification: float(row.TransitionPercent)
                for row in transitions.itertuples(index=False)
            },
            "per_student_share_summary": student_share_summary.to_dict(
                orient="records"
            ),
        },
        "problem_score_low_mean": low_problems[
            ["ProblemID", "AttemptCount", "StudentCount", "MeanScore", "MedianScore"]
        ].to_dict(orient="records"),
        "problem_score_high_mean": high_problems[
            ["ProblemID", "AttemptCount", "StudentCount", "MeanScore", "MedianScore"]
        ].to_dict(orient="records"),
        "initial_score_groups": {
            **baseline_details,
            "groups": baseline_groups.to_dict(orient="records"),
            "progression_unit": baseline_details["progression_unit"],
        },
        "input_reconstruction_validation_passed": bool(
            reconstruction_summary["validation_passed"]
        ),
        "analysis_validation_checks": validation_checks,
        "analysis_validation_passed": bool(all(validation_checks.values())),
        "package_versions": {
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "figures": figures,
    }
    summary = json_safe(summary)
    with (output_dir / "eda_summary.json").open("w", encoding="utf-8") as file:
        json.dump(
            summary,
            file,
            indent=2,
            sort_keys=True,
            default=json_default,
            allow_nan=False,
        )
        file.write("\n")

    return summary


def main() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = repository_root / "analysis" / "outputs"
    attempts, diagnostics, reconstruction_summary = load_approved_outputs(output_dir)
    summary = write_outputs(
        output_dir,
        attempts,
        diagnostics,
        reconstruction_summary,
    )
    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            default=json_default,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
