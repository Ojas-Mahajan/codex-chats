"""Chat list widget - scrollable list of conversations for the left panel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual import on
from textual.message import Message as TextualMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Select, Static
from textual.widgets._select import Option, SelectCurrent, SelectOverlay, Text

from ..models import Conversation
from .directory_list import DirectoryFilter, normalize_directory
from .hidden_scroll import HiddenScrollVertical


@dataclass(frozen=True)
class ConversationListEntry:
    """A visible conversation row for one activity date."""

    conversation: Conversation
    activity_date: date

    @property
    def date_label(self) -> str:
        """Return a short date label like 'Jun 22'."""
        return self.activity_date.strftime("%b %d")


class ConversationItem(Static):
    """A single conversation entry in the list."""

    DEFAULT_CSS = """
    ConversationItem {
        height: 3;
        padding: 0 1;
        background: #171717;
        border-bottom: solid #2f3336;
        content-align-vertical: middle;
    }
    ConversationItem:hover {
        background: #232629;
    }
    ConversationItem.--selected {
        background: #30343a;
        border-left: thick #c9d1d9;
    }
    ConversationItem .title-text {
        color: #d7dde5;
    }
    ConversationItem.--selected .title-text {
        color: #f2f5f8;
    }
    ConversationItem .meta-text {
        color: #8b949e;
    }
    ConversationItem.--selected .meta-text {
        color: #c9d1d9;
    }
    """

    def __init__(self, entry: ConversationListEntry, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entry = entry
        self.conversation = entry.conversation

    def compose(self) -> ComposeResult:
        conv = self.conversation
        indicator = "●" if conv.has_transcript else "○"

        # Truncate title for display
        display_title = conv.title
        if len(display_title) > 38:
            display_title = display_title[:35] + "…"

        line1 = f"{indicator}  {self.entry.date_label}  {display_title}"

        meta_parts = []
        if self.entry.activity_date != conv.local_last_modified.date():
            meta_parts.append(f"last {conv.date_label}")
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
        background: #202124;
        color: #aeb6c2;
        text-style: bold;
        border-left: solid #3f454c;
        border-bottom: solid #30363d;
    }
    DateSeparator.today {
        background: #16212d;
        color: #9cc7f1;
        border-left: thick #6f9fcf;
    }
    DateSeparator.yesterday {
        background: #242016;
        color: #dbc37b;
        border-left: thick #a98b45;
    }
    DateSeparator.older {
        background: #14231f;
        color: #8bc9bb;
        border-left: thick #4e9a88;
    }
    """

    def __init__(self, label: str, **kwargs) -> None:
        existing_classes = kwargs.pop("classes", "")
        classes = f"{existing_classes} {label.lower()}".strip()
        super().__init__(f"  {label.upper()}", markup=False, classes=classes, **kwargs)


class NonRepeatingSelect(Select):
    """A Select that does not repeat the current value in its open menu."""

    def _setup_options_renderables(self) -> None:
        current_value = self.value
        self._overlay_option_indexes: list[int] = []
        options: list[Option] = []

        for index, (prompt, value) in enumerate(self._options):
            if value == current_value:
                continue

            options.append(
                Option(Text(self.prompt, style="dim"))
                if value == self.NULL
                else Option(prompt)
            )
            self._overlay_option_indexes.append(index)

        option_list = self.query_one(SelectOverlay)
        option_list.clear_options()
        option_list.add_options(options)

    def _watch_expanded(self, expanded: bool) -> None:
        try:
            overlay = self.query_one(SelectOverlay)
        except Exception:
            return

        self.set_class(expanded, "-expanded")
        if expanded:
            self._setup_options_renderables()
            overlay.focus(scroll_visible=False)
            overlay.select(0 if overlay.option_count else None)
            self.query_one(SelectCurrent).has_value = self.value != self.NULL

    @on(SelectOverlay.UpdateSelection)
    def _update_selection(self, event: SelectOverlay.UpdateSelection) -> None:
        event.stop()
        option_index = self._overlay_option_indexes[event.option_index]
        value = self._options[option_index][1]
        if value != self.value:
            self.value = value

        self.focus()
        self.expanded = False


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


def get_date_group_for_date(activity_date: date, now: datetime | None = None) -> str:
    """Return the logical date bucket for a local activity date."""
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone().date()
    delta = (local_now - activity_date).days

    if delta <= 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    return "Older"


