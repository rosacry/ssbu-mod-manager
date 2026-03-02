from dataclasses import dataclass, field
from typing import Any

DEFAULT_COSTUME_COUNT = 8
HIDDEN_DISP_ORDER = -1
UNSIGNED_BYTE_WRAP = 256
SIGNED_BYTE_MAX = 127


@dataclass
class Character:
    index: int
    ui_chara_id: str
    name_id: str
    fighter_kind: str
    disp_order: int
    name_normal: str = ""
    name_upper: str = ""
    color_num: int = DEFAULT_COSTUME_COUNT
    costume_indices: list[int] = field(default_factory=lambda: list(range(DEFAULT_COSTUME_COUNT)))
    chara_ref: Any = None

    @property
    def is_custom(self) -> bool:
        fk = self.fighter_kind
        if fk.startswith("fighter_kind_"):
            fk = fk[len("fighter_kind_"):]
        return fk != self.name_id

    @property
    def logical_disp_order(self):
        if self.disp_order == HIDDEN_DISP_ORDER:
            return "Hidden"
        return self.disp_order if self.disp_order >= 0 else self.disp_order + UNSIGNED_BYTE_WRAP

    @property
    def is_hidden(self) -> bool:
        return self.disp_order == HIDDEN_DISP_ORDER
