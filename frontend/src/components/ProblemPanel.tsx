import type { ProblemDetail } from '../types/api'

interface ProblemPanelProps {
  problem: ProblemDetail | null
  loading: boolean
  error: string | null
}

export function ProblemPanel({ problem, loading, error }: ProblemPanelProps) {
  return (
    <section className="problem-panel" aria-labelledby="problem-panel-title">
      {loading ? (
        <p className="status-message" role="status">
          Loading problem…
        </p>
      ) : error ? (
        <p className="error-message" role="alert">
          {error}
        </p>
      ) : problem ? (
        <>
          <div className="problem-title-row">
            <div>
              <p className="eyebrow">Problem</p>
              <h3 id="problem-panel-title">{problem.title}</h3>
            </div>
            <span
              className={`difficulty difficulty-${problem.difficulty.toLowerCase()}`}
            >
              {problem.difficulty}
            </span>
          </div>

          <div className="problem-description">{problem.description}</div>

          <section className="test-cases" aria-labelledby="test-cases-title">
            <div className="section-heading">
              <h4 id="test-cases-title">Sample test cases</h4>
              <span>{problem.public_test_cases.length} public</span>
            </div>
            {problem.public_test_cases.length > 0 ? (
              <div className="test-case-list">
                {problem.public_test_cases.map((testCase, index) => (
                  <article className="test-case" key={testCase.id}>
                    <h5>Example {index + 1}</h5>
                    <div className="test-case-values">
                      <div>
                        <span className="code-label">Input</span>
                        <pre>{testCase.input_data || '(empty)'}</pre>
                      </div>
                      <div>
                        <span className="code-label">Expected output</span>
                        <pre>{testCase.expected_output || '(empty)'}</pre>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="status-message">No public test cases are available.</p>
            )}
          </section>

          <p className="hidden-test-note">
            {problem.hidden_test_case_count} hidden test case
            {problem.hidden_test_case_count === 1 ? '' : 's'} are used for evaluation.
          </p>
        </>
      ) : (
        <div className="empty-workspace">
          <span className="empty-mark" aria-hidden="true">01</span>
          <h3>Select a problem</h3>
          <p>Choose a problem to view its description and sample cases.</p>
        </div>
      )}
    </section>
  )
}
