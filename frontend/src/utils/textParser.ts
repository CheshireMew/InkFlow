/**
 * Utility to parse variant text that might contain numbered lists.
 * E.g. "1. Option A\n2. Option B\n3. Option C" -> ["Option A", "Option B", "Option C"]
 */
export function parseVariants(variants: string[]): string[] {
  // If we already have multiple variants, assume they are correct
  if (variants.length > 1) return variants;
  if (variants.length === 0) return [];

  const text = variants[0];

  // Try to split by numbered list pattern (1. 2. 3. or 1) 2) 3))
  // Regex looks for newline followed by number and dot/paren
  const itemPattern = /(?:^|\n)\s*\d+[.)][ \t]*/;

  // Quick check if it looks like a list
  if (!itemPattern.test(text)) {
    return variants;
  }

  const items = text
    .split(/(?:^|\n)\s*\d+[.)][ \t]*/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  if (items.length > 1) {
    return items;
  }

  return variants;
}
