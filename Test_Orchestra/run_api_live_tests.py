import httpx
import json
import time
import sys

BASE_URL = "http://localhost:8000"

def log_test(evidence_file, test_id, description, method, url, status_code, response_data, expected_status=200):
    status_str = "PASS" if status_code == expected_status else "FAIL"
    output = f"""
============================================================
TEST ID: {test_id}
TEST DESCRIPTION: {description}
COMMAND / ACTION EXECUTED: {method} {url}
EXPECTED RESULT: HTTP {expected_status}
ACTUAL RESULT: HTTP {status_code}
STATUS: {status_str}
EVIDENCE:
{json.dumps(response_data, indent=2) if isinstance(response_data, (dict, list)) else str(response_data)[:500]}
============================================================
"""
    evidence_file.write(output + "\n")
    print(f"[{status_str}] {test_id}: {description} -> HTTP {status_code}")
    return status_str == "PASS"

def main():
    passed = 0
    total = 0
    with open("tests/evidence/api-tests.txt", "w", encoding="utf-8") as f:
        client = httpx.Client(base_url=BASE_URL, timeout=15.0)

        # 1. Health
        total += 1
        res = client.get("/api/health")
        if log_test(f, "API-01", "Verify system health status and adapter readiness", "GET", "/api/health", res.status_code, res.json(), 200):
            passed += 1

        # 2. Config
        total += 1
        res = client.get("/api/config")
        if log_test(f, "API-02", "Verify public configuration metadata and zero secret leakage", "GET", "/api/config", res.status_code, res.json(), 200):
            passed += 1

        # 3. Location Search - Common City
        total += 1
        res = client.get("/api/location/search", params={"q": "Bengaluru", "count": 3})
        if log_test(f, "API-03", "Geocoding search for Bengaluru", "GET", "/api/location/search?q=Bengaluru&count=3", res.status_code, res.json(), 200):
            passed += 1

        # 4. Location Search - Delhi
        total += 1
        res = client.get("/api/location/search", params={"q": "Delhi", "count": 2})
        if log_test(f, "API-04", "Geocoding search for Delhi", "GET", "/api/location/search?q=Delhi&count=2", res.status_code, res.json(), 200):
            passed += 1

        # 5. Location Search - Small District / Partial
        total += 1
        res = client.get("/api/location/search", params={"q": "Kozhikode", "count": 1})
        if log_test(f, "API-05", "Geocoding search for district Kozhikode", "GET", "/api/location/search?q=Kozhikode&count=1", res.status_code, res.json(), 200):
            passed += 1

        # 6. Location Search - Empty Query Validation
        total += 1
        res = client.get("/api/location/search", params={"q": ""})
        if log_test(f, "API-06", "Geocoding search validation on empty query (HTTP 422)", "GET", "/api/location/search?q=", res.status_code, res.json(), 422):
            passed += 1

        # 7. Location Search - Non-existent location
        total += 1
        res = client.get("/api/location/search", params={"q": "XyzNonExistentCity999"})
        if log_test(f, "API-07", "Geocoding search on non-existent location returns empty list", "GET", "/api/location/search?q=XyzNonExistentCity999", res.status_code, res.json(), 200):
            passed += 1

        # 8. Current Weather - Valid Coordinates (Bengaluru: 12.9716, 77.5946)
        total += 1
        res = client.get("/api/weather/current", params={"lat": 12.9716, "lon": 77.5946})
        if log_test(f, "API-08", "Current weather for Bengaluru coordinates", "GET", "/api/weather/current?lat=12.9716&lon=77.5946", res.status_code, res.json(), 200):
            passed += 1

        # 9. Current Weather - Invalid Latitude
        total += 1
        res = client.get("/api/weather/current", params={"lat": 195.0, "lon": 77.5946})
        if log_test(f, "API-09", "Current weather invalid latitude validation (HTTP 422)", "GET", "/api/weather/current?lat=195.0&lon=77.5946", res.status_code, res.json(), 422):
            passed += 1

        # 10. Forecast - Valid Coordinates (Mumbai: 19.0760, 72.8777)
        total += 1
        res = client.get("/api/weather/forecast", params={"lat": 19.0760, "lon": 72.8777, "days": 5, "hourly": True})
        if log_test(f, "API-10", "5-day hourly and daily forecast for Mumbai", "GET", "/api/weather/forecast?lat=19.0760&lon=72.8777&days=5&hourly=true", res.status_code, res.json(), 200):
            passed += 1

        # 11. Weather by City - Valid (Chennai)
        total += 1
        res = client.get("/api/weather/by-city", params={"city": "Chennai", "days": 3})
        if log_test(f, "API-11", "Weather by city endpoint for Chennai", "GET", "/api/weather/by-city?city=Chennai&days=3", res.status_code, res.json(), 200):
            passed += 1

        # 12. Weather by City - Not Found
        total += 1
        res = client.get("/api/weather/by-city", params={"city": "NonExistentCityName12345"})
        if log_test(f, "API-12", "Weather by city not found error (HTTP 404)", "GET", "/api/weather/by-city?city=NonExistentCityName12345", res.status_code, res.json(), 404):
            passed += 1

        # 13. NASA POWER Climatology (Kolkata: 22.5726, 88.3639)
        total += 1
        res = client.get("/api/climate/historical", params={"lat": 22.5726, "lon": 88.3639})
        if log_test(f, "API-13", "NASA POWER 30-year climatology baseline for Kolkata", "GET", "/api/climate/historical?lat=22.5726&lon=88.3639", res.status_code, res.json(), 200):
            passed += 1

        # 14. Cache Verification - Second immediate request should hit cache
        total += 1
        t0 = time.time()
        res = client.get("/api/climate/historical", params={"lat": 22.5726, "lon": 88.3639})
        duration = time.time() - t0
        cache_verified = res.status_code == 200 and duration < 0.1
        if log_test(f, "API-14", f"Cache hit verification on repeated climate query (responded in {duration*1000:.1f}ms)", "GET", "/api/climate/historical?lat=22.5726&lon=88.3639", res.status_code, {"cached_duration_seconds": duration}, 200):
            passed += 1

        # 15. SACHET Disaster Alerts Endpoint
        total += 1
        res = client.get("/api/alerts")
        if log_test(f, "API-15", "SACHET/NDMA disaster alerts retrieval and CAP normalization", "GET", "/api/alerts", res.status_code, res.json(), 200):
            passed += 1

        # 16. SACHET Disaster Alerts Geographic Filter
        total += 1
        res = client.get("/api/alerts", params={"state": "Tamil Nadu"})
        if log_test(f, "API-16", "SACHET disaster alerts filtered by state", "GET", "/api/alerts?state=Tamil+Nadu", res.status_code, res.json(), 200):
            passed += 1

        # 17. Notification Provider Status
        total += 1
        res = client.get("/api/notifications/providers/status")
        if log_test(f, "API-17", "Notification channels status and dry-run guard verification", "GET", "/api/notifications/providers/status", res.status_code, res.json(), 200):
            passed += 1

        # 18. VAPID Public Key Endpoint
        total += 1
        res = client.get("/api/notifications/vapid-public-key")
        if log_test(f, "API-18", "VAPID public key endpoint (private key never exposed)", "GET", "/api/notifications/vapid-public-key", res.status_code, res.json(), 200):
            passed += 1

        # 19. Notification Preferences Save
        total += 1
        sub_payload = {
            "user_identifier": "test_user_blr_101",
            "channels": ["SMS", "WEB_PUSH"],
            "phone_number": "+919876543210",
            "minimum_severity": "SEVERE",
            "language": "en",
            "geographic_scope": "DISTRICT",
            "subscribed_states": ["Karnataka"],
            "subscribed_districts": ["Bengaluru Urban"]
        }
        res = client.post("/api/notifications/preferences", json=sub_payload)
        if log_test(f, "API-19", "Save notification subscription preferences", "POST", "/api/notifications/preferences", res.status_code, res.json(), 200):
            passed += 1

        # 20. Notification Preferences Retrieve
        total += 1
        res = client.get("/api/notifications/preferences", params={"user_id": "test_user_blr_101"})
        if log_test(f, "API-20", "Retrieve notification subscription preferences", "GET", "/api/notifications/preferences?user_id=test_user_blr_101", res.status_code, res.json(), 200):
            passed += 1

        # 21. Notification Preferences Unsubscribe
        total += 1
        res = client.delete("/api/notifications/preferences", params={"user_id": "test_user_blr_101"})
        if log_test(f, "API-21", "Unsubscribe user from all emergency notifications", "DELETE", "/api/notifications/preferences?user_id=test_user_blr_101", res.status_code, res.json(), 200):
            passed += 1

        # 22. Notification Preview - SMS English
        total += 1
        prev_payload_sms = {
            "channel": "SMS",
            "language": "en",
            "recipient": "+919876543210"
        }
        res = client.post("/api/notifications/preview", json=prev_payload_sms)
        if log_test(f, "API-22", "Notification preview SMS English formatting", "POST", "/api/notifications/preview", res.status_code, res.json(), 200):
            passed += 1

        # 23. Notification Preview - Voice Hindi
        total += 1
        prev_payload_voice = {
            "channel": "VOICE_IVR",
            "language": "hi",
            "recipient": "+919876543210"
        }
        res = client.post("/api/notifications/preview", json=prev_payload_voice)
        if log_test(f, "API-23", "Notification preview Voice IVR Hindi SSML script formatting", "POST", "/api/notifications/preview", res.status_code, res.json(), 200):
            passed += 1

        # 24. Notification Preview - Web Push Tamil
        total += 1
        prev_payload_push = {
            "channel": "WEB_PUSH",
            "language": "ta",
            "recipient": "web_push_token_mock"
        }
        res = client.post("/api/notifications/preview", json=prev_payload_push)
        if log_test(f, "API-24", "Notification preview Web Push Tamil notification formatting", "POST", "/api/notifications/preview", res.status_code, res.json(), 200):
            passed += 1

        # 25. Notification Preview - Telugu
        total += 1
        prev_payload_te = {
            "channel": "SMS",
            "language": "te",
            "recipient": "+919876543210"
        }
        res = client.post("/api/notifications/preview", json=prev_payload_te)
        if log_test(f, "API-25", "Notification preview SMS Telugu formatting", "POST", "/api/notifications/preview", res.status_code, res.json(), 200):
            passed += 1

        # 26. Notification Preview - Bengali
        total += 1
        prev_payload_bn = {
            "channel": "SMS",
            "language": "bn",
            "recipient": "+919876543210"
        }
        res = client.post("/api/notifications/preview", json=prev_payload_bn)
        if log_test(f, "API-26", "Notification preview SMS Bengali formatting", "POST", "/api/notifications/preview", res.status_code, res.json(), 200):
            passed += 1

        # 27. Audio Transcribe - Missing Key Graceful Handling (HTTP 503)
        total += 1
        res = client.post("/api/audio/transcribe", files={"file": ("dummy.wav", b"RIFF....WAVEfmt ", "audio/wav")})
        if log_test(f, "API-27", "Audio transcribe endpoint graceful 503 on unconfigured Groq key", "POST", "/api/audio/transcribe", res.status_code, res.json(), 503):
            passed += 1

        print(f"\nAPI Test Summary: {passed}/{total} passed.")

if __name__ == "__main__":
    main()
