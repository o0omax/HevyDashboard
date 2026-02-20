# HevyDashboard

Streamlit dashboard that connects to the Hevy API and gamifies a **Starting Strength** routine using 5RM progression.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your Hevy API key:
   ```bash
   export HEVY_API_KEY=your_api_key_here
   ```
3. Run the app:
   ```bash
   streamlit run app.py
   ```

## What it tracks

- Latest Hevy workout with title `Starting Strength`
- Highest successful 5-rep set for:
  - Squat
  - Bench Press
  - Deadlift
  - Overhead Press
- Per-exercise level (1–5) and progress bar to next level
- Total Strength Score (sum of all exercise levels)
- Linear Progression Streak (consecutive workouts with increases and no drops)
