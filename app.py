import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

HEVY_BASE_URL = "https://api.hevyapp.com/v1"
TARGET_WORKOUT_TITLE = "Starting Strength"

EXERCISE_TARGETS_5RM = {
    "Squat": [80, 100, 125, 145, 170],
    "Deadlift": [100, 120, 145, 170, 200],
    "Bench Press": [60, 80, 95, 115, 130],
    "Overhead Press": [40, 50, 60, 70, 85],
}

EXERCISE_ALIASES = {
    "Squat": ["squat"],
    "Deadlift": ["deadlift"],
    "Bench Press": ["bench press", "bench"],
    "Overhead Press": ["overhead press", "shoulder press", "press"],
}

LEVEL_LABELS = {
    0: "Unranked",
    1: "Novice",
    2: "Decent",
    3: "Intermediate",
    4: "Advanced",
    5: "Elite",
}


@dataclass
class ExerciseProgress:
    exercise: str
    best_5rm: float
    level: int
    progress_to_next: float
    next_target: Optional[float]


class HevyClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        return {
            "accept": "application/json",
            "api-key": self.api_key,
        }

    def get_workouts(self, page: int = 1, page_size: int = 10) -> List[Dict[str, Any]]:
        response = requests.get(
            f"{HEVY_BASE_URL}/workouts",
            headers=self._headers(),
            params={"page": page, "pageSize": page_size},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("workouts", [])


def normalize_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def canonical_exercise_name(raw_name: str) -> Optional[str]:
    normalized = normalize_name(raw_name)
    for canonical, aliases in EXERCISE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def is_successful_5_rep_set(set_data: Dict[str, Any]) -> bool:
    reps = set_data.get("reps")
    completed = set_data.get("completed")
    if reps != 5:
        return False
    if completed is None:
        return True
    return bool(completed)


def extract_weight_kg(set_data: Dict[str, Any]) -> float:
    if set_data.get("weight_kg") is not None:
        return float(set_data["weight_kg"])
    if set_data.get("weight_lbs") is not None:
        return float(set_data["weight_lbs"]) * 0.453592
    if set_data.get("weight") is not None:
        return float(set_data["weight"])
    return 0.0


def extract_workout_5rms(workout: Dict[str, Any]) -> Dict[str, float]:
    best = {name: 0.0 for name in EXERCISE_TARGETS_5RM}
    for exercise in workout.get("exercises", []):
        canonical = canonical_exercise_name(exercise.get("title", ""))
        if canonical is None:
            continue
        for set_data in exercise.get("sets", []):
            if is_successful_5_rep_set(set_data):
                best[canonical] = max(best[canonical], extract_weight_kg(set_data))
    return best


def level_for_weight(exercise: str, weight: float) -> Tuple[int, float, Optional[float]]:
    targets = EXERCISE_TARGETS_5RM[exercise]
    level = 0
    for idx, target in enumerate(targets, start=1):
        if weight >= target:
            level = idx

    if level >= len(targets):
        return 5, 1.0, None

    next_target = targets[level]
    previous_target = 0 if level == 0 else targets[level - 1]
    span = next_target - previous_target
    progressed = max(0.0, min(weight - previous_target, span)) if span > 0 else 0.0
    progress = progressed / span if span > 0 else 0.0
    return level, progress, next_target


def build_progress(best_5rms: Dict[str, float]) -> List[ExerciseProgress]:
    progress_cards: List[ExerciseProgress] = []
    for exercise in EXERCISE_TARGETS_5RM:
        weight = best_5rms.get(exercise, 0.0)
        level, progress, next_target = level_for_weight(exercise, weight)
        progress_cards.append(
            ExerciseProgress(
                exercise=exercise,
                best_5rm=weight,
                level=level,
                progress_to_next=progress,
                next_target=next_target,
            )
        )
    return progress_cards


def filter_starting_strength(workouts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        w
        for w in workouts
        if normalize_name(w.get("title", "")) == normalize_name(TARGET_WORKOUT_TITLE)
    ]


def compute_linear_progression_streak(workouts: List[Dict[str, Any]]) -> int:
    if len(workouts) < 2:
        return 0

    top_weights = [extract_workout_5rms(workout) for workout in workouts]
    streak = 0
    for current, previous in zip(top_weights, top_weights[1:]):
        deltas = [current[name] - previous[name] for name in EXERCISE_TARGETS_5RM]
        any_increase = any(delta > 0 for delta in deltas)
        any_drop = any(delta < 0 for delta in deltas)
        if any_increase and not any_drop:
            streak += 1
        else:
            break
    return streak


def load_starting_strength_workouts(client: HevyClient, max_pages: int = 8) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        workouts = client.get_workouts(page=page, page_size=10)
        if not workouts:
            break
        matches.extend(filter_starting_strength(workouts))
    return matches


def main() -> None:
    st.set_page_config(page_title="Hevy Starting Strength Dashboard", page_icon="💪", layout="wide")
    st.title("💪 Starting Strength Gamified Dashboard")
    st.caption("Tracks your 5RM levels from Hevy workouts named 'Starting Strength'.")

    st.sidebar.header("Profile")
    st.sidebar.write("Height: **193 cm**")
    st.sidebar.write("Bodyweight: **95 kg**")

    api_key = os.getenv("HEVY_API_KEY")
    if not api_key:
        st.error("Missing HEVY_API_KEY. Set it in your environment before running Streamlit.")
        st.stop()

    client = HevyClient(api_key)

    try:
        starting_strength_workouts = load_starting_strength_workouts(client)
    except requests.RequestException as exc:
        st.error(f"Failed to fetch Hevy workouts: {exc}")
        st.stop()

    if not starting_strength_workouts:
        st.warning("No workouts found with title 'Starting Strength'.")
        st.stop()

    latest_workout = starting_strength_workouts[0]
    latest_5rms = extract_workout_5rms(latest_workout)
    progress_cards = build_progress(latest_5rms)

    total_strength_score = sum(card.level for card in progress_cards)
    progression_streak = compute_linear_progression_streak(starting_strength_workouts)

    c1, c2, c3 = st.columns(3)
    c1.metric("Latest Workout", latest_workout.get("start_time", "N/A"))
    c2.metric("Total Strength Score", f"{total_strength_score}/20")
    c3.metric("Linear Progression Streak", f"{progression_streak} workouts")

    st.subheader("5RM Level Progress")

    for card in progress_cards:
        st.markdown(f"### {card.exercise}")
        st.write(f"Best successful 5RM: **{card.best_5rm:.1f} kg**")
        st.write(f"Level {card.level} — **{LEVEL_LABELS[card.level]}**")

        if card.level < 5 and card.next_target is not None:
            st.progress(card.progress_to_next, text=f"Progress to next level ({card.next_target:.0f} kg)")
        else:
            st.progress(1.0, text="Max level reached (Elite)")

    st.divider()
    st.markdown("#### Level Targets (5RM at 95kg BW)")
    st.table(EXERCISE_TARGETS_5RM)


if __name__ == "__main__":
    main()
