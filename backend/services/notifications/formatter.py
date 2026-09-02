from typing import Dict, Any, Optional
from backend.schemas.alerts import DisasterAlert

def format_whatsapp_alert(alert: DisasterAlert, language: str = "en") -> str:
    """Formats an official disaster alert for WhatsApp delivery in preferred language."""
    time_str = alert.issued_time.strftime("%d %b %Y, %H:%M UTC") if alert.issued_time else "Immediate"
    
    if language == "hi":
        return (
            f"🚨 *WeatherGPT आधिकारिक आपदा चेतावनी*\n\n"
            f"⚠️ *आपदा प्रकार:* {alert.event_type}\n"
            f"🔴 *तीव्रता:* {alert.severity.value}\n"
            f"📍 *प्रभावित क्षेत्र:* {alert.affected_area}\n"
            f"⏱️ *समय:* {time_str}\n"
            f"🛡️ *आधिकारिक सुरक्षा निर्देश:* {alert.instruction or 'सुरक्षित स्थान पर रहें।'}\n\n"
            f"🏛️ *स्रोत:* SACHET / NDMA (आधिकारिक राष्ट्रीय फ़ीड)\n\n"
            f"🌐 *वेबसाइट:* https://weather-gpt-team-layers.vercel.app/"
        )
    elif language == "ta":
        return (
            f"🚨 *WeatherGPT அதிகாரப்பூர்வ பேரிடர் எச்சரிக்கை*\n\n"
            f"⚠️ *பேரிடர்:* {alert.event_type}\n"
            f"🔴 *தீவிரம்:* {alert.severity.value}\n"
            f"📍 *பாதிக்கப்பட்ட பகுதி:* {alert.affected_area}\n"
            f"⏱️ *நேரம்:* {time_str}\n"
            f"🛡️ *அதிகாரப்பூர்வ வழிகாட்டல்:* {alert.instruction or 'பாதுகாப்பான இடங்களில் இருக்கவும்.'}\n\n"
            f"🏛️ *மூலம்:* SACHET / NDMA\n\n"
            f"🌐 *வலைத்தளம்:* https://weather-gpt-team-layers.vercel.app/"
        )
    elif language == "te":
        return (
            f"🚨 *WeatherGPT అధికారిక విపత్తు హెచ్చరిక*\n\n"
            f"⚠️ *విపత్తు:* {alert.event_type}\n"
            f"🔴 *తీవ్రత:* {alert.severity.value}\n"
            f"📍 *ప్రభావిత ప్రాంతం:* {alert.affected_area}\n"
            f"⏱️ *సమయం:* {time_str}\n"
            f"🛡️ *రక్షణ సూచనలు:* {alert.instruction or 'సురక్షిత ప్రదేశాల్లో ఉండండి.'}\n\n"
            f"🏛️ *మూలం:* SACHET / NDMA\n\n"
            f"🌐 *వెబ్‌సైట్:* https://weather-gpt-team-layers.vercel.app/"
        )
    elif language == "bn":
        return (
            f"🚨 *WeatherGPT সরকারি দুর্যোগ সতর্কতা*\n\n"
            f"⚠️ *দুর্যোগ:* {alert.event_type}\n"
            f"🔴 *তীব্রতা:* {alert.severity.value}\n"
            f"📍 *প্রভাবিত এলাকা:* {alert.affected_area}\n"
            f"⏱️ *সময়:* {time_str}\n"
            f"🛡️ *সরকারি নির্দেশিকা:* {alert.instruction or 'নিরাপদ স্থানে আশ্রয় নিন।'}\n\n"
            f"🏛️ *উৎস:* SACHET / NDMA\n\n"
            f"🌐 *ওয়েবসাইট:* https://weather-gpt-team-layers.vercel.app/"
        )
    else: # Default English
        return (
            f"🚨 *WEATHERGPT OFFICIAL DISASTER ALERT*\n\n"
            f"⚠️ *Hazard:* {alert.event_type}\n"
            f"🔴 *Severity:* {alert.severity.value.upper()}\n"
            f"📍 *Affected Area:* {alert.affected_area}\n"
            f"⏱️ *Issued:* {time_str}\n"
            f"🛡️ *Official Instruction:* {alert.instruction or 'Please follow local emergency management directives.'}\n\n"
            f"🏛️ *Source:* SACHET / NDMA (Official Emergency Feed)\n\n"
            f"🌐 *Live Dashboard:* https://weather-gpt-team-layers.vercel.app/"
        )

def format_sms_alert(alert: DisasterAlert, language: str = "en") -> str:
    """Formats a concise disaster alert for SMS delivery (character-constrained)."""
    if language == "hi":
        return f"[WeatherGPT आपदा अलर्ट] {alert.event_type} ({alert.severity.value}) - {alert.affected_area}. निर्देश: {alert.instruction or 'सुरक्षित रहें।'} स्रोत: NDMA"
    elif language == "ta":
        return f"[WeatherGPT எச்சரிக்கை] {alert.event_type} ({alert.severity.value}) - {alert.affected_area}. {alert.instruction or 'பாதுகாப்பாக இருங்கள்.'} மூலம்: NDMA"
    elif language == "te":
        return f"[WeatherGPT హెచ్చరిక] {alert.event_type} ({alert.severity.value}) - {alert.affected_area}. {alert.instruction or 'సురక్షితంగా ఉండండి.'} మూలం: NDMA"
    elif language == "bn":
        return f"[WeatherGPT সতর্কতা] {alert.event_type} ({alert.severity.value}) - {alert.affected_area}. {alert.instruction or 'নিরাপদে থাকুন।'} উৎস: NDMA"
    else:
        return f"[WeatherGPT Alert] {alert.event_type} ({alert.severity.value.upper()}) for {alert.affected_area}. Action: {alert.instruction or 'Stay in secure shelters.'} Source: SACHET/NDMA"

def format_voice_script(alert: DisasterAlert, language: str = "en") -> str:
    """Formats spoken script for emergency Voice/IVR call."""
    if language == "hi":
        return f"यह वेदर जीपीटी की आधिकारिक आपदा चेतावनी है। {alert.affected_area} के लिए {alert.event_type} की {alert.severity.value} चेतावनी जारी की गई है। कृपया निर्देश का पालन करें: {alert.instruction or 'सुरक्षित स्थान पर रहें।'} स्रोत: एन डी एम ए।"
    else:
        return f"This is an official WeatherGPT emergency disaster bulletin. An official {alert.event_type} alert of {alert.severity.value} severity has been issued for {alert.affected_area}. Official instruction: {alert.instruction or 'Follow local emergency guidelines and stay in secure shelters.'} Source: SACHET NDMA."
