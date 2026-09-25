import { describe, expect, it } from "vitest";
import { FORECAST_HORIZONS_H } from "@/domain/forecast";
import { toLocalMeters } from "@/lib/geo/local-metric";
import { DEMO_CANDIDATES } from "./candidates";
import { DEMO_CURRENT_FIELD, DEMO_FORECAST_DETAILS, DEMO_FORECAST_RUN } from "./forecast";

const COAST_PROBE_M = 350;

function touchesLandAndWater([lng, lat]: readonly [number, number]): boolean {
  const kmLng = COAST_PROBE_M / (111_320 * Math.cos((lat * Math.PI) / 180));
  const kmLat = COAST_PROBE_M / 111_320;
  const probes = [
    [lng + kmLng, lat],
    [lng - kmLng, lat],
    [lng, lat + kmLat],
    [lng, lat - kmLat],
    [lng + kmLng, lat + kmLat],
    [lng - kmLng, lat - kmLat],
    [lng + kmLng, lat - kmLat],
    [lng - kmLng, lat + kmLat],
  ].map(([x, y]) => DEMO_CURRENT_FIELD.isWater(x, y));
  return probes.includes(true) && probes.includes(false);
}

describe("demo drift forecast", () => {
  it("forecasts every demo candidate from its own centroid", () => {
    expect(DEMO_FORECAST_DETAILS.map((forecast) => forecast.candidateId)).toEqual(
      DEMO_CANDIDATES.map((candidate) => candidate.id),
    );
    for (const forecast of DEMO_FORECAST_DETAILS) {
      const candidate = DEMO_CANDIDATES.find((entry) => entry.id === forecast.candidateId);
      const [dx, dy] = toLocalMeters(candidate!.centroid, forecast.origin);
      expect(Math.hypot(dx, dy)).toBeLessThan(5);
    }
  });

  it("keeps hourly paths for −48 … +72 h", () => {
    for (const forecast of DEMO_FORECAST_DETAILS) {
      expect(forecast.medianPath).toHaveLength(73);
      expect(forecast.hindcastPath).toHaveLength(DEMO_FORECAST_RUN.hindcastHours + 1);
      expect(forecast.beachedByHour).toHaveLength(73);
      expect(forecast.envelopes.map((envelope) => envelope.horizonH)).toEqual([
        ...FORECAST_HORIZONS_H,
      ]);
    }
  });

  it("never lets the beached share decrease with lead time", () => {
    for (const { beachedByHour, beachingAny } of DEMO_FORECAST_DETAILS) {
      beachedByHour.slice(1).forEach((share, index) => {
        expect(share).toBeGreaterThanOrEqual(beachedByHour[index]);
      });
      expect(beachedByHour[72]).toBeCloseTo(beachingAny.value, 2);
    }
  });

  it("splits beached members between coast stretches without losing any", () => {
    for (const { beaching, beachingAny } of DEMO_FORECAST_DETAILS) {
      const members = beaching.reduce((sum, risk) => sum + risk.members, 0);
      expect(members / DEMO_FORECAST_RUN.ensembleSize).toBeCloseTo(beachingAny.value, 2);
      for (const risk of beaching) {
        expect(risk.probability.low).toBeLessThanOrEqual(risk.probability.value);
        expect(risk.probability.value).toBeLessThanOrEqual(risk.probability.high);
        expect(risk.windowH[0]).toBeLessThanOrEqual(risk.windowH[1]);
        expect(risk.windowH[1]).toBeLessThanOrEqual(72);
      }
    }
  });

  it("draws beaching stretches along the real coastline", () => {
    const paths = DEMO_FORECAST_DETAILS.flatMap((forecast) =>
      forecast.beaching.flatMap((risk) => risk.path),
    );
    expect(paths.length).toBeGreaterThan(0);
    for (const vertex of paths) expect(touchesLandAndWater(vertex)).toBe(true);
  });

  it("accounts for every backward member in the source estimate", () => {
    for (const { sources } of DEMO_FORECAST_DETAILS) {
      const members = sources.reduce((sum, source) => sum + source.members, 0);
      expect(members).toBe(DEMO_FORECAST_RUN.ensembleSize);
    }
  });

  it("tells the Motagua story for the lead candidate", () => {
    const [lead] = DEMO_FORECAST_DETAILS;
    expect(lead.sources[0].id).toBe("motagua");
    expect(lead.beaching[0].id).toBe("omoa");
    expect(lead.beaching[0].severity).toBe("alarm");
    expect(lead.beachingRisk).toEqual({
      segment: lead.beaching[0].name,
      probability: lead.beaching[0].probability.value,
    });
  });

  it("returns no current over land", () => {
    expect(DEMO_CURRENT_FIELD.velocityAt(-88.3, 15.6)).toBeNull();
    expect(DEMO_CURRENT_FIELD.velocityAt(-88.2, 15.95)).not.toBeNull();
  });
});
