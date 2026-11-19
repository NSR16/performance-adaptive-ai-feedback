import type {
  HistoryItem,
  ProblemDetail,
  ProblemSummary,
  SubmissionCreate,
  SubmissionDetail,
  SubmissionResponse,
} from '../types/api'

export class ApiHttpError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown) {
    super(`Backend returned HTTP ${status}: ${formatDetail(detail)}`)
    this.name = 'ApiHttpError'
    this.status = status
    this.detail = detail
  }
}

export class ApiNetworkError extends Error {
  constructor() {
    super('The backend could not be reached.')
    this.name = 'ApiNetworkError'
  }
}

export class ApiResponseError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiResponseError'
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') {
    return detail
  }
  if (detail === undefined || detail === null) {
    return 'No error detail was provided.'
  }
  return JSON.stringify(detail)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiNetworkError()
  }

  if (!response.ok) {
    let detail: unknown = response.statusText
    try {
      const body: unknown = await response.json()
      if (typeof body === 'object' && body !== null && 'detail' in body) {
        detail = body.detail
      } else {
        detail = body
      }
    } catch {
      // Retain the HTTP status text if the response body is not JSON.
    }
    throw new ApiHttpError(response.status, detail)
  }

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiResponseError('The backend returned an invalid JSON response.')
  }
}

export function getProblems(): Promise<ProblemSummary[]> {
  return request<ProblemSummary[]>('/api/problems')
}

export function getProblem(problemId: number): Promise<ProblemDetail> {
  return request<ProblemDetail>(`/api/problems/${problemId}`)
}

export function submitSolution(payload: SubmissionCreate): Promise<SubmissionResponse> {
  return request<SubmissionResponse>('/api/submissions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
}

export function getSubmission(submissionId: number): Promise<SubmissionDetail> {
  return request<SubmissionDetail>(`/api/submissions/${submissionId}`)
}

export function getSubmissionHistory(
  studentId: number,
  problemId: number,
): Promise<HistoryItem[]> {
  return request<HistoryItem[]>(
    `/api/students/${studentId}/problems/${problemId}/history`,
  )
}
