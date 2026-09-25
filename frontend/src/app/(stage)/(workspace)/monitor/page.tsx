import type { Metadata } from "next";
import { CandidateInspector } from "@/features/inspector/candidate-inspector";
import { MonitorLayers } from "@/features/monitor/map/monitor-layers";
import { ShellSlot } from "@/features/shell/shell-slots";
import { SceneRail } from "@/features/time-rail/scene-rail";
import { SceneStepper } from "@/features/time-rail/scene-stepper";

export const metadata: Metadata = { title: "Мониторинг" };

export default function MonitorPage() {
  return (
    <>
      <MonitorLayers />
      <CandidateInspector />
      <ShellSlot region="rail">
        <SceneRail />
      </ShellSlot>
      <ShellSlot region="stepper">
        <SceneStepper />
      </ShellSlot>
    </>
  );
}
