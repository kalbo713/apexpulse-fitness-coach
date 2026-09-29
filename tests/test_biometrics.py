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
    check_fasting_status,
    display_step_summary_card,
    display_biometrics_summary_card,
    format_live_telemetry_system_block,
    log_steps,
    log_cycling_session,
    delete_workout_record,
    google_search_live,
    get_garmin_telemetry,
    log_strength_workout,
    fetch_youtube_video,
    sync_garmin_steps_to_db,
    create_chat_session,
    save_message_to_session,
    list_chat_sessions,
    get_chat_session_history,
    delete_chat_session,
    generate_session_title,
    categorize_and_title_session,
    VALID_CATEGORIES,
    chat_with_gemini,
    root_agent,
)


def test_offline_fallback_telemetry():
    fallback = get_development_fallback_telemetry("2026-09-26")
    assert fallback["mode"] == "offline_fallback"
    assert fallback["garmin_steps"] == 0  # Decoupled from simulated steps
    assert fallback["resting_heart_rate"] == 51
    assert fallback["sleep_score"] == 80
    assert fallback["blood_pressure"] == "113/77"
    assert "weekly_steps" in fallback
    assert "yearly_steps" in fallback
    assert "weekly_avg_bp" in fallback
    assert "yearly_avg_bp" in fallback
    assert "weekly_avg_weight" in fallback
    assert "yearly_weight_delta" in fallback
    assert "weekly_avg_sleep_score" in fallback
    assert "weekly_avg_rhr" in fallback
    assert "hrv_avg_ms" in fallback
    assert "weekly_avg_stress" in fallback
    assert "pulse_ox" in fallback


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
    assert "display_biometrics_summary_card" in tool_names
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
    assert "weekly_steps" in telemetry
    assert "yearly_steps" in telemetry
    assert telemetry["garmin_steps"] >= 0
    assert "/" in telemetry["blood_pressure"]
    assert telemetry["hrv_status"] in ["Balanced", "Unbalanced", "Low", "Poor", "Maintained", "Optimal"]
    assert 0 <= telemetry["training_readiness"] <= 100


def test_step_card_and_hybrid_tracking():
    # 1. Test live Garmin default
    telemetry = get_garmin_telemetry()
    garmin_steps = telemetry.get("garmin_steps", 0)

    step_sum = get_step_summary(force_garmin_sync=True)
    assert step_sum["daily"]["steps"] == garmin_steps
    assert step_sum["daily"]["source"] == "garmin_fenix_7_live"
    assert "weekly" in step_sum
    assert "yearly" in step_sum

    # 2. Test A2UI Step Card: verify 3-column multi-timeframe view (Today, 7 Days, 1 Year)
    card_json = display_step_summary_card()
    card_data = json.loads(card_json)
    assert isinstance(card_data, list)
    assert len(card_data) == 2
    assert card_data[0]["beginRendering"]["root"] == "step_card_root"
    
    # Inspect component IDs inside surfaceUpdate
    components = card_data[1]["surfaceUpdate"]["components"]
    component_ids = [c["id"] for c in components]
    assert "title_text" in component_ids
    assert "today_header" in component_ids
    assert "weekly_header" in component_ids
    assert "yearly_header" in component_ids
    assert "today_text" in component_ids
    assert "weekly_text" in component_ids
    assert "yearly_text" in component_ids
    assert "source_text" in component_ids

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


def test_biometrics_summary_card():
    card_json = display_biometrics_summary_card()
    card_data = json.loads(card_json)
    assert isinstance(card_data, list)
    assert len(card_data) == 2
    assert card_data[0]["beginRendering"]["root"] == "biometrics_dashboard_root"

    components = card_data[1]["surfaceUpdate"]["components"]
    component_ids = [c["id"] for c in components]
    assert "bio_title_text" in component_ids
    assert "cardio_header" in component_ids
    assert "cardio_bp_text" in component_ids
    assert "cardio_hr_text" in component_ids
    assert "cardio_recovery_text" in component_ids
    assert "body_sleep_header" in component_ids
    assert "body_weight_text" in component_ids
    assert "sleep_score_text" in component_ids
    assert "stress_text" in component_ids
    assert "bio_footer_text" in component_ids


