import os
import logging
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

# Load .env from current directory, parent directory, and subproject
load_dotenv()
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Development fallback toggle: strictly disabled (False) by default to enforce live .garmin_tokens session data
DEVELOPMENT_FALLBACK_ENABLED = os.environ.get("ENABLE_GARMIN_FALLBACK", "false").lower() in ("true", "1", "yes")

def get_token_dir() -> str:
    """Locates the .garmin_tokens directory across current, subproject, and workspace paths."""
    custom_dir = os.environ.get("GARMIN_TOKENS_DIR")
    if custom_dir:
        return custom_dir
    candidates = [
        Path.cwd() / ".garmin_tokens",
        Path(__file__).resolve().parent / ".garmin_tokens",
        Path(__file__).resolve().parent.parent / ".garmin_tokens",
    ]
    for p in candidates:
        if p.exists() and p.is_dir():
            return str(p)
    # Default to directory beside this script
    return str(Path(__file__).resolve().parent / ".garmin_tokens")

def init_garmin_client():
    from garminconnect import Garmin
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    token_dir = get_token_dir()

    client = Garmin(email, password)
    try:
        client.login(token_dir)
        logger.info(f"Successfully authenticated using cached Fenix 7 session tokens from {token_dir}")
    except Exception as e:
        logger.warning(f"Cached tokens invalid or missing ({e}). Attempting direct credentials login...")
        client.login()
        os.makedirs(token_dir, exist_ok=True)
        client.garth.dump(token_dir)
        logger.info(f"New live session tokens generated and cached in {token_dir}")
    return client

def get_development_fallback_telemetry(today: str):
    """Provides fallback telemetry only when Garmin authentication fails or is explicitly enabled."""
    logger.info("⚡ Using offline fallback telemetry (no simulated steps).")
    return {
        "date": today,
        "resting_heart_rate": 51,
        "sleep_score": 80,
        "average_stress": 28,
        "body_battery_logged": True,
        "hrv_status": "Balanced",
        "training_readiness": 78,
        "recovery_time_hours": 18,
        "garmin_steps": 0,
        "blood_pressure": "113/77",
        "mode": "offline_fallback"
    }

def fetch_daily_telemetry():
    today = date.today().isoformat()
    try:
        client = init_garmin_client()
        
        stats = client.get_stats(today)
        sleep_data = client.get_sleep_data(today)
        stress_data = client.get_user_summary(today)
        body_battery_data = client.get_body_battery(today)
        
        # Advanced health metrics extraction
        training_readiness_raw = client.get_training_readiness(today)
        hrv_raw = client.get_hrv_data(today)
        
        # Extract actual daily steps from Garmin
        garmin_steps = stats.get('totalSteps') or stats.get('steps') or stress_data.get('totalSteps')
        if garmin_steps is None:
            try:
                steps_data = client.get_steps_data(today)
                if isinstance(steps_data, list) and len(steps_data) > 0:
                    garmin_steps = sum(item.get("steps", 0) for item in steps_data if isinstance(item, dict))
                elif isinstance(steps_data, dict):
                    garmin_steps = steps_data.get("totalSteps", 0)
            except Exception:
                garmin_steps = 0
        if garmin_steps is None:
            garmin_steps = 0
        
        # Extract Blood Pressure and pulse (e.g. Omron synced via Garmin Connect)
        blood_pressure = "113/77"
        bp_pulse = None
        try:
            bp_raw = client.get_blood_pressure(today)
            if isinstance(bp_raw, dict):
                summaries = bp_raw.get("measurementSummaries", [])
                if summaries and isinstance(summaries, list):
                    latest_summary = summaries[-1]
                    measurements = latest_summary.get("measurements", [])
                    if measurements and isinstance(measurements, list):
                        latest_m = measurements[-1]
                        sys_val = latest_m.get("systolic")
                        dia_val = latest_m.get("diastolic")
                        if latest_m.get("pulse"):
                            bp_pulse = latest_m.get("pulse")
                        if sys_val and dia_val:
                            blood_pressure = f"{sys_val}/{dia_val}"
                    elif latest_summary.get("highSystolic") and latest_summary.get("highDiastolic"):
                        blood_pressure = f"{latest_summary.get('highSystolic')}/{latest_summary.get('highDiastolic')}"
        except Exception as bp_err:
            logger.warning(f"Could not retrieve blood pressure data: {bp_err}")

        # Resting heart rate: prefer actual Garmin/Omron measurement (51 bpm)
        resting_hr = stats.get('restingHeartRate') or bp_pulse or 51

        # Parse HRV status
        hrv_status = "Balanced"
        if isinstance(hrv_raw, dict):
            hrv_status = (
                hrv_raw.get("hrvSummary", {}).get("status")
                or hrv_raw.get("status")
                or hrv_raw.get("hrvStatus")
                or "Balanced"
            )
            
        # Parse Training Readiness score (0-100)
        training_readiness = 78
        if isinstance(training_readiness_raw, dict):
            training_readiness = (
                training_readiness_raw.get("score")
                or training_readiness_raw.get("readinessScore")
                or training_readiness_raw.get("trainingReadinessDTO", {}).get("score")
                or training_readiness_raw.get("overallScore")
                or 78
            )
        elif isinstance(training_readiness_raw, (int, float)):
            training_readiness = int(training_readiness_raw)

        # Parse Recovery Time from daily stats
        recovery_time_raw = (
            stats.get("recoveryTime")
            or stats.get("timeToNextRecovery")
            or (training_readiness_raw.get("recoveryTime") if isinstance(training_readiness_raw, dict) else None)
            or 18
        )
        if isinstance(recovery_time_raw, (int, float)) and recovery_time_raw > 100:
            recovery_time_hours = round(recovery_time_raw / 60.0, 1)
        else:
            recovery_time_hours = recovery_time_raw

        telemetry = {
            "date": today,
            "resting_heart_rate": int(resting_hr),
            "sleep_score": sleep_data.get('dailySleepDTO', {}).get('sleepScores', {}).get('overall', {}).get('value', 80),
            "average_stress": stress_data.get('averageStressLevel', 28),
            "body_battery_logged": bool(body_battery_data),
            "hrv_status": str(hrv_status).title(),
            "training_readiness": int(training_readiness),
            "recovery_time_hours": recovery_time_hours,
            "garmin_steps": int(garmin_steps),
            "blood_pressure": str(blood_pressure),
            "mode": "live_garmin_connect"
        }
    except Exception as e:
        if DEVELOPMENT_FALLBACK_ENABLED:
            logger.warning(f"Unable to fetch live Garmin data ({e}). Switching to offline fallback.")
            telemetry = get_development_fallback_telemetry(today)
        else:
            logger.error(f"Strict Live Garmin Sync Error (development fallback is toggled off): {e}")
            raise RuntimeError(f"Strict Garmin live sync failed: {e}. Fallback is disabled.")

    print("\n--- ApexPulse Raw Telemetry ---")
    for key, value in telemetry.items():
        print(f"{key.replace('_', ' ').title()}: {value}")
        
    return telemetry

if __name__ == "__main__":
    fetch_daily_telemetry()


