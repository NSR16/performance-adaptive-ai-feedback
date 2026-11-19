import type { ProblemSummary } from '../types/api'

interface ProblemSelectorProps {
  problems: ProblemSummary[]
  selectedProblemId: number | null
  onChange: (problemId: number) => void
  disabled?: boolean
}

export function ProblemSelector({
  problems,
  selectedProblemId,
  onChange,
  disabled = false,
}: ProblemSelectorProps) {
  return (
    <label className="problem-selector">
      <span className="sr-only">Select a programming problem</span>
      <select
        value={selectedProblemId ?? ''}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
      >
        {problems.map((problem) => (
          <option key={problem.id} value={problem.id}>
            {problem.title} · {problem.difficulty}
          </option>
        ))}
      </select>
    </label>
  )
}