def test_format_live_telemetry_system_block():
    sample_telemetry = {
        "daily_steps": "8,450",
        "weekly_steps": "58,200",
        "weekly_avg_steps": "8,314",
        "yearly_steps": "2,840,000",
        "yearly_avg_steps": "7,780",
        "latest_bp": "118/76 (Pulse: 52 bpm @ Today 08:30)",
        "weekly_avg_bp": "117/75",
        "yearly_avg_bp": "119/78 (Range: 108/68 - 132/84)",
        "weight_lbs": 200.0,
        "weight_goal_lbs": 175.0,
        "weekly_avg_weight": 200.4,
        "yearly_weight_delta": "-8.5",
        "sleep_score": 82,
        "sleep_duration": "7h 45m",
        "weekly_avg_sleep_score": 80,
        "weekly_avg_sleep_dur": "7h 30m",
        "rhr": 52,
        "weekly_avg_rhr": 53,
        "hrv_status": "Balanced",
        "hrv_avg_ms": 58,
        "daily_stress": 24,
        "weekly_avg_stress": 26,
        "pulse_ox": 97,
    }
    block = format_live_telemetry_system_block(sample_telemetry)
    assert "[LIVE GARMIN & BIOMETRIC TELEMETRY]" in block
    assert "- STEPS: Today: 8,450 | 7-Day Total: 58,200 (Avg: 8,314) | 1-Year Total: 2,840,000 (Avg: 7,780)" in block
    assert "- BLOOD PRESSURE: Latest: 118/76 (Pulse: 52 bpm @ Today 08:30) | 7-Day Avg: 117/75 | 1-Year Avg: 119/78 (Range: 108/68 - 132/84)" in block
    assert "- WEIGHT: Current: 200.0 lbs (Goal: 175.0 lbs) | 7-Day Avg: 200.4 lbs | 1-Year Trend: -8.5 lbs" in block
    assert "- SLEEP: Last Night: 82/100 (7h 45m) | 7-Day Avg: 80/100 (7h 30m)" in block
    assert "- CARDIOVASCULAR & RECOVERY: Resting HR: 52 bpm (7-Day Avg: 53 bpm) | HRV Status: Balanced (58 ms) | Stress: 24 (7-Day Avg: 26) | Pulse Ox: 97%" in block


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


def test_log_strength_and_mobility_equipment():
    # 1. Kettlebell log
    kb_res = log_strength_workout(exercise_name="Turkish Get-Up", sets=3, reps=5, weight_lbs=15.0, rpe=8)
    assert kb_res["status"] == "success"
    assert kb_res["volume_load_lbs"] == 225.0

    # 2. Dumbbell log (12 lbs)
    db_res = log_strength_workout(exercise_name="Dumbbell Lateral Raise", sets=4, reps=12, weight_lbs=12.0, rpe=7)
    assert db_res["status"] == "success"
    assert db_res["volume_load_lbs"] == 576.0

    # 3. Circular Balance Board drill (0 lbs)
    bb_res = log_strength_workout(exercise_name="Circular Balance Board Stability Drill", sets=3, reps=1, weight_lbs=0.0, rpe=6)
    assert bb_res["status"] == "success"

    # 4. Calf Stretcher mobility flow (0 lbs)
    cs_res = log_strength_workout(exercise_name="Calf Stretcher Mobility & Plantar Stretch", sets=2, reps=1, weight_lbs=0.0, rpe=5)
    assert cs_res["status"] == "success"

    # 5. Check expanded equipment baseline in profile
    profile = get_user_biometric_profile()
    assert "Dumbbell pairs" in profile["static_baselines"]["equipment_suite"]
    assert "Circular balance board" in profile["static_baselines"]["equipment_suite"]
    assert "Calf stretcher" in profile["static_baselines"]["equipment_suite"]
    assert "Yoga mat" in profile["static_baselines"]["equipment_suite"]


