from datetime import datetime, timedelta
from pathlib import Path
import pickle
import sys

import gradio as gr
import pandas as pd

print("Starting app...", flush=True)

MODEL_PATH = Path(__file__).with_name("model_bundle.pkl")
if not MODEL_PATH.exists():
    raise FileNotFoundError("model_bundle.pkl is missing. Upload it beside app.py.")

print("Loading model bundle...", flush=True)
with MODEL_PATH.open("rb") as file:
    bundle = pickle.load(file)
print("Model bundle loaded.", flush=True)

model = bundle["model"]
feature_columns = bundle["feature_columns"]
airline_rank = bundle["airline_rank"]
destination_rank = bundle["destination_rank"]
source_categories = bundle["source_categories"]
stop_mapping = bundle["stop_mapping"]

ERROR_MARGIN = 55.0


def predict_fare(
    airline,
    source,
    destination,
    journey_date,
    total_stops,
    departure_time,
    arrival_time,
):
    try:
        if not all([
            airline,
            source,
            destination,
            journey_date,
            total_stops,
            departure_time,
            arrival_time,
        ]):
            return "Please complete all fields."

        if source == destination:
            return "Source and destination must be different."

        journey = pd.to_datetime(journey_date, errors="raise")
        departure = datetime.strptime(departure_time.strip(), "%H:%M")
        arrival = datetime.strptime(arrival_time.strip(), "%H:%M")

        if arrival <= departure:
            arrival += timedelta(days=1)

        duration = arrival - departure
        total_minutes = int(duration.total_seconds() // 60)
        duration_hours = total_minutes // 60
        duration_minutes = total_minutes % 60

        if duration_hours > 24:
            return "The calculated duration is longer than 24 hours. Check the times."

        row = {column: 0 for column in feature_columns}

        values = {
            "Airline": airline_rank[airline],
            "Destination": destination_rank[destination],
            "Total_Stops": stop_mapping[total_stops],
            "Journey_day": journey.day,
            "Journey_month": journey.month,
            "Arrival_Time_hour": arrival.hour,
            "Arrival_Time_minute": arrival.minute,
            "Dep_Time_hour": departure.hour,
            "Dep_Time_minute": departure.minute,
            "Duration_hour": duration_hours,
            "Duration_min": duration_minutes,
        }

        for column, value in values.items():
            if column in row:
                row[column] = value

        source_column = f"Source_{source}"
        if source_column in row:
            row[source_column] = 1

        input_df = pd.DataFrame([row], columns=feature_columns)
        prediction = float(model.predict(input_df)[0])

        lower = max(0, prediction - ERROR_MARGIN)
        upper = prediction + ERROR_MARGIN

        return (
            f"## Estimated fare: **${prediction:,.2f} CAD**\n\n"
            f"### Expected range: **${lower:,.2f}–${upper:,.2f} CAD**\n\n"
            "_Based on training-data patterns, not live airline inventory._"
        )

    except ValueError:
        return "Use YYYY-MM-DD for the date and HH:MM for the times."
    except Exception as error:
        print(f"Prediction error: {error}", file=sys.stderr, flush=True)
        return f"Prediction error: {error}"


APP_THEME = gr.themes.Soft()

with gr.Blocks(
    title="Canadian Flight Fare Estimator",
) as demo:
    gr.Markdown(
        """
        # ✈️ Canadian Flight Fare Estimator

        Estimate a likely Canadian flight fare and view a realistic price range.
        """
    )

    gr.Markdown("## Trip details")

    with gr.Row():
        source_input = gr.Dropdown(
            choices=source_categories,
            label="Flying from",
            value=source_categories[0] if source_categories else None,
        )
        destination_input = gr.Dropdown(
            choices=list(destination_rank.keys()),
            label="Flying to",
            value=list(destination_rank.keys())[0] if destination_rank else None,
        )

    with gr.Row():
        journey_date_input = gr.Textbox(
            label="Travel date",
            value="2026-08-15",
            placeholder="YYYY-MM-DD",
        )
        airline_input = gr.Dropdown(
            choices=list(airline_rank.keys()),
            label="Airline",
            value=list(airline_rank.keys())[0] if airline_rank else None,
        )
        stops_input = gr.Dropdown(
            choices=list(stop_mapping.keys()),
            label="Stops",
            value="non-stop" if "non-stop" in stop_mapping else list(stop_mapping.keys())[0],
        )

    with gr.Accordion("Advanced flight schedule", open=False):
        gr.Markdown(
            "Use the defaults when you do not know the exact schedule yet."
        )
        with gr.Row():
            departure_input = gr.Textbox(
                label="Departure time",
                value="09:00",
                placeholder="HH:MM",
            )
            arrival_input = gr.Textbox(
                label="Arrival time",
                value="11:30",
                placeholder="HH:MM",
            )

    estimate_button = gr.Button("Estimate fare", variant="primary", size="lg")
    output = gr.Markdown()

    estimate_button.click(
        fn=predict_fare,
        inputs=[
            airline_input,
            source_input,
            destination_input,
            journey_date_input,
            stops_input,
            departure_input,
            arrival_input,
        ],
        outputs=output,
    )

    gr.Markdown(
        """
        ---
        This portfolio tool does not search live airline prices or guarantee availability.
        """
    )

print("Launching Gradio...", flush=True)

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        theme=APP_THEME,
        ssr_mode=False,
    )
