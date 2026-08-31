'use client';

import React, { useState } from 'react';
import { DisasterAlert, LocationResult, AlertSeverity } from '../types';

interface DisasterAlertBannerProps {
  alerts: DisasterAlert[] | null;
  isLoading: boolean;
  error: string | null;
  location: LocationResult | null;
  onRetry?: () => void;
}

export default function DisasterAlertBanner({
  alerts,
  isLoading,
  error,
  location,
  onRetry,
}: DisasterAlertBannerProps) {
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-5 animate-pulse space-y-3">
        <div className="h-4 bg-slate-800 rounded w-1/3"></div>
        <div className="h-10 bg-slate-800 rounded-xl w-full"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full bg-amber-950/40 border border-amber-800/80 rounded-3xl p-5 text-xs text-amber-200 flex items-center justify-between shadow-lg">
        <div className="flex items-center space-x-3">
          <span className="text-xl">⚠️</span>
          <div>
            <div className="font-bold text-amber-300">Official Disaster Feed Notice</div>
            <div>Unable to refresh real-time SACHET / NDMA alert feed. ({error})</div>
          </div>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-3 py-1.5 rounded-lg bg-amber-900/80 hover:bg-amber-800 text-amber-100 font-medium transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  const activeAlerts = alerts?.filter((a) => a.is_active) || [];
  const hasActiveAlerts = activeAlerts.length > 0;

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

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-5 md:p-6 shadow-xl space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-amber-500 to-rose-600 flex items-center justify-center text-sm shadow-md shadow-amber-500/20 text-white">
            🚨
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Official Disaster & Emergency Watch
              </h3>
              <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-950 text-slate-300 border border-slate-800">
                SACHET / NDMA Feeds
              </span>
            </div>
            <p className="text-xs text-slate-400">
              National Disaster Management Authority authoritative CAP emergency bulletins
            </p>
          </div>
        </div>

        {hasActiveAlerts && (
          <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-rose-950 text-rose-300 border border-rose-800 animate-pulse">
            {activeAlerts.length} Active {activeAlerts.length === 1 ? 'Warning' : 'Warnings'}
          </span>
        )}
      </div>

      {/* Active Alerts List */}
      {hasActiveAlerts ? (
        <div className="space-y-3 pt-1">
          {activeAlerts.map((alert) => {
            const isExpanded = expandedAlertId === alert.alert_id;
            return (
              <div
                key={alert.alert_id}
                className="p-4 rounded-2xl bg-slate-950/80 border border-rose-900/60 shadow-lg space-y-2.5 transition-all"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getSeverityBadge(alert.severity)}`}>
                        {alert.severity} Severity
                      </span>
                      <span className="text-xs font-bold text-white">
                        {alert.event_type}
                      </span>
                      <span className="text-[10px] font-mono text-slate-500">
                        [{alert.scope} Level]
                      </span>
                    </div>
                    <h4 className="text-sm font-bold text-rose-200 mt-1">
                      {alert.title}
                    </h4>
                  </div>

                  <button
                    type="button"
                    onClick={() => setExpandedAlertId(isExpanded ? null : alert.alert_id)}
                    className="text-xs font-medium text-sky-400 hover:text-sky-300 transition-colors"
                  >
                    {isExpanded ? '▲ Hide Details' : '▼ View Safety Instructions'}
                  </button>
                </div>

                <p className="text-xs text-slate-300 leading-relaxed">
                  {alert.headline || alert.description}
                </p>

                {/* Expanded Bulletin Details */}
                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-2 text-xs">
                    {alert.instruction && (
                      <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded-xl text-amber-200">
                        <strong className="text-amber-400">Official Safety Instruction:</strong>
                        <p className="mt-1 leading-relaxed">{alert.instruction}</p>
                      </div>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-slate-400 font-mono bg-slate-900/60 p-2.5 rounded-xl border border-slate-800">
                      <div>
                        <span className="text-slate-500">Affected Area:</span> {alert.affected_area}
                      </div>
                      <div>
                        <span className="text-slate-500">Urgency:</span> {alert.urgency} ({alert.certainty})
                      </div>
                      {alert.effective_time && (
                        <div>
                          <span className="text-slate-500">Effective:</span> {new Date(alert.effective_time).toLocaleString()}
                        </div>
                      )}
                      {alert.expires_time && (
                        <div>
                          <span className="text-slate-500">Expires:</span> {new Date(alert.expires_time).toLocaleString()}
                        </div>
                      )}
                    </div>

                    {alert.source_url && (
                      <div className="text-right">
                        <a
                          href={alert.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] text-sky-400 hover:underline"
                        >
                          View Official Bulletin Source →
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty / All Clear State */
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2 text-slate-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
            <span>
              No active disaster warnings or severe weather advisories for{' '}
              <strong className="text-white">{location?.name || 'this location'}</strong>.
            </span>
          </div>
          <span className="text-[10px] text-slate-500 font-mono hidden sm:inline-block">
            Feed Synced with SACHET / NDMA
          </span>
        </div>
      )}
    </div>
  );
}
