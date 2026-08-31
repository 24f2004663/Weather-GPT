'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Header from '../components/Header';
import CurrentWeatherCard from '../components/CurrentWeatherCard';
import PersonalizedInsights from '../components/PersonalizedInsights';
import DisasterAlertBanner from '../components/DisasterAlertBanner';
import HourlyForecastStrip from '../components/HourlyForecastStrip';
import WeatherCharts from '../components/WeatherCharts';
import WeatherMap from '../components/WeatherMap';
import DailyForecastGrid from '../components/DailyForecastGrid';
import ClimateSection from '../components/ClimateSection';
import ChatPanel from '../components/ChatPanel';
import SourceAttributionPanel from '../components/SourceAttributionPanel';
import NotificationSettingsModal from '../components/NotificationSettingsModal';

import {
  LocationResult,
  NormalizedWeatherResponse,
  NasaPowerClimateResponse,
  DisasterAlert,
} from '../types';
import { getWeatherForecast, getHistoricalClimate, fetchDisasterAlerts } from '../lib/api';

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

export default function HomePage() {
  const [selectedLocation, setSelectedLocation] = useState<LocationResult>(DEFAULT_LOCATION);
  const [currentLanguage, setCurrentLanguage] = useState<string>('en');
  const [isNotificationModalOpen, setIsNotificationModalOpen] = useState<boolean>(false);
  const [weatherData, setWeatherData] = useState<NormalizedWeatherResponse | null>(null);
  const [climateData, setClimateData] = useState<NasaPowerClimateResponse | null>(null);
  const [alerts, setAlerts] = useState<DisasterAlert[] | null>(null);

  const [isLoadingWeather, setIsLoadingWeather] = useState<boolean>(true);
  const [isLoadingClimate, setIsLoadingClimate] = useState<boolean>(true);
  const [isLoadingAlerts, setIsLoadingAlerts] = useState<boolean>(true);

  const [weatherError, setWeatherError] = useState<string | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);

  const loadDataForLocation = useCallback(async (loc: LocationResult) => {
    setIsLoadingWeather(true);
    setIsLoadingClimate(true);
    setIsLoadingAlerts(true);
    setWeatherError(null);
    setAlertsError(null);

    // 1. Load Real-Time & Forecast Weather
    try {
      const wRes = await getWeatherForecast(loc.latitude, loc.longitude, 7, true);
      setWeatherData(wRes);
    } catch (err: any) {
      console.error('Failed to load weather:', err);
      setWeatherError(err.message || 'Unable to retrieve weather data from backend.');
    } finally {
      setIsLoadingWeather(false);
    }

    // 2. Load Climatological Historical Baseline
    try {
      const cRes = await getHistoricalClimate(loc.latitude, loc.longitude);
      setClimateData(cRes);
    } catch (err: any) {
      console.error('Failed to load climate baseline:', err);
      setClimateData(null);
    } finally {
      setIsLoadingClimate(false);
    }

    // 3. Load Real-Time Official Disaster Alerts from SACHET/NDMA
    try {
      const aRes = await fetchDisasterAlerts(
        loc.latitude,
        loc.longitude,
        loc.admin1,
        loc.name,
        true
      );
      setAlerts(aRes.alerts);
    } catch (err: any) {
      console.error('Failed to load disaster alerts:', err);
      setAlertsError(err.message || 'Failed to refresh disaster alerts.');
      setAlerts([]);
    } finally {
      setIsLoadingAlerts(false);
    }
  }, []);

  useEffect(() => {
    loadDataForLocation(selectedLocation);
  }, [selectedLocation, loadDataForLocation]);

  const handleSelectLocation = (newLoc: LocationResult) => {
    setSelectedLocation(newLoc);
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 antialiased selection:bg-sky-500 selection:text-white">
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
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
        {weatherError && (
          <div className="p-4 rounded-2xl bg-rose-950/60 border border-rose-800 text-xs text-rose-200 flex items-center justify-between shadow-lg">
            <span>⚠️ {weatherError}</span>
            <button
              type="button"
              onClick={() => loadDataForLocation(selectedLocation)}
              className="px-3 py-1 bg-rose-900 hover:bg-rose-800 text-white rounded-lg font-medium transition-colors"
            >
              Retry
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
            />

            {/* 4. Interactive Geospatial Weather & Alert Map */}
            <WeatherMap
              location={selectedLocation}
              weather={weatherData}
              alerts={alerts}
            />

            {/* 5. 24-Hour Hourly Scrollable Strip */}
            {weatherData && weatherData.hourly && (
              <HourlyForecastStrip hourly={weatherData.hourly} />
            )}

            {/* 6. Meteorological Trend Charts (SVG) */}
            {weatherData && (
              <WeatherCharts
                hourly={weatherData.hourly || []}
                daily={weatherData.daily || []}
              />
            )}

            {/* 7. 7-Day Synoptic Forecast Grid */}
            {weatherData && weatherData.daily && (
              <DailyForecastGrid daily={weatherData.daily} />
            )}

            {/* 8. 30-Year NASA POWER Climatological Baseline */}
            <ClimateSection
              climate={climateData}
              isLoading={isLoadingClimate}
            />
          </section>

          {/* Right Column (5 cols): AI Intelligence Assistant & Voice Hub */}
          <section className="lg:col-span-5 space-y-6 sticky top-20" aria-label="AI WeatherGPT Assistant">
            <ChatPanel
              selectedLocation={selectedLocation}
              currentLanguage={currentLanguage}
            />
          </section>
        </div>

        {/* Footer Data Source Attribution */}
        <SourceAttributionPanel />
      </main>
    </div>
  );
}
