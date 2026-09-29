'use client';

import React from 'react';
import {
  Sun,
  Moon,
  CloudSun,
  CloudMoon,
  Cloud,
  Cloudy,
  CloudFog,
  CloudDrizzle,
  CloudRain,
  CloudRainWind,
  CloudLightning,
  CloudSnow,
  type LucideIcon,
} from 'lucide-react';

/**
 * Single source of truth for weather glyphs.
 *
 * Replaces the emoji the components used to inline. Emoji render differently on every
 * platform, cannot be recoloured to follow the theme, and carry no accessible name;
 * a line icon inherits currentColor and sizes predictably against the type.
 */
const DAY_ICONS: Record<string, LucideIcon> = {
  'clear-day': Sun,
  'mainly-clear': CloudSun,
  'partly-cloudy': CloudSun,
  overcast: Cloudy,
  fog: CloudFog,
  drizzle: CloudDrizzle,
  'rain-light': CloudRain,
  'rain-moderate': CloudRain,
  'rain-heavy': CloudRainWind,
  'rain-showers': CloudRain,
  thunderstorm: CloudLightning,
  'thunderstorm-hail': CloudLightning,
  snow: CloudSnow,
  'snow-light': CloudSnow,
  'snow-heavy': CloudSnow,
};

/** Only the clear/partly-clear states have a distinct night form; rain looks the same. */
const NIGHT_OVERRIDES: Record<string, LucideIcon> = {
  'clear-day': Moon,
  'clear-night': Moon,
  'mainly-clear': CloudMoon,
  'partly-cloudy': CloudMoon,
};

export function resolveWeatherIcon(iconKey?: string, isDay: boolean = true): LucideIcon {
  if (!iconKey) return Cloud;
  if (!isDay && NIGHT_OVERRIDES[iconKey]) return NIGHT_OVERRIDES[iconKey];
  return DAY_ICONS[iconKey] ?? Cloud;
}

interface WeatherIconProps {
  iconKey?: string;
  isDay?: boolean;
  /** Pixel size; matches lucide's own `size` prop. */
  size?: number;
  className?: string;
  /** Accessible name. Omit for a purely decorative glyph sitting beside its own label. */
  label?: string;
}

export default function WeatherIcon({
  iconKey,
  isDay = true,
  size = 24,
  className = '',
  label,
}: WeatherIconProps) {
  const Icon = resolveWeatherIcon(iconKey, isDay);
  return (
    <Icon
      size={size}
      className={className}
      strokeWidth={1.5}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'img' : undefined}
    />
  );
}
