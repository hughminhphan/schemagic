import type { ReactNode } from "react";
import Header from "./Header";

interface Props {
  children: ReactNode;
  header?: "default" | "withBack" | "wordmarkOnly" | "none";
  backHref?: string;
  headerRight?: ReactNode;
}

export default function AppShell({
  children,
  header = "default",
  backHref,
  headerRight,
}: Props) {
  return (
    <div className="grid-bg min-h-screen flex flex-col">
      {header !== "none" ? (
        <Header layout={header} backHref={backHref} right={headerRight} />
      ) : null}
      <main className="flex-1 flex flex-col">{children}</main>
    </div>
  );
}
