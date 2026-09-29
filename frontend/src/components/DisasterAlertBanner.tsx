'use client';

import React, { useState } from 'react';
import { DisasterAlert, LocationResult, AlertSeverity } from '../types';
import { t } from '../lib/translations';
import { Siren, AlertTriangle } from 'lucide-react';

interface DisasterAlertBannerProps {
  alerts: DisasterAlert[] | null;
  isLoading: boolean;
  error: string | null;
  location: LocationResult | null;
  onRetry?: () => void;
  currentLanguage?: string;
}

export default function DisasterAlertBanner({
  alerts,
  isLoading,
  error,
  location,
  onRetry,
  currentLanguage = 'en',
}: DisasterAlertBannerProps) {
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="w-full glass rounded-3xl p-5 animate-pulse space-y-3">
        <div className="h-4 bg-white/20 rounded w-1/3"></div>
        <div className="h-10 bg-white/20 rounded-xl w-full"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div data-surface="dark" className="w-full bg-black/40 backdrop-blur-2xl border border-white/20 rounded-3xl p-5 text-xs text-amber-200 flex items-center justify-between shadow-lg">
        <div className="flex items-center space-x-3">
          <AlertTriangle size={20} strokeWidth={2} aria-hidden="true" />
          <div>
            <div className="font-bold text-amber-300">{t('disasterFeedNotice', currentLanguage)}</div>
            <div>{t('disasterFeedError', currentLanguage)} ({error})</div>
          </div>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-3 py-1.5 rounded-lg bg-amber-900/80 hover:bg-amber-800 text-amber-100 font-medium transition-colors"
          >
            {t('retry', currentLanguage)}
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
    <div className="w-full glass rounded-3xl p-5 md:p-6 shadow-lg space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-amber-500 to-rose-600 flex items-center justify-center text-sm shadow-md shadow-amber-500/20 text-white">
            <Siren size={16} strokeWidth={2} aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                {t('disasterWatchTitle', currentLanguage)}
              </h3>
              <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-white/10 text-white/80 border border-white/20">
                {t('sachetNdmaFeeds', currentLanguage)}
              </span>
            </div>
            <p className="text-xs text-white/70">
              {t('sachetNdmaSubtitle', currentLanguage)}
            </p>
          </div>
        </div>

        {hasActiveAlerts && (
          <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-rose-950 text-rose-300 border border-rose-800 animate-pulse">
            {activeAlerts.length} {activeAlerts.length === 1 ? t('activeWarning', currentLanguage) : t('activeWarnings', currentLanguage)}
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
                className="p-4 rounded-2xl bg-white/5 backdrop-blur-md border border-rose-500/40 shadow-lg space-y-2.5 transition-colors"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getSeverityBadge(alert.severity)}`}>
                        {alert.severity} {t('severityLabel', currentLanguage)}
                      </span>
                      <span className="text-xs font-bold text-white">
                        {alert.event_type}
                      </span>
                      <span className="text-[10px] font-mono text-white/50">
                        [{alert.scope} {t('levelLabel', currentLanguage)}]
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
                    {isExpanded ? t('hideDetails', currentLanguage) : t('viewInstructions', currentLanguage)}
                  </button>
                </div>

                <p className="text-xs text-white/80 leading-relaxed">
                  {alert.headline || alert.description}
                </p>

                {/* Expanded Bulletin Details */}
                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-white/20 space-y-2 text-xs">
                    {alert.instruction && (
                      <div className="p-3 bg-black/20 border border-white/10 rounded-xl text-amber-200">
                        <strong className="text-amber-400">{t('safetyInstructionLabel', currentLanguage)}</strong>
                        <p className="mt-1 leading-relaxed">{alert.instruction}</p>
                      </div>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-white/70 font-mono bg-black/20 p-2.5 rounded-xl border border-white/10">
                      <div>
                        <span className="text-white/50">{t('affectedArea', currentLanguage)}</span> {alert.affected_area}
                      </div>
                      <div>
                        <span className="text-white/50">{t('urgency', currentLanguage)}</span> {alert.urgency} ({alert.certainty})
                      </div>
                      {alert.effective_time && (
                        <div>
                          <span className="text-white/50">{t('effective', currentLanguage)}</span> {new Date(alert.effective_time).toLocaleString()}
                        </div>
                      )}
                      {alert.expires_time && (
                        <div>
                          <span className="text-white/50">{t('expires', currentLanguage)}</span> {new Date(alert.expires_time).toLocaleString()}
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
                          {t('viewOfficialBulletin', currentLanguage)}
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
        <div className="p-4 rounded-2xl glass-inset flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2 text-white/80">
            <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
            <span>
              {t('noActiveAlertsForLocation', currentLanguage)}{' '}
              <strong className="text-white">{location?.name || ''}</strong>.
            </span>
          </div>
          <span className="text-[10px] text-white/50 font-mono hidden sm:inline-block">
            {t('feedSyncedSachet', currentLanguage)}
          </span>
        </div>
      )}
    </div>
  );
}
