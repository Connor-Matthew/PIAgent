export type AdditionalConfigEntry = [string, unknown]

export function getAdditionalConfigEntries(
  config: Record<string, unknown>,
  renderedKeys: string[],
): AdditionalConfigEntry[] {
  const rendered = new Set(renderedKeys)
  return Object.entries(config).filter(([key]) => !rendered.has(key))
}

export function formatConfigValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
