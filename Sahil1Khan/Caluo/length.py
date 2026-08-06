class LengthConverter:
    conversion = {
        "mm": 0.001,
        "cm": 0.01,
        "m": 1,
        "km": 1000,
        "inch": 0.0254,
        "yard": 0.9144,
        "mile": 1609.344,
        "foot": 0.3048
    }

    def convert(self, value, from_unit, to_unit):
        try:
            value = float(value)
            if from_unit not in self.conversion or to_unit not in self.conversion:
                raise ValueError("Unsupported unit")
            meters = value * self.conversion[from_unit]
            result = meters / self.conversion[to_unit]
            return round(result, 6)
        except Exception:
            return None