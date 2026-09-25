import { StageRoot } from "@/features/stage/stage-root";

export default function StageLayout({ children }: LayoutProps<"/">) {
  return <StageRoot>{children}</StageRoot>;
}
