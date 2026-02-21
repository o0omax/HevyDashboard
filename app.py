import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st
import pandas as pd
import plotly.express as px

# --- KONFIGURATION & GYM-RUNDUNG ---
HEVY_BASE_URL = "https://api.hevyapp.com/v1"
TARGET_WORKOUT_TITLE = "Starting Strength"

def gym_round(value: float) -> float:
    """Rundet auf den nächsten im Gym machbaren 2.5kg Schritt."""
    return round(value / 2.5) * 2.5

# Deine exakten 1RM-Werte aus den Chat-Protokollen (95kg Male)
RAW_1RM_TARGETS = {
    "Squat": [89, 118, 153, 192, 234],
    "Bench Press": [67, 89, 116, 147, 180],
    "Deadlift": [105, 138, 176, 220, 266],
    "Overhead Press": [41, 57, 76, 97, 121]  # Shoulder Press
}

# Umrechnung auf 5RM-Arbeitsgewichte (1RM * 0.89) mit Gym-Rundung
EXERCISE_TARGETS_5RM = {
    ex: [gym_round(val * 0.89) for val in targets]
    for ex, targets in RAW_1RM_TARGETS.items()
}

INCREMENTS = {
    "Squat": 2.5,
    "Deadlift": 2.5,
    "Bench Press": 2.5,
    "Overhead Press": 2.5
}

EXERCISE_ALIASES = {
    "Squat": ["squat", "kniebeuge"],
    "Deadlift": ["deadlift", "kreuzheben"],
    "Bench Press": ["bench press", "bench", "bankdrücken"],
    "Overhead Press": ["overhead press", "shoulder press", "press", "schulterdrücken"],
}

LEVEL_LABELS = {
    0: "Below Beginner",
    1: "Beginner",
    2: "Novice",
    3: "Intermediate",
    4: "Advanced",
    5: "Elite",
}

LEVEL_DESCRIPTIONS = {
    "Beginner": "Technik-Phase: Stärker als 5% der Trainierenden. Die Basis sitzt.",
    "Novice": "Grundlagen-Phase: Stärker als 20%. Typisches Ende von Starting Strength.",
    "Intermediate": "Aufbau-Phase: Stärker als 50%. Du gehörst zur oberen Hälfte im Gym.",
    "Advanced": "Profi-Phase: Stärker als 80%. Du bist einer der Stärksten im Studio.",
    "Elite": "Wettkampf-Phase: Stärker als 95%. Absolutes Top-Niveau."
}

# --- API CLIENT ---
class HevyClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    def _headers(self) -> Dict[str, str]:
        return {"accept": "application/json", "api-key": self.api_key}

    def get_workouts(self, page: int = 1, page_size: int = 10) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{HEVY_BASE_URL}/workouts",
                headers=self._headers(),
                params={"page": page, "pageSize": page_size},
                timeout=30,
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else payload.get("workouts", [])
        except:
            return []

# --- LOGIK-FUNKTIONEN ---

def normalize_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())

def canonical_exercise_name(raw_name: str) -> Optional[str]:
    normalized = normalize_name(raw_name)
    for canonical, aliases in EXERCISE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None

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
    progress = (weight - previous_target) / span if span > 0 else 0.0
    return level, progress, next_target

