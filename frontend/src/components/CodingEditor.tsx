import Editor from '@monaco-editor/react'

interface CodingEditorProps {
  sourceCode: string
  onSourceCodeChange: (sourceCode: string) => void
  onSubmit: () => void
  submitting: boolean
  disabled: boolean
  hasCode: boolean
}

export function CodingEditor({
  sourceCode,
  onSourceCodeChange,
  onSubmit,
  submitting,
  disabled,
  hasCode,
}: CodingEditorProps) {
  return (
    <section className="editor-panel" aria-labelledby="editor-title">
      <div className="editor-heading">
        <div>
          <p className="eyebrow">Your solution</p>
          <h3 id="editor-title">Java editor</h3>
        </div>
        <span className="language-badge">JAVA</span>
      </div>
      <div className="monaco-frame">
        <Editor
          height="460px"
          language="java"
          theme="vs-dark"
          value={sourceCode}
          onChange={(value) => onSourceCodeChange(value ?? '')}
          options={{
            automaticLayout: true,
            fontSize: 14,
            lineNumbers: 'on',
            minimap: { enabled: false },
            readOnly: disabled,
            scrollBeyondLastLine: false,
            tabSize: 4,
          }}
        />
      </div>
      <div className="editor-footer">
        <p className="editor-hint">
          {disabled
            ? 'Select a problem to begin coding.'
            : 'Your code is sent to the backend for evaluation.'}
        </p>
        <button
          className="submit-button"
          disabled={disabled || submitting || !hasCode}
          onClick={onSubmit}
          type="button"
        >
          {submitting ? (
            <>
              <span className="button-spinner" aria-hidden="true" />
              Evaluating…
            </>
          ) : (
            'Submit solution'
          )}
        </button>
      </div>
    </section>
  )
}
