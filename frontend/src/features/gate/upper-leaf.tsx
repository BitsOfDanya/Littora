import { SITE } from "@/config/site";
import { BrandMark } from "@/ui/brand-mark";

function EventLine() {
  return (
    <p className="text-[12px] leading-4 text-(--gate-ink) md:text-[13px]">
      {SITE.event} · команда <span className="font-semibold">{SITE.team}</span>
    </p>
  );
}

function Wordmark() {
  return (
    <h1 className="flex items-end gap-3 text-(--gate-ink) md:gap-5">
      <BrandMark height={32} className="mb-2 md:hidden" />
      <BrandMark height={56} className="mb-[0.16em] hidden md:block" />
      <span className="-ml-[0.04em] font-serif text-[64px] leading-[0.86] font-medium tracking-[0.035em] italic [font-variation-settings:'opsz'_60] md:text-[clamp(64px,min(11.4vw,19dvh),172px)]">
        {SITE.product}
      </span>
    </h1>
  );
}

export function UpperLeafContent() {
  return (
    <div className="absolute inset-0 flex flex-col justify-between pt-4 pr-[calc(var(--gauge-col)+16px)] pb-5 pl-4 md:pt-[calc(var(--gate-frame)+16px)] md:pr-[calc(var(--gauge-col)+var(--gate-frame)+24px)] md:pb-8 md:pl-[calc(var(--gate-frame)+var(--gate-pad))]">
      <EventLine />
      <Wordmark />
    </div>
  );
}
