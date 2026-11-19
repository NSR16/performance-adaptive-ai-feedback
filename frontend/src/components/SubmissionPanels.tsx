import ReactMarkdown from 'react-markdown'
import type { SubmissionDetail, SubmissionResponse } from '../types/api'

interface SubmissionPanelsProps {
  result: SubmissionResponse | SubmissionDetail
}

export function SubmissionPanels({ result }: SubmissionPanelsProps) {
  const isSubmissionDetail = 'submitted_at' in result
  const generationStatus = isSubmissionDetail
    ? result.feedback_generation_status
    : result.generation_status
  const feedbackError = isSubmissionDetail
    ? result.feedback_error_message
    : result.error_message
  const feedbackFailed = generationStatus === 'FAILED'

  return (
    <div className="submission-panels" aria-live="polite">
      {isSubmissionDetail && (
        <section className="submission-detail-meta" aria-label="Submission details">
          <dl>
            <div>
              <dt>Student</dt>
              <dd>{result.student_id}</dd>
            </div>
            <div>
              <dt>Problem</dt>
              <dd>{result.problem_id}</dd>
            </div>
            <div>
              <dt>Submitted</dt>
              <dd>{new Date(result.submitted_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt>Improvement streak</dt>
              <dd>{result.improvement_streak ?? 'Not available'}</dd>
            </div>
          </dl>
          <details>
            <summary>Submitted source code</summary>
            <pre>{result.source_code}</pre>
          </details>
        </section>
      )}
      <section className="result-panel" aria-labelledby="result-title">
        <div className="result-heading">
          <div>
            <p className="eyebrow">Evaluation</p>
            <h3 id="result-title">Submission #{result.submission_id}</h3>
          </div>
          <span className="result-status">
            {result.evaluation_status ?? 'Not available'}
          </span>
        </div>
        <dl className="result-metrics">
          <div>
            <dt>Tests passed</dt>
            <dd>
              {result.passed_tests ?? '—'} / {result.total_tests ?? '—'}
            </dd>
          </div>
          <div>
            <dt>Score</dt>
            <dd>{result.score === null ? 'Not available' : `${result.score}%`}</dd>
          </div>
          <div>
            <dt>Progress classification</dt>
            <dd>{result.progress_classification ?? 'Not available'}</dd>
          </div>
          <div>
            <dt>Selected assistance</dt>
            <dd>{result.selected_assistance_level ?? 'Not available'}</dd>
          </div>
        </dl>
      </section>

      <section className="feedback-panel" aria-labelledby="feedback-title">
        <div className="feedback-heading">
          <div>
            <p className="eyebrow">Adaptive response</p>
            <h3 id="feedback-title">AI feedback</h3>
          </div>
          <span className={`generation-status${feedbackFailed ? ' failed' : ''}`}>
            {generationStatus ?? 'Not available'}
          </span>
        </div>
        <dl className="adaptive-metrics">
          <div>
            <dt>Selected assistance</dt>
            <dd>{result.selected_assistance_level ?? 'Not available'}</dd>
          </div>
          {result.progress_classification !== null && (
            <div>
              <dt>Progress classification</dt>
              <dd>{result.progress_classification}</dd>
            </div>
          )}
          {result.model_name !== null && (
            <div>
              <dt>Model</dt>
              <dd>{result.model_name}</dd>
            </div>
          )}
        </dl>
        {feedbackFailed ? (
          <p className="feedback-failure" role="status">
            Evaluation succeeded, but feedback generation failed.
            {feedbackError ? ` ${feedbackError}` : ''}
          </p>
        ) : result.feedback_text !== null ? (
          <div className="feedback-markdown">
            <ReactMarkdown>{result.feedback_text}</ReactMarkdown>
          </div>
        ) : (
          <p className="status-message">Feedback text is not available.</p>
        )}
      </section>
    </div>
  )
}
