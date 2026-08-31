'use client';

import React, { useState } from 'react';
import { HourlyForecast, DailyForecast } from '../types';

interface WeatherChartsProps {
  hourly: HourlyForecast[];
  daily: DailyForecast[];
}

export default function WeatherCharts({ hourly, daily }: WeatherChartsProps) {
  const [activeTab, setActiveTab] = useState<'temp' | 'precip' | '7day'>('temp');

  if (!hourly || hourly.length === 0) {
    return null;
  }

  // 1. 24-Hour Hourly Temperature Curve
  const next24 = hourly.slice(0, 24);
  const temps = next24.map((h) => h.temperature_c);
  const minTemp = Math.floor(Math.min(...temps) - 1);
  const maxTemp = Math.ceil(Math.max(...temps) + 1);
  const tempRange = maxTemp - minTemp || 1;

  const width = 800;
  const height = 180;
  const paddingX = 30;
  const paddingY = 25;

  const getX = (index: number) => {
    return paddingX + (index / (next24.length - 1)) * (width - 2 * paddingX);
  };

  const getY = (val: number) => {
    const norm = (val - minTemp) / tempRange;
    return height - paddingY - norm * (height - 2 * paddingY);
  };

  // Build SVG Path
  const points = next24.map((h, i) => `${getX(i)},${getY(h.temperature_c)}`);
  const svgPath = `M ${points.join(' L ')}`;
  const svgAreaPath = `${svgPath} L ${getX(next24.length - 1)},${height} L ${getX(0)},${height} Z`;

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            Meteorological Trends
          </h3>
          <p className="text-xs text-slate-400">Visualized hourly and synoptic projections</p>
        </div>

        {/* Tab Controls */}
        <div className="flex bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab('temp')}
            className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeTab === 'temp'
                ? 'bg-sky-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Hourly Temp (°C)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('precip')}
            className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeTab === 'precip'
                ? 'bg-sky-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Rain Probability (%)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('7day')}
            className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeTab === '7day'
                ? 'bg-sky-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            7-Day Max / Min
          </button>
        </div>
      </div>

      {/* Tab 1: Hourly Temperature SVG Curve */}
      {activeTab === 'temp' && (
        <div className="w-full overflow-x-auto">
          <div className="min-w-[600px]">
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-44 overflow-visible">
              <defs>
                <linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Shaded Area under curve */}
              <path d={svgAreaPath} fill="url(#tempGradient)" />

              {/* Grid Lines */}
              <line x1={paddingX} y1={getY(maxTemp)} x2={width - paddingX} y2={getY(maxTemp)} stroke="#334155" strokeDasharray="3 3" />
              <line x1={paddingX} y1={getY(minTemp)} x2={width - paddingX} y2={getY(minTemp)} stroke="#334155" strokeDasharray="3 3" />

              {/* Main Line */}
              <path d={svgPath} fill="none" stroke="#38bdf8" strokeWidth="2.5" strokeLinecap="round" />

              {/* Data points and labels (every 3 hours for readability) */}
              {next24.map((h, i) => {
                if (i % 3 !== 0 && i !== next24.length - 1) return null;
                const x = getX(i);
                const y = getY(h.temperature_c);
                const hourLabel = new Date(h.time).toLocaleTimeString([], { hour: 'numeric', hour12: true });

                return (
                  <g key={i}>
                    <circle cx={x} cy={y} r="4" fill="#38bdf8" stroke="#0f172a" strokeWidth="2" />
                    <text x={x} y={y - 8} textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="bold" fontFamily="sans-serif">
                      {h.temperature_c.toFixed(0)}°
                    </text>
                    <text x={x} y={height - 5} textAnchor="middle" fill="#94a3b8" fontSize="9" fontFamily="sans-serif">
                      {hourLabel}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>
      )}

      {/* Tab 2: Hourly Precipitation Probability Bars */}
      {activeTab === 'precip' && (
        <div className="w-full overflow-x-auto">
          <div className="min-w-[600px] h-44 flex items-end justify-between gap-1.5 px-4 pt-4 pb-2 bg-slate-950/60 rounded-2xl border border-slate-800">
            {next24.map((h, i) => {
              const prob = h.precipitation_probability ?? 0;
              const barHeight = Math.max(prob, 4);
              const hourLabel = new Date(h.time).toLocaleTimeString([], { hour: 'numeric', hour12: true });

              return (
                <div key={i} className="flex-1 flex flex-col items-center justify-end h-full group">
                  <span className="text-[9px] font-mono text-sky-400 opacity-0 group-hover:opacity-100 transition-opacity">
                    {prob}%
                  </span>
                  <div
                    style={{ height: `${barHeight}%` }}
                    className={`w-full max-w-[18px] rounded-t-md transition-all ${
                      prob > 50 ? 'bg-sky-500 shadow-md shadow-sky-500/30' : prob > 20 ? 'bg-sky-600/80' : 'bg-slate-800'
                    }`}
                  ></div>
                  <span className="text-[8px] font-mono text-slate-500 mt-1 truncate">
                    {i % 4 === 0 ? hourLabel : ''}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 3: 7-Day High vs Low Temperature Comparison */}
      {activeTab === '7day' && daily && daily.length > 0 && (
        <div className="w-full space-y-2.5">
          {daily.slice(0, 7).map((d, i) => {
            const overallMax = Math.max(...daily.map((x) => x.temperature_max_c));
            const overallMin = Math.min(...daily.map((x) => x.temperature_min_c));
            const totalSpan = overallMax - overallMin || 1;

            const leftPercent = ((d.temperature_min_c - overallMin) / totalSpan) * 100;
            const barWidth = Math.max(((d.temperature_max_c - d.temperature_min_c) / totalSpan) * 100, 8);

            return (
              <div key={i} className="flex items-center text-xs gap-3">
                <span className="w-20 font-medium text-slate-300 truncate">
                  {new Date(d.date).toLocaleDateString([], { weekday: 'short', month: 'numeric', day: 'numeric' })}
                </span>
                <span className="w-8 text-right text-slate-400 font-mono">
                  {d.temperature_min_c.toFixed(0)}°
                </span>
                <div className="flex-1 bg-slate-950 h-3 rounded-full relative overflow-hidden">
                  <div
                    style={{ left: `${leftPercent}%`, width: `${barWidth}%` }}
                    className="absolute h-full bg-gradient-to-r from-sky-500 to-amber-500 rounded-full"
                  ></div>
                </div>
                <span className="w-8 text-white font-bold font-mono">
                  {d.temperature_max_c.toFixed(0)}°
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
