'use client';

import React from 'react';
import { NormalizedWeatherResponse, LocationResult } from '../types';
import { t } from '../lib/translations';

interface PersonalizedInsightsProps {
  weather: NormalizedWeatherResponse | null;
  location: LocationResult | null;
  currentLanguage?: string;
}

export default function PersonalizedInsights({ weather, location, currentLanguage = 'en' }: PersonalizedInsightsProps) {
  if (!weather || !weather.current) {
    return null;
  }

  const { current, hourly, daily } = weather;

  // 1. Umbrella Recommendation
  const todayDaily = daily && daily.length > 0 ? daily[0] : null;
  const rainProb = todayDaily?.precipitation_probability_max ?? 0;
  const rainSum = todayDaily?.precipitation_sum_mm ?? 0;
  const currentRain = current.precipitation_mm ?? 0;

  const needsUmbrella = rainProb >= 35 || rainSum >= 1.0 || currentRain > 0.1;

  // 2. UV Index Advice
  const maxUV = todayDaily?.uv_index_max ?? current.uv_index ?? 0;
  const highUV = maxUV >= 6;

  // 3. Thermal Comfort / Heat Caution
  const feelsLike = current.apparent_temperature_c ?? current.temperature_c;
  const isExtremeHeat = feelsLike >= 38;
  const isCold = feelsLike <= 15;

  // 4. Best Outdoor Window Search (next 12 hours)
  let bestWindow = 'Morning / Late Afternoon';
  if (hourly && hourly.length >= 12) {
    const candidateSlots = [];
    for (let i = 0; i < 12; i++) {
      const slot = hourly[i];
      const p = slot.precipitation_probability ?? 0;
      const t = slot.temperature_c;
      // Score: lower precipitation and moderate temperature (20-28°C) is best
      const tempDiff = Math.abs(t - 24);
      const score = p * 2 + tempDiff;
      candidateSlots.push({ slot, score });
    }
    candidateSlots.sort((a, b) => a.score - b.score);
    if (candidateSlots.length > 0) {
      try {
        const bestDate = new Date(candidateSlots[0].slot.time);
        bestWindow = bestDate.toLocaleTimeString([], { hour: 'numeric', hour12: true });
      } catch {
        bestWindow = 'Next 3-4 Hours';
      }
    }
  }

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-sm shadow-md text-white">
            💡
          </div>
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {t('personalizedInsights', currentLanguage)}
            </h3>
            <p className="text-xs text-slate-400">
              {t('actionableRecommendations', currentLanguage)}
            </p>
          </div>
        </div>
        <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-950 text-sky-400 border border-sky-900/60">
          AI Advisory
        </span>
      </div>

      {/* Grid of Decision Insights */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs pt-1">
        {/* Card 1: Umbrella */}
        <div className={`p-4 rounded-2xl border flex flex-col justify-between space-y-1.5 ${
          needsUmbrella
            ? 'bg-sky-950/40 border-sky-800 text-sky-200'
            : 'bg-slate-950/60 border-slate-800/80 text-slate-300'
        }`}>
          <div className="flex justify-between items-center font-bold">
            <span>☔ {needsUmbrella ? t('carryUmbrella', currentLanguage) : t('noUmbrella', currentLanguage)}</span>
            <span className="text-base">{needsUmbrella ? '🌧️' : '☀️'}</span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            {needsUmbrella
              ? `${t('umbrellaReason', currentLanguage)} (Rain chance: ${rainProb}%)`
              : t('noUmbrellaReason', currentLanguage)}
          </p>
        </div>

        {/* Card 2: Thermal Comfort */}
        <div className={`p-4 rounded-2xl border flex flex-col justify-between space-y-1.5 ${
          isExtremeHeat
            ? 'bg-amber-950/40 border-amber-800 text-amber-200'
            : isCold
            ? 'bg-cyan-950/40 border-cyan-800 text-cyan-200'
            : 'bg-slate-950/60 border-slate-800/80 text-slate-300'
        }`}>
          <div className="flex justify-between items-center font-bold">
            <span>🌡️ {isExtremeHeat ? t('extremeHeat', currentLanguage) : isCold ? t('coldAdvisory', currentLanguage) : t('mildComfort', currentLanguage)}</span>
            <span className="text-base">{isExtremeHeat ? '🔥' : isCold ? '❄️' : '✨'}</span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            {isExtremeHeat
              ? `${t('extremeHeatReason', currentLanguage)} (${feelsLike.toFixed(0)}°C)`
              : isCold
              ? `${t('coldAdvisoryReason', currentLanguage)} (${feelsLike.toFixed(0)}°C)`
              : `${t('mildComfortReason', currentLanguage)} (${feelsLike.toFixed(0)}°C)`}
          </p>
        </div>

        {/* Card 3: UV & Sun Exposure */}
        <div className={`p-4 rounded-2xl border flex flex-col justify-between space-y-1.5 ${
          highUV
            ? 'bg-purple-950/40 border-purple-800 text-purple-200'
            : 'bg-slate-950/60 border-slate-800/80 text-slate-300'
        }`}>
          <div className="flex justify-between items-center font-bold">
            <span>🧴 {highUV ? t('highUVAdvisory', currentLanguage) : t('normalUV', currentLanguage)}</span>
            <span className="text-base">{highUV ? '☀️' : '⛅'}</span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            {highUV
              ? `${t('highUVReason', currentLanguage)} (UV: ${maxUV.toFixed(1)})`
              : `${t('normalUVReason', currentLanguage)} (UV: ${maxUV.toFixed(1)})`}
          </p>
        </div>

        {/* Card 4: Best Outdoor Window */}
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80 text-slate-300 flex flex-col justify-between space-y-1.5">
          <div className="flex justify-between items-center font-bold text-white">
            <span>🏃 {t('safeOutdoorWindow', currentLanguage)}</span>
            <span className="text-base">🕒</span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            {t('optimalWindow', currentLanguage)}: <strong className="text-sky-300">{bestWindow}</strong>.
          </p>
        </div>
      </div>

      <div className="text-[10px] text-slate-500 font-mono pt-1">
        * Contextual insights are informational suggestions based on Open-Meteo numerical predictions. Official SACHET/NDMA emergency warnings take legal precedence.
      </div>
    </div>
  );
}
