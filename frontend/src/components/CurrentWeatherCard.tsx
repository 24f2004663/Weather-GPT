'use client';

import React from 'react';
import { NormalizedWeatherResponse } from '../types';
import { t } from '../lib/translations';
import WeatherIcon from './WeatherIcon';

/**
 * Parses a backend timestamp as UTC.
 *
 * The API serialises naive UTC datetimes with no zone designator
 * ("2026-09-29T06:45:00"). `new Date()` reads a bare timestamp as LOCAL time, which in
 * IST would put the observation 5h30m in the future and render a negative age. Append
 * the designator unless one is already present.
 */
function parseUtc(value: string | undefined): Date | null {
  if (!value) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value);
  const parsed = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

interface CurrentWeatherCardProps {
  weather: NormalizedWeatherResponse | null;
  isLoading: boolean;
  currentLanguage?: string;
}

export default function CurrentWeatherCard({ weather, isLoading, currentLanguage = 'en' }: CurrentWeatherCardProps) {
  // The age is computed once per render rather than on a timer.
  //
  // A ticking clock here rewrote the badge text every 60s, and this card sits behind
  // backdrop-filter: blur(30px) — any DOM mutation inside forces the whole blurred pane
  // to re-rasterize, which reads as the card flashing. Measured: one mutation per
  // minute, one visible re-render per minute. The age still refreshes whenever the
  // weather data reloads, which is what actually changes the underlying observation.
  const now = Date.now();

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
      <div className="w-full glass rounded-3xl p-8 text-center space-y-3">
        <WeatherIcon size={40} className="mx-auto text-ink/70" />
        <h3 className="text-lg font-semibold text-ink">{t('noWeatherDataSelected', currentLanguage)}</h3>
        <p className="text-xs text-ink/60 max-w-sm mx-auto">
          {t('noWeatherDataDesc', currentLanguage)}
        </p>
      </div>
    );
  }

  const { current, location, timezone, elevation_m, stale } = weather;

  // How old the underlying observation is — the thing a user actually needs to judge,
  // rather than whether the backend happened to serve it from its cache.
  const observedAt = parseUtc(current.observed_time as unknown as string);
  const ageMinutes = observedAt ? Math.floor((now - observedAt.getTime()) / 60_000) : null;
  const observationAge =
    ageMinutes === null || ageMinutes < 0
      ? ''
      : ageMinutes < 1
        ? t('ageJustNow', currentLanguage)
        : ageMinutes < 60
          ? `${ageMinutes} ${t('ageMinutesAgo', currentLanguage)}`
          : `${Math.floor(ageMinutes / 60)} ${t('ageHoursAgo', currentLanguage)}`;

  // No `transition-all` on the card below. It carries backdrop-filter: blur(30px), and
  // a transition on *all* properties re-animates that filter whenever anything inside
  // changes size — the observation-age label reflowing once a minute was enough — which
  // reads as the whole pane flashing. .glass-strong already transitions just
  // background-color, border-color and box-shadow.
  return (
    <div className="w-full glass-strong rounded-3xl p-6 md:p-8 shadow-[0_8px_32px_rgba(0,0,0,0.12)] space-y-6 relative overflow-hidden">
      {/* Top Banner: Location & Cache Status */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-sky-400">
              {t('liveObservation', currentLanguage)}
            </span>
            <span
              title={stale ? t('staleTooltip', currentLanguage) : t('liveTooltip', currentLanguage)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                stale
                  ? 'bg-rose-950/80 text-rose-300 border border-rose-800'
                  : 'bg-emerald-950/80 text-emerald-400 border border-emerald-800'
              }`}
            >
              {stale ? t('dataStale', currentLanguage) : t('dataLive', currentLanguage)}
              {observationAge ? ` · ${observationAge}` : ''}
            </span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight mt-1">
            {location.name}
            {location.admin1 ? <span className="text-white/70 text-xl font-medium">, {location.admin1}</span> : null}
          </h2>
          <p className="text-xs text-white/70">
            {location.country || 'Global Location'} • {location.latitude.toFixed(2)}°N, {location.longitude.toFixed(2)}°E
            {elevation_m !== null && elevation_m !== undefined ? ` • ${elevation_m}m elev.` : ''}
          </p>
        </div>

        <div className="text-right text-[11px] font-mono text-white/70">
          <div>{t('timezoneLabel', currentLanguage)}: {timezone}</div>
          <div className="text-[10px] text-white/60">
            {t('observedLabel', currentLanguage)}: {new Date(current.observed_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>
      </div>

      {/* Hero Temperature & Condition.
          Centred vertical stack with an ultralight numeral, after the Apple Weather
          hierarchy: the temperature is the single focal element and the glyph supports
          it rather than competing at equal size. */}
      <div className="flex flex-col gap-6 py-2">
        <div className="flex flex-col items-center text-center w-full">
          <WeatherIcon
            iconKey={current.icon_key}
            isDay={current.is_day !== 0}
            size={56}
            className="text-ink/90 drop-shadow-sm"
          />
          <div className="mt-2 flex items-start justify-center">
            <span className="text-7xl sm:text-8xl font-extralight tracking-tighter leading-none text-ink tabular-nums">
              {current.temperature_c !== null ? Math.round(current.temperature_c) : '--'}
            </span>
            <span className="text-3xl sm:text-4xl font-extralight text-ink/70 leading-none mt-1">°</span>
          </div>
          <div className="mt-2 text-lg font-medium text-ink/90">
            {current.weather_condition}
          </div>
          <div className="text-sm text-ink/60">
            {t('feelsLike', currentLanguage)}{' '}
            {current.apparent_temperature_c !== null && current.apparent_temperature_c !== undefined
              ? `${Math.round(current.apparent_temperature_c)}°`
              : t('unavailable', currentLanguage)}
          </div>
        </div>

        {/* Highlight Stats Pill */}
        <div className="glass-inset rounded-3xl p-5 w-full grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div>
            <div className="text-white/60 font-medium">{t('humidity', currentLanguage)}</div>
            <div className="text-sm font-bold text-white mt-0.5">
              {current.humidity_percent !== null && current.humidity_percent !== undefined
                ? `${current.humidity_percent}%`
                : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-white/60 font-medium">{t('windSpeed', currentLanguage)}</div>
            <div className="text-sm font-bold text-white mt-0.5">
              {current.wind_speed_kmh !== null && current.wind_speed_kmh !== undefined
                ? `${current.wind_speed_kmh} km/h`
                : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-white/60 font-medium">{t('precipitation', currentLanguage)}</div>
            <div className="text-sm font-bold text-white mt-0.5">
              {current.precipitation_mm !== null && current.precipitation_mm !== undefined
                ? `${current.precipitation_mm} mm`
                : '0.0 mm'}
            </div>
          </div>
          <div>
            <div className="text-white/60 font-medium">{t('uvIndex', currentLanguage)}</div>
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