def test_chat_sessions_and_auto_titling():
    # 1. Test auto-titling and category tagging across all 4 valid categories
    t1, cat1 = categorize_and_title_session("Can you help me with my post-ride recovery stretches and hydration?")
    assert len(t1.split()) <= 4
    assert cat1 == "Recovery"
    assert cat1 in VALID_CATEGORIES

    t2, cat2 = categorize_and_title_session("Show my daily, weekly, and yearly step tracking summary card via A2UI.")
    assert len(t2.split()) <= 4
    assert cat2 == "Workouts"
    assert cat2 in VALID_CATEGORIES

    t3, cat3 = categorize_and_title_session("What is my current 16/8 fasting window and protein target?")
    assert len(t3.split()) <= 4
    assert cat3 == "Nutrition"
    assert cat3 in VALID_CATEGORIES

    t4, cat4 = categorize_and_title_session("Hello coach, please tell me how you can help me today.")
    assert len(t4.split()) <= 4
    assert cat4 == "General"
    assert cat4 in VALID_CATEGORIES

    # Test initial prompt keywords for Nutrition (fasting, protein, meal, sodium, calories)
    _, cat_fasting = categorize_and_title_session("How many hours do I have left in my fasting window?")
    assert cat_fasting == "Nutrition"

    _, cat_protein = categorize_and_title_session("Calculate my daily protein requirements based on 200 lbs.")
    assert cat_protein == "Nutrition"

    _, cat_meal = categorize_and_title_session("Suggest a high-protein post-workout meal to hit 60g protein.")
    assert cat_meal == "Nutrition"

    _, cat_sodium = categorize_and_title_session("How much sodium and electrolytes should I consume daily?")
    assert cat_sodium == "Nutrition"

    _, cat_calories = categorize_and_title_session("What is my target calories and macro split?")
    assert cat_calories == "Nutrition"

    # 2. Test create_chat_session with category
    user_id = "test_user_sidebar"
    sess = create_chat_session(user_id=user_id, title="Initial Chat", category="Workouts")
    session_id = sess["session_id"]
    assert session_id.startswith("session_")
    assert sess["user_id"] == user_id
    assert sess["title"] == "Initial Chat"
    assert sess["category"] == "Workouts"
    assert sess["messages"] == []

    # 3. Test save_message_to_session & auto-titling + auto-tagging on first user prompt
    save_message_to_session(
        session_id=session_id,
        role="user",
        text="What are some good kettlebell routines for shoulder mobility?",
        user_id=user_id,
    )
    
    # Verify title & category auto-updated
    hist1 = get_chat_session_history(session_id=session_id, user_id=user_id)
    assert hist1 is not None
    assert hist1["title"] != "Initial Chat"
    assert hist1["category"] == "Workouts"
    assert len(hist1["messages"]) == 1
    assert hist1["messages"][0]["role"] == "user"
    assert "kettlebell" in hist1["messages"][0]["text"].lower()

    # 4. Save agent reply
    save_message_to_session(
        session_id=session_id,
        role="agent",
        text="Here is a great shoulder mobility routine using your 15 lb kettlebell.",
        user_id=user_id,
        parts=[{"kind": "text", "text": "Here is a great shoulder mobility routine using your 15 lb kettlebell."}]
    )
    hist2 = get_chat_session_history(session_id=session_id, user_id=user_id)
    assert len(hist2["messages"]) == 2
    assert hist2["messages"][1]["role"] == "agent"

    # 5. List sessions
    all_sessions = list_chat_sessions(user_id=user_id)
    assert len(all_sessions) >= 1
    matching = [s for s in all_sessions if s["session_id"] == session_id]
    assert len(matching) == 1
    assert matching[0]["message_count"] == 2
    assert matching[0]["category"] == "Workouts"

    # 6. Delete session
    del_ok = delete_chat_session(session_id=session_id, user_id=user_id)
    assert del_ok is True
    hist_after_del = get_chat_session_history(session_id=session_id, user_id=user_id)
    assert hist_after_del is None


