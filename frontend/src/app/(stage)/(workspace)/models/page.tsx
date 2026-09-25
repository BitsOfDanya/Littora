import type { Metadata } from "next";
import { ModelsReport } from "@/features/models/models-report";

export const metadata: Metadata = { title: "Модели" };

export default function ModelsPage() {
  return <ModelsReport />;
}
