class ModeManager:
    def __init__(self):
        self.mode = "Scientific"
        self.modes = [
            "Scientific",
            "Length"
        ]

    def set_mode(self, mode):
        if mode in self.modes:
            self.mode = mode

    def get_mode(self):
        return self.mode

    def get_modes(self):
        return self.modes