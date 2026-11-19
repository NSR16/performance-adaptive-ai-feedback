import { useEffect, useState } from 'react'
import { SubmissionPanels } from './SubmissionPanels'
import {
  ApiHttpError,
  ApiNetworkError,
  ApiResponseError,
  getSubmission,
  getSubmissionHistory,
} from '../services/api'
import type { HistoryItem, SubmissionDetail } from '../types/api'

interface SubmissionHistoryProps {
  studentId: number
  problemId: number
}

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

function newestFirst(items: HistoryItem[]): HistoryItem[] {
  return [...items].sort((left, right) => {
    const timeDifference =
      Date.parse(right.submitted_at) - Date.parse(left.submitted_at)
    if (Number.isFinite(timeDifference) && timeDifference !== 0) {
      return timeDifference
    }
    return right.submission_id - left.submission_id
  })
}

function formatScore(score: string | null): string {
  return score === null ? '—' : `${score}%`
}

export function SubmissionHistory({
  studentId,
  problemId,
}: SubmissionHistoryProps) {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyRetryCount, setHistoryRetryCount] = useState(0)
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<number | null>(
    null,
  )
  const [selectedSubmission, setSelectedSubmission] =
    useState<SubmissionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailRetryCount, setDetailRetryCount] = useState(0)

  useEffect(() => {
    let active = true
    setItems([])
    setHistoryLoading(true)
    setHistoryError(null)

    getSubmissionHistory(studentId, problemId)
      .then((history) => {
        if (active) {
          setItems(newestFirst(history))
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setHistoryError(describeError(error))
        }
      })
      .finally(() => {
        if (active) {
          setHistoryLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [studentId, problemId, historyRetryCount])

  useEffect(() => {
    if (selectedSubmissionId === null) {
      setSelectedSubmission(null)
      setDetailLoading(false)
      setDetailError(null)
      return
    }

    let active = true
    setSelectedSubmission(null)
    setDetailLoading(true)
    setDetailError(null)

    getSubmission(selectedSubmissionId)
      .then((submission) => {
        if (active) {
          setSelectedSubmission(submission)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setDetailError(describeError(error))
        }
      })
      .finally(() => {
        if (active) {
          setDetailLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [selectedSubmissionId, detailRetryCount])

  return (
    <section className="history-panel" aria-labelledby="history-title">
      <div className="history-heading">
        <div>
          <p className="eyebrow">Your attempts</p>
          <h3 id="history-title">Submission history</h3>
        </div>
        {!historyLoading && !historyError && (
          <span className="history-count">{items.length}</span>
        )}
      </div>

      {historyLoading ? (
        <p className="status-message" role="status">
          Loading submission history…
        </p>
      ) : historyError ? (
        <div className="history-error" role="alert">
          <p>{historyError}</p>
          <button
            className="secondary-button"
            onClick={() => setHistoryRetryCount((count) => count + 1)}
            type="button"
          >
            Try again
          </button>
        </div>
      ) : items.length === 0 ? (
        <p className="status-message">No submissions for this problem yet.</p>
      ) : (
        <div className="history-layout">
          <ol className="history-list">
            {items.map((item) => (
              <li key={item.submission_id}>
                <button
                  aria-pressed={selectedSubmissionId === item.submission_id}
                  className={`history-entry${
                    selectedSubmissionId === item.submission_id ? ' selected' : ''
                  }`}
                  onClick={() => setSelectedSubmissionId(item.submission_id)}
                  type="button"
                >
                  <span className="history-entry-heading">
                    <strong>Submission #{item.submission_id}</strong>
                    <time dateTime={item.submitted_at}>
                      {new Date(item.submitted_at).toLocaleString()}
                    </time>
                  </span>
                  <span className="history-entry-metrics">
                    <span>{item.evaluation_status ?? 'Status unavailable'}</span>
                    <span>
                      Tests {item.passed_tests ?? '—'} / {item.total_tests ?? '—'}
                    </span>
                    <span>Score {formatScore(item.score)}</span>
                    <span>
                      Progress {item.progress_classification ?? '—'}
                    </span>
                    <span>
                      Assistance {item.selected_assistance_level ?? '—'}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>

          <div className="history-detail" aria-live="polite">
            {detailLoading ? (
              <p className="status-message" role="status">
                Loading submission details…
              </p>
            ) : detailError ? (
              <div className="history-error" role="alert">
                <p>{detailError}</p>
                <button
                  className="secondary-button"
                  onClick={() => setDetailRetryCount((count) => count + 1)}
                  type="button"
                >
                  Try again
                </button>
              </div>
            ) : selectedSubmission ? (
              <SubmissionPanels result={selectedSubmission} />
            ) : (
              <div className="history-empty">
                <span className="history-empty-mark" aria-hidden="true">
                  ↖
                </span>
                <h4>Select a submission</h4>
                <p>
                  Choose an attempt from the history list to review its
                  evaluation results and AI feedback.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
