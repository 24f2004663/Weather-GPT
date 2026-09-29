'use client';

import React from 'react';
import { HourlyForecast } from '../types';
import { t } from '../lib/translations';
import WeatherIcon from './WeatherIcon';
import { CloudRain } from 'lucide-react';

interface HourlyForecastStripProps {
  hourly: HourlyForecast[];
  currentLanguage?: string;
}

export default function HourlyForecastStrip({ hourly, currentLanguage = 'en' }: HourlyForecastStripProps) {
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

  return (
    <div className="w-full glass rounded-3xl p-6 shadow-lg space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-white/90">
            {t('timeline24h', currentLanguage)}
          </h3>
          <p className="text-xs text-white/70">{t('timelineSub', currentLanguage)}</p>
        </div>
        <span className="text-xs text-sky-200 font-mono">{t('horizontalScroll', currentLanguage)}</span>
      </div>

      {/* Horizontal Scroll Strip */}
      <div className="flex gap-3 overflow-x-auto pb-2 pt-1 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-transparent">
        {hourly.slice(0, 24).map((item, idx) => (
          <div
            key={idx}
            className="flex-shrink-0 w-24 bg-white/5 hover:glass-inset rounded-2xl p-3 text-center flex flex-col justify-between items-center transition-colors"
          >
            <span className="text-[11px] font-medium text-white/80">
              {formatHour(item.time)}
            </span>
            <span className="my-2 text-ink/85" title={item.weather_condition}>
              <WeatherIcon iconKey={item.icon_key} size={24} />
            </span>
            <div className="text-sm font-semibold text-ink tabular-nums">
              {Math.round(item.temperature_c)}°
            </div>
            {item.precipitation_probability !== null && item.precipitation_probability !== undefined && (
              <span className="mt-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-sky-900/40 text-sky-200 border border-sky-400/20">
                <CloudRain size={10} strokeWidth={2} aria-hidden="true" className="inline-block mr-1 -mt-0.5" />{item.precipitation_probability}%
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
