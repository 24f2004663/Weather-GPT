'use client';

import React, { useEffect, useState } from 'react';
import { DisasterAlert, AlertSeverity } from '../types';
import { fetchGdacsTop7 } from '../lib/api';

interface GdacsAlertsPanelProps {
  onAlertsLoaded?: (alerts: DisasterAlert[]) => void;
}

export default function GdacsAlertsPanel({ onAlertsLoaded }: GdacsAlertsPanelProps) {
  const [alerts, setAlerts] = useState<DisasterAlert[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadGdacs = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetchGdacsTop7();
      const loadedAlerts = res.alerts || [];
      setAlerts(loadedAlerts);
      if (onAlertsLoaded) {
        onAlertsLoaded(loadedAlerts);
      }
    } catch (err: any) {
      console.error('GDACS top 7 error:', err);
      setError(err.message || 'Failed to load GDACS live alerts');
      setAlerts([]);
    } finally {
      setIsLoading(false);
    }
  }, [onAlertsLoaded]);

  useEffect(() => {
    loadGdacs();
  }, [loadGdacs]);

  const getSeverityBadge = (sev: AlertSeverity) => {
    switch (sev) {
      case 'Extreme':
        return 'bg-rose-950 text-rose-300 border-rose-800';
      case 'Severe':
        return 'bg-amber-950 text-amber-300 border-amber-800';
      case 'Moderate':
        return 'bg-yellow-950 text-yellow-300 border-yellow-800';
      case 'Minor':
        return 'bg-sky-950 text-sky-300 border-sky-800';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  const getEventEmoji = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes('cyclone') || t.includes('typhoon') || t.includes('hurricane')) return '🌀';
    if (t.includes('earthquake') || t.includes('tremor')) return '🌋';
    if (t.includes('flood') || t.includes('inundation')) return '🌊';
    if (t.includes('drought') || t.includes('heat')) return '☀️';
    if (t.includes('fire') || t.includes('wildfire')) return '🔥';
    if (t.includes('tsunami')) return '🌊';
    if (t.includes('volcano')) return '🌋';
    return '🚨';
  };

  if (isLoading) {
    return (
      <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-5 animate-pulse space-y-3">
        <div className="h-4 bg-slate-800 rounded w-1/3"></div>
        <div className="h-16 bg-slate-800 rounded-xl w-full"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-5 text-xs text-slate-400 flex items-center justify-between">
        <span>🌐 Live GDACS feed temporarily unavailable ({error})</span>
        <button
          type="button"
          onClick={loadGdacs}
          className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-5 md:p-6 shadow-xl space-y-4">
      {/* Panel Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-sm shadow-md text-white">
            🌐
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Top 7 Live Global Disaster Watch
              </h3>
              <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-950 text-slate-300 border border-slate-800">
                GDACS Live Feed
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Global Disaster Alert and Coordination System (UN / EC Framework)
            </p>
          </div>
        </div>

        <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-sky-950 text-sky-300 border border-sky-800">
          {alerts.length} {alerts.length === 1 ? 'Event' : 'Events'} Ranked
        </span>
      </div>

      {/* Alerts Grid / List */}
      {alerts.length > 0 ? (
        <div className="space-y-2.5 pt-1">
          {alerts.map((alert, idx) => (
            <div
              key={alert.alert_id}
              className="p-3.5 rounded-2xl bg-slate-950/80 border border-slate-800 hover:border-slate-700 transition-all flex flex-wrap items-start justify-between gap-3"
            >
              <div className="flex items-start space-x-3 flex-1 min-w-[240px]">
                <div className="text-xl pt-0.5">{getEventEmoji(alert.event_type)}</div>
                <div className="space-y-1">
                  <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                    <span className="text-xs font-mono font-bold text-sky-400">#{idx + 1}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getSeverityBadge(alert.severity)}`}>
                      {alert.severity}
                    </span>
                    <span className="text-xs font-bold text-white">
                      {alert.event_type}
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      📍 {alert.affected_area}
                    </span>
                  </div>

                  <h4 className="text-xs font-semibold text-slate-200 leading-snug">
                    {alert.title}
                  </h4>

                  <div className="flex items-center space-x-3 text-[10px] text-slate-500 font-mono">
                    {alert.issued_time && (
                      <span>Issued: {new Date(alert.issued_time).toLocaleDateString()}</span>
                    )}
                    {alert.polygon_coordinates && alert.polygon_coordinates.length > 0 && (
                      <span>Coords: {alert.polygon_coordinates[0][0].toFixed(2)}°, {alert.polygon_coordinates[0][1].toFixed(2)}°</span>
                    )}
                  </div>
                </div>
              </div>

              {alert.source_url && (
                <a
                  href={alert.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] font-medium text-sky-400 hover:text-sky-300 transition-colors whitespace-nowrap"
                >
                  View Bulletin →
                </a>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400 font-mono text-center">
          No active high-severity GDACS events currently logged in live feed.
        </div>
      )}

      {/* Attribution Footer */}
      <div className="pt-1 text-[10px] text-slate-500 font-mono text-right border-t border-slate-800/60">
        Source: GDACS (UN-OCHA & European Commission)
      </div>
    </div>
  );
}
