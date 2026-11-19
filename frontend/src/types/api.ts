export interface ProblemSummary {
  id: number
  title: string
  difficulty: string
}

export interface PublicTestCase {
  id: number
  input_data: string
  expected_output: string
  sequence_order: number
}

export interface ProblemDetail {
  id: number
  title: string
  description: string
  difficulty: string
  starter_code: string | null
  public_test_cases: PublicTestCase[]
  hidden_test_case_count: number
}

export interface SubmissionCreate {
  student_id: number
  problem_id: number
  source_code: string
}

export interface SubmissionResponse {
  submission_id: number
  evaluation_status: string
  passed_tests: number
  total_tests: number
  score: string | null
  progress_classification: string | null
  selected_assistance_level: string
  feedback_text: string | null
  generation_status: string
  model_name: string | null
  error_message: string | null
}

export interface SubmissionDetail {
  submission_id: number
  student_id: number
  problem_id: number
  submitted_at: string
  source_code: string
  evaluation_status: string | null
  passed_tests: number | null
  total_tests: number | null
  score: string | null
  progress_classification: string | null
  selected_assistance_level: string | null
  improvement_streak: number | null
  feedback_text: string | null
  feedback_generation_status: string | null
  feedback_error_message: string | null
  model_name: string | null
}

export interface HistoryItem {
  submission_id: number
  submitted_at: string
  evaluation_status: string | null
  passed_tests: number | null
  total_tests: number | null
  score: string | null
  progress_classification: string | null
  selected_assistance_level: string | null
}
