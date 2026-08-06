import tkinter as tk
from tkinter import ttk
from ui import CalculatorUI
from converter_ui import ConverterUI
from mode_manager import ModeManager

root = tk.Tk()
root.title("Caluo")
root.geometry("450x650")
root.resizable(False, False)

mode_manager = ModeManager()

control_frame = tk.Frame(root)
control_frame.pack(fill="x", padx=20, pady=(10, 0))

mode_label = tk.Label(control_frame, text="Mode", font=("Arial", 14))
mode_label.pack(side="left")

mode_selector = ttk.Combobox(
    control_frame,
    values=mode_manager.get_modes(),
    state="readonly",
    font=("Arial", 14),
    width=14
)
mode_selector.current(0)
mode_selector.pack(side="left", padx=(10, 0), fill="x", expand=True)

calculator_ui = CalculatorUI(root)
converter_ui = ConverterUI(root)
converter_ui.set_units(sorted(converter_ui.converter.conversion.keys()))
converter_ui.hide()
calculator_ui.show()


def on_mode_change(event=None):
    mode = mode_selector.get()
    mode_manager.set_mode(mode)
    if mode == "Length":
        calculator_ui.hide()
        converter_ui.show()
    else:
        converter_ui.hide()
        calculator_ui.show()

mode_selector.bind("<<ComboboxSelected>>", on_mode_change)

root.mainloop()