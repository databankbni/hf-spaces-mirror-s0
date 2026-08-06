import tkinter as tk
import math

class CalculatorUI:
    def __init__(self, root):
        self.root = root
        self.frame = tk.Frame(root)

        self.display = tk.Entry(
            self.frame,
            font=("Arial", 24),
            justify="right",
            bd=8
        )
        self.display.pack(
            fill="x",
            padx=10,
            pady=10
        )

        self.button_frame = tk.Frame(self.frame)
        self.button_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        self.buttons = [
            ["sin", "cos", "tan", "√", "∛"],
            ["x²", "x³", "^", "log", "ln"],
            ["7","8","9","/","C"],
            ["4","5","6","*","("],
            ["1","2","3","-", ")"],
            ["0",".","%","+","="],
            ["π", "e", "!", "⌫", "+/-"]
        ]
        self.create_buttons()

    def show(self):
        self.frame.pack(fill="both", expand=True)

    def hide(self):
        self.frame.pack_forget()

    def create_buttons(self):
        for row in range(len(self.buttons)):
            self.button_frame.grid_rowconfigure(
                row,
                weight=1
            )
            for col in range(len(self.buttons[row])):
                self.button_frame.grid_columnconfigure(
                    col,
                    weight=1
                )
                button_text = self.buttons[row][col]
                button = tk.Button(
                    self.button_frame,
                    text=button_text,
                    font=("Arial",18),
                    width=5,
                    height=2,
                    command=lambda t=button_text: self.on_button_click(t)
                )
                button.grid(
                    row=row,
                    column=col,
                    sticky="nsew",
                    padx=4,
                    pady=4
                )

    def on_button_click(self, label):
        current = self.display.get()

        if label == "C":
            self.display.delete(0, tk.END)
            return

        if label == "⌫":
            self.display.delete(len(current)-1, tk.END)
            return

        if label == "=":
            self.calculate_result()
            return

        if label == "+/-":
            if current.startswith("-"):
                self.display.delete(0)
            else:
                self.display.insert(0, "-")
            return

        if label == "π":
            self.display.insert(tk.END, "pi")
            return

        if label == "e":
            self.display.insert(tk.END, "e")
            return

        if label == "x²":
            self.display.insert(tk.END, "**2")
            return

        if label == "x³":
            self.display.insert(tk.END, "**3")
            return

        if label == "^":
            self.display.insert(tk.END, "**")
            return

        if label == "√":
            self.display.insert(tk.END, "sqrt(")
            return

        if label == "∛":
            self.display.insert(tk.END, "**(1/3)")
            return

        if label in {"sin", "cos", "tan", "log", "ln"}:
            self.display.insert(tk.END, f"{label}(")
            return

        if label == "!":
            self.display.insert(tk.END, "!")
            return

        self.display.insert(tk.END, label)

    def calculate_result(self):
        expression = self.display.get()
        try:
            expression = expression.replace("ln(", "LN_PLACEHOLDER(")
            expression = expression.replace("log(", "math.log10(")
            expression = expression.replace("LN_PLACEHOLDER(", "math.log(")
            expression = expression.replace("sqrt(", "math.sqrt(")
            expression = expression.replace("pi", "math.pi")
            expression = expression.replace("e", "math.e")
            expression = expression.replace("sin(", "math.sin(")
            expression = expression.replace("cos(", "math.cos(")
            expression = expression.replace("tan(", "math.tan(")
            expression = expression.replace("%", "/100")

            if "!" in expression:
                parts = expression.split("!")
                if len(parts) == 2 and parts[1] == "":
                    value = int(parts[0])
                    result = math.factorial(value)
                else:
                    raise ValueError("Invalid factorial syntax")
            else:
                result = eval(expression, {"math": math, "__builtins__": {}})

            self.display.delete(0, tk.END)
            self.display.insert(0, str(result))
        except Exception:
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")
