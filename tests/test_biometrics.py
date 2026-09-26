import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from garmin_sync import get_development_fallback_telemetry
from app.agent import (
    STATIC_PROFILE,
    FIRESTORE_BIOMETRICS,
    STEP_LOGS,
    calculate_age_from_dob,
    log_weight,
    get_user_biometric_profile,
    calculate_protein_targets,
    get_step_summary,
    get_workout_and_fasting_summary,
    display_step_summary_card,
    log_steps,
    log_cycling_session,
    delete_workout_record,
    google_search_live,
    get_garmin_telemetry,
    fetch_youtube_video,
    sync_garmin_steps_to_db,
    root_agent,
)


def test_offline_fallback_telemetry():
    fallback = get_development_fallback_telemetry("2026-09-26")
    assert fallback["mode"] == "offline_fallback"
    assert fallback["garmin_steps"] == 0  # Decoupled from 8450 simulated steps
    assert fallback["resting_heart_rate"] == 51
    assert fallback["sleep_score"] == 80
    assert fallback["blood_pressure"] == "113/77"


def test_calculate_age_from_dob():
    # DOB: December 12, 1966
    computed_age = calculate_age_from_dob("1966-12-12")
    assert computed_age == 59
    # Test boundary calculations
    assert calculate_age_from_dob("2000-01-01") >= 26


def test_static_profile_baselines():
    expected_age = calculate_age_from_dob("1966-12-12")
    assert STATIC_PROFILE["age"] == expected_age
    assert STATIC_PROFILE["dob"] == "1966-12-12"
    assert STATIC_PROFILE["height"] == "5'5\""
    assert STATIC_PROFILE["height_inches"] == 65
    assert STATIC_PROFILE["height_cm"] == 165.1


def test_log_weight_dynamic_tool_call():
    # Simulated Tool Call: Logging dynamic weight of 200 lbs to Firestore
    res = log_weight(weight_lbs=200.0, notes="Baseline weight recorded via simulated tool call")
    assert res["status"] == "success"
    assert res["current_weight_lbs"] == 200.0
    assert res["bmi"] == 33.3
    assert res["static_age"] == 59
    assert res["static_height"] == "5'5\""
    assert res["daily_protein_target_g"] == 200
    assert res["firestore_document"] == "users/user_profile/biometrics"
    assert FIRESTORE_BIOMETRICS["current_weight_lbs"] == 200.0


def test_get_user_biometric_profile():
    profile = get_user_biometric_profile()
    assert profile["static_baselines"]["age"] == 59
    assert profile["static_baselines"]["dob"] == "1966-12-12"
    assert profile["static_baselines"]["height"] == "5'5\""
    assert profile["dynamic_firestore_metrics"]["current_weight_lbs"] == 200.0
    assert profile["dynamic_firestore_metrics"]["bmi"] == 33.3
    assert len(profile["age_and_biometric_guidance"]) > 0


def test_calculate_protein_targets_with_dynamic_weight():
    # Calling without args should use the dynamic weight in Firestore (200 lbs)
    res = calculate_protein_targets()
    assert res["body_weight_lbs"] == 200.0
    assert res["daily_protein_target_grams"] == 200
    assert res["user_age"] == 59
    assert res["target_protein_per_meal_grams"] == 67
    assert res["leucine_threshold_met"] is True


def test_agent_toolset():
    tool_names = [getattr(t, "__name__", getattr(t, "name", str(t))) for t in root_agent.tools]
    assert "log_weight" in tool_names
    assert "get_user_biometric_profile" in tool_names
    assert "log_steps" in tool_names
    assert "delete_workout_record" in tool_names
    assert "display_step_summary_card" in tool_names
    assert "google_search_live" in tool_names
    assert "get_garmin_telemetry" in tool_names
    assert "fetch_youtube_video" in tool_names


def test_delete_workout_record():
    # 1. Log a cycling session and step entry
    log_cycling_session(duration_minutes=45, target_zone="Zone 2", avg_power_watts=175, avg_cadence_rpm=88)
    log_steps(steps=8450)
    
    # 2. Execute deletion
    del_res = delete_workout_record(uid="test_user", record_type="indoor_cycling", date="today")
    assert del_res["status"] == "success"
    assert "indoor_cycling" in del_res["record_type"]

    del_steps = delete_workout_record(uid="test_user", record_type="steps", date="today")
    assert del_steps["status"] == "success"


