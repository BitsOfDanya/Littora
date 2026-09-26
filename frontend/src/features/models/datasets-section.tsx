"use client";

import { DATASET_ROLE_LABEL, DATASETS, type DatasetEntry, doiUrl } from "@/config/datasets";
import { Button } from "@/ui/button";
import { IconCheck, IconCopy } from "@/ui/icons";
import { Caps } from "@/ui/section";
import { ReportSection } from "./report-section";
import { type CopyState, useCopyText } from "./use-copy-text";

const FACT_LABEL = "text-[12px] leading-4 text-text-tertiary";
const FACT_VALUE = "text-[12px] leading-4 text-text-secondary";

const CITE_LABEL: Record<CopyState, string> = {
  idle: "Цитировать",
  copied: "Скопировано",
  failed: "Скопируйте вручную",
};

function CiteButton({
  entry,
  state,
  onCopy,
}: {
  entry: DatasetEntry;
  state: CopyState;
  onCopy: () => void;
}) {
  return (
    <Button
      size="sm"
      onClick={onCopy}
      title={entry.citation}
      aria-label={`Цитировать ${entry.name}: скопировать ссылку на источник`}
      icon={state === "copied" ? <IconCheck size={14} /> : <IconCopy size={14} />}
      className="min-w-[128px] justify-start"
    >
      <span aria-live="polite">{CITE_LABEL[state]}</span>
    </Button>
  );
}

function selectContents(element: HTMLElement | null) {
  if (!element) return;
  const range = document.createRange();
  range.selectNodeContents(element);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

function DoiLink({ label, doi }: { label: string; doi: string }) {
  const cut = doi.indexOf("/") + 1;
  const prefix = doi.slice(0, cut);
  const suffix = doi.slice(cut);
  return (
    <span className="flex flex-col">
      <span className={FACT_LABEL}>{label}</span>
      <a
        href={doiUrl(doi)}
        target="_blank"
        rel="noreferrer"
        className="w-fit font-mono text-[11px] leading-4 break-words text-text-primary underline decoration-line-control underline-offset-2 hover:decoration-text-primary"
      >
        doi:{prefix}
        <wbr />
        {suffix}
      </a>
    </span>
  );
}

function DatasetRow({ entry }: { entry: DatasetEntry }) {
  const [copyState, copy] = useCopyText();
  const facts: readonly [string, string][] = [
    ["Разметка", entry.labels],
    ["Сенсор", entry.sensor],
    ["Период", entry.period],
    ["Район", entry.coverage],
    ["Объём", entry.volume],
    ["В Littora", entry.useInLittora],
  ];
  return (
    <article
      aria-labelledby={`dataset-${entry.id}`}
      className="grid grid-cols-12 gap-x-6 gap-y-3 border-b border-line-hairline py-4"
    >
      <header className="col-span-12 flex flex-col gap-1 @2xl:col-span-4 @4xl:col-span-3">
        <h3
          id={`dataset-${entry.id}`}
          className="text-[15px] leading-5 font-semibold text-text-primary"
        >
          {entry.name}
        </h3>
        <p className="text-[12px] leading-4 text-text-secondary">{entry.fullName}</p>
        <p className="text-[12px] leading-4 text-text-tertiary">{entry.source}</p>
        <Caps className="mt-1">
          {entry.roles.map((role) => DATASET_ROLE_LABEL[role]).join(" · ")}
        </Caps>
      </header>
      <div className="col-span-12 flex flex-col gap-2 @2xl:col-span-8 @4xl:col-span-6">
        <p className="text-[13px] leading-5 text-text-primary">{entry.contents}</p>
        <dl className="grid grid-cols-[76px_minmax(0,1fr)] gap-x-3 gap-y-1">
          {facts.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className={FACT_LABEL}>{label}</dt>
              <dd className={FACT_VALUE}>{value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="col-span-12 flex flex-wrap items-start gap-x-6 gap-y-2 @2xl:col-start-5 @2xl:col-end-13 @4xl:col-span-3 @4xl:col-start-auto @4xl:flex-col @4xl:gap-y-2.5">
        <span className="flex flex-col">
          <span className={FACT_LABEL}>Лицензия</span>
          <span className="font-mono text-[12px] leading-4 text-text-primary">{entry.license}</span>
        </span>
        <DoiLink label="Данные" doi={entry.doi} />
        <DoiLink label="Статья" doi={entry.paperDoi} />
        <CiteButton entry={entry} state={copyState} onCopy={() => copy(entry.citation)} />
      </div>
      {copyState === "failed" ? (
        <p
          ref={selectContents}
          className="col-span-12 border border-dashed border-line-control bg-surface-sunken p-2 font-mono text-[11px] leading-4 text-text-primary select-all"
        >
          {entry.citation}
        </p>
      ) : null}
    </article>
  );
}

export function DatasetsSection({ index = 4 }: { index?: number }) {
  return (
    <ReportSection id="datasets" index={index}>
      <div
        aria-hidden
        className="hidden grid-cols-12 gap-x-6 border-b border-text-primary pb-2 text-[12px] leading-4 font-medium text-text-secondary @4xl:grid"
      >
        <span className="col-span-3">Набор</span>
        <span className="col-span-6">Состав и происхождение</span>
        <span className="col-span-3">Лицензия и ссылки</span>
      </div>
      <div className="border-t border-text-primary @4xl:border-t-0">
        {DATASETS.map((entry) => (
          <DatasetRow key={entry.id} entry={entry} />
        ))}
      </div>
      <p className="mt-3 text-[12px] leading-4 text-text-tertiary">
        Размеры и доступность проверены по Zenodo 24–25.09.2026. Цитата копируется целиком: статья и
        DOI набора.
      </p>
    </ReportSection>
  );
}
