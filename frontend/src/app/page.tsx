'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import Header from '../components/Header';
import CurrentWeatherCard from '../components/CurrentWeatherCard';
import PersonalizedInsights from '../components/PersonalizedInsights';
import DisasterAlertBanner from '../components/DisasterAlertBanner';
import GdacsAlertsPanel from '../components/GdacsAlertsPanel';
import HourlyForecastStrip from '../components/HourlyForecastStrip';
import WeatherCharts from '../components/WeatherCharts';
import WeatherMap from '../components/WeatherMap';
import DailyForecastGrid from '../components/DailyForecastGrid';
import ClimateSection from '../components/ClimateSection';
import ChatPanel from '../components/ChatPanel';
import SourceAttributionPanel from '../components/SourceAttributionPanel';
import NotificationSettingsModal from '../components/NotificationSettingsModal';
import WeatherBackground from '../components/WeatherBackground';

import {
  LocationResult,
  NormalizedWeatherResponse,
  NasaPowerClimateResponse,
  DisasterAlert,
} from '../types';
import { getWeatherForecast, getHistoricalClimate, fetchDisasterAlerts, reverseGeocode, API_BASE_URL } from '../lib/api';
import { t, localeTag } from '../lib/translations';
import { AlertTriangle } from 'lucide-react';

// Default initial location: Chennai, Tamil Nadu, India
const DEFAULT_LOCATION: LocationResult = {
  name: 'Chennai',
  admin1: 'Tamil Nadu',
  country: 'India',
  country_code: 'IN',
  latitude: 13.0827,
  longitude: 80.2707,
  timezone: 'Asia/Kolkata',
  elevation: 10.0,
};

/**
 * True when a location carries no geocoding identity, i.e. the backend built it from
 * bare coordinates rather than resolving it through the geocoding API.
 */
function isPlaceholderLocation(loc: LocationResult | undefined): boolean {
  if (!loc) return true;
  // These arrive as JSON null, not undefined, so both have to be treated as absent.
  const absent = (v: unknown) => v === undefined || v === null;
  return absent(loc.id) && absent(loc.country) && absent(loc.admin1);
}

/**
 * The weather endpoints are queried by coordinate, so their responses carry a
 * "Location (13.08, 80.27)" placeholder instead of a resolved place name. We already
 * hold the geocoded location those coordinates came from, so re-attach it rather than
 * showing the user a coordinate pair where a city name belongs.
 */
function withResolvedLocation(
  weather: NormalizedWeatherResponse,
  resolved: LocationResult | null,
): NormalizedWeatherResponse {
  if (!resolved || !isPlaceholderLocation(weather.location)) return weather;
  return { ...weather, location: resolved };
}

const LOCATION_STORAGE_KEY = 'weathergpt:last-location';

/**
 * Reads the last location the user chose.
 *
 * Returns null on anything unexpected — private-mode throws, cleared site data, or a
 * payload from an older shape. A bad restore would silently show one city's alerts
 * under another city's name, so the shape is validated rather than trusted.
 */
function readStoredLocation(): LocationResult | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(LOCATION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      typeof parsed?.name !== 'string' ||
      typeof parsed?.latitude !== 'number' ||
      typeof parsed?.longitude !== 'number' ||
      Number.isNaN(parsed.latitude) ||
      Number.isNaN(parsed.longitude)
    ) {
      return null;
    }
    return parsed as LocationResult;
  } catch {
    return null;
  }
}

/**
 * True when a location has coordinates but no real place name behind them — either the
 * literal fallback label, or a coordinate-shaped stand-in with no administrative detail.
 * Such an entry is worth re-resolving rather than displaying.
 */
function isUnnamedLocation(loc: LocationResult): boolean {
  const name = (loc.name || '').trim();
  if (!name) return true;
  if (/^my location$/i.test(name)) return true;
  if (/^location\s*\(/i.test(name)) return true;
  return !loc.admin1 && !loc.country;
}

function storeLocation(loc: LocationResult): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(loc));
  } catch {
    // Private mode or blocked site data — the app still works, it just won't remember.
  }
}

