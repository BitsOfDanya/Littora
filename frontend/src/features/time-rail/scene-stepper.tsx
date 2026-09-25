"use client";

import { formatPercent } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import { useWorkspaceStore } from "@/state/workspace-store";
import { DemoTag } from "@/ui/demo-mark";
import { IconCaution } from "@/ui/icons";
import { StepperStrip } from "@/ui/stepper-strip";
import { useSceneStepping } from "./use-scene-stepping";
import { useSelectedScene } from "./use-selected-scene";

export function SceneStepper() {
  const { scenes, isDemo } = useSelectedScene();
  const stepping = useSceneStepping(scenes);
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  const scene = stepping.current;

  return (
    <StepperStrip
      label="Снимок"
      previousLabel="Предыдущий пролёт"
      nextLabel="Следующий пролёт"
      canStepBack={stepping.canStepBack}
      canStepForward={stepping.canStepForward}
      onStep={(direction) => stepping.step(direction)}
    >
      {scene ? (
        <>
          <span className="font-mono text-[14px] font-semibold whitespace-nowrap text-text-primary">
            {formatUtcDateTime(scene.acquiredAt)}
          </span>
          <span className="font-mono text-[12px] text-text-secondary">{scene.platform}</span>
          {scene.usability === "usable" ? null : (
            <span className="inline-flex items-center gap-1 text-[12px] text-state-caution">
              <IconCaution size={12} />
              {formatPercent(scene.cloudCover)}
            </span>
          )}
          {isDemo ? <DemoTag /> : null}
        </>
      ) : (
        <span className="flex flex-col items-center text-[12px] leading-4 text-text-secondary">
          <span>Снимок не выбран · каталог не подключён</span>
          <button
            type="button"
            onClick={() => setDemoFixtures(true)}
            className="text-text-primary underline underline-offset-2"
          >
            Показать на демо-данных
          </button>
        </span>
      )}
    </StepperStrip>
  );
}
