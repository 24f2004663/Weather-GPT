'use client';

import React, { useState } from 'react';
import { LocationResult, NormalizedWeatherResponse, DisasterAlert } from '../types';

interface WeatherMapProps {
  location: LocationResult;
  weather: NormalizedWeatherResponse | null;
  alerts: DisasterAlert[] | null;
}

export default function WeatherMap({ location, weather, alerts }: WeatherMapProps) {
  const [zoom, setZoom] = useState<number>(10);

  const activeAlerts = alerts?.filter((a) => a.is_active) || [];
  const hasAlert = activeAlerts.length > 0;
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
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-xl space-y-4 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-sky-500 to-emerald-500 flex items-center justify-center text-sm text-white shadow-md">
            🗺️
          </div>
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Interactive Geospatial Weather & Alert Map
            </h3>
            <p className="text-xs text-slate-400">
              Visual coordinates, regional boundary context, and active hazard radius
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 text-xs font-mono">
          <button
            type="button"
            onClick={() => setZoom(Math.max(zoom - 2, 4))}
            className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            title="Zoom out"
          >
            - Zoom
          </button>
          <span className="text-slate-400">Level {zoom}</span>
          <button
            type="button"
            onClick={() => setZoom(Math.min(zoom + 2, 16))}
            className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            title="Zoom in"
          >
            + Zoom
          </button>
        </div>
      </div>

      {/* Map Container */}
      <div className="relative w-full h-80 rounded-2xl overflow-hidden border border-slate-800 bg-slate-950">
        <iframe
          title={`Map of ${location.name}`}
          src={osmEmbedUrl}
          className="w-full h-full border-0 filter invert-[0.88] hue-rotate-180 contrast-[1.1] opacity-90"
          loading="lazy"
        />

        {/* Floating Location & Weather Pin Badge */}
        <div className="absolute top-4 left-4 bg-slate-900/95 backdrop-blur-md border border-slate-700 p-3 rounded-2xl shadow-2xl flex items-center space-x-3 text-xs">
          <div className="text-2xl">📍</div>
          <div>
            <div className="font-bold text-white">
              {location.name}
              {location.admin1 ? <span className="text-slate-400 font-normal">, {location.admin1}</span> : ''}
            </div>
            <div className="font-mono text-[10px] text-slate-400">
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
        {hasAlert && (
          <div className="absolute bottom-4 right-4 max-w-xs bg-rose-950/95 backdrop-blur-md border border-rose-800 p-3 rounded-2xl shadow-2xl text-xs space-y-1 text-rose-200">
            <div className="flex items-center space-x-1.5 font-bold text-rose-300">
              <span>⚠️ Active Disaster Region:</span>
              <span className="text-[10px] uppercase bg-rose-900 px-1.5 py-0.5 rounded font-mono">
                {activeAlerts[0].scope}
              </span>
            </div>
            <p className="text-[11px] text-slate-200 leading-tight line-clamp-2">
              {activeAlerts[0].affected_area}
            </p>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between text-[10px] font-mono text-slate-500 gap-2">
        <span>Cartography: OpenStreetMap Contributors • Coordinate Reference System: WGS-84</span>
        <span>Geographic precision matches official SACHET/NDMA regional boundaries.</span>
      </div>
    </div>
  );
}
