"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TrendPoint } from "@/lib/mock-data";

interface CpvTrendChartProps {
  points: TrendPoint[];
  target: number;
}

export function CpvTrendChart({ points, target }: CpvTrendChartProps) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#252523" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="weekLabel"
            stroke="#86857f"
            tick={{ fontSize: 11 }}
            axisLine={{ stroke: "#252523" }}
            tickLine={false}
          />
          <YAxis
            stroke="#86857f"
            tick={{ fontSize: 11 }}
            axisLine={{ stroke: "#252523" }}
            tickLine={false}
            tickFormatter={(v) => `${v.toFixed(2)} €`}
            domain={[0.3, "dataMax + 0.05"]}
          />
          <Tooltip
            contentStyle={{
              background: "#0e0e0c",
              border: "1px solid #252523",
              borderRadius: 6,
              fontSize: 12,
              color: "#e7e7e4",
            }}
            labelStyle={{ color: "#86857f" }}
            formatter={(v: number) => [`${v.toFixed(2)} €`, "CPV"]}
          />
          <ReferenceLine
            y={target}
            stroke="#86857f"
            strokeDasharray="4 4"
            label={{
              value: `target ${target.toFixed(2)} €`,
              fill: "#86857f",
              fontSize: 11,
              position: "right",
            }}
          />
          <Line
            type="monotone"
            dataKey="cpv"
            stroke="#3aa882"
            strokeWidth={2}
            dot={{ r: 3, fill: "#3aa882", stroke: "#3aa882" }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
