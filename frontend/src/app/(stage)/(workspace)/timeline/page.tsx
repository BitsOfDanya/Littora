import type { Metadata } from "next";
import { ModeHint } from "@/features/analysis/mode-hint";
import { ShellSlot } from "@/features/shell/shell-slots";
import { CompareDivider } from "@/features/timeline/compare-divider";
import { CompareInspector } from "@/features/timeline/compare-inspector";
import { CompareMapLayers } from "@/features/timeline/compare-map-layers";
import { CompareMethodBox } from "@/features/timeline/compare-method-box";
import { CompareRail } from "@/features/timeline/compare-rail";
import { CompareStepper } from "@/features/timeline/compare-stepper";
import { TimelineCompareKeys } from "@/features/timeline/timeline-compare-keys";

export const metadata: Metadata = { title: "Динамика" };

export default function TimelinePage() {
  return (
    <>
      <ModeHint
        title="Динамика"
        steps={[
          "Выберите пролёты на ленте",
          "«Посчитать» — детектор по каждому",
          "Сравните два пролёта: новые, сохранившиеся, исчезнувшие зоны",
        ]}
      />
      <CompareMapLayers />
      <TimelineCompareKeys />
      <ShellSlot region="map-overlay">
        <CompareDivider />
        <CompareMethodBox />
      </ShellSlot>
      <CompareInspector />
      <ShellSlot region="rail">
        <CompareRail />
      </ShellSlot>
      <ShellSlot region="stepper">
        <CompareStepper />
      </ShellSlot>
    </>
  );
}
