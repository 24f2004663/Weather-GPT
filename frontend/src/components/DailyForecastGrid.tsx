'use client';

import React from 'react';
import { DailyForecast } from '../types';

interface DailyForecastGridProps {
  daily: DailyForecast[];
}

export default function DailyForecastGrid({ daily }: DailyForecastGridProps) {
  if (!daily || daily.length === 0) {
    return null;
  }

  const formatWeekday = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
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
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-xl space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            7-Day Synoptic Forecast
          </h3>
          <p className="text-xs text-slate-400">Multi-day high/low projections and rain probability</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3">
        {daily.slice(0, 7).map((day, idx) => (
          <div
            key={idx}
            className="bg-slate-950/70 border border-slate-800/80 rounded-2xl p-4 flex flex-col justify-between items-center text-center hover:border-slate-700 transition-colors space-y-2"
          >
            <div className="text-xs font-semibold text-slate-300">
              {formatWeekday(day.date)}
            </div>

            <div className="text-3xl my-1 select-none" title={day.weather_condition}>
              {getConditionEmoji(day.icon_key)}
            </div>

            <div className="text-xs font-medium text-slate-300 line-clamp-1">
              {day.weather_condition}
            </div>

            <div className="flex items-center space-x-1.5 text-xs">
              <span className="font-bold text-white">{day.temperature_max_c.toFixed(0)}°</span>
              <span className="text-slate-500">/</span>
              <span className="text-slate-400">{day.temperature_min_c.toFixed(0)}°</span>
            </div>

            {day.precipitation_probability_max !== null && day.precipitation_probability_max !== undefined && (
              <div className="w-full text-[10px] font-semibold text-sky-400 bg-sky-950/60 border border-sky-900/60 rounded-lg py-0.5">
                🌧️ {day.precipitation_probability_max}%
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
