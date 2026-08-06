import tkinter as tk
from tkinter import ttk
from length import LengthConverter

class ConverterUI:
    def __init__(self, root):
        self.frame = tk.Frame(root)
        self.converter = LengthConverter()

        self.value_label = tk.Label(
            self.frame,
            text="Value",
            font=("Arial", 14)
        )
        self.value_label.pack(pady=(20, 5))

        self.value_entry = tk.Entry(
            self.frame,
            font=("Arial", 18),
            justify="center"
        )
        self.value_entry.pack(fill="x", padx=20)
        self.value_entry.bind("<Return>", lambda event: self.convert())

        self.from_label = tk.Label(
            self.frame,
            text="From",
            font=("Arial", 14)
        )
        self.from_label.pack(pady=(20, 5))

        self.from_unit = ttk.Combobox(
            self.frame,
            state="readonly",
            font=("Arial", 14)
        )
        self.from_unit.pack(fill="x", padx=20)

        self.to_label = tk.Label(
            self.frame,
            text="To",
            font=("Arial", 14)
        )
        self.to_label.pack(pady=(20, 5))

        self.to_unit = ttk.Combobox(
            self.frame,
            state="readonly",
            font=("Arial", 14)
        )
        self.to_unit.pack(fill="x", padx=20)

        self.convert_button = tk.Button(
            self.frame,
            text="Convert",
            font=("Arial", 16),
            height=2,
            command=self.convert
        )
        self.convert_button.pack(
            fill="x",
            padx=20,
            pady=20
        )

        self.result = tk.Label(
            self.frame,
            text="",
            font=("Arial", 20)
        )
        self.result.pack(pady=10)

    def show(self):
        self.frame.pack(fill="both", expand=True)

    def hide(self):
        self.frame.pack_forget()

    def set_units(self, units):
        self.from_unit["values"] = units
        self.to_unit["values"] = units
        if len(units) > 0:
            self.from_unit.current(0)
            self.to_unit.current(1 if len(units) > 1 else 0)

    def convert(self):
        value = self.value_entry.get().strip()
        from_unit = self.from_unit.get()
        to_unit = self.to_unit.get()

        if not value:
            self.result.config(text="Enter a value")
            return

        if not from_unit or not to_unit:
            self.result.config(text="Select units")
            return

        result = self.converter.convert(value, from_unit, to_unit)
        if result is None:
            self.result.config(text="Error")
        else:
            self.result.config(text=f"{result} {to_unit}")