"""Directory sidebar widget for filtering conversations by working directory."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message as TextualMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..models import Conversation


DirectoryFilter = Optional[str]


@dataclass(frozen=True)
class DirectoryEntry:
    """A directory filter entry shown in the sidebar."""

    path: DirectoryFilter
    label: str
    detail: str
    count: int


def normalize_directory(cwd: str) -> str:
    """Normalize a conversation cwd for directory filtering."""
    return cwd or ""


class DirectoryItem(Static):
    """A single directory row."""

    DEFAULT_CSS = """
    DirectoryItem {
        height: 3;
        padding: 0 1;
        border-bottom: solid #333333;
        content-align-vertical: middle;
    }
    DirectoryItem:hover {
        background: $surface-lighten-1;
    }
    DirectoryItem.--selected {
        background: $surface-lighten-1;
        border-left: thick #555555;
    }
    DirectoryItem.--active {
        text-style: bold;
    }
    DirectoryItem .directory-label {
        color: $text;
    }
    DirectoryItem .directory-detail {
        color: $text-disabled;
    }
    """

    def __init__(self, entry: DirectoryEntry, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entry = entry

    def compose(self) -> ComposeResult:
        count_label = f"{self.entry.count} chat"
        if self.entry.count != 1:
            count_label += "s"
        yield Static(self.entry.label, classes="directory-label", markup=False)
        yield Static(
            f"{count_label}  {self.entry.detail}",
            classes="directory-detail",
            markup=False,
        )


class DirectoryList(Widget):
    """Leftmost sidebar: filter conversations by working directory."""

    can_focus = True

    DEFAULT_CSS = """
    DirectoryList {
        width: 30;
        min-width: 24;
        max-width: 40;
        height: 1fr;
        border-right: solid #333333;
    }
    DirectoryList:focus {
        border: solid #555555;
    }
    DirectoryList #directory-list {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 0 0;
    }
    """

    BINDINGS = [
        Binding("up,k", "cursor_up", "Up", show=False),
        Binding("down,j", "cursor_down", "Down", show=False),
        Binding("right,l", "focus_chat_list", "Focus Chats", show=False),
        Binding("enter", "select_directory", "Select Directory", show=False),
    ]

    selected_index: reactive[int] = reactive(0, init=False)

    class DirectorySelected(TextualMessage):
        """Posted when a directory filter is selected."""

        def __init__(self, directory: DirectoryFilter) -> None:
            super().__init__()
            self.directory = directory

    def __init__(self, conversations: list[Conversation], **kwargs) -> None:
        super().__init__(**kwargs)
        self.conversations = conversations
        self.entries = self._build_entries(conversations)
        self.active_directory: DirectoryFilter = None

    def compose(self) -> ComposeResult:
        yield Vertical(id="directory-list")

    def on_mount(self) -> None:
        """Populate the directory list."""
        self._rebuild_list()
        self._highlight_selected()

    def _build_entries(
        self, conversations: list[Conversation]
    ) -> list[DirectoryEntry]:
        """Build sorted directory entries from conversations."""
        grouped: dict[str, list[Conversation]] = defaultdict(list)
        for conversation in conversations:
            grouped[normalize_directory(conversation.cwd)].append(conversation)

        entries = [
            DirectoryEntry(
                path=None,
                label="All",
                detail="directories",
                count=len(conversations),
            )
        ]

        sorted_dirs = sorted(
            grouped.items(),
            key=lambda item: max(c.last_modified for c in item[1]),
            reverse=True,
        )
        for path, grouped_conversations in sorted_dirs:
            label = "Unknown" if not path else Path(path).name or path
            detail = "" if not path else path
            if len(detail) > 28:
                detail = "..." + detail[-25:]
            entries.append(
                DirectoryEntry(
                    path=path,
                    label=label,
                    detail=detail,
                    count=len(grouped_conversations),
                )
            )
        return entries

    def _rebuild_list(self) -> None:
        """Rebuild directory row widgets."""
        container = self.query_one("#directory-list", Vertical)
        container.remove_children()
        for entry in self.entries:
            container.mount(DirectoryItem(entry))

    def _highlight_selected(self) -> None:
        """Update selected and active visual states."""
        container = self.query_one("#directory-list", Vertical)
        items = list(container.query(DirectoryItem))
        for index, item in enumerate(items):
            if index == self.selected_index:
                item.add_class("--selected")
            else:
                item.remove_class("--selected")

            if item.entry.path == self.active_directory:
                item.add_class("--active")
            else:
                item.remove_class("--active")

        if items and 0 <= self.selected_index < len(items):
            items[self.selected_index].scroll_visible()

    def _active_index(self) -> int:
        """Return the index for the active directory."""
        for index, entry in enumerate(self.entries):
            if entry.path == self.active_directory:
                return index
        return 0

    def _select_current(self) -> None:
        """Apply the currently highlighted directory filter."""
        if not self.entries:
            return
        self.active_directory = self.entries[self.selected_index].path
        self._highlight_selected()
        self.post_message(self.DirectorySelected(self.active_directory))

    def action_cursor_up(self) -> None:
        """Move selection up."""
        if self.selected_index > 0:
            self.selected_index -= 1
            self._highlight_selected()

    def action_cursor_down(self) -> None:
        """Move selection down."""
        if self.selected_index < len(self.entries) - 1:
            self.selected_index += 1
            self._highlight_selected()

    def action_focus_chat_list(self) -> None:
        """Move focus to the conversation list."""
        self.app.action_focus_list()

    def action_select_directory(self) -> None:
        """Select the highlighted directory."""
        self._select_current()

    def on_click(self, event) -> None:
        """Handle click on a directory row."""
        container = self.query_one("#directory-list", Vertical)
        items = list(container.query(DirectoryItem))
        for index, item in enumerate(items):
            if item is event.widget or item in event.widget.ancestors_with_self:
                self.selected_index = index
                self._select_current()
                break

    def replace_conversations(
        self, conversations: list[Conversation]
    ) -> DirectoryFilter:
        """Replace backing data and preserve active directory when possible."""
        self.conversations = list(conversations)
        self.entries = self._build_entries(self.conversations)
        available = {entry.path for entry in self.entries}
        if self.active_directory not in available:
            self.active_directory = None
        self.selected_index = self._active_index()
        self._rebuild_list()
        self._highlight_selected()
        return self.active_directory
