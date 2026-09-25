import { PlannedTag } from "@/ui/planned";
import { PIPELINE_STEPS } from "./copy";
import { ReportSection } from "./report-section";

export function PipelineSection() {
  return (
    <ReportSection id="pipeline" index={6} aside={<PlannedTag capability="model_evaluation" />}>
      <ol className="grid grid-cols-1 gap-x-6 @xl:grid-cols-2 @3xl:grid-cols-3 @4xl:grid-cols-6">
        {PIPELINE_STEPS.map((step, index) => (
          <li
            key={step.title}
            className="flex flex-col gap-1.5 border-t border-dashed border-line-control pt-2.5 pb-4"
          >
            <span className="flex items-center justify-between gap-2">
              <span className="font-mono text-[11px] text-text-tertiary">
                {String(index + 1).padStart(2, "0")}
              </span>
              <PlannedTag capability="model_evaluation" />
            </span>
            <span className="text-[13px] leading-[18px] font-semibold text-text-primary">
              {step.title}
            </span>
            <span className="text-[12px] leading-4 text-text-secondary">{step.text}</span>
          </li>
        ))}
      </ol>
    </ReportSection>
  );
}
