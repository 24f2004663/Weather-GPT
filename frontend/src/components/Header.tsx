'use client';

import React, { useState, useEffect, useRef } from 'react';
import { LocationResult } from '../types';
import { searchLocations, reverseGeocode } from '../lib/api';
import { t } from '../lib/translations';
import { CloudLightning, Search, Bell, MapPin } from 'lucide-react';

interface HeaderProps {
  selectedLocation: LocationResult | null;
  onSelectLocation: (location: LocationResult) => void;
  isLoadingWeather: boolean;
  currentLanguage: string;
  onLanguageChange: (lang: string) => void;
  onOpenNotificationSettings?: () => void;
}

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिंदी (Hindi)' },
  { code: 'ta', label: 'தமிழ் (Tamil)' },
  { code: 'te', label: 'తెలుగు (Telugu)' },
  { code: 'bn', label: 'বাংলা (Bengali)' },
];

export default function Header({
  selectedLocation,
  onSelectLocation,
  isLoadingWeather,
  currentLanguage,
  onLanguageChange,
  onOpenNotificationSettings,
}: HeaderProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<LocationResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Debounced search
  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    const handler = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await searchLocations(query, 5);
        setResults(res.results);
        setIsOpen(res.results.length > 0);
      } catch (err) {
        setResults([]);
        setIsOpen(false);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => clearTimeout(handler);
  }, [query]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (loc: LocationResult) => {
    onSelectLocation(loc);
    setQuery('');
    setIsOpen(false);
  };

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      setGeoError('Geolocation not supported by your browser');
      return;
    }
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const latitude = parseFloat(pos.coords.latitude.toFixed(4));
        const longitude = parseFloat(pos.coords.longitude.toFixed(4));
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

        // Name the place rather than showing "My Location". The resolved admin1/admin2
        // also give the alert query a state and district to match on, which bare
        // coordinates cannot provide.
        const resolved = await reverseGeocode(latitude, longitude);
        onSelectLocation(
          resolved
            ? { ...resolved, latitude, longitude, timezone: resolved.timezone || timezone }
            : { name: t('myLocation', currentLanguage), latitude, longitude, timezone },
        );
      },
      (err) => {
        setGeoError('Location permission denied or unavailable');
      }
    );
  };

  return (
    <header className="w-full bg-black/10 backdrop-blur-2xl border-b border-white/10 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        {/* Brand & Tagline */}
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-sky-500 via-indigo-500 to-indigo-700 flex items-center justify-center font-bold text-xl shadow-lg shadow-sky-500/20 text-white">
            <CloudLightning size={20} strokeWidth={2} aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              {/* Gradient runs ink -> ink -> sky. The middle stop used to be a literal
                  slate-100, which vanished against a light grey backdrop and left the
                  wordmark reading "Wea___erGPT". Both ends now follow the theme. */}
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-ink via-ink/90 to-sky-500 bg-clip-text text-transparent">
                WeatherGPT
              </h1>
              <span className="px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase rounded-full bg-sky-950 text-sky-400 border border-sky-800">
                {t('aiPlatform', currentLanguage)}
              </span>
            </div>
            <p className="text-xs text-ink/60">{t('weatherTagline', currentLanguage)}</p>
          </div>
        </div>

        {/* Location Search Bar & Geolocation Button */}
        <div className="flex-1 max-w-lg relative" ref={dropdownRef}>
          <div className="relative flex items-center">
            <Search size={15} strokeWidth={2} aria-hidden="true" className="absolute left-3.5 text-ink/60" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('searchPlaceholder', currentLanguage)}
              className="w-full bg-white/10 border border-white/20 focus:border-white/40 rounded-xl pl-10 pr-24 py-2 text-sm text-white placeholder-white/50 focus:outline-none transition-colors backdrop-blur-md"
              aria-label={t('searchAriaLabel', currentLanguage)}
            />
            {isSearching && (
              <span className="absolute right-12 text-xs text-sky-400 animate-pulse font-mono">
                ...
              </span>
            )}
            <button
              type="button"
              onClick={handleUseCurrentLocation}
              title={t('useCurrentLocation', currentLanguage)}
              className="absolute right-2 px-2 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-white/90 text-xs font-medium border border-white/20 transition-colors flex items-center gap-1 backdrop-blur-sm"
            >
              <span>{t('gpsButton', currentLanguage)}</span>
            </button>
          </div>

          {geoError && (
            <div className="absolute top-full left-0 right-0 mt-1 p-2 bg-rose-950/90 border border-rose-800/80 rounded-lg text-xs text-rose-300 shadow-xl z-50">
              {geoError}
            </div>
          )}

          {/* Autocomplete Dropdown */}
          {isOpen && results.length > 0 && (
            <ul
              data-surface="dark"
              className="absolute top-full left-0 right-0 mt-1.5 bg-black/60 backdrop-blur-2xl border border-white/10 rounded-xl shadow-2xl overflow-hidden z-50 max-h-60 overflow-y-auto divide-y divide-white/10"
              role="listbox"
            >
              {results.map((loc, idx) => (
                <li
                  key={idx}
                  onClick={() => handleSelect(loc)}
                  className="px-4 py-2.5 hover:bg-white/10 cursor-pointer flex justify-between items-center text-xs transition-colors"
                  role="option"
                  aria-selected="false"
                >
                  <div className="font-medium text-white">
                    {loc.name}
                    {loc.admin1 ? <span className="text-slate-400">, {loc.admin1}</span> : null}
                    {loc.country ? <span className="text-slate-500"> ({loc.country})</span> : null}
                  </div>
                  <div className="font-mono text-[10px] text-slate-500">
                    {loc.latitude.toFixed(2)}°, {loc.longitude.toFixed(2)}°
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Action Controls: Notification Modal Button, Language Selector & Location Pill */}
        <div className="flex items-center space-x-2.5">
          {/* Alert Preferences Modal Button */}
          {onOpenNotificationSettings && (
            <button
              type="button"
              onClick={onOpenNotificationSettings}
              className="px-3 py-1.5 rounded-xl bg-amber-950/70 hover:bg-amber-900 border border-amber-800 text-amber-200 text-xs font-bold transition-colors flex items-center gap-1.5 shadow-sm"
              title={t('alertSettingsTooltip', currentLanguage)}
            >
              <Bell size={13} strokeWidth={2} aria-hidden="true" />
              <span className="hidden sm:inline">{t('alertSettings', currentLanguage)}</span>
            </button>
          )}

          {/* Language Selector */}
          <div className="relative">
            <select
              value={currentLanguage}
              onChange={(e) => onLanguageChange(e.target.value)}
              className="bg-white/10 text-white border border-white/20 rounded-xl px-2.5 py-1.5 text-xs font-medium focus:outline-none focus:border-white/40 cursor-pointer backdrop-blur-md"
              aria-label={t('selectLanguage', currentLanguage)}
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code} className="bg-slate-900 text-[#fff]">
                  🌐 {lang.label}
                </option>
              ))}
            </select>
          </div>

          {/* Selected Location Pill */}
          {selectedLocation && (
            <div className="glass px-3 py-1.5 rounded-xl flex items-center space-x-2 text-xs">
              <MapPin size={13} strokeWidth={2.5} aria-hidden="true" className="text-sky-400" />
              <span className="font-semibold text-white truncate max-w-[100px] sm:max-w-[140px]">
                {selectedLocation.name}
              </span>
              {isLoadingWeather && (
                <span className="h-2 w-2 rounded-full bg-sky-400 animate-ping"></span>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
