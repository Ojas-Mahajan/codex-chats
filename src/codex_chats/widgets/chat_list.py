"""Chat list widget — scrollable list of conversations for the left panel."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message as TextualMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static

from ..models import Conversation


class ConversationItem(Static):
    """A single conversation entry in the list."""

    DEFAULT_CSS = """
    ConversationItem {
        height: 3;
        padding: 0 1;
        border-bottom: solid $surface-lighten-2;
        content-align-vertical: middle;
    }
    ConversationItem:hover {
        background: $surface-lighten-1;
    }
    ConversationItem.--selected {
        background: $accent 30%;
        border-left: thick $accent;
    }
    ConversationItem .date-badge {
        color: $text-muted;
    }
    ConversationItem .title-text {
        color: $text;
    }
    ConversationItem .meta-text {
        color: $text-disabled;
    }
    ConversationItem .has-logs {
        color: $success;
    }
    ConversationItem .no-logs {
        color: $text-disabled;
    }
    """

    def __init__(self, conversation: Conversation, **kwargs) -> None:
        super().__init__(**kwargs)
        self.conversation = conversation

    def compose(self) -> ComposeResult:
        conv = self.conversation
        log_indicator = "●" if conv.has_logs else "○"

        # Truncate title for display
        display_title = conv.title
        if len(display_title) > 38:
            display_title = display_title[:35] + "…"

        line1 = f"{log_indicator}  {conv.date_label}  {display_title}"
        meta_parts = [conv.size_label]
        if conv.has_logs:
            meta_parts.append(f"{conv.message_count} msgs")
        if conv.artifacts:
            meta_parts.append(f"{len(conv.artifacts)} artifacts")
        line2 = f"   {'  •  '.join(meta_parts)}"

        yield Static(line1, classes="title-text", markup=False)
        yield Static(line2, classes="meta-text", markup=False)


class ChatList(Widget):
    """Left panel: scrollable, filterable list of conversations."""

    DEFAULT_CSS = """
    ChatList {
        width: 1fr;
        height: 1fr;
    }
    ChatList #search-input {
        dock: top;
        margin: 0 0 0 0;
        border: solid $primary;
    }
    ChatList #conversation-list {
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("up,k", "cursor_up", "Up", show=False),
        Binding("down,j", "cursor_down", "Down", show=False),
    ]

    selected_index: reactive[int] = reactive(0, init=False)
    search_query: reactive[str] = reactive("", init=False)

    class ConversationSelected(TextualMessage):
        """Posted when a conversation is selected."""

        def __init__(self, conversation: Conversation) -> None:
            super().__init__()
            self.conversation = conversation

    def __init__(
        self, conversations: list[Conversation], **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.all_conversations = conversations
        self._filtered: list[Conversation] = list(conversations)

    def compose(self) -> ComposeResult:
        yield Input(placeholder="🔍 Search conversations…", id="search-input")
        yield Vertical(id="conversation-list")

    def on_mount(self) -> None:
        """Populate the list on mount."""
        self._rebuild_list()
        # Select the first item if available
        if self._filtered:
            self.selected_index = 0
            self._highlight_selected()
            self.post_message(self.ConversationSelected(self._filtered[0]))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter conversations when the search input changes."""
        self.search_query = event.value.lower().strip()
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Filter conversations based on the search query."""
        query = self.search_query
        if not query:
            self._filtered = list(self.all_conversations)
        else:
            self._filtered = [
                c
                for c in self.all_conversations
                if query in c.title.lower()
                or query in c.id.lower()
                or any(
                    query in (m.content or "").lower()
                    for m in c.messages
                    if m.content
                )
            ]
        self.selected_index = 0
        self._rebuild_list()
        if self._filtered:
            self._highlight_selected()
            self.post_message(self.ConversationSelected(self._filtered[0]))

    def _rebuild_list(self) -> None:
        """Rebuild the conversation list widgets."""
        container = self.query_one("#conversation-list", Vertical)
        container.remove_children()
        for i, conv in enumerate(self._filtered):
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
        # Scroll the selected item into view
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

    def on_click(self, event) -> None:
        """Handle click on a conversation item."""
        # Find which ConversationItem was clicked
        container = self.query_one("#conversation-list", Vertical)
        items = list(container.query(ConversationItem))
        for i, item in enumerate(items):
            if item is event.widget or item in event.widget.ancestors_with_self:
                self.selected_index = i
                self._highlight_selected()
                self.post_message(
                    self.ConversationSelected(self._filtered[i])
                )
                break
