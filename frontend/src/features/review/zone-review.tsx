"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createReview,
  getAnalysisReviews,
  type ReviewInput,
  type ReviewLabel,
} from "@/lib/api/review";
import { formatPercent } from "@/lib/format/numbers";
import { queryKeys } from "@/lib/query/query-keys";
import { cn } from "@/ui/cn";
import { Button } from "@/ui/button";

const MAIN_LABELS: readonly [ReviewLabel, string][] = [
  ["likely_debris", "мусор"],
  ["ship", "судно"],
  ["structure", "сооружение"],
  ["plume", "шлейф/цветение"],
  ["land_edge", "берег"],
  ["water", "не видно"],
];

const MORE_LABELS: readonly [ReviewLabel, string][] = [
  ["wake", "кильватер"],
  ["foam", "пена"],
  ["slick", "пятно"],
  ["cloud_edge", "край облака"],
  ["unknown", "не понять"],
];

const TITLES = new Map<ReviewLabel, string>([...MAIN_LABELS, ...MORE_LABELS]);

function LabelButton({
  label,
  title,
  active,
  onPick,
}: {
  label: ReviewLabel;
  title: string;
  active: boolean;
  onPick: (label: ReviewLabel) => void;
}) {
  return (
    <Button
      size="sm"
      variant={active ? "primary" : "default"}
      aria-pressed={active}
      onClick={() => onPick(label)}
    >
      {title}
    </Button>
  );
}

export function ZoneReview({ analysisId, zoneId }: { analysisId: string; zoneId: string }) {
  const client = useQueryClient();
  const [confidence, setConfidence] = useState<1 | 2 | 3>(2);
  const [comment, setComment] = useState("");
  const [more, setMore] = useState(false);
  const reviews = useQuery({
    queryKey: queryKeys.reviews.analysis(analysisId),
    queryFn: ({ signal }) => getAnalysisReviews(analysisId, signal),
  });
  const save = useMutation({
    mutationFn: (input: ReviewInput) => createReview(analysisId, zoneId, input),
    onSuccess: () => {
      setComment("");
      void client.invalidateQueries({ queryKey: queryKeys.reviews.all });
    },
  });
  const zone = reviews.data?.zones.find((item) => item.zone_id === zoneId) ?? null;
  const summary = reviews.data?.summary ?? null;
  const pick = (label: ReviewLabel) =>
    save.mutate({ label, confidence, comment: comment.trim() || null, reviewer: null });

  return (
    <div className="flex flex-col gap-2 text-[12px] leading-4">
      <p className="text-text-secondary">
        Что это на самом деле? Отметка команды копится и идёт в дообучение как трудный пример.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {MAIN_LABELS.map(([label, title]) => (
          <LabelButton
            key={label}
            label={label}
            title={title}
            active={zone?.consensus === label}
            onPick={pick}
          />
        ))}
        <Button size="sm" variant="quiet" onClick={() => setMore((value) => !value)}>
          {more ? "меньше" : "ещё"}
        </Button>
      </div>
      {more ? (
        <div className="flex flex-wrap gap-1.5">
          {MORE_LABELS.map(([label, title]) => (
            <LabelButton
              key={label}
              label={label}
              title={title}
              active={zone?.consensus === label}
              onPick={pick}
            />
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-text-secondary">
        <span>Уверенность</span>
        {([1, 2, 3] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={confidence === value}
            onClick={() => setConfidence(value)}
            className={cn(
              "h-6 min-w-6 rounded-[2px] border border-line-hairline px-1.5 font-mono text-[11px]",
              confidence === value ? "bg-surface-raised text-text-primary" : "text-text-secondary",
            )}
          >
            {value}
          </button>
        ))}
        <input
          value={comment}
          maxLength={200}
          onChange={(event) => setComment(event.target.value)}
          placeholder="комментарий, необязательно"
          className="h-6 min-w-0 flex-1 rounded-[2px] border border-line-hairline bg-transparent px-2 text-[12px] text-text-primary placeholder:text-text-tertiary"
        />
      </div>
      {save.isError ? <p className="text-state-alarm">Отметка не сохранилась, повторите.</p> : null}
      {zone && zone.reviews.length ? (
        <p className="text-text-secondary">
          Отметки по зоне:{" "}
          {zone.reviews
            .map((item) => `${TITLES.get(item.label) ?? item.label_title} (${item.confidence})`)
            .join(", ")}
          {zone.consensus ? ` · итог: ${TITLES.get(zone.consensus) ?? zone.consensus}` : null}
        </p>
      ) : null}
      {summary && summary.zones ? (
        <p className="text-text-tertiary">
          В этом анализе проверено {summary.zones} из {summary.zones_total} зон; мусором команда
          признала{" "}
          {summary.precision.value === null ? "—" : formatPercent(summary.precision.value, 0)}{" "}
          проверенных.
        </p>
      ) : null}
    </div>
  );
}
