import { useEffect, useRef, useState } from 'react'
import { ProblemSelector } from './components/ProblemSelector'
import { CodingEditor } from './components/CodingEditor'
import { ProblemPanel } from './components/ProblemPanel'
import { SubmissionHistory } from './components/SubmissionHistory'
import { SubmissionPanels } from './components/SubmissionPanels'
import {
  ApiHttpError,
  ApiNetworkError,
  ApiResponseError,
  getProblem,
  getProblems,
  submitSolution,
} from './services/api'
import type {
  ProblemDetail,
  ProblemSummary,
  SubmissionResponse,
} from './types/api'
import './App.css'

const DEMO_STUDENT_ID = 1

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
    setSelectedProblemId(problemId)
    setSubmissionResult(null)
    setSubmissionError(null)
  }

  async function handleSubmit() {
    if (
      !selectedProblem ||
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
        student_id: DEMO_STUDENT_ID,
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
      </header>

      <main className="workspace">
        <div className="workspace-heading">
          <div>
            <p className="eyebrow">Independent problem-solving</p>
            <h2>Practice workspace</h2>
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
              disabled={!selectedProblem || problemLoading}
              hasCode={sourceCode.trim().length > 0}
            />
            {submissionError && (
              <p className="submission-error" role="alert">
                {submissionError}
              </p>
            )}
            {isSubmitting && (
              <p className="submission-progress" role="status">
                Submission in progress. The backend is evaluating your code and
                generating feedback; this may take a little while.
              </p>
            )}
            {submissionResult && (
              <SubmissionPanels result={submissionResult} />
            )}
          </div>
        </div>
        {selectedProblemId !== null && (
          <SubmissionHistory
            key={`${DEMO_STUDENT_ID}-${selectedProblemId}-${historyRefreshCount}`}
            studentId={DEMO_STUDENT_ID}
            problemId={selectedProblemId}
          />
        )}
      </main>
    </div>
  )
}

export default App