def process_workouts(workouts: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for w in workouts:
        if TARGET_WORKOUT_TITLE.lower() in normalize_name(w.get("title", "")):
            date = w.get("start_time")[:10]
            for ex in w.get("exercises", []):
                name = canonical_exercise_name(ex.get("title", ""))
                if name:
                    w_sets = [s for s in ex.get("sets", []) if s.get("type") == "normal"]
                    if w_sets:
                        success = all(s.get("reps") == 5 for s in w_sets)
                        weight = float(w_sets[0].get("weight_kg") or 0)
                        rows.append({"Datum": date, "Übung": name, "Gewicht": weight, "Erfolg": success})
    return pd.DataFrame(rows).sort_values("Datum")

def main() -> None:
    st.set_page_config(page_title="SS Dashboard (95kg)", page_icon="💪", layout="wide")
    st.title("💪 Starting Strength Tracker (95kg Male)")

    api_key = os.getenv("HEVY_API_KEY")
    if not api_key:
        st.error("Missing HEVY_API_KEY. Bitte in Umgebungsvariablen setzen.")
        st.stop()

    client = HevyClient(api_key)

    all_workouts = []
    with st.spinner('Synchronisiere Daten...'):
        for p in range(1, 15):
            batch = client.get_workouts(page=p)
            if not batch: break
            all_workouts.extend(batch)

    if not all_workouts:
        st.warning("Keine 'Starting Strength' Workouts in Hevy gefunden.")
        st.stop()

    df = process_workouts(all_workouts)
    
    # 1. Metriken & Nächste Session
    st.subheader("🎯 Nächste Session & Aktuelles Level")
    cols = st.columns(4)
    
    for i, exercise in enumerate(INCREMENTS.keys()):
        ex_df = df[df["Übung"] == exercise]
        if not ex_df.empty:
            last_entry = ex_df.iloc[-1]
            last_w = last_entry["Gewicht"]
            succ = last_entry["Erfolg"]
            
            next_w = last_w + INCREMENTS[exercise] if succ else last_w
            lvl, prog, next_t = level_for_weight(exercise, last_w)
            
            with cols[i]:
                st.metric(label=exercise, value=f"{next_w} kg", delta=f"{INCREMENTS[exercise] if succ else 0} kg")
                st.write(f"Level: **{LEVEL_LABELS[lvl]}**")
                st.progress(prog, text=f"{last_w}kg / {next_t}kg" if next_t else "MAX reached")
                color = "green" if succ else "red"
                st.markdown(f"<small style='color:{color}'>Letztes Training: {'✅ 5/5/5' if succ else '❌ Fail'}</small>", unsafe_allow_html=True)

    st.divider()

    # 2. Die visuelle Level-Leiter
    st.subheader("🏆 StrengthLevel.com Benchmarks (Gym-Ready 5RM)")
    targets_display = pd.DataFrame(EXERCISE_TARGETS_5RM).T
    targets_display.columns = ["Beginner", "Novice", "Intermediate", "Advanced", "Elite"]
    
    def highlight_achieved(s):
        ex = s.name
        ex_success_df = df[(df["Übung"] == ex) & (df["Erfolg"] == True)]
        best_w = ex_success_df["Gewicht"].max() if not ex_success_df.empty else 0
        return ['background-color: #155724; color: #d4edda; font-weight: bold' if best_w >= v else 'color: #6c757d' for v in s]

    st.table(targets_display.style.apply(highlight_achieved, axis=1).format("{:.1f}"))

    # 2b. Level Beschreibungen
    st.markdown("### ℹ️ Was bedeuten die Level?")
    desc_cols = st.columns(len(LEVEL_DESCRIPTIONS))
    for i, (level, desc) in enumerate(LEVEL_DESCRIPTIONS.items()):
        with desc_cols[i]:
            st.info(f"**{level}**\n\n{desc}")

    st.divider()

    # 3. Graph
    st.subheader("📊 Fortschrittsgraph")
    df["Status"] = df["Erfolg"].map({True: "Erfolgreich (5/5/5)", False: "Stagnation (Fail)"})
    
    fig = px.line(df, x="Datum", y="Gewicht", color="Übung", markers=True, 
                  line_shape="hv", symbol="Status",
                  color_discrete_sequence=px.colors.qualitative.Pastel)
    
    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, use_container_width=True)

    # 4. Rohdaten
    with st.expander("Ganze Historie einsehen"):
        st.dataframe(df.sort_values("Datum", ascending=False), use_container_width=True)

if __name__ == "__main__":
    main()