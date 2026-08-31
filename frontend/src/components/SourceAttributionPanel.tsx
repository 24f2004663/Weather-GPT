'use client';

import React from 'react';

export default function SourceAttributionPanel() {
  return (
    <footer className="w-full pt-8 pb-12 border-t border-slate-800 text-xs text-slate-400 space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">WeatherGPT Platform</div>
          <p className="text-slate-400 leading-relaxed text-[11px]">
            AI weather intelligence and official disaster awareness architecture. Built for resilience and accuracy.
          </p>
        </div>

        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">Real-Time Meteorology</div>
          <p className="text-slate-400 leading-relaxed text-[11px]">
            High-resolution numerical weather forecasts and geocoding powered by{' '}
            <span className="text-sky-400 font-medium">Open-Meteo</span>.
          </p>
        </div>

        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">Historical Climatology</div>
          <p className="text-slate-400 leading-relaxed text-[11px]">
            30-year agroclimatology baseline averages supplied by{' '}
            <span className="text-indigo-400 font-medium">NASA POWER</span>.
          </p>
        </div>

        <div>
          <div className="font-bold text-white uppercase tracking-wider mb-2">Safety & Alerts</div>
          <p className="text-slate-400 leading-relaxed text-[11px]">
            Prepared for official CAP alert feeds via{' '}
            <span className="text-amber-400 font-medium">SACHET / NDMA</span>.
          </p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row justify-between items-center pt-6 border-t border-slate-800/60 gap-3 text-[11px] text-slate-500 font-mono">
        <div>© 2026 WeatherGPT. All meteorological data strictly attributed to verified sources.</div>
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
