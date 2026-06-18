"""UI button placement — clear of hand zones, easy target hold."""

from __future__ import annotations

from typing import List, Tuple


class UILayout:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._rebuild()

    def resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._rebuild()

    def _rebuild(self) -> None:
        w, h = self.width, self.height
        self.hand_zone_bottom = int(h * 0.70)
        self.left_hand_margin = int(w * 0.30)
        self.right_hand_margin = int(w * 0.70)

        list_w = min(500, int(w * 0.42))
        self.mission_list_x = 36
        self.mission_list_w = list_w
        self.mission_start_y = 118
        self.mission_row_h = 38

        pw = min(380, int(w * 0.32))
        self.preview_rect = (w - pw - 24, 112, pw, int(h * 0.40))

        # Center-screen action buttons — well above holographic hands
        btn_w, btn_h = 320, 56
        btn_y = int(h * 0.54)
        self.deploy_btn = (w // 2 - btn_w // 2, btn_y, btn_w, btn_h)
        self.confirm_btn = (w // 2 - btn_w // 2, btn_y, btn_w, btn_h)
        self.aar_btn = (w // 2 - btn_w // 2, btn_y, btn_w, btn_h)
        self.hint_y = h - 48

    def mission_row_rects(self, count: int) -> List[Tuple[int, int, int, int]]:
        return [
            (self.mission_list_x, self.mission_start_y + i * self.mission_row_h, self.mission_list_w, self.mission_row_h - 4)
            for i in range(count)
        ]

    def cordon_rects(self, count: int) -> List[Tuple[int, int, int, int]]:
        return [(40, 78 + i * 54, self.width - 80, 46) for i in range(count)]
