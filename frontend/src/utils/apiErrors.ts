function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function getApiErrorMessage(error: unknown, fallback: string) {
  if (isRecord(error)) {
    const response = isRecord(error.response) ? error.response : null
    const data = response && isRecord(response.data) ? response.data : null
    const detail = data?.detail

    if (typeof detail === 'string' && detail) {
      return detail
    }

    if (isRecord(detail)) {
      if (typeof detail.error === 'string' && detail.error) {
        return detail.error
      }
      if (typeof detail.message === 'string' && detail.message) {
        return detail.message
      }
      return JSON.stringify(detail)
    }

    if (typeof error.message === 'string' && error.message) {
      return error.message
    }
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  return fallback
}

export function getApiErrorStatus(error: unknown) {
  if (!isRecord(error)) return null
  const response = isRecord(error.response) ? error.response : null
  return typeof response?.status === 'number' ? response.status : null
}
