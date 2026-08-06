import gradio as gr

ALARMS = {
    "Tilt Warning / Device in critical tilt": """
### Device in Critical Tilt

**Action:**
1. Immediately return the device to an upright position.
2. Check all connections.
3. Confirm suction resumes.

The warning clears automatically once the device is upright.
""",

    "Canister Full / Secretion canister full or hose blocked": """
### Secretion Canister Full or Hose Blocked

**Follow these exact steps (from official Quick Guide):**

1. Prepare a new secretion canister
2. **Clamp the patient catheter** (Do **not** clamp the hose system!)
3. Deactivate the keylock
4. Stop the therapy
5. Remove the hose system from the secretion canister
6. Remove the secretion canister
7. Close the pop-off valve, bacterial filter and secretion hose with the appropriate protection caps
8. Dispose of the full canister correctly
9. Connect the new secretion canister
10. Connect the hose system
11. Start therapy again  
    → Wait until the **actual vacuum** matches the **target vacuum**
12. Remove the clamp from the patient catheter

**Also check for blockages:**
• Bacterial and viral filter in the secretion canister
• Bacterial and viral filter in the hose system
• Kinks in the hose system
""",

    "Low Battery": """
### Low Battery

1. Connect the device to AC power immediately
2. Confirm the charging indicator is lit
3. Battery runtime is approximately 16 hours when fully charged
""",

    "Suction Fault / Vacuum too low": """
### Vacuum Too Low

**Check these points for leakage and re-attach if necessary:**

1. Connection from the hose system to the **patient catheter**
2. Connection from the hose system to the **secretion canister system**
3. **Secretion canister connection**

Also inspect for blockages or kinks in the hose system.
""",

    "Vacuum too high": """
### Vacuum Too High

**Possible causes (from official IFU):**
• Ventilation valve is defective
• Additional vacuum sources in the drainage area
• Excessively high vacuum applied from the outside

**Actions:**
1. Remove any additional vacuum sources
2. Check hose connections
3. Contact ATMOS service — the device may need inspection
"""
}

def alarm_help(alarm):
    return ALARMS.get(alarm, "Please select a valid alarm.")

def ask_question(question):
    if not question or not question.strip():
        return "Please type a question about the ATMOS C051."

    q = question.lower().strip()

    if any(w in q for w in ["canister", "secret", "full", "replace", "change", "exchange"]):
        return ALARMS["Canister Full / Secretion canister full or hose blocked"]

    if any(w in q for w in ["battery", "charge", "power", "runtime"]):
        return "Battery runtime is approximately **16 hours** when fully charged. Connect to AC power and confirm the charging indicator is on."

    if any(w in q for w in ["air leak", "leak", "flow"]):
        return "The C051 continuously measures and displays air leak in real time with graphical trends."

    if any(w in q for w in ["tilt", "upright", "position"]):
        return "Keep the device upright at all times. Return it to upright position immediately if the tilt warning appears."

    if "vacuum" in q:
        return "Target vacuum is set by the user. Actual vacuum is measured on the patient side. Always wait until actual vacuum matches target vacuum after changing the canister."

    return "This assistant covers device operation only (setup, alarms, canister change, battery, vacuum). For clinical decisions, please refer to the official operating instructions or contact ATMOS support."

with gr.Blocks(title="ATMOS C051 Quick Support") as demo:
    gr.Markdown("# ATMOS C051 Bedside Support Assistant")
    gr.Markdown("**Based on official ATMOS Quick Guide • No login required • Device operation only**")

    with gr.Tab("Alarm Help"):
        alarm_dropdown = gr.Dropdown(
            choices=list(ALARMS.keys()),
            label="Select an Alarm",
            value="Canister Full / Secretion canister full or hose blocked"
        )
        alarm_output = gr.Markdown()
        alarm_dropdown.change(alarm_help, alarm_dropdown, alarm_output)

    with gr.Tab("Ask a Question"):
        question_input = gr.Textbox(
            label="Your Question",
            placeholder="How do I change the canister? What do I do for vacuum too low?",
            lines=2
        )
        answer_output = gr.Markdown()
        gr.Button("Get Help", variant="primary").click(ask_question, question_input, answer_output)

    gr.Markdown("---\nThis is a quick-reference tool only. Always follow your hospital protocol and the full ATMOS operating instructions.")

demo.launch()