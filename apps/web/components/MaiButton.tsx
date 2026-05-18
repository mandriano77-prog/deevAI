"use client";

import { useState } from "react";

import { MaiOverlay } from "./MaiOverlay";

export function MaiButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-6 right-6 z-50 flex h-[52px] w-[52px] items-center justify-center rounded-full bg-amber-500 text-xs font-extrabold text-black shadow-2xl shadow-amber-500/30 transition hover:scale-105"
        aria-label="Apri M.AI"
      >
        M.AI
      </button>
      {open ? <MaiOverlay onClose={() => setOpen(false)} /> : null}
    </>
  );
}