def test_fasting_status_countdown_and_schedule():
    import datetime
    from unittest.mock import patch
    import zoneinfo

    ny_tz = zoneinfo.ZoneInfo("America/New_York")

    # 1. Test default return values
    res = check_fasting_status()
    assert res["eating_window_start_hour"] == 13
    assert res["eating_window_end_hour"] == 21
    assert res["protocol"] == "16/8 Intermittent Fasting"
    assert res["eating_window"] == "1:00 PM - 9:00 PM (13:00 - 21:00 ET)"
    assert res["timezone"] == "America/New_York (Eastern Time)"
    assert "state" in res
    assert "hours_remaining_in_current_state" in res
    assert "guidance" in res

    # 2. Test morning fasted state (e.g. 10:00 AM ET -> 3.0h remaining until 1:00 PM)
    mock_10am = datetime.datetime(2026, 9, 27, 10, 0, 0, tzinfo=ny_tz)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = mock_10am
        mock_dt.time = datetime.time
        mock_dt.date = datetime.date
        res_10am = check_fasting_status()
        assert res_10am["state"] == "FASTING_ACTIVE"
        assert res_10am["in_eating_window"] is False
        assert res_10am["hours_remaining_in_current_state"] == 3.0
        assert "opens in 3h 0m at 1:00 PM (13:00 ET)" in res_10am["guidance"]

    # 3. Test eating window opens precisely at 13:00 (1:00 PM ET -> 8.0h remaining until 9:00 PM)
    mock_1pm = datetime.datetime(2026, 9, 27, 13, 0, 0, tzinfo=ny_tz)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = mock_1pm
        mock_dt.time = datetime.time
        mock_dt.date = datetime.date
        res_1pm = check_fasting_status()
        assert res_1pm["state"] == "EATING_WINDOW_OPEN"
        assert res_1pm["in_eating_window"] is True
        assert res_1pm["hours_remaining_in_current_state"] == 8.0
        assert "OPEN until 9:00 PM (21:00 ET)" in res_1pm["guidance"]

    # 4. Test mid-eating window (e.g. 4:30 PM ET / 16:30 -> 4.5h remaining until 9:00 PM)
    mock_430pm = datetime.datetime(2026, 9, 27, 16, 30, 0, tzinfo=ny_tz)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = mock_430pm
        mock_dt.time = datetime.time
        mock_dt.date = datetime.date
        res_430pm = check_fasting_status()
        assert res_430pm["state"] == "EATING_WINDOW_OPEN"
        assert res_430pm["in_eating_window"] is True
        assert res_430pm["hours_remaining_in_current_state"] == 4.5

    # 5. Test fasting begins precisely at 21:00 (9:00 PM ET -> 16.0h remaining until 1:00 PM tomorrow)
    mock_9pm = datetime.datetime(2026, 9, 27, 21, 0, 0, tzinfo=ny_tz)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = mock_9pm
        mock_dt.time = datetime.time
        mock_dt.date = datetime.date
        res_9pm = check_fasting_status()
        assert res_9pm["state"] == "FASTING_ACTIVE"
        assert res_9pm["in_eating_window"] is False
        assert res_9pm["hours_remaining_in_current_state"] == 16.0
        assert "opens in 16h 0m at 1:00 PM (13:00 ET)" in res_9pm["guidance"]

    # 6. Test late night fasted state (e.g. 11:00 PM ET / 23:00 -> 14.0h remaining until 1:00 PM tomorrow)
    mock_11pm = datetime.datetime(2026, 9, 27, 23, 0, 0, tzinfo=ny_tz)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = mock_11pm
        mock_dt.time = datetime.time
        mock_dt.date = datetime.date
        res_11pm = check_fasting_status()
        assert res_11pm["state"] == "FASTING_ACTIVE"
        assert res_11pm["in_eating_window"] is False
        assert res_11pm["hours_remaining_in_current_state"] == 14.0

    # 7. Verify workout and fasting summary integration
    summary = get_workout_and_fasting_summary()
    assert "fasting_check" in summary
    assert summary["fasting_check"]["eating_window"] == "1:00 PM - 9:00 PM (13:00 - 21:00 ET)"
    assert summary["fasting_check"]["eating_window_start_hour"] == 13
    assert summary["fasting_check"]["eating_window_end_hour"] == 21

    # 8. Verify user biometric profile guidance mentions 1:00 PM – 9:00 PM
    profile = get_user_biometric_profile()
    assert any("1:00 PM – 9:00 PM" in g for g in profile["age_and_biometric_guidance"])


