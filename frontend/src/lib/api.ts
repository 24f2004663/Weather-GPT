import {
  HealthStatus,
  ConfigStatus,
  LocationSearchResponse,
  NormalizedWeatherResponse,
  NasaPowerClimateResponse,
  AlertListResponse,
  ChatRequest,
  ChatResponse,
} from '../types';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchHealthStatus(): Promise<HealthStatus> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) {
      throw new Error(`Health check failed with status: ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    return {
      status: 'unhealthy',
      version: '0.7.1',
      environment: 'unknown',
      timestamp: new Date().toISOString(),
      services: {
        backend_connected: false,
      },
    };
  }
}

export async function fetchConfigStatus(): Promise<ConfigStatus | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/config`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) {
      throw new Error(`Config fetch failed with status: ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    console.error('Failed to fetch config status:', error);
    return null;
  }
}

export async function searchLocations(query: string, count: number = 5): Promise<LocationSearchResponse> {
  const url = `${API_BASE_URL}/api/location/search?q=${encodeURIComponent(query)}&count=${count}`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Location search failed: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function getWeatherForecast(
  lat: number,
  lon: number,
  days: number = 7,
  hourly: boolean = true
): Promise<NormalizedWeatherResponse> {
  const url = `${API_BASE_URL}/api/weather/forecast?lat=${lat}&lon=${lon}&days=${days}&hourly=${hourly}`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    if (res.status === 503) {
      const body = await res.json().catch(() => ({}));
      throw new Error(
        body.hint || 'Weather data temporarily unavailable (rate limit). Please wait a moment and retry.'
      );
    }
    throw new Error(`Weather fetch failed: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function getWeatherByCity(city: string, days: number = 7): Promise<NormalizedWeatherResponse> {
  const url = `${API_BASE_URL}/api/weather/by-city?city=${encodeURIComponent(city)}&days=${days}`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    if (res.status === 503) {
      const body = await res.json().catch(() => ({}));
      throw new Error(
        body.hint || 'Weather data temporarily unavailable (rate limit). Please wait a moment and retry.'
      );
    }
    throw new Error(`Weather by city failed: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function getHistoricalClimate(lat: number, lon: number): Promise<NasaPowerClimateResponse> {
  const url = `${API_BASE_URL}/api/climate/historical?lat=${lat}&lon=${lon}`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Climate fetch failed: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function fetchDisasterAlerts(
  lat?: number,
  lon?: number,
  state?: string,
  district?: string,
  activeOnly: boolean = true
): Promise<AlertListResponse> {
  const params = new URLSearchParams();
  if (lat !== undefined) params.append('lat', lat.toString());
  if (lon !== undefined) params.append('lon', lon.toString());
  if (state) params.append('state', state);
  if (district) params.append('district', district);
  params.append('active_only', activeOnly.toString());

  const url = `${API_BASE_URL}/api/alerts?${params.toString()}`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Alerts fetch failed: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  const url = `${API_BASE_URL}/api/chat`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    cache: 'no-store',
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(errBody.detail || `AI service error: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function fetchVapidPublicKey(): Promise<{ public_key: string | null; status: string; claim_email: string }> {
  const url = `${API_BASE_URL}/api/notifications/vapid-public-key`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    return { public_key: null, status: 'NOT_CONFIGURED', claim_email: '' };
  }
  return await res.json();
}

export async function transcribeAudio(formData: FormData): Promise<{ transcription: string; language: string }> {
  const url = `${API_BASE_URL}/api/audio/transcribe`;
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`Transcription failed: HTTP ${res.status}`);
  }
  return await res.json();
}
