# Historical dataset reconstruction: methodology and assumptions

## Scope

This Stage 2 pipeline reconstructs operational programming attempts from the
CodeWorkout Spring 2019 dataset. It uses only `MainTable.csv`,
`CodeStates.csv`, and `Subject.csv` for the primary reconstruction.
`early.csv` and `late.csv` are not inputs to attempt counts, scores, or progress.
The source dataset is read-only; generated files are written to `analysis/outputs/`.

## Operational attempt and event relationships

- One top-level `Run.Program` row is one operational attempt. Its original
  `EventID` is the attempt identifier.
- Each attempt is linked to exactly one `Compile` row where the Compile's
  `ParentEventID` equals the Run.Program `EventID`.
- Every `Compile.Error` row is retained in `attempt_diagnostics.csv` and linked
  to its Compile through `ParentEventID`. `AttemptID` on that row identifies
  the Run.Program ancestor. Diagnostic rows are not attempts.
- Compilation outcome (`Compile.Result`) is stored once on the attempt. The
  diagnostic count is a separate field and measure.
- Attempts retain their original MainTable identifiers, source fields, score,
  timestamp, and `Order`; Compile source columns are retained with a `Compile_`
  prefix. Code is joined by `CodeStateID`. Subject metadata is joined by
  `SubjectID`.

## Ordering and progress

Within each `(SubjectID, AssignmentID, ProblemID)` group, attempts are sorted
by `Order`, not by timestamp. `AttemptNumber` starts at 1 for each group.
`PreviousScore` and `ScoreDelta` compare an attempt only with the immediately
preceding attempt in that group. The score is parsed numerically while blank
scores remain missing; unknown scores are never filled with zero.

Classification is based on the unrounded adjacent-score delta:

- `IMPROVING` when delta > 0.05
- `REGRESSING` when delta < -0.05
- `STAGNANT` otherwise, including both threshold boundaries
- `UNCLASSIFIABLE` for the first attempt or when either score in a transition
  is unavailable

## Subject metadata deduplication

Duplicate `SubjectID` rows are removed only if all metadata columns are
identical. Conflicting metadata for a duplicate ID raises an error rather than
choosing a row. Attempts without a Subject.csv match are retained, and
unmatched metadata remains missing.

## Validation and reproducibility

Run from the repository root with:

```powershell
python analysis\scripts\reconstruct_attempts.py
```

The script checks event types and IDs, parent resolution and event types,
student/assignment/problem/code-state agreement across each event link, exactly
one Compile per Run.Program, diagnostic attachment, full CodeStates coverage,
unique attempt IDs, output ordering, adjacent-score calculations, and saved
output contents. It stops with an explicit error on an unexpected relationship
or a failed validation.

Machine-readable counts and validation results are saved in
`analysis/outputs/reconstruction_summary.json` and
`analysis/outputs/reconstruction_summary.csv`. Detailed event, compile-outcome,
and transition counts are also written as CSV summaries.

## Stage 2 execution results

The reconstruction completed with `validation_passed: true`.

- **69,627 attempts** were written, with 69,627 unique attempt IDs and exactly
  one unique Compile event attached to each.
- All **62,316** Compile.Error diagnostic rows were retained and linked to
  failed Compile events; they belong to **28,058** attempts. The other **41,569**
  attempts have successful Compile events and no diagnostics.
- CodeStates coverage is **69,627 of 69,627 attempts**.
- The attempts form **16,179** student-assignment-problem groups and are sorted
  by `Order` within every group. The saved output re-check verified sequential
  attempt numbers, adjacent previous scores and deltas, and their threshold
  classifications.
- Attempt scores are missing on **0** rows in this release. The pipeline
  preserves blank scores as missing rather than imputing a value.
- Subject.csv has **373 source rows** and **372 unique students**. One
  duplicate row with identical metadata was removed. Metadata matched
  **66,438 attempts**; **3,189 attempts** (41 students) have no matching
  Subject.csv record and remain in the output.
- Transition classifications are **20,503 IMPROVING**, **7,329 REGRESSING**,
  **25,616 STAGNANT**, and **16,179 UNCLASSIFIABLE**. Unclassifiable rows are
  the first attempt in each group in this release.

The Run.Program timestamp sequence contains three one-second backward steps
when sorted by `Order`. The attempts are still sequenced by the dataset's
declared within-group event ordering; timestamps are retained as recorded.

The auxiliary `early.csv` and `late.csv` files were not used for primary
statistics. Although all their student-assignment-problem keys match
MainTable, their `Attempts` values differ from reconstructed counts on 599 of
9,106 early rows and 363 of 5,722 late rows. `CorrectEventually` also differs
from final-score-positive on 559 early and 365 late rows. Their summary-field
semantics remain unresolved.

## Assumptions and limitations

- Treating each top-level `Run.Program` as an attempt is an operational
  definition supported by the event-parent relationships and the score
  placement. The data does not independently establish whether every event
  corresponds to a distinct deliberate submission action.
- Dataset metadata declares ordering consistent only within
  `(SubjectID, AssignmentID, ProblemID)`. `Order` is therefore used only to
  sequence attempts within those groups. Timestamps are preserved for reference
  and are not used to infer time spent.
- Subject.csv's `X-Grade` label is retained as supplied; its meaning is not
  inferred.
- This historical observational dataset cannot establish the causal effect of
  adaptive AI feedback.
