import re

ALLOWED_PATTERN = re.compile(r'^[\d\s\+\-\*\/\.\(\)]+$')


def calculator(expression):
    """
    Safely evaluates a basic arithmetic expression and returns the result.
    Only allows numbers and +, -, *, /, (, ) — nothing else.
    """
    cleaned = expression.strip()

    if not ALLOWED_PATTERN.match(cleaned):
        return f"Calculator error: expression contains disallowed characters: '{expression}'"

    try:
        result = eval(cleaned, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"Calculator error: could not evaluate '{expression}': {str(e)}"


if __name__ == "__main__":
    print(calculator("15 + 4827.50 * 0.15"))
    print(calculator("(230 + 180) / 2"))
    print(calculator("import os"))
    print(calculator("__import__('os').system('echo hacked')"))