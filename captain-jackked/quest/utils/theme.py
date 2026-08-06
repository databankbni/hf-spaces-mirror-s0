import colorsys

class AppThemeEngine:
    @staticmethod
    def generate(hue: float, is_light: bool):
        """
        Generates the primary, surface, and canvas colors based on the Quest design system.
        Ported from quest_shared/lib/view/format/theme.dart
        """
        # Locked S/L Constants
        if is_light:
            pS, pL = 0.50, 0.30
            sS, sL = 0.11, 0.94
            cS, cL = 0.50, 0.97
        else:
            pS, pL = 0.90, 0.65
            sS, sL = 0.07, 0.10
            cS, cL = 0.18, 0.08

        # Calculate HSL for each component
        # Note: colorsys uses 0-1 for all values. Hue is 0-360 in input.
        
        primary_h = (hue % 360) / 360.0
        surface_h = ((hue + 120) % 360) / 360.0
        canvas_h = ((hue - 120) % 360) / 360.0

        primary = colorsys.hls_to_rgb(primary_h, pL, pS)
        surface = colorsys.hls_to_rgb(surface_h, sL, sS)
        canvas = colorsys.hls_to_rgb(canvas_h, cL, cS)

        # Convert to Hex for easy CSS consumption if needed, or return RGB 0-255
        return {
            'primary': _to_hex(primary),
            'surface': _to_hex(surface),
            'canvas': _to_hex(canvas),
            'highlight': _to_rgba(primary, 0.2)
        }

def _to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))

def _to_rgba(rgb, alpha):
    return 'rgba({}, {}, {}, {})'.format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255), alpha)
