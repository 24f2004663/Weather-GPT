from typing import Dict, Tuple

# WMO Weather interpretation codes (WW) mapping
# Format: code -> (Condition Name, Short Description, Icon Category)
WMO_CODE_MAP: Dict[int, Tuple[str, str, str]] = {
    0: ("Clear Sky", "Cloud development not observed or not observable", "clear-day"),
    1: ("Mainly Clear", "Clouds generally dissolving or becoming less developed", "mainly-clear"),
    2: ("Partly Cloudy", "State of sky on the whole unchanged", "partly-cloudy"),
    3: ("Overcast", "Clouds generally forming or developing", "overcast"),
    45: ("Fog", "Fog or ice fog, sky visible", "fog"),
    48: ("Depositing Rime Fog", "Fog or ice fog, sky invisible", "fog"),
    51: ("Light Drizzle", "Drizzle, not freezing, slight", "drizzle"),
    53: ("Moderate Drizzle", "Drizzle, not freezing, moderate", "drizzle"),
    55: ("Dense Drizzle", "Drizzle, not freezing, dense", "drizzle"),
    56: ("Light Freezing Drizzle", "Drizzle, freezing, slight", "freezing-drizzle"),
    57: ("Dense Freezing Drizzle", "Drizzle, freezing, dense", "freezing-drizzle"),
    61: ("Slight Rain", "Rain, not freezing, intermittent, slight", "rain-light"),
    63: ("Moderate Rain", "Rain, not freezing, continuous, moderate", "rain-moderate"),
    65: ("Heavy Rain", "Rain, not freezing, continuous, heavy", "rain-heavy"),
    66: ("Light Freezing Rain", "Rain, freezing, slight", "freezing-rain"),
    67: ("Heavy Freezing Rain", "Rain, freezing, heavy", "freezing-rain"),
    71: ("Slight Snow Fall", "Snow flakes, slight", "snow-light"),
    73: ("Moderate Snow Fall", "Snow flakes, moderate", "snow-moderate"),
    75: ("Heavy Snow Fall", "Snow flakes, heavy", "snow-heavy"),
    77: ("Snow Grains", "Snow grains with or without fog", "snow"),
    80: ("Slight Rain Showers", "Rain shower(s), slight", "rain-showers"),
    81: ("Moderate Rain Showers", "Rain shower(s), moderate", "rain-showers"),
    82: ("Violent Rain Showers", "Rain shower(s), violent", "rain-showers-heavy"),
    85: ("Slight Snow Showers", "Snow shower(s), slight", "snow-showers"),
    86: ("Heavy Snow Showers", "Snow shower(s), heavy", "snow-showers"),
    95: ("Thunderstorm", "Thunderstorm, slight or moderate, without hail", "thunderstorm"),
    96: ("Thunderstorm with Slight Hail", "Thunderstorm with slight hail", "thunderstorm-hail"),
    99: ("Thunderstorm with Heavy Hail", "Thunderstorm with heavy hail", "thunderstorm-hail"),
}

def decode_wmo_code(code: int) -> Tuple[str, str, str]:
    """
    Returns (condition_name, description, icon_key) for any WMO code with safe fallback.
    """
    return WMO_CODE_MAP.get(code, ("Unknown", f"Weather code {code}", "cloudy"))
