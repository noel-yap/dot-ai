// NOT an extraction candidate. These functions are short, flat, and
// already named for what they compute; every value has an obvious
// meaning and nothing nests past one level. Extracting helpers or
// renaming pieces here would add indirection without removing any
// reading burden.
//
// Per the skill's "When NOT to use" section, this file is a fixture for
// the extraction-for-clarity skill evaluation and is intentionally NOT
// a refactor candidate.

export function mean(values: readonly number[]): number {
  const total = values.reduce((acc, v) => acc + v, 0);
  return total / values.length;
}

export function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}