class ChatList(Widget):
    """Left panel: scrollable, filterable list of conversations."""

    can_focus = True
    ALL_MODELS_FILTER = "all"
    ALL_GPT_MODELS_FILTER = "all_gpt"
    CODEX_GPT_MODELS = (
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
        "gpt-5.2",
    )

    DATE_FILTER_OPTIONS = [
        ("All dates", "all"),
        ("Today", "today"),
        ("Yesterday", "yesterday"),
        ("Last 7 days", "last_7"),
        ("Last 30 days", "last_30"),
    ]

    DEFAULT_CSS = """
    ChatList {
        width: 1fr;
        height: 1fr;
        background: #171717;
    }
    ChatList #controls {
        dock: top;
        height: 6;
        background: #171717;
    }
    ChatList #search-input {
        height: 3;
        margin: 0 0 0 0;
        color: #d7dde5;
        background: #121416;
        border: solid #3f454c;
    }
    ChatList #search-input:focus {
        border: solid #6f8193;
        background: #161b20;
    }
    ChatList #filter-row {
        height: 3;
        background: #171717;
    }
    ChatList Select {
        width: 1fr;
        height: 3;
        color: #d7dde5;
        background: #121416;
        border: solid #3f454c;
    }
    ChatList Select:focus {
        border: solid #6f8193;
        background: #161b20;
    }
    ChatList #conversation-list {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 0 0;
    }
    """

    BINDINGS = [
        Binding("up,k", "cursor_up", "Up", show=True),
        Binding("down,j", "cursor_down", "Down", show=True),
        Binding("enter,o", "open_session", "Open Session", show=False),
    ]

    selected_index: reactive[int] = reactive(0, init=False)
    search_query: reactive[str] = reactive("", init=False)
    date_filter: reactive[str] = reactive("all", init=False)
    model_filter: reactive[str] = reactive("all", init=False)

    class ConversationSelected(TextualMessage):
        """Posted when a conversation is selected."""

        def __init__(
            self,
            conversation: Optional[Conversation],
            activity_date: date | None = None,
        ) -> None:
            super().__init__()
            self.conversation = conversation
            self.activity_date = activity_date

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
        self._filtered: list[ConversationListEntry] = self._build_entries(conversations)
        self._search_index = self._build_search_index(conversations)
        self.directory_filter: DirectoryFilter = None

    def _activity_dates(self, conversation: Conversation) -> tuple[date, ...]:
        """Return local activity dates for a conversation."""
        return conversation.activity_dates or (conversation.local_last_modified.date(),)

    def _build_entries(
        self, conversations: list[Conversation]
    ) -> list[ConversationListEntry]:
        """Build visible rows, including one row per active day."""
        entries = [
            ConversationListEntry(conversation, activity_date)
            for conversation in conversations
            for activity_date in self._activity_dates(conversation)
        ]
        return sorted(
            entries,
            key=lambda entry: (entry.activity_date, entry.conversation.last_modified),
            reverse=True,
        )

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

    def _model_options(self) -> list[tuple[str, str]]:
        """Build selectable model filter options from the current conversations."""
        discovered_models = {c.model for c in self.all_conversations if c.model}
        extra_models = sorted(discovered_models.difference(self.CODEX_GPT_MODELS))
        return [
            ("All models", self.ALL_MODELS_FILTER),
            ("All GPT models", self.ALL_GPT_MODELS_FILTER),
            *[(model, model) for model in self.CODEX_GPT_MODELS],
            *[(model, model) for model in extra_models],
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="controls"):
            yield Input(placeholder="🔍 Search conversations…", id="search-input")
            with Horizontal(id="filter-row"):
                yield Select(
                    self.DATE_FILTER_OPTIONS,
                    value=self.date_filter,
                    allow_blank=False,
                    compact=True,
                    id="date-filter",
                )
                yield NonRepeatingSelect(
                    self._model_options(),
                    value=self.model_filter,
                    allow_blank=False,
                    compact=True,
                    id="model-filter",
                )
        yield HiddenScrollVertical(id="conversation-list")

    def on_mount(self) -> None:
        """Populate the list on mount."""
        self._rebuild_list()
        if self._filtered:
            self.selected_index = 0
            self._highlight_selected()
            entry = self._filtered[0]
            self.post_message(
                self.ConversationSelected(entry.conversation, entry.activity_date)
            )
        else:
            self.post_message(self.ConversationSelected(None))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter conversations when the search input changes."""
        self.search_query = event.value.lower().strip()
        self._apply_filter()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Apply date and model filters when either select changes."""
        if event.select.id == "date-filter":
            self.date_filter = str(event.value)
        elif event.select.id == "model-filter":
            self.model_filter = str(event.value)
        else:
            return
        self._apply_filter()

    def _matches_date_filter(self, activity_date: date) -> bool:
        """Return whether a conversation matches the selected date filter."""
        if self.date_filter == "all":
            return True

        local_now = datetime.now(timezone.utc).astimezone().date()
        delta = (local_now - activity_date).days

        if self.date_filter == "today":
            return delta <= 0
        if self.date_filter == "yesterday":
            return delta == 1
        if self.date_filter == "last_7":
            return delta <= 6
        if self.date_filter == "last_30":
            return delta <= 29
        return True

    def _matches_model_filter(self, conversation: Conversation) -> bool:
        """Return whether a conversation matches the selected model filter."""
        if self.model_filter == self.ALL_MODELS_FILTER:
            return True
        if self.model_filter == self.ALL_GPT_MODELS_FILTER:
            return conversation.model.lower().startswith("gpt")
        return conversation.model == self.model_filter

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
        conversations = [
            c
            for c in conversations
            if self._matches_model_filter(c)
        ]
        if query:
            conversations = [
                c for c in conversations if query in self._search_index.get(c.id, "")
            ]

        entries = self._build_entries(conversations)
        self._filtered = [
            entry
            for entry in entries
            if self._matches_date_filter(entry.activity_date)
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
            for index, entry in enumerate(self._filtered):
                if entry.conversation.id == preferred_id:
                    return index

        return min(max(fallback_index, 0), len(self._filtered) - 1)

    def _emit_selection(self) -> None:
        """Notify the app about the currently selected conversation."""
        if self._filtered:
            self._highlight_selected()
            entry = self._filtered[self.selected_index]
            self.post_message(
                self.ConversationSelected(entry.conversation, entry.activity_date)
            )
        else:
            self.post_message(self.ConversationSelected(None))

    def _rebuild_list(self) -> None:
        """Rebuild the conversation list widgets."""
        container = self.query_one("#conversation-list", HiddenScrollVertical)
        container.remove_children()

        last_group = None
        for entry in self._filtered:
            group = get_date_group_for_date(entry.activity_date)
            if group != last_group:
                container.mount(DateSeparator(group))
                last_group = group

            container.mount(ConversationItem(entry))

    def _highlight_selected(self) -> None:
        """Update the visual highlight for the selected conversation."""
        container = self.query_one("#conversation-list", HiddenScrollVertical)
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
            entry = self._filtered[self.selected_index]
            self.post_message(
                self.ConversationSelected(entry.conversation, entry.activity_date)
            )

    def action_cursor_down(self) -> None:
        """Move selection down."""
        if self._filtered and self.selected_index < len(self._filtered) - 1:
            self.selected_index += 1
            self._highlight_selected()
            entry = self._filtered[self.selected_index]
            self.post_message(
                self.ConversationSelected(entry.conversation, entry.activity_date)
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
            entry = self._filtered[self.selected_index]
            self.post_message(self.OpenSession(entry.conversation))

    def on_click(self, event) -> None:
        """Handle click on a conversation item."""
        container = self.query_one("#conversation-list", HiddenScrollVertical)
        items = list(container.query(ConversationItem))
        for i, item in enumerate(items):
            if item is event.widget or item in event.widget.ancestors_with_self:
                if self.selected_index == i:
                    self.post_message(self.OpenSession(self._filtered[i].conversation))
                else:
                    self.selected_index = i
                    self._highlight_selected()
                    entry = self._filtered[i]
                    self.post_message(
                        self.ConversationSelected(
                            entry.conversation,
                            entry.activity_date,
                        )
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
        self._refresh_model_filter_options()
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

    def _refresh_model_filter_options(self) -> None:
        """Refresh model select options after the backing conversations change."""
        options = self._model_options()
        available_values = {value for _, value in options}
        if self.model_filter not in available_values:
            self.model_filter = self.ALL_MODELS_FILTER

        try:
            model_select = self.query_one("#model-filter", Select)
        except Exception:
            return

        model_select.set_options(options)
        model_select.value = self.model_filter
