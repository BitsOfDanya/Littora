"use client";

import { useQuery } from "@tanstack/react-query";
import type { CompositeLayerId, LayerId } from "@/config/layers";
import { type Analysis, getTargetEstimates } from "@/lib/api/analyses";
import { useMapLayersStore } from "@/state/map-layers-store";
import { cn } from "@/ui/cn";
import { CONCENTRATION_UNIT } from "./analysis-copy";
import { formatConcentration } from "./format";

const COMPOSITES: readonly [CompositeLayerId, string, keyof Analysis["layers"]][] = [
  ["scene-true-color", "RGB", "image"],
  ["scene-false-color", "Ложные", "false_color"],
  ["scene-fdi", "FDI", "fdi"],
  ["scene-ndvi", "NDVI", "ndvi"],
];

const TOGGLES: readonly [LayerId, string, keyof Analysis["layers"] | null][] = [
  ["no-data", "Маска", "mask"],
  ["debris-probability", "Вероятность", "probability"],
  ["coverage", "Покрытие", "coverage"],
  ["density", "Плотность", "coverage"],
  ["detector-zones", "Зоны", null],
];

const CHIP =
  "h-7 rounded-[2px] border px-2 text-[12px] leading-none transition-colors disabled:cursor-not-allowed disabled:opacity-40";

export function LayerChips({ analysis }: { analysis: Analysis }) {
  const composite = useMapLayersStore((state) => state.composite);
  const visible = useMapLayersStore((state) => state.visible);
  const setComposite = useMapLayersStore((state) => state.setComposite);
  const toggleLayer = useMapLayersStore((state) => state.toggleLayer);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] font-semibold text-text-secondary">Показать на карте</span>
      <div className="flex flex-wrap gap-1">
        {COMPOSITES.map(([id, label, key]) => (
          <button
            key={id}
            type="button"
            aria-pressed={composite === id}
            disabled={!analysis.layers[key]}
            onClick={() => setComposite(id)}
            className={cn(
              CHIP,
              composite === id
                ? "border-text-primary bg-surface-raised text-text-primary"
                : "border-line-control text-text-secondary hover:text-text-primary",
            )}
          >
            {label}
          </button>
        ))}
        <span aria-hidden className="mx-1 w-px self-stretch bg-line-hairline" />
        {TOGGLES.map(([id, label, key]) => (
          <button
            key={id}
            type="button"
            aria-pressed={Boolean(visible[id])}
            disabled={key !== null && !analysis.layers[key]}
            onClick={() => toggleLayer(id)}
            className={cn(
              CHIP,
              visible[id]
                ? "border-text-primary bg-surface-raised text-text-primary"
                : "border-line-control text-text-secondary hover:text-text-primary",
            )}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function TargetComparison({ analysis }: { analysis: Analysis }) {
  const estimates = useQuery({
    queryKey: ["analyses", "targets", analysis.id],
    queryFn: ({ signal }) => getTargetEstimates(analysis.id, signal),
    staleTime: Infinity,
  });
  const rows = estimates.data?.targets ?? [];
  if (!rows.length) return null;
  return (
    <div className="flex flex-col gap-1.5 text-[12px] leading-4">
      <span className="text-[11px] font-semibold text-text-secondary">
        Все целевые величины для этого района и даты
      </span>
      <table className="w-full border-collapse">
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              className={cn(
                "border-b border-line-hairline",
                row.selected && "shadow-[inset_3px_0_0_var(--accent-selection)]",
              )}
            >
              <td className="py-1 pl-2">
                <span className="text-text-primary">{row.title}</span>
                <span className="block text-[11px] text-text-tertiary">
                  {row.size_class}
                  {row.selected ? " · выбрана" : ""}
                </span>
              </td>
              <td className="py-1 pl-2 text-right align-top">
                {row.value === null ? (
                  <span className="text-text-tertiary">{row.status.label}</span>
                ) : (
                  <>
                    <span className="font-mono text-text-primary">
                      {formatConcentration(row.value)}
                    </span>
                    <span className="block text-[11px] text-text-tertiary">
                      {formatConcentration(row.lower)}–{formatConcentration(row.upper)}{" "}
                      {CONCENTRATION_UNIT}
                    </span>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[11px] leading-[14px] text-text-tertiary">
        Разные величины — разные совокупности (пластик или весь мусор, свой размер и метод учёта):
        их сравнивают рядом, но не складывают и не подменяют друг другом.
      </p>
    </div>
  );
}
