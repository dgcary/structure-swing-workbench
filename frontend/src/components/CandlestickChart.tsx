import { useEffect, useRef } from "react";
import { dispose, init } from "klinecharts";
import type { Chart, KLineData } from "klinecharts";

export function CandlestickChart({ bars }: { bars: KLineData[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);
  const barsRef = useRef<KLineData[]>(bars);
  barsRef.current = bars;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = init(container);
    if (!chart) return;
    chartRef.current = chart;
    chart.setDataLoader({
      getBars: ({ callback }) => {
        callback([...barsRef.current]);
      },
    });
    return () => {
      dispose(container);
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.resetData();
  }, [bars]);

  return <div ref={containerRef} className="chart-container" />;
}
