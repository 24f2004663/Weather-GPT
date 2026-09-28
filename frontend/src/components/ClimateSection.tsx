'use client';

import React, { useState } from 'react';
import { NasaPowerClimateResponse } from '../types';
import { t } from '../lib/translations';

interface ClimateSectionProps {
  climate: NasaPowerClimateResponse | null;
  isLoading: boolean;
  currentLanguage?: string;
}

export default function ClimateSection({
  climate,
  isLoading,
  currentLanguage = 'en',
}: ClimateSectionProps) {
  const [expanded, setExpanded] = useState(false);

  if (isLoading) {
    return (
      <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 animate-pulse space-y-4">
        <div className="h-5 bg-slate-800 rounded w-1/4"></div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="h-16 bg-slate-800 rounded-xl"></div>
          <div className="h-16 bg-slate-800 rounded-xl"></div>
          <div className="h-16 bg-slate-800 rounded-xl"></div>
          <div className="h-16 bg-slate-800 rounded-xl"></div>
        </div>
      </div>
    );
  }

  if (!climate) {
    return null;
  }

  const { annual_averages, monthly_data, location, cached } = climate;

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
              {t('climatologicalContext', currentLanguage)}
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-950 text-indigo-300 border border-indigo-800">
              {t('nasaBaseline', currentLanguage)}
            </span>
          </div>
          <h3 className="text-xl font-bold text-white mt-1">
            {t('historicalClimateProfileFor', currentLanguage)} {location.name}
          </h3>
          <p className="text-xs text-slate-400">
            {t('longTermAverages', currentLanguage)}
          </p>
        </div>

        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-xs font-medium text-sky-400 hover:text-sky-300 transition-colors flex items-center gap-1"
        >
          {expanded ? t('collapseMonthly', currentLanguage) : t('viewMonthly', currentLanguage)}
        </button>
      </div>

      {/* Annual Summary Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 text-xs">
        <div className="bg-slate-950/70 border border-slate-800 p-3.5 rounded-2xl">
          <div className="text-slate-400 font-medium">{t('avgTemperature', currentLanguage)}</div>
          <div className="text-base font-bold text-white mt-1">
            {annual_averages['T2M'] !== undefined ? `${annual_averages['T2M'].toFixed(1)}°C` : 'N/A'}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{t('annualMean', currentLanguage)}</div>
        </div>

        <div className="bg-slate-950/70 border border-slate-800 p-3.5 rounded-2xl">
          <div className="text-slate-400 font-medium">{t('avgPrecipitation', currentLanguage)}</div>
          <div className="text-base font-bold text-white mt-1">
            {annual_averages['PRECTOTCORR'] !== undefined ? `${annual_averages['PRECTOTCORR'].toFixed(1)} mm/day` : 'N/A'}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{t('precipitationRate', currentLanguage)}</div>
        </div>

        <div className="bg-slate-950/70 border border-slate-800 p-3.5 rounded-2xl">
          <div className="text-slate-400 font-medium">{t('solarRadiation', currentLanguage)}</div>
          <div className="text-base font-bold text-white mt-1">
            {annual_averages['ALLSKY_SFC_SW_DWN'] !== undefined ? `${annual_averages['ALLSKY_SFC_SW_DWN'].toFixed(1)} kWh/m²` : 'N/A'}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{t('surfaceIrradiance', currentLanguage)}</div>
        </div>

        <div className="bg-slate-950/70 border border-slate-800 p-3.5 rounded-2xl">
          <div className="text-slate-400 font-medium">{t('relativeHumidity', currentLanguage)}</div>
          <div className="text-base font-bold text-white mt-1">
            {annual_averages['RH2M'] !== undefined ? `${annual_averages['RH2M'].toFixed(0)}%` : 'N/A'}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{t('meanHumidity2m', currentLanguage)}</div>
        </div>

        <div className="bg-slate-950/70 border border-slate-800 p-3.5 rounded-2xl">
          <div className="text-slate-400 font-medium">{t('avgWindSpeed', currentLanguage)}</div>
          <div className="text-base font-bold text-white mt-1">
            {annual_averages['WS10M'] !== undefined ? `${annual_averages['WS10M'].toFixed(1)} m/s` : 'N/A'}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{t('windSpeed10m', currentLanguage)}</div>
        </div>
      </div>

      {/* Expandable Monthly Breakdown Table */}
      {expanded && monthly_data && monthly_data.length > 0 && (
        <div className="space-y-3 pt-2 border-t border-slate-800">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {t('monthlyClimateProfile', currentLanguage)}
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left text-slate-300">
              <thead className="text-[11px] text-slate-400 uppercase bg-slate-950/80 border-b border-slate-800 font-mono">
                <tr>
                  <th className="px-3 py-2">{t('monthHeader', currentLanguage)}</th>
                  <th className="px-3 py-2">{t('avgTempHeader', currentLanguage)}</th>
                  <th className="px-3 py-2">{t('precipHeader', currentLanguage)}</th>
                  <th className="px-3 py-2">{t('solarHeader', currentLanguage)}</th>
                  <th className="px-3 py-2">{t('humidityHeader', currentLanguage)}</th>
                  <th className="px-3 py-2">{t('windHeader', currentLanguage)}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {monthly_data.map((m) => (
                  <tr key={m.month} className="hover:bg-slate-800/40">
                    <td className="px-3 py-2 font-sans font-medium text-white">{m.month}</td>
                    <td className="px-3 py-2">{m.temperature_2m_c !== null && m.temperature_2m_c !== undefined ? m.temperature_2m_c.toFixed(1) : '-'}</td>
                    <td className="px-3 py-2">{m.precipitation_mm_day !== null && m.precipitation_mm_day !== undefined ? m.precipitation_mm_day.toFixed(1) : '-'}</td>
                    <td className="px-3 py-2">{m.solar_radiation_kwh_m2_day !== null && m.solar_radiation_kwh_m2_day !== undefined ? m.solar_radiation_kwh_m2_day.toFixed(1) : '-'}</td>
                    <td className="px-3 py-2">{m.relative_humidity_percent !== null && m.relative_humidity_percent !== undefined ? m.relative_humidity_percent.toFixed(0) : '-'}</td>
                    <td className="px-3 py-2">{m.wind_speed_10m_ms !== null && m.wind_speed_10m_ms !== undefined ? m.wind_speed_10m_ms.toFixed(1) : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
