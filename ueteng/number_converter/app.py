import gradio as gr

# --- Utility functions ---

def char_to_val(c):
    """Convert a single character to integer value (0–15)."""
    if c.isdigit():
        return int(c)
    return 10 + ord(c.upper()) - ord('A')

def val_to_char(v):
    """Convert a value 0–15 to hex digit."""
    if v < 10:
        return str(v)
    return chr(ord('A') + v - 10)

def to_decimal(num_str, base):
    """Convert string in base -> decimal float (with validation)."""
    if "." in num_str:
        int_part, frac_part = num_str.split(".")
    else:
        int_part, frac_part = num_str, ""

    # integer part
    int_val = 0
    for i, c in enumerate(int_part[::-1]):
        v = char_to_val(c)
        if v >= base:  # ❌ invalid digit
            raise ValueError(f"Invalid digit '{c}' for base {base}")
        int_val += v * (base ** i)

    # fractional part
    frac_val = 0
    for i, c in enumerate(frac_part, start=1):
        v = char_to_val(c)
        if v >= base:  # ❌ invalid digit
            raise ValueError(f"Invalid digit '{c}' for base {base}")
        frac_val += v * (base ** -i)

    return int_val + frac_val

def from_decimal(num, base, precision=10):
    """Convert decimal float -> string in base, with fractional part."""
    int_part = int(num)
    frac_part = num - int_part

    # integer conversion
    int_digits = []
    if int_part == 0:
        int_digits.append("0")
    else:
        while int_part > 0:
            int_digits.append(val_to_char(int_part % base))
            int_part //= base
    int_digits = int_digits[::-1]

    # fractional conversion
    frac_digits = []
    count = 0
    while frac_part > 0 and count < precision:
        frac_part *= base
        digit = int(frac_part)
        if digit >= base:  # safeguard
            raise ValueError(f"Invalid conversion result digit {digit} for base {base}")
        frac_digits.append(val_to_char(digit))
        frac_part -= digit
        count += 1

    if frac_digits:
        return "".join(int_digits) + "." + "".join(frac_digits)
    else:
        return "".join(int_digits)

# --- Conversion wrapper ---

def convert_number(number_str, from_base, to_base):
    try:
        num = to_decimal(number_str.strip(), from_base)
        result = from_decimal(num, to_base)
        return result
    except Exception as e:
        return f"Error: {e}"

# --- Gradio Interface ---
with gr.Blocks() as demo:
    gr.Markdown("# 🔢 Base Converter (2, 8, 10, 16)\nSupports fractional numbers with validation.")

    with gr.Row():
        number_str = gr.Textbox(label="Enter Number", value="101.11")
        from_base = gr.Dropdown([2, 8, 10, 16], label="From Base", value=2)
        to_base = gr.Dropdown([2, 8, 10, 16], label="To Base", value=10)

    result = gr.Textbox(label="Converted Result")

    convert_btn = gr.Button("Convert")
    convert_btn.click(fn=convert_number, inputs=[number_str, from_base, to_base], outputs=result)

import os
port = int(os.environ.get("PORT", 7860))
demo.launch(server_name="0.0.0.0", server_port=port)
