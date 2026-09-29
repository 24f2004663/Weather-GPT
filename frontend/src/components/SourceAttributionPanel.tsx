'use client';

import React from 'react';
import { t } from '../lib/translations';

interface SourceAttributionPanelProps {
  currentLanguage?: string;
}

export default function SourceAttributionPanel({ currentLanguage = 'en' }: SourceAttributionPanelProps) {
  return (
    <footer className="w-full pt-8 pb-12 border-t border-white/20 text-xs text-white/70 space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">{t('platformTitle', currentLanguage)}</div>
          <p className="text-white/70 leading-relaxed text-[11px]">
            {t('platformDesc', currentLanguage)}
          </p>
        </div>

        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">{t('realTimeMeteorology', currentLanguage)}</div>
          <p className="text-white/70 leading-relaxed text-[11px]">
            {t('realTimeMeteorologyDesc', currentLanguage)}{' '}
            <span className="text-sky-400 font-medium">Open-Meteo</span>.
          </p>
        </div>

        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">{t('historicalClimatology', currentLanguage)}</div>
          <p className="text-white/70 leading-relaxed text-[11px]">
            {t('historicalClimatologyDesc', currentLanguage)}{' '}
            <span className="text-indigo-400 font-medium">NASA POWER</span>.
          </p>
        </div>

        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">{t('safetyAlerts', currentLanguage)}</div>
          <p className="text-white/70 leading-relaxed text-[11px]">
            {t('safetyAlertsDesc', currentLanguage)}{' '}
            <span className="text-amber-400 font-medium">SACHET / NDMA</span>.
          </p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row justify-between items-center pt-6 border-t border-white/10 gap-3 text-[11px] text-white/50 font-mono">
        <div>{t('copyrightNotice', currentLanguage)}</div>
        <div className="flex items-center space-x-4">
          <span>FastAPI</span>
          <span>Next.js 14</span>
          <span>Open-Meteo</span>
          <span>NASA POWER</span>
          <span>Gemini AI</span>
        </div>
      </div>
    </footer>
  );
}
