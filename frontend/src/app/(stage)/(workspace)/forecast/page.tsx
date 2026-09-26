import type { Metadata } from "next";
import { ModeHint } from "@/features/analysis/mode-hint";
import { ForecastCandidates } from "@/features/forecast/forecast-candidates";
import { ForecastEffects } from "@/features/forecast/forecast-effects";
import { ForecastHotkeys } from "@/features/forecast/forecast-hotkeys";
import { ForecastInspector } from "@/features/forecast/forecast-inspector";
import { ForecastLayers } from "@/features/forecast/forecast-layers";
import { HorizonRail } from "@/features/forecast/horizon-rail";
import { HorizonStepper } from "@/features/forecast/horizon-stepper";
import { ParticlesLayer } from "@/features/forecast/particles-layer";
import { ShellSlot } from "@/features/shell/shell-slots";

export const metadata: Metadata = { title: "Прогноз" };

export default function ForecastPage() {
  return (
    <>
      <ModeHint
        title="Прогноз дрейфа"
        steps={[
          "Выберите анализ с зонами",
          "Облако — где зона будет через 6–72 ч",
          "Пунктир назад — откуда она пришла; это сценарий, не прогноз",
        ]}
      />
      <ForecastLayers />
      <ForecastCandidates />
      <ParticlesLayer />
      <ForecastHotkeys />
      <ForecastEffects />
      <ForecastInspector />
      <ShellSlot region="rail">
        <HorizonRail />
      </ShellSlot>
      <ShellSlot region="stepper">
        <HorizonStepper />
      </ShellSlot>
    </>
  );
}
