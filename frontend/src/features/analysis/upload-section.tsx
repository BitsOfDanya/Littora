"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { easeToIfOutside, fitTo } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { type Analysis, uploadImage } from "@/lib/api/analyses";
import { formatNumber } from "@/lib/format/numbers";
import { queryKeys } from "@/lib/query/query-keys";
import { useAnalysisStore } from "@/state/analysis-store";
import { Button } from "@/ui/button";
import { PanelSection } from "@/ui/section";
import { visibleBounds } from "./area";
import { useCurrentAnalysis } from "./use-analysis";

const LIMITS = [
  "Детекция мусора — только для GeoTIFF Sentinel-2 с 11–13 каналами (B01–B12; порядок как у L2A, L1C или MARIDA, либо имена каналов в файле) и пикселем около 10 м: патч MARIDA, экспорт из Copernicus Browser или свой кроп L2A.",
  "Значения: отражение 0–1 или цифровые отсчёты L2A; смещение baseline 04.00+ вычитается автоматически. L1C (без атмосферной коррекции) обработается, но точность ниже: модель обучена на L2A.",
  "Маски SCL в файле нет: вода определяется по NDWI (B03 и B08), облака не маскируются и могут дать ложные зоны.",
  "PNG, JPEG и RGB GeoTIFF: по трём видимым каналам мусор не определяется (на MARIDA F1 0,03), поэтому показываются снимок и яркие аномалии — места для визуальной проверки, не детекция.",
  "Файл без привязки ложится на видимую часть карты: сначала откройте нужный район. Площади считаются как для пикселя 10 м.",
  "До 150 МБ и 12 млн пикселей. Концентрация выдаётся, только если район и дата попадают в область полевого профиля.",
];

function areaBounds(analysis: Analysis) {
  const [west, south, east, north] = analysis.request.bbox;
  return [west, south, east, north] as const;
}

function UploadSummary({ analysis }: { analysis: Analysis }) {
  const map = useMainMap();
  const upload = analysis.upload;
  if (!upload) return null;
  const anomalies = upload.anomalies;
  return (
    <div className="flex flex-col gap-1.5 rounded-[2px] border border-line-hairline bg-surface-raised px-2.5 py-2 text-[12px] leading-4">
      <span className="font-semibold text-text-primary">
        {upload.kind === "sentinel2"
          ? `Sentinel-2, ${upload.bands} каналов: детектор отработал — результат ниже`
          : `Картинка, ${upload.bands} канала: детекция невозможна, показаны снимок и яркие аномалии`}
      </span>
      {analysis.messages.map((message) => (
        <span key={message} className="text-text-secondary">
          {message}
        </span>
      ))}
      {upload.kind === "visible" ? (
        anomalies.length ? (
          <>
            <span className="text-text-secondary">
              Ярких аномалий на снимке: {anomalies.length} (розовые на карте). Это суда, пена, блики
              или скопления — различить их по RGB нельзя.
            </span>
            <div className="flex flex-wrap gap-1">
              {anomalies.slice(0, 12).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => map && easeToIfOutside(map, [item.centroid[0], item.centroid[1]])}
                  className="h-6 rounded-[2px] border border-line-control px-1.5 font-mono text-[11px] text-text-secondary hover:text-text-primary"
                  title={`${formatNumber(item.pixels)} пикс., контраст ${formatNumber(item.contrast, 0)}`}
                >
                  {item.id}
                </button>
              ))}
            </div>
          </>
        ) : (
          <span className="text-text-secondary">Ярких аномалий не найдено.</span>
        )
      ) : null}
    </div>
  );
}

export function UploadSection() {
  const client = useQueryClient();
  const map = useMainMap();
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  const input = useRef<HTMLInputElement>(null);
  const [date, setDate] = useState("");
  const [open, setOpen] = useState(false);
  const current = useCurrentAnalysis().data ?? null;
  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadImage(file, {
        name: file.name,
        bbox: map ? visibleBounds(map) : null,
        date: date || null,
      }),
    onSuccess: (analysis) => {
      client.setQueryData(queryKeys.analyses.detail(analysis.id), analysis);
      void client.invalidateQueries({ queryKey: ["analyses", "list"] });
      setAnalysis(analysis.id);
      if (map) fitTo(map, areaBounds(analysis));
    },
  });
  const pick = (file: File | undefined) => {
    if (file) upload.mutate(file);
  };

  return (
    <PanelSection
      title="Свой снимок"
      aside={
        <Button size="sm" variant="quiet" onClick={() => setOpen((value) => !value)}>
          {open ? "свернуть" : "загрузить"}
        </Button>
      }
    >
      <p className="text-[12px] leading-4 text-text-secondary">
        Загрузите GeoTIFF Sentinel-2 — сервис сам наложит его на карту и прогонит тот же детектор,
        флаги, композиты и долю покрытия. PNG и JPEG тоже примет: покажет снимок и яркие аномалии.
      </p>
      {open ? (
        <>
          <div
            role="button"
            tabIndex={0}
            onClick={() => input.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") input.current?.click();
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              pick(event.dataTransfer.files[0]);
            }}
            className="flex min-h-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-[2px] border border-dashed border-line-control px-3 py-3 text-center text-[12px] leading-4 text-text-secondary hover:border-line-strong hover:text-text-primary"
          >
            <span className="font-semibold text-text-primary">
              {upload.isPending ? "Загружаем и считаем…" : "Перетащите файл или нажмите"}
            </span>
            <span>GeoTIFF (.tif) · PNG · JPEG · до 150 МБ</span>
          </div>
          <input
            ref={input}
            type="file"
            accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg"
            className="hidden"
            onChange={(event) => {
              pick(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <label className="flex items-center gap-2 text-[12px] text-text-secondary">
            Дата снимка
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="h-7 rounded-[2px] border border-line-control bg-transparent px-2 text-text-primary"
            />
            <span className="text-text-tertiary">для концентрации и погоды; иначе — сегодня</span>
          </label>
          {upload.isError ? (
            <p className="text-[12px] leading-4 text-state-alarm">
              {upload.error instanceof Error ? upload.error.message : "Файл не обработан"}
            </p>
          ) : null}
          <details className="text-[12px] leading-4">
            <summary className="cursor-pointer text-text-secondary hover:text-text-primary">
              Ограничения
            </summary>
            <ul className="mt-1 flex list-disc flex-col gap-1 pl-4 text-text-secondary">
              {LIMITS.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </details>
        </>
      ) : null}
      {current?.upload ? <UploadSummary analysis={current} /> : null}
    </PanelSection>
  );
}
