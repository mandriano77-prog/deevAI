import type { ReactNode } from "react";

import { Sidebar } from "@/components/sidebar";
import { MaiButton } from "@/components/MaiButton";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="relative flex-1 overflow-y-auto bg-ink-900">
        {children}
        <MaiButton />
      </div>
    </div>
  );
}
