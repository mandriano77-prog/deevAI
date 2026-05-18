/**
 * DeevAI wordmark — three treatments, one component.
 *
 *   <Wordmark variant="logo" />        →  DeevAI  (primary, caps frame + lowercase i)
 *   <Wordmark variant="text" />        →  DeevAI  (sentence-case, for navbars and docs)
 *   <Wordmark variant="editorial" />   →  m·AI·naus (hero / pitch deck moments)
 *
 * Pronounced "Manaus" in all variants — the "i" is a visual wink, silent in speech.
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
        <span>m</span>
        <span className="text-ink-400 mx-1 -translate-y-[0.06em]">·</span>
        <span className="text-accent-400">AI</span>
        <span className="text-ink-400 mx-1 -translate-y-[0.06em]">·</span>
        <span>naus</span>
      </span>
    );
  }

  // Default: logo variant — DeevAI
  return (
    <span
      className={clsx(
        "font-sans font-medium tracking-tight inline-flex items-baseline",
        className,
      )}
    >
      <span>MA</span>
      <span className="text-accent-400 font-normal">i</span>
      <span>NAUS</span>
    </span>
  );
}