def test_multimodal_image_processing():
    import base64
    from google.genai import types as genai_types
    from unittest.mock import patch, MagicMock

    # 1. Test Base64 decoding of sample dummy image data
    sample_raw_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    sample_b64 = base64.b64encode(sample_raw_bytes).decode("utf-8")
    sample_data_url = f"data:image/png;base64,{sample_b64}"

    # 2. Test types.Part.from_bytes creation
    part = genai_types.Part.from_bytes(data=sample_raw_bytes, mime_type="image/png")
    assert part is not None
    assert part.inline_data is not None
    assert part.inline_data.data == sample_raw_bytes
    assert part.inline_data.mime_type == "image/png"

    # 3. Test chat_with_gemini with single image_base64 parameter
    with patch("app.agent.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "I analyzed your attached image. This organic salmon and spinach meal provides approximately 48g of protein and satisfies your leucine threshold."
        mock_instance.models.generate_content.return_value = mock_resp
        mock_client_cls.return_value = mock_instance

        # Force model = None in chat_with_gemini so it routes through Client.models.generate_content
        with patch("app.agent.model", None):
            response = chat_with_gemini(
                prompt="Analyze my post-workout meal in this photo for protein content.",
                image_base64=sample_data_url,
                image_mime_type="image/png"
            )
            assert "salmon" in response.lower() or "protein" in response.lower()
            assert mock_instance.models.generate_content.called
            call_kwargs = mock_instance.models.generate_content.call_args[1]
            contents = call_kwargs.get("contents", [])
            assert len(contents) == 2
            assert isinstance(contents[1], genai_types.Part)
            assert contents[1].inline_data.mime_type == "image/png"

    # 4. Test chat_with_gemini with batch images (3 images)
    with patch("app.agent.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "I analyzed all 3 images: your goblet squat depth, kettlebell swing hip hinge, and balance board stability form look excellent."
        mock_instance.models.generate_content.return_value = mock_resp
        mock_client_cls.return_value = mock_instance

        with patch("app.agent.model", None):
            batch_images = [sample_data_url, sample_data_url, sample_data_url]
            response = chat_with_gemini(
                prompt="Review my 3 workout form photos.",
                images=batch_images
            )
            assert "squat" in response.lower() or "form" in response.lower()
            call_kwargs = mock_instance.models.generate_content.call_args[1]
            contents = call_kwargs.get("contents", [])
            # 1 text part + 3 image parts = 4 total parts
            assert len(contents) == 4
            for i in range(1, 4):
                assert isinstance(contents[i], genai_types.Part)
                assert contents[i].inline_data.mime_type == "image/png"

    # 5. Test strict 5-image maximum limit enforcement (e.g., providing 7 images caps at 5)
    with patch("app.agent.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Processed 5 images under maximum limit."
        mock_instance.models.generate_content.return_value = mock_resp
        mock_client_cls.return_value = mock_instance

        with patch("app.agent.model", None):
            seven_images = [sample_data_url] * 7
            chat_with_gemini(
                prompt="Review these 7 photos.",
                images=seven_images
            )
            call_kwargs = mock_instance.models.generate_content.call_args[1]
            contents = call_kwargs.get("contents", [])
            # 1 text part + 5 image parts (capped) = 6 total parts
            assert len(contents) == 6


if __name__ == "__main__":
    test_offline_fallback_telemetry()
    test_calculate_age_from_dob()
    test_static_profile_baselines()
    test_log_weight_dynamic_tool_call()
    test_get_user_biometric_profile()
    test_calculate_protein_targets_with_dynamic_weight()
    test_agent_toolset()
    test_delete_workout_record()
    test_log_strength_and_mobility_equipment()
    test_garmin_telemetry()
    test_step_card_and_hybrid_tracking()
    test_biometrics_summary_card()
    test_format_live_telemetry_system_block()
    test_fetch_youtube_video()
    test_google_search_live_tool()
    test_chat_sessions_and_auto_titling()
    test_fasting_status_countdown_and_schedule()
    test_multimodal_image_processing()
    print("All multi-timeframe telemetry, master biometrics card, step analytics card, system prompt formatting, hybrid biometric, Omron blood pressure, Garmin telemetry, expanded strength & mobility equipment, hybrid step tracking, YouTube video retrieval, Firestore memory deletion, chat session management & auto-titling, 16/8 fasting schedule (1PM-9PM ET), multimodal batch image inputs (5 max), and search grounding tests passed successfully!")





