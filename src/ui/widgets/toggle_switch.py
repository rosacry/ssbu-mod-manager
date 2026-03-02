import customtkinter as ctk
from src.ui import theme


class ToggleSwitch(ctk.CTkFrame):
    def __init__(self, parent, text="", command=None, initial=True, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._state = initial
        self._command = command

        self.switch = ctk.CTkSwitch(
            self,
            text=text,
            command=self._on_toggle,
            onvalue=True,
            offvalue=False,
            font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS),
        )
        self.switch.pack(anchor="w")

        if initial:
            self.switch.select()
        else:
            self.switch.deselect()

    def _on_toggle(self):
        self._state = self.switch.get()
        if self._command:
            self._command(self._state)

    @property
    def state(self):
        return self._state

    def set(self, value: bool):
        self._state = value
        if value:
            self.switch.select()
        else:
            self.switch.deselect()
