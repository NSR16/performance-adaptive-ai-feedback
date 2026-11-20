import type { StudentSummary } from '../types/api'

interface StudentSelectorProps {
  students: StudentSummary[]
  selectedStudentId: number | null
  onChange: (studentId: number) => void
  disabled?: boolean
}

export function StudentSelector({
  students,
  selectedStudentId,
  onChange,
  disabled = false,
}: StudentSelectorProps) {
  return (
    <label className="student-selector">
      <span className="sr-only">Select a student</span>
      <select
        value={selectedStudentId ?? ''}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
      >
        {students.map((student) => (
          <option key={student.id} value={student.id}>
            {student.display_name}
          </option>
        ))}
      </select>
    </label>
  )
}
