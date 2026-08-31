'use client';

import React from 'react';
import { HourlyForecast } from '../types';

interface HourlyForecastStripProps {
  hourly: HourlyForecast[];
}

export default function HourlyForecastStrip({ hourly }: HourlyForecastStripProps) {
  if (!hourly || hourly.length === 0) {
    return null;
  }

  const formatHour = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: 'numeric', hour12: true });
    } catch {
      return isoString.split('T')[1] || isoString;
    }
  };

  const getConditionEmoji = (iconKey: string) => {
    switch (iconKey) {
      case 'clear-day': return '☀️';
      case 'mainly-clear': return '🌤️';
      case 'partly-cloudy': return '⛅';
      case 'overcast': return '☁️';
      case 'fog': return '🌫️';
      case 'drizzle': return '🌦️';
      case 'rain-light':
      case 'rain-moderate': return '🌧️';
      case 'rain-heavy': return '⛈️';
      case 'thunderstorm': return '⚡';
      default: return '🌤️';
    }
  };

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            Hourly Timeline (Next 24h)
          </h3>
          <p className="text-xs text-slate-400">Hourly temperature and precipitation probability</p>
        </div>
        <span className="text-xs text-sky-400 font-mono">Horizontal Scroll →</span>
      </div>

      {/* Horizontal Scroll Strip */}
      <div className="flex gap-3 overflow-x-auto pb-2 pt-1 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900">
        {hourly.slice(0, 24).map((item, idx) => (
          <div
            key={idx}
            className="flex-shrink-0 w-24 bg-slate-950/70 hover:bg-slate-800/60 border border-slate-800/80 rounded-2xl p-3 text-center flex flex-col justify-between items-center transition-colors"
          >
            <span className="text-[11px] font-medium text-slate-400">
              {formatHour(item.time)}
            </span>
            <span className="text-2xl my-2 select-none" title={item.weather_condition}>
              {getConditionEmoji(item.icon_key)}
            </span>
            <div className="text-sm font-bold text-white">
              {item.temperature_c.toFixed(1)}°
            </div>
            {item.precipitation_probability !== null && item.precipitation_probability !== undefined && (
              <span className="mt-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-sky-950/80 text-sky-400 border border-sky-850">
                🌧️ {item.precipitation_probability}%
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
