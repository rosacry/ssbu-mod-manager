from dataclasses import dataclass, field
from typing import Any


@dataclass
class Character:
    index: int
    ui_chara_id: str
    name_id: str
    fighter_kind: str
    disp_order: int
    name_normal: str = ""
    name_upper: str = ""
    color_num: int = 8
    costume_indices: list[int] = field(default_factory=lambda: list(range(8)))
    chara_ref: Any = None

    @property
    def is_custom(self) -> bool:
        fk = self.fighter_kind
        if fk.startswith("fighter_kind_"):
            fk = fk[len("fighter_kind_"):]
        return fk != self.name_id

    @property
    def logical_disp_order(self):
        if self.disp_order == -1:
            return "Hidden"
        return self.disp_order if self.disp_order >= 0 else self.disp_order + 256

    @property
    def is_hidden(self) -> bool:
        return self.disp_order == -1
