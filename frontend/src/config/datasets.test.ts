import { describe, expect, it } from "vitest";
import { DATASETS, doiUrl } from "./datasets";

describe("reference datasets", () => {
  it("lists the six sets named in the Models report", () => {
    expect(DATASETS.map((entry) => entry.name)).toEqual([
      "MARIDA",
      "MADOS",
      "PLP 2019",
      "PLP 2021",
      "PLP 2022–23",
      "Windrows MED",
    ]);
  });

  it("keeps DOIs bare and resolvable through doi.org", () => {
    for (const entry of DATASETS) {
      for (const doi of [entry.doi, entry.paperDoi]) {
        expect(doi).toMatch(/^10\.\d{4,9}\/\S+$/);
        expect(doiUrl(doi)).toBe(`https://doi.org/${doi}`);
      }
      expect(entry.doi).toMatch(/^10\.5281\/zenodo\.\d+$/);
    }
  });

  it("puts both the article and the dataset DOI into every citation", () => {
    for (const entry of DATASETS) {
      expect(entry.citation).toContain(doiUrl(entry.doi));
      expect(entry.citation).toContain(doiUrl(entry.paperDoi));
    }
  });

  it("records the primary role first and a licence for every set", () => {
    for (const entry of DATASETS) {
      expect(entry.roles[0]).toBe(entry.role);
      expect(entry.license).toBe("CC BY 4.0");
    }
  });
});
