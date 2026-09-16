/**
 * Brand → generic drug-name expansion.
 *
 * ClinicalTrials.gov indexes interventions under their generic names far more
 * consistently than under brand names, so "Keytruda trials" retrieves a small
 * fraction of what "Pembrolizumab trials" does. We therefore *append* the
 * generic name to the outbound query rather than replacing the user's wording:
 * retrieval improves while the question the user actually asked stays intact,
 * both on screen and in the recent-query list.
 *
 * This is a deliberately small, auditable list rather than a fuzzy matcher. A
 * wrong expansion would silently change what the user asked, so the map only
 * contains unambiguous brand/generic pairs.
 */

export const BRAND_TO_GENERIC: Readonly<Record<string, string>> = {
  keytruda: "Pembrolizumab",
  ozempic: "Semaglutide",
  wegovy: "Semaglutide",
  humira: "Adalimumab",
  opdivo: "Nivolumab",
  tecentriq: "Atezolizumab",
};

/** Word-boundary match so "Keytrudaish" or "myozempicplan" are left alone. */
const boundary = (brand: string) => new RegExp(`\\b${brand}\\b`, "gi");

/** A brand already followed by its generic, in either "(X)" or bare form. */
const alreadyExpanded = (brand: string, generic: string) =>
  new RegExp(`\\b${brand}\\b[\\s(]*${generic}\\b`, "i");

/**
 * Append the generic name after each recognised brand name.
 *
 * Idempotent and non-destructive:
 * - matching is case-insensitive, the user's own casing is preserved;
 * - a brand already followed by its generic is left untouched, so running this
 *   twice can never produce "Keytruda (Pembrolizumab) (Pembrolizumab)";
 * - a query that only names the generic drug is unchanged;
 * - words that merely contain a brand name are not rewritten.
 *
 * Two brands sharing a generic (Ozempic and Wegovy are both semaglutide) are
 * each expanded, because in a comparison both arms need the same treatment.
 */
export function expandBrandNames(query: string): string {
  let expanded = query;

  for (const [brand, generic] of Object.entries(BRAND_TO_GENERIC)) {
    if (alreadyExpanded(brand, generic).test(expanded)) continue;
    expanded = expanded.replace(boundary(brand), (match) => `${match} (${generic})`);
  }

  return expanded;
}

/** The brands recognised in a query — used to explain the expansion in the UI. */
export function detectedBrands(query: string): string[] {
  return Object.keys(BRAND_TO_GENERIC).filter((brand) => boundary(brand).test(query));
}
