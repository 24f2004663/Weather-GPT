"""
Live Weather Provider Smoke Test Module.
Verifies external connectivity to Open-Meteo and NASA POWER when internet access is present.
"""
import asyncio
from backend.services.weather.open_meteo import open_meteo_provider
from backend.services.weather.nasa_power import nasa_power_provider

async def run_live_provider_smoke_tests():
    print("=" * 65)
    print("WEATHERGPT PHASE 2/3 — LIVE WEATHER PROVIDER SMOKE TEST")
    print("=" * 65)

    # 1. Open-Meteo Geocoding
    print("\n1. Testing Open-Meteo Geocoding ('Chennai')...")
    try:
        locs = await open_meteo_provider.resolve_location("Chennai", count=1)
        if locs:
            print(f"  SUCCESS: Found {locs[0].name} ({locs[0].latitude}, {locs[0].longitude})")
        else:
            print("  NO RESULTS")
    except Exception as e:
        print(f"  OFFLINE / ISOLATED: {type(e).__name__}: {str(e)}")

    # 2. Open-Meteo Forecast
    print("\n2. Testing Open-Meteo Forecast (13.08, 80.27)...")
    try:
        w_data = await open_meteo_provider.get_forecast(lat=13.08, lon=80.27, days=3)
        print(f"  SUCCESS: Current Temp: {w_data.current.temperature_c}°C, Daily Days: {len(w_data.daily)}")
    except Exception as e:
        print(f"  OFFLINE / ISOLATED: {type(e).__name__}: {str(e)}")

    # 3. NASA POWER Climatology
    print("\n3. Testing NASA POWER Climatology (13.08, 80.27)...")
    try:
        c_data = await nasa_power_provider.get_climatology(lat=13.08, lon=80.27)
        print(f"  SUCCESS: Annual Avg T2M: {c_data.annual_averages.get('T2M')}°C")
    except Exception as e:
        print(f"  OFFLINE / ISOLATED: {type(e).__name__}: {str(e)}")

    print("\n" + "=" * 65)

if __name__ == "__main__":
    asyncio.run(run_live_provider_smoke_tests())
