"""Chat list widget - scrollable list of conversations for the left panel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message as TextualMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static

from ..models import Conversation
from .directory_list import DirectoryFilter, normalize_directory


class ConversationItem(Static):
    """A single conversation entry in the list."""

    DEFAULT_CSS = """
    ConversationItem {
        height: 3;
        padding: 0 1;
        border-bottom: solid #333333;
        content-align-vertical: middle;
    }
    ConversationItem:hover {
        background: $surface-lighten-1;
    }
    ConversationItem.--selected {
        background: $surface-lighten-1;
        border-left: thick #555555;
    }
    ConversationItem .title-text {
        color: $text;
    }
    ConversationItem .meta-text {
        color: $text-disabled;
    }
    """

    def __init__(self, conversation: Conversation, **kwargs) -> None:
        super().__init__(**kwargs)
        self.conversation = conversation

    def compose(self) -> ComposeResult:
        conv = self.conversation
        indicator = "●" if conv.has_transcript else "○"

        # Truncate title for display
        display_title = conv.title
        if len(display_title) > 38:
            display_title = display_title[:35] + "…"

        line1 = f"{indicator}  {conv.date_label}  {display_title}"

        meta_parts = []
        if conv.msg_count_from_history > 0:
            meta_parts.append(f"{conv.msg_count_from_history} msgs")
        if conv.model:
            meta_parts.append(conv.model)
        if conv.cwd:
            # Show just the last directory component
            cwd_short = conv.cwd.rstrip("/").rsplit("/", 1)[-1]
            meta_parts.append(cwd_short)
        line2 = f"   {'  •  '.join(meta_parts)}" if meta_parts else ""

        yield Static(line1, classes="title-text", markup=False)
        if line2:
            yield Static(line2, classes="meta-text", markup=False)


class DateSeparator(Static):
    """A separator grouping conversations by date."""

    DEFAULT_CSS = """
    DateSeparator {
        height: 3;
        padding: 0 1;
        content-align: left middle;
        background: $surface-lighten-1;
        color: $text-muted;
        text-style: bold;
        border-left: solid #333333;
        border-bottom: solid #333333;
    }
    DateSeparator.today {
        background: #0d1d2e;
        color: #8fc5ff;
        border-left: thick #2f8cff;
    }
    DateSeparator.yesterday {
        background: #261f12;
        color: #e7c16d;
        border-left: thick #b8842a;
    }
    DateSeparator.older {
        background: #10231f;
        color: #82cdbc;
        border-left: thick #2f8f7b;
    }
    """

    def __init__(self, label: str, **kwargs) -> None:
        existing_classes = kwargs.pop("classes", "")
        classes = f"{existing_classes} {label.lower()}".strip()
        super().__init__(f"  {label.upper()}", markup=False, classes=classes, **kwargs)


def get_date_group(dt: datetime, now: datetime | None = None) -> str:
    """Return the logical date bucket for a conversation timestamp."""
    now = now or datetime.now(timezone.utc)

    # Compare local dates instead of strict 24h periods
    local_now = now.astimezone().date()
    local_dt = dt.astimezone().date() if dt.tzinfo else dt.date()
    delta = (local_now - local_dt).days

    if delta <= 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    return "Older"


class ChatList(Widget):
    """Left panel: scrollable, filterable list of conversations."""

    can_focus = True

    DEFAULT_CSS = """
    ChatList {
        width: 1fr;
        height: 1fr;
    }
    ChatList #search-input {
        dock: top;
        margin: 0 0 0 0;
        color: $text;
        background: #071521;
        border: solid #1e3a5f;
    }
    ChatList #search-input:focus {
        border: solid #2f8cff;
        background: #0a1c2d;
    }
    ChatList #conversation-list {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 1;
        scrollbar-background: #151515;
        scrollbar-background-hover: #151515;
        scrollbar-background-active: #151515;
        scrollbar-color: #cfd6e3;
        scrollbar-color-hover: #eef2f8;
        scrollbar-color-active: #ffffff;
    }
    """

    BINDINGS = [
        Binding("up,k", "cursor_up", "Up", show=True),
        Binding("down,j", "cursor_down", "Down", show=True),
        Binding("left,h", "focus_directory", "Directories", show=True),
        Binding("right,l", "focus_right", "Transcript", show=True),
        Binding("enter,o", "open_session", "Open Session", show=False),
    ]

    selected_index: reactive[int] = reactive(0, init=False)
    search_query: reactive[str] = reactive("", init=False)

    class ConversationSelected(TextualMessage):
        """Posted when a conversation is selected."""

        def __init__(self, conversation: Optional[Conversation]) -> None:
            super().__init__()
            self.conversation = conversation

    class OpenSession(TextualMessage):
        """Posted when a conversation should be opened."""

        def __init__(self, conversation: Conversation) -> None:
            super().__init__()
            self.conversation = conversation

    def __init__(
        self, conversations: list[Conversation], **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.all_conversations = conversations
        self._filtered: list[Conversation] = list(conversations)
        self._search_index = self._build_search_index(conversations)
        self.directory_filter: DirectoryFilter = None

    def _build_search_index(
        self, conversations: list[Conversation]
    ) -> dict[str, str]:
        """Precompute lowercase metadata text for fast incremental filtering."""
        index = {}
        for conversation in conversations:
            parts = [
                conversation.title,
                conversation.id,
                conversation.model,
                conversation.cwd,
            ]
            index[conversation.id] = "\n".join(parts).lower()
        return index

    def compose(self) -> ComposeResult:
        yield Input(placeholder="🔍 Search conversations…", id="search-input")
        yield Vertical(id="conversation-list")

    def on_mount(self) -> None:
        """Populate the list on mount."""
        self._rebuild_list()
        if self._filtered:
            self.selected_index = 0
            self._highlight_selected()
            self.post_message(self.ConversationSelected(self._filtered[0]))
        else:
            self.post_message(self.ConversationSelected(None))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter conversations when the search input changes."""
        self.search_query = event.value.lower().strip()
        self._apply_filter()

    def _apply_filter(
        self, preferred_id: str | None = None, fallback_index: int = 0
    ) -> None:
        """Filter conversations based on the search query."""
        query = self.search_query
        conversations = [
            c
            for c in self.all_conversations
            if self.directory_filter is None
            or normalize_directory(c.cwd) == self.directory_filter
        ]
        if not query:
            self._filtered = list(conversations)
        else:
            self._filtered = [
                c
                for c in conversations
                if query in self._search_index.get(c.id, "")
            ]
        self.selected_index = self._resolve_selected_index(
            preferred_id=preferred_id,
            fallback_index=fallback_index,
        )
        self._rebuild_list()
        self._emit_selection()

    def _resolve_selected_index(
        self, preferred_id: str | None = None, fallback_index: int = 0
    ) -> int:
        """Resolve a valid selected index after filtering or refreshing."""
        if not self._filtered:
            return 0

        if preferred_id:
            for index, conversation in enumerate(self._filtered):
                if conversation.id == preferred_id:
                    return index

        return min(max(fallback_index, 0), len(self._filtered) - 1)

    def _emit_selection(self) -> None:
        """Notify the app about the currently selected conversation."""
        if self._filtered:
            self._highlight_selected()
            self.post_message(
                self.ConversationSelected(self._filtered[self.selected_index])
            )
        else:
            self.post_message(self.ConversationSelected(None))

    def _rebuild_list(self) -> None:
        """Rebuild the conversation list widgets."""
        container = self.query_one("#conversation-list", Vertical)
        container.remove_children()

        last_group = None
        for conv in self._filtered:
            group = get_date_group(conv.last_modified)
            if group != last_group:
                container.mount(DateSeparator(group))
                last_group = group

            container.mount(ConversationItem(conv))

    def _highlight_selected(self) -> None:
        """Update the visual highlight for the selected conversation."""
        container = self.query_one("#conversation-list", Vertical)
        items = list(container.query(ConversationItem))
        for i, item in enumerate(items):
            if i == self.selected_index:
                item.add_class("--selected")
            else:
                item.remove_class("--selected")
        if items and 0 <= self.selected_index < len(items):
            items[self.selected_index].scroll_visible()

    def action_cursor_up(self) -> None:
        """Move selection up."""
        if self._filtered and self.selected_index > 0:
            self.selected_index -= 1
            self._highlight_selected()
            self.post_message(
                self.ConversationSelected(self._filtered[self.selected_index])
            )

    def action_cursor_down(self) -> None:
        """Move selection down."""
        if self._filtered and self.selected_index < len(self._filtered) - 1:
            self.selected_index += 1
            self._highlight_selected()
            self.post_message(
                self.ConversationSelected(self._filtered[self.selected_index])
            )

    def action_focus_directory(self) -> None:
        """Move focus to the directory sidebar."""
        self.app.action_focus_directory_panel()

    def action_focus_right(self) -> None:
        """Move focus to the transcript viewer."""
        self.app.action_focus_right_panel()

    def action_open_session(self) -> None:
        """Open the currently selected session."""
        if self._filtered and 0 <= self.selected_index < len(self._filtered):
            self.post_message(
                self.OpenSession(self._filtered[self.selected_index])
            )

    def on_click(self, event) -> None:
        """Handle click on a conversation item."""
        container = self.query_one("#conversation-list", Vertical)
        items = list(container.query(ConversationItem))
        for i, item in enumerate(items):
            if item is event.widget or item in event.widget.ancestors_with_self:
                if self.selected_index == i:
                    self.post_message(self.OpenSession(self._filtered[i]))
                else:
                    self.selected_index = i
                    self._highlight_selected()
                    self.post_message(
                        self.ConversationSelected(self._filtered[i])
                    )
                break

    def remove_conversation(self, sid: str) -> None:
        """Remove a conversation by ID from the lists and rebuild."""
        fallback_index = self.selected_index
        self.all_conversations = [c for c in self.all_conversations if c.id != sid]
        self._search_index.pop(sid, None)
        self._apply_filter(fallback_index=fallback_index)

    def replace_conversations(
        self,
        conversations: list[Conversation],
        *,
        preferred_id: str | None = None,
        fallback_index: int = 0,
    ) -> None:
        """Replace the backing data and refresh the visible list."""
        self.all_conversations = list(conversations)
        self._search_index = self._build_search_index(self.all_conversations)
        self._apply_filter(preferred_id=preferred_id, fallback_index=fallback_index)

    def set_directory_filter(
        self,
        directory: DirectoryFilter,
        *,
        preferred_id: str | None = None,
        fallback_index: int = 0,
    ) -> None:
        """Set the active directory filter and refresh visible conversations."""
        self.directory_filter = directory
        self._apply_filter(preferred_id=preferred_id, fallback_index=fallback_index)
