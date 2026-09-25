import type { Metadata } from "next";
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
