import { WorkspaceShell } from "@/features/shell/workspace-shell";

export default function WorkspaceLayout({ children }: LayoutProps<"/">) {
  return <WorkspaceShell>{children}</WorkspaceShell>;
}
