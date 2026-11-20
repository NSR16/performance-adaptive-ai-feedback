import { useEffect, useRef, useState } from 'react'
import { ProblemSelector } from './components/ProblemSelector'
import { CodingEditor } from './components/CodingEditor'
import { ProblemPanel } from './components/ProblemPanel'
import { SubmissionHistory } from './components/SubmissionHistory'
import { SubmissionPanels } from './components/SubmissionPanels'
import { StudentSelector } from './components/StudentSelector'
import {
  ApiHttpError,
  ApiNetworkError,
  ApiResponseError,
  getProblem,
  getProblems,
  getStudents,
  submitSolution,
} from './services/api'
import type {
  ProblemDetail,
  ProblemSummary,
  StudentSummary,
  SubmissionResponse,
} from './types/api'
import './App.css'

function describeError(error: unknown): string {
  if (error instanceof ApiHttpError) {
    return error.message
  }
  if (error instanceof ApiNetworkError) {
    return 'Could not connect to the backend. Check that it is running and try again.'
  }
  if (error instanceof ApiResponseError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unexpected error occurred.'
}

function App() {
  const [students, setStudents] = useState<StudentSummary[]>([])
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null)
  const [studentsLoading, setStudentsLoading] = useState(true)
  const [studentsError, setStudentsError] = useState<string | null>(null)
  const [studentRetryCount, setStudentRetryCount] = useState(0)
  const [problems, setProblems] = useState<ProblemSummary[]>([])
  const [selectedProblemId, setSelectedProblemId] = useState<number | null>(null)
  const [selectedProblem, setSelectedProblem] = useState<ProblemDetail | null>(null)
  const [problemsLoading, setProblemsLoading] = useState(true)
  const [problemLoading, setProblemLoading] = useState(false)
  const [problemsError, setProblemsError] = useState<string | null>(null)
  const [problemError, setProblemError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const [sourceCode, setSourceCode] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [submissionResult, setSubmissionResult] =
    useState<SubmissionResponse | null>(null)
  const [historyRefreshCount, setHistoryRefreshCount] = useState(0)
  const submissionInFlight = useRef(false)
  const [activeView, setActiveView] = useState<'workspace' | 'history'>(
    'workspace',
  )

  useEffect(() => {
    let active = true
    setStudentsLoading(true)
    setStudentsError(null)

    getStudents()
      .then((items) => {
        if (!active) {
          return
        }
        setStudents(items)
        setSelectedStudentId((currentId) =>
          items.some((student) => student.id === currentId)
            ? currentId
            : (items[0]?.id ?? null),
        )
      })
      .catch((error: unknown) => {
        if (active) {
          setStudentsError(describeError(error))
        }
      })
      .finally(() => {
        if (active) {
          setStudentsLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [studentRetryCount])

  useEffect(() => {
    let active = true
    setProblemsLoading(true)
    setProblemsError(null)

    getProblems()
      .then((items) => {
        if (!active) {
          return
        }
        setProblems(items)
        setSelectedProblemId(items[0]?.id ?? null)
        setSubmissionResult(null)
        setSubmissionError(null)
      })
      .catch((error: unknown) => {
        if (active) {
          setProblemsError(describeError(error))
        }
      })
      .finally(() => {
        if (active) {
          setProblemsLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [retryCount])

  useEffect(() => {
    if (selectedProblemId === null) {
      setSelectedProblem(null)
      setProblemError(null)
      setProblemLoading(false)
      return
    }

    let active = true
    setSelectedProblem(null)
    setProblemLoading(true)
    setProblemError(null)

    getProblem(selectedProblemId)
      .then((problem) => {
        if (active) {
          setSelectedProblem(problem)
          setSourceCode(problem.starter_code ?? '')
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setProblemError(describeError(error))
        }
      })
      .finally(() => {
        if (active) {
          setProblemLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [selectedProblemId])

  function handleProblemChange(problemId: number) {
    if (problemId === selectedProblemId || submissionInFlight.current) {
      return
    }

    setSelectedProblemId(problemId)
    setSourceCode('')
    setSubmissionResult(null)
    setSubmissionError(null)
  }

  function handleStudentChange(studentId: number) {
    if (studentId === selectedStudentId || submissionInFlight.current) {
      return
    }

    setSelectedStudentId(studentId)
    setSourceCode(
      selectedProblem?.id === selectedProblemId
        ? (selectedProblem.starter_code ?? '')
        : '',
    )
    setSubmissionResult(null)
    setSubmissionError(null)
  }

  async function handleSubmit() {
    if (
      !selectedProblem ||
      selectedStudentId === null ||
      submissionInFlight.current ||
      sourceCode.trim().length === 0
    ) {
      return
    }

    submissionInFlight.current = true
    setIsSubmitting(true)
    setSubmissionError(null)
    setSubmissionResult(null)

    try {
      const result = await submitSolution({
        student_id: selectedStudentId,
        problem_id: selectedProblem.id,
        source_code: sourceCode,
      })
      setSubmissionResult(result)
    } catch (error: unknown) {
      setSubmissionError(describeError(error))
    } finally {
      submissionInFlight.current = false
      setIsSubmitting(false)
      setHistoryRefreshCount((count) => count + 1)
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-mark" aria-hidden="true">
          PA
        </div>
        <div>
          <p className="eyebrow">Research workspace</p>
          <h1>Performance-Adaptive AI Feedback</h1>
        </div>
        <div className="header-student">
          <span className="eyebrow">Student</span>
          {studentsLoading ? (
            <span className="header-status" role="status">
              Loading…
            </span>
          ) : studentsError ? (
            <div className="student-load-error" role="alert">
              <span>Could not load students.</span>
              <button
                className="text-button"
                onClick={() => setStudentRetryCount((count) => count + 1)}
                type="button"
              >
                Retry
              </button>
            </div>
          ) : students.length > 0 ? (
            <StudentSelector
              students={students}
              selectedStudentId={selectedStudentId}
              onChange={handleStudentChange}
              disabled={isSubmitting}
            />
          ) : (
            <span className="header-status">No students available</span>
          )}
        </div>
      </header>

      <main className="workspace">
        <nav className="view-tabs" role="tablist" aria-label="Workspace views">
          <button
            aria-selected={activeView === 'workspace'}
            className={`view-tab${activeView === 'workspace' ? ' active' : ''}`}
            onClick={() => setActiveView('workspace')}
            role="tab"
            type="button"
          >
            Workspace
          </button>
          <button
            aria-selected={activeView === 'history'}
            className={`view-tab${activeView === 'history' ? ' active' : ''}`}
            onClick={() => setActiveView('history')}
            role="tab"
            type="button"
          >
            Submission History
          </button>
        </nav>

        {activeView === 'workspace' ? (
          <section
            aria-labelledby="workspace-title"
            className="workspace-view"
            role="tabpanel"
          >
            <div className="workspace-heading">
              <div>
                <p className="eyebrow">Independent problem-solving</p>
                <h2 id="workspace-title">Practice workspace</h2>
              </div>
              <div className="problem-picker">
                <span className="eyebrow">Problem</span>
                {problemsLoading ? (
                  <span className="status-message" role="status">
                    Loading problems…
                  </span>
                ) : problemsError ? (
                  <div className="problem-load-error" role="alert">
                    <span>{problemsError}</span>
                    <button
                      className="text-button"
                      onClick={() => setRetryCount((count) => count + 1)}
                      type="button"
                    >
                      Retry
                    </button>
                  </div>
                ) : problems.length > 0 ? (
                  <ProblemSelector
                    problems={problems}
                    selectedProblemId={selectedProblemId}
                    onChange={handleProblemChange}
                    disabled={isSubmitting}
                  />
                ) : (
                  <span className="status-message">No problems available</span>
                )}
              </div>
            </div>

            <div className="workspace-grid">
              <ProblemPanel
                problem={selectedProblem}
                loading={problemLoading}
                error={problemError}
              />

              <div className="editor-column">
                <CodingEditor
                  sourceCode={sourceCode}
                  onSourceCodeChange={setSourceCode}
                  onSubmit={handleSubmit}
                  submitting={isSubmitting}
                  disabled={
                    !selectedProblem || problemLoading || selectedStudentId === null
                  }
                  hasCode={sourceCode.trim().length > 0}
                />
                {submissionError && (
                  <p className="submission-error" role="alert">
                    {submissionError}
                  </p>
                )}
                {isSubmitting && (
                  <p className="submission-progress" role="status">
                    Submission in progress. The backend is evaluating your code
                    and generating feedback; this may take a little while.
                  </p>
                )}
                {submissionResult && (
                  <SubmissionPanels result={submissionResult} />
                )}
              </div>
            </div>
          </section>
        ) : (
          <section
            aria-labelledby="history-view-title"
            className="history-view"
            role="tabpanel"
          >
            <div className="history-view-heading">
              <div>
                <p className="eyebrow">Selected problem</p>
                <h2 id="history-view-title">
                  {problems.find((problem) => problem.id === selectedProblemId)
                    ?.title ?? 'Submission history'}
                </h2>
              </div>
              <button
                className="text-button"
                onClick={() => setActiveView('workspace')}
                type="button"
              >
                Change problem
              </button>
            </div>
            {studentsLoading || problemsLoading ? (
              <p className="status-message" role="status">
                Loading student and problem selections…
              </p>
            ) : studentsError ? (
              <p className="error-message" role="alert">
                {studentsError}
              </p>
            ) : problemsError ? (
              <p className="error-message" role="alert">
                {problemsError}
              </p>
            ) : selectedStudentId !== null && selectedProblemId !== null ? (
              <SubmissionHistory
                key={`${selectedStudentId}-${selectedProblemId}-${historyRefreshCount}`}
                studentId={selectedStudentId}
                problemId={selectedProblemId}
              />
            ) : (
              <p className="history-no-selection">
                Select a student and a problem in Workspace to view submissions.
              </p>
            )}
          </section>
        )}
      </main>
    </div>
  )
}

export default App
