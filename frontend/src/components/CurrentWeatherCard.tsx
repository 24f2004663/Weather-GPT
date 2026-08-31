'use client';

import React from 'react';
import { NormalizedWeatherResponse } from '../types';
import { t } from '../lib/translations';

interface CurrentWeatherCardProps {
  weather: NormalizedWeatherResponse | null;
  isLoading: boolean;
  currentLanguage?: string;
}

export default function CurrentWeatherCard({ weather, isLoading, currentLanguage = 'en' }: CurrentWeatherCardProps) {
  if (isLoading) {
    return (
      <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 animate-pulse space-y-6">
        <div className="h-6 bg-slate-800 rounded-md w-1/3"></div>
        <div className="h-16 bg-slate-800 rounded-xl w-1/2"></div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4">
          <div className="h-14 bg-slate-800 rounded-xl"></div>
          <div className="h-14 bg-slate-800 rounded-xl"></div>
          <div className="h-14 bg-slate-800 rounded-xl"></div>
          <div className="h-14 bg-slate-800 rounded-xl"></div>
        </div>
      </div>
    );
  }

  if (!weather) {
    return (
      <div className="w-full bg-slate-900/80 border border-slate-800 rounded-3xl p-8 text-center space-y-3">
        <div className="text-4xl">🌤️</div>
        <h3 className="text-lg font-semibold text-white">No Weather Data Selected</h3>
        <p className="text-xs text-slate-400 max-w-sm mx-auto">
          Search for a city above or allow GPS to view real-time meteorological observations.
        </p>
      </div>
    );
  }

  const { current, location, timezone, elevation_m, cached } = weather;

  const getWeatherIcon = (iconKey: string) => {
    switch (iconKey) {
      case 'clear-day': return '☀️';
      case 'mainly-clear': return '🌤️';
      case 'partly-cloudy': return '⛅';
      case 'overcast': return '☁️';
      case 'fog': return '🌫️';
      case 'drizzle': return '🌦️';
      case 'rain-light': return '🌧️';
      case 'rain-moderate': return '🌧️';
      case 'rain-heavy': return '⛈️';
      case 'thunderstorm': return '⚡';
      case 'thunderstorm-hail': return '⛈️';
      case 'snow':
      case 'snow-light':
      case 'snow-heavy': return '❄️';
      default: return '🌤️';
    }
  };

  return (
    <div className="w-full bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl space-y-6 relative overflow-hidden">
      {/* Top Banner: Location & Cache Status */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-sky-400">
              {t('liveObservation', currentLanguage)}
            </span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
              cached
                ? 'bg-amber-950/80 text-amber-400 border border-amber-800'
                : 'bg-emerald-950/80 text-emerald-400 border border-emerald-800'
            }`}>
              {cached ? 'CACHE HIT' : 'LIVE FEED'}
            </span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight mt-1">
            {location.name}
            {location.admin1 ? <span className="text-slate-400 text-xl font-medium">, {location.admin1}</span> : null}
          </h2>
          <p className="text-xs text-slate-400">
            {location.country || 'Global Location'} • {location.latitude.toFixed(2)}°N, {location.longitude.toFixed(2)}°E
            {elevation_m !== null && elevation_m !== undefined ? ` • ${elevation_m}m elev.` : ''}
          </p>
        </div>

        <div className="text-right text-[11px] font-mono text-slate-400">
          <div>Timezone: {timezone}</div>
          <div className="text-[10px] text-slate-500">
            Observed: {new Date(current.observed_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>
      </div>

      {/* Hero Temperature & Condition */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 py-2">
        <div className="flex items-center space-x-5">
          <div className="text-6xl sm:text-7xl filter drop-shadow-md select-none">
            {getWeatherIcon(current.icon_key)}
          </div>
          <div>
            <div className="text-5xl sm:text-6xl font-black tracking-tighter text-white">
              {current.temperature_c !== null ? `${current.temperature_c.toFixed(1)}°` : 'N/A'}
              <span className="text-2xl sm:text-3xl text-sky-400 font-medium ml-1">C</span>
            </div>
            <div className="text-lg font-semibold text-slate-200">
              {current.weather_condition}
            </div>
            <div className="text-xs text-slate-400">
              {t('feelsLike', currentLanguage)}:{' '}
              <span className="text-slate-200 font-medium">
                {current.apparent_temperature_c !== null && current.apparent_temperature_c !== undefined
                  ? `${current.apparent_temperature_c.toFixed(1)}°C`
                  : 'Unavailable'}
              </span>
            </div>
          </div>
        </div>

        {/* Highlight Stats Pill */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-2xl p-4 sm:max-w-xs w-full grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-slate-500 font-medium">{t('humidity', currentLanguage)}</div>
            <div className="text-sm font-bold text-white mt-0.5">
              {current.humidity_percent !== null && current.humidity_percent !== undefined
                ? `${current.humidity_percent}%`
                : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-slate-500 font-medium">{t('windSpeed', currentLanguage)}</div>
            <div className="text-sm font-bold text-white mt-0.5">
              {current.wind_speed_kmh !== null && current.wind_speed_kmh !== undefined
                ? `${current.wind_speed_kmh} km/h`
                : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-slate-500 font-medium">{t('precipitation', currentLanguage)}</div>
            <div className="text-sm font-bold text-white mt-0.5">
              {current.precipitation_mm !== null && current.precipitation_mm !== undefined
                ? `${current.precipitation_mm} mm`
                : '0.0 mm'}
            </div>
          </div>
          <div>
            <div className="text-slate-500 font-medium">{t('uvIndex', currentLanguage)}</div>
            <div className="text-sm font-bold text-white mt-0.5">
              {current.uv_index !== null && current.uv_index !== undefined
                ? `${current.uv_index}`
                : 'N/A'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
