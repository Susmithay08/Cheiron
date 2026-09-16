import { describe, expect, it } from "vitest";

import { BRAND_TO_GENERIC, detectedBrands, expandBrandNames } from "./synonyms";

describe("expandBrandNames", () => {
  it.each(Object.entries(BRAND_TO_GENERIC))(
    "appends the generic name for %s",
    (brand, generic) => {
      const query = `How many ${brand} trials are there?`;
      expect(expandBrandNames(query)).toBe(`How many ${brand} (${generic}) trials are there?`);
    },
  );

  it("matches case-insensitively and preserves the user's casing", () => {
    expect(expandBrandNames("How many KEYTRUDA trials are there?")).toBe(
      "How many KEYTRUDA (Pembrolizumab) trials are there?",
    );
    expect(expandBrandNames("keytruda vs opdivo")).toBe(
      "keytruda (Pembrolizumab) vs opdivo (Nivolumab)",
    );
  });

  it("expands both arms of a comparison, even when they share a generic", () => {
    expect(expandBrandNames("Compare trial counts by phase for Ozempic vs Wegovy")).toBe(
      "Compare trial counts by phase for Ozempic (Semaglutide) vs Wegovy (Semaglutide)",
    );
  });

  it("is idempotent — repeated execution never double-appends", () => {
    const once = expandBrandNames("How many Keytruda trials are there?");
    expect(expandBrandNames(once)).toBe(once);
    expect(expandBrandNames(expandBrandNames(once))).toBe(once);
    expect(once).not.toContain("(Pembrolizumab) (Pembrolizumab)");
  });

  it("leaves a query that already names both brand and generic alone", () => {
    const query = "Keytruda (Pembrolizumab) trials by phase";
    expect(expandBrandNames(query)).toBe(query);
    expect(expandBrandNames("Keytruda Pembrolizumab trials")).toBe(
      "Keytruda Pembrolizumab trials",
    );
  });

  it("does not touch a pure generic-name query", () => {
    const query = "How has the number of trials for Pembrolizumab changed since 2015?";
    expect(expandBrandNames(query)).toBe(query);
  });

  it("does not rewrite unrelated words that merely contain a brand name", () => {
    expect(expandBrandNames("keytrudaish substances and myozempicplan")).toBe(
      "keytrudaish substances and myozempicplan",
    );
    expect(expandBrandNames("humidity in trials")).toBe("humidity in trials");
  });

  it("leaves queries with no known brand untouched", () => {
    for (const query of ["", "   ", "breast cancer trials by phase", "hello"]) {
      expect(expandBrandNames(query)).toBe(query);
    }
  });

  it("reports which brands it recognised", () => {
    expect(detectedBrands("Ozempic vs Wegovy").sort()).toEqual(["ozempic", "wegovy"]);
    expect(detectedBrands("breast cancer")).toEqual([]);
  });
});
