import re
import math
import gradio as gr
from length import LengthConverter

converter = LengthConverter()
LENGTH_UNITS = sorted(converter.conversion.keys())


def evaluate_expression(expression):
    if expression is None or not str(expression).strip():
        return "Enter an expression"

    expr = str(expression).strip()
    expr = expr.replace("^", "**")
    expr = expr.replace("%", "/100")
    expr = expr.replace("√", "math.sqrt(")
    expr = expr.replace("π", "math.pi")
    expr = re.sub(r"\bln\(", "math.log(", expr)
    expr = re.sub(r"\blog\(", "math.log10(", expr)
    expr = re.sub(r"\bpi\b", "math.pi", expr)
    expr = re.sub(r"(?<![A-Za-z0-9_])e(?![A-Za-z0-9_])", "math.e", expr)
    expr = re.sub(r"\bsin\(", "math.sin(", expr)
    expr = re.sub(r"\bcos\(", "math.cos(", expr)
    expr = re.sub(r"\btan\(", "math.tan(", expr)
    expr = re.sub(r"\babs\(", "math.fabs(", expr)
    expr = re.sub(r"\bsqrt\(", "math.sqrt(", expr)

    try:
        if "!" in expr:
            if expr.endswith("!"):
                value = expr[:-1].strip()
                if value.isdigit():
                    result = math.factorial(int(value))
                else:
                    raise ValueError("Invalid factorial syntax")
            else:
                raise ValueError("Invalid factorial syntax")
        else:
            result = eval(expr, {"math": math, "__builtins__": {}})
        return str(result)
    except Exception as error:
        return f"Error: {error}"


def convert_length(value, from_unit, to_unit):
    if value is None:
        return "Enter a value"
    if not from_unit or not to_unit:
        return "Choose both units"

    result = converter.convert(value, from_unit, to_unit)
    if result is None:
        return "Conversion error"
    return f"{result} {to_unit}"


def create_app():
    with gr.Blocks() as demo:
        gr.Markdown("# Caluo Web Calculator")
        with gr.Tabs():
            with gr.TabItem("Calculator"):
                expr_input = gr.Textbox(label="Expression", placeholder="e.g. 2+2 or sin(3.14/2)")
                expr_output = gr.Textbox(label="Result")
                eval_button = gr.Button("Evaluate")
                eval_button.click(evaluate_expression, inputs=expr_input, outputs=expr_output)

            with gr.TabItem("Length Converter"):
                value_input = gr.Number(value=1, label="Value")
                from_unit_input = gr.Dropdown(LENGTH_UNITS, label="From Unit", value=LENGTH_UNITS[0])
                to_unit_input = gr.Dropdown(LENGTH_UNITS, label="To Unit", value=LENGTH_UNITS[1])
                convert_button = gr.Button("Convert")
                convert_output = gr.Textbox(label="Result")
                convert_button.click(
                    convert_length,
                    inputs=[value_input, from_unit_input, to_unit_input],
                    outputs=convert_output,
                )

    return demo


if __name__ == "__main__":
    app = create_app()
    app.launch()
