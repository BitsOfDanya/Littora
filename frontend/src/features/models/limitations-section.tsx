import { LIMITATIONS } from "./copy";
import { ReportSection } from "./report-section";

export function LimitationsSection() {
  return (
    <ReportSection id="limits" index={5}>
      <ul className="grid grid-cols-12 gap-x-8 border-t border-text-primary">
        {LIMITATIONS.map((item) => (
          <li
            key={item.term}
            className="col-span-12 flex gap-3 border-b border-line-hairline py-3 @3xl:col-span-6"
          >
            <span aria-hidden className="mt-[7px] size-1.5 shrink-0 bg-text-secondary" />
            <p className="text-[13px] leading-5 text-text-secondary">
              <span className="font-semibold text-text-primary">{item.term}.</span> {item.text}
            </p>
          </li>
        ))}
      </ul>
    </ReportSection>
  );
}
