'use client';

import React, { useState, useEffect } from 'react';
import { LocationResult } from '../types';
import { API_BASE_URL } from '../lib/api';

interface NotificationSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedLocation: LocationResult | null;
  currentLanguage: string;
  onSubscriptionChange?: (isSubscribed: boolean) => void;
}

export default function NotificationSettingsModal({
  isOpen,
  onClose,
  selectedLocation,
  currentLanguage,
  onSubscriptionChange,
}: NotificationSettingsModalProps) {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [channels, setChannels] = useState<{ whatsapp: boolean; sms: boolean; voice: boolean; web_push: boolean }>({
    whatsapp: true,
    sms: true,
    voice: false,
    web_push: true,
  });
  const [severity, setSeverity] = useState<'Severe' | 'Extreme'>('Severe');
  const [language, setLanguage] = useState<string>(currentLanguage || 'en');
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [providerStatus, setProviderStatus] = useState<Record<string, string>>({});
  const [webPushStatus, setWebPushStatus] = useState<string>('Ready');

  const userId = 'weathergpt_web_user'; // Prototype client identifier

  useEffect(() => {
    if (isOpen) {
      // 1. Fetch current preferences
      fetch(`${API_BASE_URL}/api/notifications/preferences?user_id=${userId}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data && data.is_opted_in) {
            setIsSubscribed(true);
            setPhoneNumber(data.phone_number || '');
            setLanguage(data.preferred_language || 'en');
            setSeverity(data.min_severity_threshold || 'Severe');
            const chs = data.enabled_channels || [];
            setChannels({
              whatsapp: chs.includes('WHATSAPP'),
              sms: chs.includes('SMS'),
              voice: chs.includes('VOICE_IVR'),
              web_push: chs.includes('WEB_PUSH'),
            });
          }
        })
        .catch(() => {});

      // 2. Fetch provider status
      fetch(`${API_BASE_URL}/api/notifications/providers/status`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data?.channels) {
            setProviderStatus(data.channels);
          }
        })
        .catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleRegisterWebPush = async (): Promise<any | null> => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator) || !('PushManager' in window)) {
      setWebPushStatus('Web Push not supported in this browser');
      return null;
    }

    try {
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') {
        setWebPushStatus('Browser notification permission denied');
        return null;
      }

      // Register SW
      const reg = await navigator.serviceWorker.register('/sw.js');
      setWebPushStatus('Service Worker Active');

      // Fetch VAPID key
      const keyRes = await fetch(`${API_BASE_URL}/api/notifications/vapid-public-key`);
      if (keyRes.ok) {
        const keyData = await keyRes.json();
        return {
          endpoint: 'browser_web_push_endpoint',
          keys: { p256dh: 'browser_p256dh_key', auth: 'browser_auth_token' },
          vapid_status: keyData.status,
        };
      }
    } catch (err: any) {
      console.warn('Web push registration notice:', err);
    }
    return null;
  };

  const handleSave = async () => {
    setIsSaving(true);
    setStatusMessage(null);

    let pushSubscriptionData = null;
    if (channels.web_push) {
      pushSubscriptionData = await handleRegisterWebPush();
    }

    const enabledList = [];
    if (channels.whatsapp) enabledList.push('WHATSAPP');
    if (channels.sms) enabledList.push('SMS');
    if (channels.voice) enabledList.push('VOICE_IVR');
    if (channels.web_push) enabledList.push('WEB_PUSH');

    try {
      const res = await fetch(`${API_BASE_URL}/api/notifications/preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_identifier: userId,
          phone_number: phoneNumber.trim() || undefined,
          whatsapp_number: phoneNumber.trim() || undefined,
          preferred_language: language,
          enabled_channels: enabledList,
          min_severity_threshold: severity,
          target_states: selectedLocation?.admin1 ? [selectedLocation.admin1] : [],
          target_districts: selectedLocation?.name ? [selectedLocation.name] : [],
          push_subscription: pushSubscriptionData || undefined,
          is_opted_in: true,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to save notification preferences.');
      }
      setIsSubscribed(true);
      if (onSubscriptionChange) onSubscriptionChange(true);
      setStatusMessage('Preferences saved. You are opted in for disaster alerts.');
    } catch (err: any) {
      setStatusMessage(err.message || 'Error updating preferences.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleUnsubscribe = async () => {
    setIsSaving(true);
    setStatusMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/notifications/preferences?user_id=${userId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setIsSubscribed(false);
        if (onSubscriptionChange) onSubscriptionChange(false);
        setStatusMessage('Successfully unsubscribed from emergency alerts.');
      }
    } catch (err: any) {
      setStatusMessage('Error unsubscribing.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-lg rounded-3xl p-6 md:p-8 shadow-2xl space-y-6 relative max-h-[90vh] overflow-y-auto">
        {/* Modal Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-2xl bg-gradient-to-tr from-amber-500 to-rose-600 flex items-center justify-center text-lg text-white shadow-lg shadow-rose-500/20">
              🚨
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Emergency Alert Preferences</h3>
              <p className="text-xs text-slate-400">Multi-Channel Proactive SACHET/NDMA Disaster Warnings</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white text-lg font-bold p-1"
          >
            ✕
          </button>
        </div>

        {statusMessage && (
          <div className="p-3 bg-sky-950/80 border border-sky-800 rounded-xl text-xs text-sky-200 flex items-center justify-between">
            <span>{statusMessage}</span>
            <button type="button" onClick={() => setStatusMessage(null)} className="text-sky-400 font-bold">×</button>
          </div>
        )}

        {/* Subscription Status Pill */}
        <div className="flex items-center justify-between p-3 bg-slate-950/80 rounded-2xl border border-slate-800 text-xs">
          <div className="flex items-center space-x-2">
            <span className={`h-2.5 w-2.5 rounded-full ${isSubscribed ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
            <span className="font-semibold text-white">
              Status: {isSubscribed ? 'Opted In (Active)' : 'Not Subscribed'}
            </span>
          </div>
          <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-400 font-mono text-[10px] border border-slate-800">
            Dry-Run Safe Mode Active
          </span>
        </div>

        {/* Form Fields */}
        <div className="space-y-4 text-xs">
          {/* Phone Number */}
          <div className="space-y-1.5">
            <label className="font-bold text-slate-200">Mobile / WhatsApp Number</label>
            <input
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="+91 98765 43210"
              className="w-full bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-xl px-3.5 py-2 text-white placeholder-slate-600 focus:outline-none"
            />
            <p className="text-[11px] text-slate-500">Required for SMS, WhatsApp, and Voice/IVR emergency calls.</p>
          </div>

          {/* Delivery Channels */}
          <div className="space-y-2">
            <label className="font-bold text-slate-200">Emergency Notification Channels</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <label className="flex items-center space-x-2.5 p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer hover:border-slate-700">
                <input
                  type="checkbox"
                  checked={channels.whatsapp}
                  onChange={(e) => setChannels({ ...channels, whatsapp: e.target.checked })}
                  className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700"
                />
                <div>
                  <div className="font-semibold text-white">💬 WhatsApp</div>
                  <div className="text-[10px] text-slate-500">Meta Cloud API ({providerStatus['WHATSAPP'] || 'DRY_RUN'})</div>
                </div>
              </label>

              <label className="flex items-center space-x-2.5 p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer hover:border-slate-700">
                <input
                  type="checkbox"
                  checked={channels.sms}
                  onChange={(e) => setChannels({ ...channels, sms: e.target.checked })}
                  className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700"
                />
                <div>
                  <div className="font-semibold text-white">📱 SMS Alerts</div>
                  <div className="text-[10px] text-slate-500">Exotel Gateway ({providerStatus['SMS'] || 'DRY_RUN'})</div>
                </div>
              </label>

              <label className="flex items-center space-x-2.5 p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer hover:border-slate-700">
                <input
                  type="checkbox"
                  checked={channels.voice}
                  onChange={(e) => setChannels({ ...channels, voice: e.target.checked })}
                  className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700"
                />
                <div>
                  <div className="font-semibold text-white">📞 Voice / IVR Call</div>
                  <div className="text-[10px] text-slate-500">Critical Warnings ({providerStatus['VOICE_IVR'] || 'DRY_RUN'})</div>
                </div>
              </label>

              <label className="flex items-center space-x-2.5 p-3 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer hover:border-slate-700">
                <input
                  type="checkbox"
                  checked={channels.web_push}
                  onChange={(e) => setChannels({ ...channels, web_push: e.target.checked })}
                  className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700"
                />
                <div>
                  <div className="font-semibold text-white">🔔 Web Push</div>
                  <div className="text-[10px] text-slate-500">Browser Push ({providerStatus['WEB_PUSH'] || 'DRY_RUN'})</div>
                </div>
              </label>
            </div>
          </div>

          {/* Minimum Severity Threshold */}
          <div className="space-y-1.5">
            <label className="font-bold text-slate-200">Minimum Severity Filter</label>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as any)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-white focus:outline-none cursor-pointer"
            >
              <option value="Severe">Severe & Extreme Alerts (Recommended)</option>
              <option value="Extreme">Extreme Emergency Only (Cyclones, Flash Floods)</option>
            </select>
          </div>

          {/* Target Region */}
          <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 space-y-1">
            <div className="font-bold text-slate-300">Geographic Coverage Scope:</div>
            <div className="text-slate-400 font-mono text-[11px]">
              {selectedLocation ? `${selectedLocation.name}, ${selectedLocation.admin1 || selectedLocation.country}` : 'India (National)'}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800">
          {isSubscribed ? (
            <button
              type="button"
              onClick={handleUnsubscribe}
              disabled={isSaving}
              className="px-4 py-2 rounded-xl bg-rose-950 hover:bg-rose-900 text-rose-300 font-bold border border-rose-800 transition-colors"
            >
              Unsubscribe All
            </button>
          ) : <div />}

          <div className="flex space-x-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="px-5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-bold transition-all shadow-lg shadow-sky-600/20"
            >
              {isSaving ? 'Saving...' : 'Save & Opt-In'}
            </button>
          </div>
        </div>

        <p className="text-[10px] text-slate-500 leading-relaxed font-mono">
          * Explicit consent notice: Emergency alerts are strictly delivered based on authoritative SACHET/NDMA bulletins. Subscriptions are currently stored in memory during this prototype session.
        </p>
      </div>
    </div>
  );
}
