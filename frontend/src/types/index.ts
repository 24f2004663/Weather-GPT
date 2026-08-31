export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  environment: string;
  timestamp: string;
  services: Record<string, boolean>;
}

export interface ConfigStatus {
  project_name: string;
  version: string;
  environment: string;
  debug: boolean;
  configured_services: Record<string, boolean>;
  allowed_origins: string[];
}

export interface LocationResult {
  id?: number;
  name: string;
  latitude: number;
  longitude: number;
  country?: string;
  country_code?: string;
  admin1?: string;
  admin2?: string;
  timezone?: string;
  elevation?: number;
  population?: number;
}

export interface LocationSearchResponse {
  query: string;
  count: number;
  results: LocationResult[];
}

export interface CurrentWeather {
  temperature_c: number;
  apparent_temperature_c?: number;
  humidity_percent?: number;
  precipitation_mm?: number;
  wind_speed_kmh?: number;
  wind_direction_deg?: number;
  wind_gusts_kmh?: number;
  weather_code: number;
  weather_condition: string;
  icon_key: string;
  is_day?: number;
  uv_index?: number;
  cloud_cover_percent?: number;
  pressure_hpa?: number;
  air_quality_index?: number;
  observed_time: string;
}

export interface HourlyForecast {
  time: string;
  temperature_c: number;
  apparent_temperature_c?: number;
  precipitation_probability?: number;
  precipitation_mm?: number;
  weather_code: number;
  weather_condition: string;
  icon_key: string;
  wind_speed_kmh?: number;
  humidity_percent?: number;
  uv_index?: number;
}

export interface DailyForecast {
  date: string;
  temperature_max_c: number;
  temperature_min_c: number;
  apparent_temperature_max_c?: number;
  apparent_temperature_min_c?: number;
  precipitation_sum_mm?: number;
  precipitation_probability_max?: number;
  precipitation_hours?: number;
  weather_code: number;
  weather_condition: string;
  icon_key: string;
  wind_speed_max_kmh?: number;
  wind_gusts_max_kmh?: number;
  wind_direction_dominant_deg?: number;
  sunrise?: string;
  sunset?: string;
  uv_index_max?: number;
}

export interface NormalizedWeatherResponse {
  provider: string;
  location: LocationResult;
  current: CurrentWeather;
  hourly: HourlyForecast[];
  daily: DailyForecast[];
  timezone: string;
  elevation_m?: number;
  cached: boolean;
  retrieved_at: string;
}

export interface MonthlyClimateMetric {
  month: string;
  temperature_2m_c?: number;
  precipitation_mm_day?: number;
  solar_radiation_kwh_m2_day?: number;
  relative_humidity_percent?: number;
  wind_speed_10m_ms?: number;
}

export interface NasaPowerClimateResponse {
  provider: string;
  location: LocationResult;
  annual_averages: Record<string, number>;
  monthly_data: MonthlyClimateMetric[];
  parameters_explained: Record<string, string>;
  cached: boolean;
  retrieved_at: string;
}

export type AlertSeverity = 'Extreme' | 'Severe' | 'Moderate' | 'Minor' | 'Unknown';
export type AlertUrgency = 'Immediate' | 'Expected' | 'Future' | 'Past' | 'Unknown';
export type AlertCertainty = 'Observed' | 'Likely' | 'Possible' | 'Unlikely' | 'Unknown';
export type AlertStatus = 'Actual' | 'Exercise' | 'System' | 'Test' | 'Draft' | 'Cancelled';
export type GeographicScope = 'District' | 'State' | 'National' | 'Unknown';

export interface DisasterAlert {
  alert_id: string;
  source: string;
  title: string;
  event_type: string;
  severity: AlertSeverity;
  original_severity?: string;
  urgency: AlertUrgency;
  certainty: AlertCertainty;
  status: AlertStatus;
  headline?: string;
  description: string;
  instruction?: string;
  effective_time?: string;
  expires_time?: string;
  issued_time: string;
  affected_area: string;
  scope: GeographicScope;
  affected_states: string[];
  affected_districts: string[];
  polygon_coordinates?: number[][];
  source_url?: string;
  is_active: boolean;
}

export interface AlertListResponse {
  source: string;
  query_location?: string;
  total_count: number;
  active_count: number;
  highest_severity?: AlertSeverity;
  alerts: DisasterAlert[];
  cached: boolean;
  last_synced: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  source_attribution?: string[];
}

export interface ChatRequest {
  messages: ChatMessage[];
  user_location?: string;
  coordinates?: { latitude: number; longitude: number };
  language_preference?: string;
  session_id?: string;
}

export interface ToolCallLog {
  tool_name: string;
  arguments: Record<string, any>;
  status: string;
  execution_time_ms: number;
}

export interface ChatResponse {
  response_message: ChatMessage;
  session_id: string;
  referenced_weather_data?: Record<string, any>;
  referenced_alerts?: Record<string, any>[];
  tools_used: string[];
  tool_execution_logs: ToolCallLog[];
}
