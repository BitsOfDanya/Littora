import type { Metadata } from "next";
import { CandidateLayers } from "@/features/monitor/candidate-layers";
import { ShellSlot } from "@/features/shell/shell-slots";
import { SurveyLayers } from "@/features/survey/survey-layers";
import { SurveyPanel } from "@/features/survey/survey-panel";
import { SurveyRail, SurveyStepper } from "@/features/survey/survey-rail";

export const metadata: Metadata = { title: "Обследование" };

export default function SurveyPage() {
  return (
    <>
      <CandidateLayers />
      <SurveyLayers />
      <SurveyPanel />
      <ShellSlot region="rail">
        <SurveyRail />
      </ShellSlot>
      <ShellSlot region="stepper">
        <SurveyStepper />
      </ShellSlot>
    </>
  );
}
