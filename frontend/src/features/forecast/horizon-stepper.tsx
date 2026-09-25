"use client";

import { useForecastRun } from "@/data/forecast";
import { FORECAST_HORIZONS_H } from "@/domain/forecast";
import { useWorkspaceStore } from "@/state/workspace-store";
import { DemoTag } from "@/ui/demo-mark";
import { StepperStrip } from "@/ui/stepper-strip";
import { horizonLabel, shiftIso } from "./drift-math";
import { chooseHorizon } from "./forecast-hotkeys";

function shortTarget(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)} ${iso.slice(11, 16)}Z`;
}

export function HorizonStepper() {
  const horizonH = useWorkspaceStore((state) => state.forecastHorizonH);
  const run = useForecastRun();
  const index = FORECAST_HORIZONS_H.indexOf(horizonH);
  const ready = run.origin !== "none";

  return (
    <StepperStrip
      label="Горизонт прогноза"
      previousLabel="Меньший горизонт"
      nextLabel="Больший горизонт"
      canStepBack={ready && index > 0}
      canStepForward={ready && index < FORECAST_HORIZONS_H.length - 1}
      onStep={(direction) => chooseHorizon(FORECAST_HORIZONS_H[index + direction])}
    >
      {ready ? (
        <>
          <span className="font-mono text-[15px] font-semibold text-text-primary">
            {horizonLabel(horizonH)}
          </span>
          <span className="font-mono text-[12px] text-text-secondary">
            цель {shortTarget(shiftIso(run.data.t0, horizonH))}
          </span>
          {run.origin === "demo" ? <DemoTag /> : null}
        </>
      ) : (
        <span className="text-[12px] text-text-secondary">
          Прогноз не подключён · drift_forecast
        </span>
      )}
    </StepperStrip>
  );
}
