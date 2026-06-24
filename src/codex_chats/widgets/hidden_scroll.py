"""Scrollable containers that never render visible scrollbar widgets."""

from __future__ import annotations

from textual.containers import Vertical, VerticalScroll


class HiddenScrollbarMixin:
    """Keep scrolling enabled while forcing Textual scrollbar widgets off."""

    @property
    def allow_vertical_scroll(self) -> bool:
        """Allow vertical scrolling even when the scrollbar is hidden."""
        return self.is_scrollable and self.styles.overflow_y != "hidden"

    @property
    def allow_horizontal_scroll(self) -> bool:
        """Allow horizontal scrolling even when the scrollbar is hidden."""
        return self.is_scrollable and self.styles.overflow_x != "hidden"

    def _refresh_scrollbars(self) -> None:
        super()._refresh_scrollbars()
        self.show_horizontal_scrollbar = False
        self.show_vertical_scrollbar = False
        if self._horizontal_scrollbar is not None:
            self.horizontal_scrollbar.display = False
        if self._vertical_scrollbar is not None:
            self.vertical_scrollbar.display = False


class HiddenScrollVertical(HiddenScrollbarMixin, Vertical):
    """Vertical container with scroll support and no visible scrollbars."""


class HiddenVerticalScroll(HiddenScrollbarMixin, VerticalScroll):
    """VerticalScroll variant with no visible scrollbar."""
