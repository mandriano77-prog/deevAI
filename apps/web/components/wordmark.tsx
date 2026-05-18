/**
 * deevAI wordmark — three treatments, one component.
 *
 *   <Wordmark variant="logo" />        →  deevAI   (primary, accent on AI)
 *   <Wordmark variant="text" />        →  deevAI   (sentence-case for navbars and docs)
 *   <Wordmark variant="editorial" />   →  d·eev·AI (hero / pitch deck moments)
 */

import { clsx } from "clsx";

type Variant = "logo" | "text" | "editorial";

interface WordmarkProps {
  variant?: Variant;
  className?: string;
}

export function Wordmark({ variant = "logo", className }: WordmarkProps) {
  if (variant === "text") {
    return (
      <span
        className={clsx(
          "font-sans font-medium tracking-tight",
          className,
        )}
      >
        deevAI
      </span>
    );
  }

  if (variant === "editorial") {
    return (
      <span
        className={clsx(
          "font-sans font-medium tracking-tightest inline-flex items-baseline",
          className,
        )}
      >
        <span>d</span>
        <span className="text-ink-400 mx-1 -translate-y-[0.06em]">·</span>
        <span>eev</span>
        <span className="text-ink-400 mx-1 -translate-y-[0.06em]">·</span>
        <span className="text-accent-400">AI</span>
      </span>
    );
  }

  // Default: logo variant — deevAI (lowercase deev, accent AI)
  return (
    <span
      className={clsx(
        "font-sans font-medium tracking-tight inline-flex items-baseline",
        className,
      )}
    >
      <span>deev</span>
      <span className="text-accent-400 font-normal">AI</span>
    </span>
  );
}