export default function HomePage() {
  const [selectedLocation, setSelectedLocation] = useState<LocationResult>(DEFAULT_LOCATION);
  const [currentLanguage, setCurrentLanguage] = useState<string>('en');
  const [isNotificationModalOpen, setIsNotificationModalOpen] = useState<boolean>(false);
  const [isAlertSubscribed, setIsAlertSubscribed] = useState<boolean>(false);
  const [weatherData, setWeatherData] = useState<NormalizedWeatherResponse | null>(null);
  const [climateData, setClimateData] = useState<NasaPowerClimateResponse | null>(null);
  const [alerts, setAlerts] = useState<DisasterAlert[] | null>(null);
  const [gdacsAlerts, setGdacsAlerts] = useState<DisasterAlert[] | null>(null);

  const [isLoadingWeather, setIsLoadingWeather] = useState<boolean>(true);
  const [isLoadingClimate, setIsLoadingClimate] = useState<boolean>(true);
  const [isLoadingAlerts, setIsLoadingAlerts] = useState<boolean>(true);

  const [weatherError, setWeatherError] = useState<string | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);

  // Set once the user picks a location themselves. Geolocation resolves asynchronously,
  // so without this a slow permission grant could land after an explicit search and
  // yank the user back off the city they just chose.
  const hasUserChosenLocation = useRef(false);

  const applyLocation = useCallback((loc: LocationResult) => {
    setSelectedLocation(loc);
    storeLocation(loc);
  }, []);

  // Startup location: last choice, else the device's position, else the default.
  // Geolocation is only requested when nothing is stored, so a returning visitor is
  // never re-prompted.
  useEffect(() => {
    let cancelled = false;
    const stored = readStoredLocation();

    if (stored) {
      setSelectedLocation(stored);
      // A location saved before reverse geocoding existed — or saved when the lookup
      // failed — is stored as the unnamed placeholder. Restoring it verbatim would pin
      // the user to "My Location" forever, so re-resolve it from its coordinates once.
      if (isUnnamedLocation(stored)) {
        void (async () => {
          const resolved = await reverseGeocode(stored.latitude, stored.longitude);
          if (cancelled || hasUserChosenLocation.current || !resolved) return;
          applyLocation({
            ...resolved,
            latitude: stored.latitude,
            longitude: stored.longitude,
            timezone: resolved.timezone || stored.timezone,
          });
        })();
      }
      return () => {
        cancelled = true;
      };
    }

    if (typeof navigator === 'undefined' || !navigator.geolocation) return;

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        if (cancelled || hasUserChosenLocation.current) return;
        const latitude = parseFloat(pos.coords.latitude.toFixed(4));
        const longitude = parseFloat(pos.coords.longitude.toFixed(4));
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

        // Name the place before applying it, so the card and the alert query both get a
        // real town, state and district instead of bare coordinates.
        const resolved = await reverseGeocode(latitude, longitude);
        if (cancelled || hasUserChosenLocation.current) return;
        applyLocation(
          resolved
            ? { ...resolved, latitude, longitude, timezone: resolved.timezone || timezone }
            : { name: 'My Location', latitude, longitude, timezone },
        );
      },
      () => {
        // Denied, unavailable, or non-secure origin — the default already stands.
      },
      { timeout: 8000, maximumAge: 600_000 },
    );
    return () => {
      cancelled = true;
    };
  }, [applyLocation]);

  const loadDataForLocation = useCallback(async (loc: LocationResult) => {
    setIsLoadingWeather(true);
    setIsLoadingClimate(true);
    setIsLoadingAlerts(true);
    setWeatherError(null);
    setAlertsError(null);

    // Execute real-time weather, historical climate, and disaster alerts concurrently
    const [weatherResult, climateResult, alertsResult] = await Promise.allSettled([
      getWeatherForecast(loc.latitude, loc.longitude, 7, true),
      getHistoricalClimate(loc.latitude, loc.longitude),
      fetchDisasterAlerts(loc.latitude, loc.longitude, loc.admin1, loc.name, true),
    ]);

    // 1. Process Weather
    if (weatherResult.status === 'fulfilled') {
      setWeatherData(withResolvedLocation(weatherResult.value, loc));
    } else {
      console.error('Failed to load weather:', weatherResult.reason);
      setWeatherError(weatherResult.reason?.message || 'Unable to retrieve weather data from backend.');
    }
    setIsLoadingWeather(false);

    // 2. Process Climatological Historical Baseline
    if (climateResult.status === 'fulfilled') {
      setClimateData(climateResult.value);
    } else {
      console.error('Failed to load climate baseline:', climateResult.reason);
      setClimateData(null);
    }
    setIsLoadingClimate(false);

    // 3. Process Real-Time Official Disaster Alerts from SACHET/NDMA
    if (alertsResult.status === 'fulfilled') {
      setAlerts(alertsResult.value.alerts);
    } else {
      console.error('Failed to load disaster alerts:', alertsResult.reason);
      setAlertsError(alertsResult.reason?.message || 'Failed to refresh disaster alerts.');
      setAlerts([]);
    }
    setIsLoadingAlerts(false);
  }, []);

  useEffect(() => {
    loadDataForLocation(selectedLocation);
  }, [selectedLocation, loadDataForLocation]);

  // Keep the document language in step with the selected UI language. The static
  // <html lang> in layout.tsx is only the SSR default; without this a Tamil or
  // Bengali interface stays declared as English, so screen readers apply English
  // pronunciation rules to regional-script content.
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.lang = localeTag(currentLanguage);
    }
  }, [currentLanguage]);

  // The backdrop is a fixed charcoal now, so the surface is always dark. Set on <html>
  // rather than passed as a prop so nested portals and the scrollbar pseudo-elements
  // resolve the same tokens. The light-theme values stay defined in globals.css, so a
  // panel can still pin data-surface="light" locally if one is ever needed.
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.surface = 'dark';
    }
  }, []);

  // Fetch initial Emergency Alert subscription status
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/notifications/preferences?user_id=weathergpt_web_user`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.is_opted_in) {
          setIsAlertSubscribed(true);
        }
      })
      .catch(() => {});
  }, []);

  /**
   * A single neutral charcoal, the same in every weather condition.
   *
   * The backdrop no longer signals the weather — that is the job of the condition icon,
   * the temperature and the alert panels. Zinc rather than slate so the grey stays truly
   * neutral instead of picking up slate's blue cast.
   */
  const BACKGROUND_GRADIENT = 'from-zinc-700 via-zinc-800 to-zinc-900';

  const handleSelectLocation = (newLoc: LocationResult) => {
    hasUserChosenLocation.current = true;
    applyLocation(newLoc);
  };

  return (
    <div className={`min-h-screen flex flex-col bg-gradient-to-br ${BACKGROUND_GRADIENT} text-ink antialiased selection:bg-ink/20 selection:text-ink relative z-0`}>
      <WeatherBackground 
        iconKey={weatherData?.current?.icon_key} 
        isDay={weatherData?.current?.is_day === 1} 
      />
      {/* Header with Search, Geolocation, Notification Settings & Multilingual Selector */}
      <Header
        selectedLocation={selectedLocation}
        onSelectLocation={handleSelectLocation}
        isLoadingWeather={isLoadingWeather}
        currentLanguage={currentLanguage}
        onLanguageChange={setCurrentLanguage}
        onOpenNotificationSettings={() => setIsNotificationModalOpen(true)}
      />

      {/* Emergency Alert Settings Subscription Modal */}
      <NotificationSettingsModal
        isOpen={isNotificationModalOpen}
        onClose={() => setIsNotificationModalOpen(false)}
        selectedLocation={selectedLocation}
        currentLanguage={currentLanguage}
        onSubscriptionChange={setIsAlertSubscribed}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
        {weatherError && (
          <div className="p-4 rounded-2xl bg-rose-950/60 border border-rose-800 text-xs text-rose-200 flex items-center justify-between shadow-lg">
            <span className="inline-flex items-center gap-1.5"><AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />{weatherError}</span>
            <button
              type="button"
              onClick={() => loadDataForLocation(selectedLocation)}
              className="px-3 py-1 bg-rose-900 hover:bg-rose-800 text-[#fff] rounded-lg font-medium transition-colors"
            >
              {t('retry', currentLanguage)}
            </button>
          </div>
        )}

        {/* 2-Column Responsive Dashboard Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column (7 cols): Weather, Alert, Map & Climate Deck */}
          <section className="lg:col-span-7 space-y-6" aria-label="Meteorological & Geospatial Dashboard">
            {/* 1. Real-Time Current Weather Card */}
            <CurrentWeatherCard
              weather={weatherData}
              isLoading={isLoadingWeather}
              currentLanguage={currentLanguage}
            />

            {/* 2. Personalized Weather Insights & Recommendations */}
            <PersonalizedInsights
              weather={weatherData}
              location={selectedLocation}
              currentLanguage={currentLanguage}
            />

            {/* 3. Official SACHET / NDMA Disaster Alert Watch */}
            <DisasterAlertBanner
              alerts={alerts}
              isLoading={isLoadingAlerts}
              error={alertsError}
              location={selectedLocation}
              onRetry={() => loadDataForLocation(selectedLocation)}
              currentLanguage={currentLanguage}
            />

            {/* 4. Top 7 Live GDACS Disaster Alerts */}
            <GdacsAlertsPanel
              onAlertsLoaded={setGdacsAlerts}
              currentLanguage={currentLanguage}
            />

            {/* 5. Interactive Geospatial Weather & Alert Map */}
            <WeatherMap
              location={selectedLocation}
              weather={weatherData}
              alerts={alerts}
              gdacsAlerts={gdacsAlerts}
              currentLanguage={currentLanguage}
            />

            {/* 6. 24-Hour Hourly Scrollable Strip */}
            {weatherData && weatherData.hourly && (
              <HourlyForecastStrip
                hourly={weatherData.hourly}
                currentLanguage={currentLanguage}
              />
            )}

            {/* 7. Meteorological Trend Charts (SVG) */}
            {weatherData && (
              <WeatherCharts
                hourly={weatherData.hourly || []}
                daily={weatherData.daily || []}
                currentLanguage={currentLanguage}
              />
            )}

            {/* 8. 7-Day Synoptic Forecast Grid */}
            {weatherData && weatherData.daily && (
              <DailyForecastGrid
                daily={weatherData.daily}
                currentLanguage={currentLanguage}
              />
            )}

            {/* 9. 30-Year NASA POWER Climatological Baseline */}
            <ClimateSection
              climate={climateData}
              isLoading={isLoadingClimate}
              currentLanguage={currentLanguage}
            />
          </section>

          {/* Right Column (5 cols): AI Intelligence Assistant & Voice Hub */}
          <section className="lg:col-span-5 space-y-6 sticky top-20" aria-label="AI WeatherGPT Assistant">
            <ChatPanel
              selectedLocation={selectedLocation}
              currentLanguage={currentLanguage}
              isAlertSubscribed={isAlertSubscribed}
              onOpenNotificationSettings={() => setIsNotificationModalOpen(true)}
            />
          </section>
        </div>

        {/* Footer Data Source Attribution */}
        <SourceAttributionPanel currentLanguage={currentLanguage} />
      </main>
    </div>
  );
}