def test_garmin_telemetry():
    telemetry = get_garmin_telemetry()
    assert "resting_heart_rate" in telemetry
    assert "sleep_score" in telemetry
    assert "average_stress" in telemetry
    assert "hrv_status" in telemetry
    assert "training_readiness" in telemetry
    assert "recovery_time_hours" in telemetry
    assert "garmin_steps" in telemetry
    assert "blood_pressure" in telemetry
    assert telemetry["garmin_steps"] >= 0
    assert "/" in telemetry["blood_pressure"]
    assert telemetry["hrv_status"] in ["Balanced", "Unbalanced", "Low", "Poor"]
    assert 0 <= telemetry["training_readiness"] <= 100


def test_step_card_and_hybrid_tracking():
    # 1. Test live Garmin default
    telemetry = get_garmin_telemetry()
    garmin_steps = telemetry.get("garmin_steps", 0)

    step_sum = get_step_summary(force_garmin_sync=True)
    assert step_sum["daily"]["steps"] == garmin_steps
    assert step_sum["daily"]["source"] == "garmin_fenix_7_live"

    # 2. Test A2UI Step Card: verify hardcoded 7-Day & Year-to-Date placeholders are removed
    card_json = display_step_summary_card()
    card_data = json.loads(card_json)
    assert isinstance(card_data, list)
    assert len(card_data) == 2
    assert card_data[0]["beginRendering"]["root"] == "step_card_root"
    
    # Inspect component IDs inside surfaceUpdate
    components = card_data[1]["surfaceUpdate"]["components"]
    component_ids = [c["id"] for c in components]
    assert "title_text" in component_ids
    assert "daily_header" in component_ids
    assert "daily_text" in component_ids
    assert "source_text" in component_ids
    assert "weekly_header" not in component_ids
    assert "weekly_text" not in component_ids
    assert "yearly_header" not in component_ids
    assert "yearly_text" not in component_ids

    # 3. Test Manual Step Override
    manual_res = log_steps(steps=5000)
    assert manual_res["status"] == "success"
    assert manual_res["steps_logged"] == 5000
    assert manual_res["total_steps_today"] == 5000
    assert manual_res["source"] == "manual_entry"

    # Verify summary preserves manual override when not forced
    step_sum_manual = get_step_summary(force_garmin_sync=False)
    assert step_sum_manual["daily"]["steps"] == 5000
    assert step_sum_manual["daily"]["source"] == "manual_entry"

    # 4. Clean up / sync back to live telemetry
    step_sum_revert = get_step_summary(force_garmin_sync=True)
    assert step_sum_revert["daily"]["steps"] == garmin_steps
    assert step_sum_revert["daily"]["source"] == "garmin_fenix_7_live"


def test_fetch_youtube_video():
    tgu_url = fetch_youtube_video("Turkish Get-Up")
    assert "youtube.com" in tgu_url
    assert "watch?v=" in tgu_url or "results?search_query=" in tgu_url
    squat_url = fetch_youtube_video("Goblet Squat with pause")
    assert "youtube.com" in squat_url


def test_google_search_live_tool():
    assert callable(google_search_live)
    assert google_search_live.__name__ == "google_search_live"
    assert "Google search" in google_search_live.__doc__ or "google" in google_search_live.__doc__.lower()


if __name__ == "__main__":
    test_offline_fallback_telemetry()
    test_calculate_age_from_dob()
    test_static_profile_baselines()
    test_log_weight_dynamic_tool_call()
    test_get_user_biometric_profile()
    test_calculate_protein_targets_with_dynamic_weight()
    test_agent_toolset()
    test_delete_workout_record()
    test_garmin_telemetry()
    test_step_card_and_hybrid_tracking()
    test_fetch_youtube_video()
    test_google_search_live_tool()
    print("All hybrid biometric, Omron blood pressure, Garmin telemetry, hybrid step tracking, YouTube video retrieval, Firestore memory deletion, and search grounding tests passed successfully!")


