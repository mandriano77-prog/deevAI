import { clsx } from "clsx";

interface MetricCardProps {
  label: string;
  value: string;
  hint?: string;
  trend?: "up" | "down" | "neutral";
  trendColor?: "good" | "bad" | "neutral";
}

export function MetricCard({
  label,
  value,
  hint,
  trend,
  trendColor = "neutral",
}: MetricCardProps) {
  const trendChar = trend === "up" ? "↑" : trend === "down" ? "↓" : "";
  const colorClass =
    trendColor === "good"
      ? "text-accent-400"
      : trendColor === "bad"
      ? "text-red-400"
      : "text-ink-400";

  return (
    <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
      <div className="text-xs text-ink-400">{label}</div>
      <div className="mt-2 text-2xl font-medium text-ink-50">{value}</div>
      {hint ? (
        <div className={clsx("mt-1 text-xs", colorClass)}>
          {trendChar ? <span className="mr-1">{trendChar}</span> : null}
          {hint}
        </div>
      ) : null}
    </div>
  );
}
