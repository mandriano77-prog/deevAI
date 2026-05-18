/**
 * DeevAI wordmark — three treatments, one component.
 *
 *   <Wordmark variant="logo" />        →  DeevAI  (primary, accent on capital A)
 *   <Wordmark variant="text" />        →  DeevAI  (sentence-case, for navbars and docs)
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
        DeevAI
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
        <span>D</span>
        <span className="text-ink-400 mx-1 -translate-y-[0.06em]">·</span>
        <span>eev</span>
        <span className="text-ink-400 mx-1 -translate-y-[0.06em]">·</span>
        <span className="text-accent-400">AI</span>
      </span>
    );
  }

  // Default: logo variant — DeevAI (accent on the "AI" part)
  return (
    <span
      className={clsx(
        "font-sans font-medium tracking-tight inline-flex items-baseline",
        className,
      )}
    >
      <span>Deev</span>
      <span className="text-accent-400 font-normal">AI</span>
    </span>
  );
}
