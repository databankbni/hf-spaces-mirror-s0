import math
import tkinter as tk

class Calculator:
    def __init__(self, display):
        self.display = display

    def insert(self, value):
        self.display.insert(tk.END, value)

    def clear(self):
        self.display.delete(0, tk.END)

    def backspace(self):
        current = self.display.get()
        self.display.delete(0, tk.END)
        self.display.insert(0, current[:-1])

    def calculate(self):
        try:
            expression = self.display.get()
            expression = expression.replace("pi", "math.pi")
            expression = expression.replace("e", "math.e")
            expression = expression.replace("√", "math.sqrt(")
            expression = expression.replace("^", "**")
            result = eval(expression, {"math": math, "__builtins__": {}})
            self.display.delete(0, tk.END)
            self.display.insert(0, str(result))
        except Exception:
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")