'use client';

import React, { useState } from 'react';
import { LocationResult, NormalizedWeatherResponse, DisasterAlert } from '../types';
import { t } from '../lib/translations';
import { Map, MapPin } from 'lucide-react';

interface WeatherMapProps {
  location: LocationResult;
  weather: NormalizedWeatherResponse | null;
  alerts: DisasterAlert[] | null;
  gdacsAlerts?: DisasterAlert[] | null;
  currentLanguage?: string;
}

export default function WeatherMap({
  location,
  weather,
  alerts,
  gdacsAlerts,
  currentLanguage = 'en',
}: WeatherMapProps) {
  const [zoom, setZoom] = useState<number>(10);

  const activeAlerts = alerts?.filter((a) => a.is_active) || [];
  const activeGdacs = gdacsAlerts?.filter((a) => a.is_active) || [];
  const primaryAlert = activeAlerts[0] || activeGdacs[0];
  const currentTemp = weather?.current?.temperature_c;

  // Simple static/interactive map view using public OpenStreetMap tiles or canvas representation
  // OpenStreetMap static tile format: https://tile.openstreetmap.org/{z}/{x}/{y}.png
  // Or responsive iframe/interactive OpenStreetMap view
  const lat = location.latitude;
  const lon = location.longitude;
  
  // Calculate bounding box for OpenStreetMap embed
  const delta = 0.08 * (12 / zoom);
  const bbox = `${lon - delta},${lat - delta},${lon + delta},${lat + delta}`;
  const osmEmbedUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat},${lon}`;

  return (
    <div className="w-full glass rounded-3xl p-6 md:p-8 shadow-lg space-y-4 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-sky-500 to-emerald-500 flex items-center justify-center text-sm text-white shadow-md">
            <Map size={16} strokeWidth={2} aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {t('interactiveMapTitle', currentLanguage)}
            </h3>
            <p className="text-xs text-white/70">
              {t('interactiveMapSubtitle', currentLanguage)}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 text-xs font-mono">
          <button
            type="button"
            onClick={() => setZoom(Math.max(zoom - 2, 4))}
            className="px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-white/80 border border-white/20 transition-colors backdrop-blur-md"
            title={t('zoomOut', currentLanguage)}
          >
            {t('zoomOut', currentLanguage)}
          </button>
          <span className="text-white/70">{t('zoomLevel', currentLanguage)} {zoom}</span>
          <button
            type="button"
            onClick={() => setZoom(Math.min(zoom + 2, 16))}
            className="px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-white/80 border border-white/20 transition-colors backdrop-blur-md"
            title={t('zoomIn', currentLanguage)}
          >
            {t('zoomIn', currentLanguage)}
          </button>
        </div>
      </div>

      {/* Map Container */}
      <div className="relative w-full h-80 rounded-2xl overflow-hidden border border-white/20 bg-black/20">
        <iframe
          title={`Map of ${location.name}`}
          src={osmEmbedUrl}
          className="w-full h-full border-0 filter invert-[0.88] hue-rotate-180 contrast-[1.1] opacity-90"
          loading="lazy"
        />

        {/* Floating Location & Weather Pin Badge */}
        <div data-surface="dark" className="absolute top-4 left-4 bg-black/40 backdrop-blur-2xl border border-white/20 p-3 rounded-2xl shadow-2xl flex items-center space-x-3 text-xs">
          <MapPin size={20} strokeWidth={2} className="text-rose-400" aria-hidden="true" />
          <div>
            <div className="font-bold text-white">
              {location.name}
              {location.admin1 ? <span className="text-white/70 font-normal">, {location.admin1}</span> : ''}
            </div>
            <div className="font-mono text-[10px] text-white/70">
              {lat.toFixed(4)}°N, {lon.toFixed(4)}°E
            </div>
          </div>
          {currentTemp !== undefined && currentTemp !== null && (
            <div className="px-2.5 py-1 rounded-xl bg-sky-950 text-sky-400 font-bold border border-sky-800 text-sm">
              {currentTemp.toFixed(0)}°C
            </div>
          )}
        </div>

        {/* Floating Active Disaster Zone Indicator if alert present */}
        {primaryAlert && (
          <div className="absolute bottom-4 right-4 max-w-xs bg-rose-950/95 backdrop-blur-md border border-rose-800 p-3 rounded-2xl shadow-2xl text-xs space-y-1 text-rose-200">
            <div className="flex items-center space-x-1.5 font-bold text-rose-300">
              <span>{t('activeDisasterRegion', currentLanguage)}</span>
              <span className="text-[10px] uppercase bg-rose-900 px-1.5 py-0.5 rounded font-mono">
                {primaryAlert.scope}
              </span>
            </div>
            <p className="text-[11px] text-white/90 leading-tight line-clamp-2">
              {primaryAlert.affected_area}
            </p>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between text-[10px] font-mono text-white/50 gap-2">
        <span>{t('mapCartographyAttribution', currentLanguage)}</span>
        <span>{t('mapPrecisionAttribution', currentLanguage)}</span>
      </div>
    </div>
  );
}
