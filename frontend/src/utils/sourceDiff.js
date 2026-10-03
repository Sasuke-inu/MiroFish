// Exact Unicode character range between the shared beginning and ending.
// This is a text comparison, not a semantic support assessment.
export function sourceDiff(before, after) {
  const left = Array.from(before), right = Array.from(after)
  let start = 0, suffix = 0
  while (start < Math.min(left.length, right.length) && left[start] === right[start]) start++
  while (suffix < left.length - start && suffix < right.length - start && left[left.length - 1 - suffix] === right[right.length - 1 - suffix]) suffix++
  return { changed: before !== after, start, beforeEnd: left.length - suffix, afterEnd: right.length - suffix,
    before: left.slice(start, left.length - suffix).join(''), after: right.slice(start, right.length - suffix).join('') }
}
