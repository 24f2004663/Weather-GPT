'use client';

import React from 'react';
import { DailyForecast } from '../types';
import { t } from '../lib/translations';
import WeatherIcon from './WeatherIcon';
import { CloudRain } from 'lucide-react';

interface DailyForecastGridProps {
  daily: DailyForecast[];
  currentLanguage?: string;
}

export default function DailyForecastGrid({ daily, currentLanguage = 'en' }: DailyForecastGridProps) {
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

  return (
    <div className="w-full glass rounded-3xl p-6 md:p-8 shadow-lg space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-white/90">
            {t('forecast7d', currentLanguage)}
          </h3>
          <p className="text-xs text-white/70">{t('multiDayProjections', currentLanguage)}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3">
        {daily.slice(0, 7).map((day, idx) => (
          <div
            key={idx}
            className="bg-white/5 border border-white/10 rounded-2xl p-4 flex flex-col justify-between items-center text-center hover:bg-white/10 transition-colors space-y-2 backdrop-blur-md"
          >
            <div className="text-xs font-semibold text-white/80">
              {formatWeekday(day.date)}
            </div>

            <div className="my-1 text-ink/85" title={day.weather_condition}>
              <WeatherIcon iconKey={day.icon_key} size={30} />
            </div>

            <div className="text-xs font-medium text-white/80 line-clamp-1">
              {day.weather_condition}
            </div>

            <div className="flex items-center space-x-1.5 text-xs">
              <span className="font-bold text-white">{day.temperature_max_c.toFixed(0)}°</span>
              <span className="text-white/50">/</span>
              <span className="text-white/70">{day.temperature_min_c.toFixed(0)}°</span>
            </div>

            {day.precipitation_probability_max !== null && day.precipitation_probability_max !== undefined && (
              <div className="w-full text-[10px] font-semibold text-sky-200 bg-sky-900/40 border border-sky-400/20 rounded-lg py-0.5">
                <CloudRain size={11} strokeWidth={2} aria-hidden="true" className="inline-block mr-1 -mt-0.5" />{day.precipitation_probability_max}%
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
