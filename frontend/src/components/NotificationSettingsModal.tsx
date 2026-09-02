'use client';

import React, { useState, useEffect } from 'react';
import { LocationResult } from '../types';
import { API_BASE_URL, sendTestNotification } from '../lib/api';

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

  // Channel test state: { [channel]: { loading: boolean, message: string | null, error: boolean } }
  const [testState, setTestState] = useState<Record<string, { loading: boolean; message: string | null; error: boolean }>>({});

  const userId = 'weathergpt_web_user'; // Registered user identifier

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
              voice: false, // Phase 3: Voice disabled
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

  function urlBase64ToUint8Array(base64String: string): Uint8Array {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

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

      // Register Service Worker
      const reg = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;
      setWebPushStatus('Service Worker Active');

      // Fetch VAPID public key
      const keyRes = await fetch(`${API_BASE_URL}/api/notifications/vapid-public-key`);
      if (!keyRes.ok) {
        setWebPushStatus('Failed to retrieve VAPID key from backend');
        return null;
      }
      const keyData = await keyRes.json();
      if (!keyData.public_key) {
        setWebPushStatus('VAPID public key not configured on backend');
        return null;
      }

      // Re-create PushSubscription tied strictly to current VAPID public key
      let sub = await reg.pushManager.getSubscription();
      if (sub) {
        try {
          await sub.unsubscribe();
        } catch (_) {}
      }
      
      const applicationServerKey = urlBase64ToUint8Array(keyData.public_key);
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey as any,
      });

      setWebPushStatus('PushSubscription Active');
      return sub.toJSON();
    } catch (err: any) {
      console.warn('Web push registration notice:', err);
      setWebPushStatus(`Push registration error: ${err.message || 'Unknown'}`);
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
      setStatusMessage('Preferences saved successfully. You are opted in for emergency alerts.');
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

  const handleRunChannelTest = async (channelKey: 'WHATSAPP' | 'WEB_PUSH' | 'SMS') => {
    if (testState[channelKey]?.loading) return;

    setTestState((prev) => ({
      ...prev,
      [channelKey]: { loading: true, message: null, error: false },
    }));

    try {
      const result = await sendTestNotification(userId, channelKey);
      setTestState((prev) => ({
        ...prev,
        [channelKey]: {
          loading: false,
          message: `✅ Test message sent! Status: ${result.status || 'SENT'} (${result.provider || 'Adapter'})`,
          error: false,
        },
      }));
    } catch (err: any) {
      setTestState((prev) => ({
        ...prev,
        [channelKey]: {
          loading: false,
          message: `❌ Test failed: ${err.message || 'Error sending test message'}`,
          error: true,
        },
      }));
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-3xl rounded-3xl p-6 md:p-8 shadow-2xl space-y-6 relative max-h-[92vh] overflow-y-auto">
        {/* Modal Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-amber-500 to-rose-600 flex items-center justify-center text-xl text-white shadow-lg shadow-rose-500/20">
              🚨
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Emergency Alert Preferences</h3>
              <p className="text-xs text-slate-400">SACHET/NDMA & GDACS Emergency Disaster Warnings — Phase 2</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white text-xl font-bold p-1 transition-colors"
          >
            ✕
          </button>
        </div>

        {statusMessage && (
          <div className="p-3.5 bg-sky-950/80 border border-sky-800 rounded-xl text-xs text-sky-200 flex items-center justify-between shadow-md">
            <span>{statusMessage}</span>
            <button type="button" onClick={() => setStatusMessage(null)} className="text-sky-400 font-bold ml-2">✕</button>
          </div>
        )}

        {/* Subscription Status Banner */}
        <div className="flex flex-wrap items-center justify-between p-4 bg-slate-950/90 rounded-2xl border border-slate-800 gap-3 text-xs">
          <div className="flex items-center space-x-2.5">
            <span className={`h-3.5 w-3.5 rounded-full ${isSubscribed ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
            <div>
              <span className="font-bold text-white">
                Status: {isSubscribed ? 'Opted In (Active Subscriber)' : 'Not Subscribed'}
              </span>
              <p className="text-[11px] text-slate-400">
                Authoritative Supabase persistence enabled
              </p>
            </div>
          </div>
          <span className="px-3 py-1 rounded-lg bg-sky-950 text-sky-300 font-mono text-[11px] font-bold border border-sky-800">
            Phase 2 Pipeline (WhatsApp + Web Push + SMS)
          </span>
        </div>

        {/* Form Fields */}
        <div className="space-y-6 text-xs">
          {/* Phone Number */}
          <div className="space-y-1.5">
            <label className="font-bold text-slate-200 text-sm">Mobile / WhatsApp Number</label>
            <input
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="+91 98765 43210"
              className="w-full bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:outline-none"
            />
            <p className="text-[11px] text-slate-500">Must match E.164 format (e.g. +919876543210) for WhatsApp and SMS alert delivery.</p>
          </div>

          {/* Delivery Channels Grid with Test Buttons */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="font-bold text-slate-200 text-sm">Emergency Notification Channels</label>
              <span className="text-[11px] text-slate-400">Test buttons send isolated test messages to your registered phone</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* WhatsApp */}
              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition-all space-y-3">
                <label className="flex items-start justify-between cursor-pointer">
                  <div className="flex items-center space-x-2.5">
                    <input
                      type="checkbox"
                      checked={channels.whatsapp}
                      onChange={(e) => setChannels({ ...channels, whatsapp: e.target.checked })}
                      className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700 mt-0.5"
                    />
                    <div>
                      <div className="font-bold text-white text-sm">💬 WhatsApp</div>
                      <div className="text-[11px] text-slate-400">Live Baileys / Twilio ({providerStatus['WHATSAPP'] || 'ACTIVE'})</div>
                    </div>
                  </div>
                  <span className="px-2.5 py-0.5 text-[10px] font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                    Phase 1 Active
                  </span>
                </label>

                {channels.whatsapp && isSubscribed && (
                  <div className="pt-2 border-t border-slate-900 space-y-2">
                    <button
                      type="button"
                      onClick={() => handleRunChannelTest('WHATSAPP')}
                      disabled={testState['WHATSAPP']?.loading}
                      className="px-3.5 py-1.5 rounded-xl bg-sky-950 hover:bg-sky-900 text-sky-300 font-bold text-xs border border-sky-800 transition-colors w-full flex items-center justify-center space-x-2"
                    >
                      <span>🧪</span>
                      <span>{testState['WHATSAPP']?.loading ? 'Sending Test...' : 'Test WhatsApp'}</span>
                    </button>
                    {testState['WHATSAPP']?.message && (
                      <p className={`text-[11px] font-mono text-center ${testState['WHATSAPP'].error ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {testState['WHATSAPP'].message}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Web Push */}
              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition-all space-y-3">
                <label className="flex items-start justify-between cursor-pointer">
                  <div className="flex items-center space-x-2.5">
                    <input
                      type="checkbox"
                      checked={channels.web_push}
                      onChange={(e) => setChannels({ ...channels, web_push: e.target.checked })}
                      className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700 mt-0.5"
                    />
                    <div>
                      <div className="font-bold text-white text-sm">🔔 Web Push</div>
                      <div className="text-[11px] text-slate-400">Browser VAPID ({providerStatus['WEB_PUSH'] || 'ACTIVE'})</div>
                    </div>
                  </div>
                  <span className="px-2.5 py-0.5 text-[10px] font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                    Phase 1 Active
                  </span>
                </label>

                {channels.web_push && isSubscribed && (
                  <div className="pt-2 border-t border-slate-900 space-y-2">
                    <button
                      type="button"
                      onClick={() => handleRunChannelTest('WEB_PUSH')}
                      disabled={testState['WEB_PUSH']?.loading}
                      className="px-3.5 py-1.5 rounded-xl bg-sky-950 hover:bg-sky-900 text-sky-300 font-bold text-xs border border-sky-800 transition-colors w-full flex items-center justify-center space-x-2"
                    >
                      <span>🧪</span>
                      <span>{testState['WEB_PUSH']?.loading ? 'Sending Test...' : 'Test Web Push'}</span>
                    </button>
                    {testState['WEB_PUSH']?.message && (
                      <p className={`text-[11px] font-mono text-center ${testState['WEB_PUSH'].error ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {testState['WEB_PUSH'].message}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* SMS Alerts (Phase 2 Active) */}
              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition-all space-y-3">
                <label className="flex items-start justify-between cursor-pointer">
                  <div className="flex items-center space-x-2.5">
                    <input
                      type="checkbox"
                      checked={channels.sms}
                      onChange={(e) => setChannels({ ...channels, sms: e.target.checked })}
                      className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700 mt-0.5"
                    />
                    <div>
                      <div className="font-bold text-white text-sm">📱 SMS Alerts</div>
                      <div className="text-[11px] text-slate-400">TextBee Android SIM Gateway ({providerStatus['SMS'] || 'ACTIVE'})</div>
                    </div>
                  </div>
                  <span className="px-2.5 py-0.5 text-[10px] font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                    Phase 2 Active
                  </span>
                </label>

                {channels.sms && isSubscribed && (
                  <div className="pt-2 border-t border-slate-900 space-y-2">
                    <button
                      type="button"
                      onClick={() => handleRunChannelTest('SMS')}
                      disabled={testState['SMS']?.loading}
                      className="px-3.5 py-1.5 rounded-xl bg-sky-950 hover:bg-sky-900 text-sky-300 font-bold text-xs border border-sky-800 transition-colors w-full flex items-center justify-center space-x-2"
                    >
                      <span>🧪</span>
                      <span>{testState['SMS']?.loading ? 'Sending Test...' : 'Test SMS'}</span>
                    </button>
                    {testState['SMS']?.message && (
                      <p className={`text-[11px] font-mono text-center ${testState['SMS'].error ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {testState['SMS'].message}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Voice / IVR Call (Phase 3 — Disabled) */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800/60 opacity-50 space-y-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-2.5">
                    <input type="checkbox" disabled checked={false} className="rounded bg-slate-900 border-slate-800 cursor-not-allowed" />
                    <div>
                      <div className="font-bold text-slate-400 text-sm">📞 Voice / IVR Call</div>
                      <div className="text-[10px] text-slate-500">Critical Warnings Call</div>
                    </div>
                  </div>
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-900 text-slate-500 border border-slate-800">
                    Phase 3 (Disabled)
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Minimum Severity Threshold */}
          <div className="space-y-1.5">
            <label className="font-bold text-slate-200 text-sm">Minimum Severity Filter</label>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as any)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none cursor-pointer"
            >
              <option value="Severe">Severe & Extreme Alerts (Recommended)</option>
              <option value="Extreme">Extreme Emergency Only (Cyclones, Flash Floods)</option>
            </select>
          </div>

          {/* Target Region */}
          <div className="p-4 bg-slate-950/80 rounded-2xl border border-slate-800 space-y-1">
            <div className="font-bold text-slate-300 text-xs">Geographic Coverage Scope:</div>
            <div className="text-slate-400 font-mono text-[11px]">
              {selectedLocation ? `${selectedLocation.name}, ${selectedLocation.admin1 || selectedLocation.country}` : 'India (National Coverage)'}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-800">
          {isSubscribed ? (
            <button
              type="button"
              onClick={handleUnsubscribe}
              disabled={isSaving}
              className="px-4 py-2.5 rounded-xl bg-rose-950 hover:bg-rose-900 text-rose-300 font-bold text-xs border border-rose-800 transition-colors"
            >
              Unsubscribe All
            </button>
          ) : <div />}

          <div className="flex space-x-3">
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium text-xs transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="px-6 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs transition-all shadow-lg shadow-sky-600/20"
            >
              {isSaving ? 'Saving...' : 'Save & Opt-In'}
            </button>
          </div>
        </div>

        <p className="text-[10px] text-slate-500 leading-relaxed font-mono">
          * Explicit consent notice: Emergency disaster alerts are powered by authoritative SACHET/NDMA and GDACS feeds. Preferences are persisted in Supabase. Phase 2 active channels: WhatsApp, Web Push, and SMS.
        </p>
      </div>
    </div>
  );
}
