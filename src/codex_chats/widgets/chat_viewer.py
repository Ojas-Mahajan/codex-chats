"""Chat viewer widget - displays a Codex conversation's full transcript."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

from rich._wrap import divide_line
from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.geometry import Size
from textual.selection import Selection
from textual.strip import Strip
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

from ..models import Conversation, Message
from ..parser import parse_session_file
from .hidden_scroll import HiddenVerticalScroll


IMAGE_TAG_RE = re.compile(
    r"<image\b(?P<attrs>[^>]*)>.*?</image>",
    flags=re.IGNORECASE | re.DOTALL,
)
IMAGE_NAME_RE = re.compile(
    r'name=(?:\[([^\]]+)\]|"([^"]+)"|([^\s>]+))',
    flags=re.IGNORECASE,
)


def _format_datetime(timestamp: datetime | None) -> str:
    """Format a timestamp for display in the user's local timezone."""
    if timestamp:
        local_timestamp = timestamp.astimezone() if timestamp.tzinfo else timestamp
        return local_timestamp.strftime("%b %d, %Y  %I:%M %p")
    return ""


def _format_timestamp(msg: Message) -> str:
    """Format a message timestamp for display."""
    return _format_datetime(msg.timestamp)


def _format_tool_calls(msg: Message) -> str:
    """Format tool calls as a readable summary."""
    if not msg.tool_calls:
        return ""

    lines = []
    for tc in msg.tool_calls:
        args_summary = []
        for k, v in tc.args.items():
            val_str = str(v)
            if len(val_str) > 100:
                val_str = val_str[:97] + "…"
            args_summary.append(f"    {k}: {val_str}")
        args_block = "\n".join(args_summary)
        lines.append(f"  🔧 {tc.name}\n{args_block}")

    return "\n".join(lines)


def _compact_attachments(content: str) -> str:
    """Replace verbose attachment tags with compact reader-friendly labels."""

    def replace_image(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        name_match = IMAGE_NAME_RE.search(attrs)
        label = "image"
        if name_match:
            label = next(group for group in name_match.groups() if group)
        return f"[Image attachment: {label}]"

    content = IMAGE_TAG_RE.sub(replace_image, content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


# Control characters (other than tab and newline) would corrupt the terminal
# output when written as raw segments.
_CONTROL_CHARS = {code: None for code in range(32) if code not in (9, 10)}
_CONTROL_CHARS[127] = None


def _message_role(msg: Message) -> str:
    """Return the transcript style role for a message."""
    if msg.msg_type == "reasoning":
        return "thinking"
    if msg.msg_type in ("function_call", "function_call_output"):
        return "tool"
    if msg.role == "user":
        return "user"
    if msg.role == "assistant":
        return "assistant"
    return "tool"


def _message_text(msg: Message) -> str:
    """Build a compact plain-text block for a message."""
    ts = _format_timestamp(msg)
    lines = [f"{msg.role_icon}  {msg.role_label}  -  {msg.display_type}"]

    if ts:
        lines.append(f"   {ts}")

    if msg.content:
        content = _compact_attachments(msg.content)
        if len(content) > 3000:
            content = (
                content[:3000]
                + "\n\n[Content truncated for display]"
            )
        lines.extend(["", content])

    if msg.tool_calls:
        tools_text = _format_tool_calls(msg)
        lines.extend(["", tools_text])

    return "\n".join(lines).translate(_CONTROL_CHARS)


def _wrap_text(body: str, width: int) -> list[str]:
    """Wrap plain text to a cell width, folding words longer than a line."""
    lines: list[str] = []
    for line in body.split("\n"):
        line = line.expandtabs(8)
        if cell_len(line) <= width:
            lines.append(line)
            continue
        start = 0
        for end in [*divide_line(line, width, fold=True), len(line)]:
            piece = line[start:end]
            lines.append(piece.rstrip() if cell_len(piece) > width else piece)
            start = end
    return lines


class _Row(NamedTuple):
    """One rendered transcript line."""

    role: str
    text: str | None = None
    separator: bool = False


class TranscriptView(Widget):
    """All message blocks of a transcript, rendered as a single widget.

    Mounting a widget per message made switching conversations slow, since
    hundreds of widgets had to be styled and laid out on every change. This
    widget wraps the transcript once per width and paints only visible lines.
    """

    ALLOW_SELECT = True
    PADDING_X = 2

    COMPONENT_CLASSES = {
        "transcript--user",
        "transcript--assistant",
        "transcript--thinking",
        "transcript--tool",
        "transcript--separator",
    }

    DEFAULT_CSS = """
    TranscriptView {
        height: auto;
        background: #171717;
    }
    TranscriptView > .transcript--user {
        background: #202124;
        color: #d7dde5;
    }
    TranscriptView > .transcript--assistant {
        background: #171717;
        color: #d7dde5;
    }
    TranscriptView > .transcript--thinking {
        background: #15191d;
        color: #aeb6c2;
    }
    TranscriptView > .transcript--tool {
        background: #141619;
        color: #9aa4af;
    }
    TranscriptView > .transcript--separator {
        color: #30363d;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._blocks: list[tuple[str, str]] = []
        self._layout_width: int | None = None
        self._rows: list[_Row] = []
        self._block_starts: list[int] = []
        self._strip_cache: dict[int, Strip] = {}

    def set_messages(self, messages: list[Message]) -> None:
        """Replace the displayed messages."""
        if self.text_selection is not None:
            self.screen.clear_selection()
        self._blocks = [(_message_role(msg), _message_text(msg)) for msg in messages]
        self._layout_width = None
        self._rows = []
        self._block_starts = []
        self._strip_cache.clear()
        self.refresh(layout=True)

    def _ensure_layout(self, width: int) -> None:
        """Wrap every message block to the given width, once per width."""
        # Skip the zero width seen before the first layout; wrapping at one
        # cell per line would be very expensive.
        if width == self._layout_width or width <= 0:
            return

        inner_width = max(1, width - 2 * self.PADDING_X)
        rows: list[_Row] = []
        block_starts: list[int] = []
        for role, body in self._blocks:
            block_starts.append(len(rows))
            rows.append(_Row(role))
            rows.extend(_Row(role, line) for line in _wrap_text(body, inner_width))
            rows.append(_Row(role))
            rows.append(_Row(role, separator=True))

        self._rows = rows
        self._block_starts = block_starts
        self._layout_width = width
        self._strip_cache.clear()

    def block_offset(self, index: int) -> int:
        """Return the first line of a message block at the last laid-out width."""
        return self._block_starts[index] if self._block_starts else 0

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        self._ensure_layout(width)
        return len(self._rows)

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        self._ensure_layout(width)
        if y >= len(self._rows):
            return Strip.blank(width, self.rich_style)

        selection = self.text_selection
        if selection is None and (cached := self._strip_cache.get(y)) is not None:
            return cached

        row = self._rows[y]
        style = self.get_component_rich_style(f"transcript--{row.role}")
        if row.separator:
            line_style = style + Style(
                color=self.get_component_rich_style("transcript--separator").color
            )
            strip = Strip([Segment("─" * width, line_style)], width).apply_offsets(0, y)
        elif row.text is None:
            strip = Strip.blank(width, style).apply_offsets(0, y)
        else:
            text = Text(row.text, end="")
            if selection is not None and (span := selection.get_span(y)) is not None:
                start, end = span
                text.stylize(
                    self.screen.get_component_rich_style("screen--selection"),
                    start,
                    len(text) if end == -1 else end,
                )
            # Selection offsets map clicks back to positions in the line text;
            # the left padding counts as the start of the line.
            padding = Segment(
                " " * self.PADDING_X,
                style + Style.from_meta({"offset": (0, y)}),
            )
            content = Strip(
                Segment.apply_style(text.render(self.app.console), style)
            ).apply_offsets(0, y)
            strip = (
                Strip([padding, *content])
                .extend_cell_length(width, style)
                .crop(0, width)
            )

        if selection is None:
            self._strip_cache[y] = strip
        return strip

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        text = "\n".join(row.text or "" for row in self._rows)
        return selection.extract(text), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self._strip_cache.clear()
        self.refresh()

    def notify_style_update(self) -> None:
        super().notify_style_update()
        self._strip_cache.clear()


class EmptyState(Static):
    """Shown when no conversation is selected or has no transcript."""

    DEFAULT_CSS = """
    EmptyState {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        background: #171717;
        color: #8b949e;
        text-style: italic;
    }
    """


class ConversationHeader(Static):
    """Header showing conversation title, ID, and metadata."""

    DEFAULT_CSS = """
    ConversationHeader {
        height: 5;
        padding: 0 1;
        background: #202124;
        border-bottom: solid #5b626b;
    }
    ConversationHeader #header-content {
        width: 1fr;
        height: 5;
    }
    ConversationHeader .viewer-label {
        height: 1;
        text-style: bold;
        color: #f2f5f8;
    }
    ConversationHeader .conv-title {
        height: 1;
        text-style: bold;
        color: #d7dde5;
    }
    ConversationHeader .conv-id {
        height: 1;
        color: #aeb6c2;
    }
    ConversationHeader .conv-meta {
        height: 2;
        color: #8b949e;
        margin-top: 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="header-content"):
            yield Static("Transcript", classes="viewer-label", markup=False)
            yield Static(classes="conv-title", markup=False)
            yield Static(classes="conv-id", markup=False)
            yield Static(classes="conv-meta", markup=False)

    def show_conversation(self, conv: Conversation) -> None:
        """Update the header in place for a conversation."""
        meta_parts = []
        started_at = _format_datetime(conv.started_at)
        if started_at:
            meta_parts.append(f"Started: {started_at}")
        meta_parts.append(f"Last active: {_format_datetime(conv.last_modified)}")
        if conv.model:
            meta_parts.append(f"Model: {conv.model}")
        if conv.cwd:
            meta_parts.append(f"Dir: {conv.cwd}")
        if conv.message_count > 0:
            meta_parts.append(f"Messages: {conv.message_count}")

        self.query_one(".conv-title", Static).update(f"📋  {conv.title}")
        self.query_one(".conv-id", Static).update(f"ID: {conv.id}")
        self.query_one(".conv-meta", Static).update("  •  ".join(meta_parts))


class ChatViewer(Widget):
    """Right panel: displays the selected conversation's transcript."""

    can_focus = True

    # Quiet period after a render during which further selections are
    # deferred, so a held arrow key doesn't re-render every transcript.
    RENDER_INTERVAL = 0.12

    BINDINGS = [
        Binding("up,k", "scroll_up", "Scroll Up", show=True),
        Binding("down,j", "scroll_down", "Scroll Down", show=True),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Top", show=False),
        Binding("end", "scroll_end", "Bottom", show=False),
    ]

    DEFAULT_CSS = """
    ChatViewer {
        width: 1fr;
        height: 1fr;
        background: #171717;
    }
    ChatViewer #viewer-header {
        height: 5;
    }
    ChatViewer #viewer-scroll {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 0 0;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pending: tuple[Conversation, date | None] | None = None
        self._render_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        # These widgets stay mounted and are updated in place: removing and
        # mounting widgets on every selection costs extra layout passes.
        with Vertical(id="viewer-header"):
            yield ConversationHeader(id="conversation-header")
        with HiddenVerticalScroll(id="viewer-scroll"):
            yield EmptyState(id="viewer-empty")
            yield TranscriptView(id="viewer-transcript")

    def on_mount(self) -> None:
        self.show_empty()

    def action_focus_left(self) -> None:
        """Return focus to the conversation list."""
        self.app.action_focus_list()

    def _viewer_scroll(self) -> HiddenVerticalScroll:
        """Return the transcript scroll container."""
        return self.query_one("#viewer-scroll", HiddenVerticalScroll)

    def action_scroll_up(self) -> None:
        """Scroll the transcript up."""
        self._viewer_scroll().scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        """Scroll the transcript down."""
        self._viewer_scroll().scroll_down(animate=False)

    def action_page_up(self) -> None:
        """Scroll the transcript up by one page."""
        self._viewer_scroll().scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        """Scroll the transcript down by one page."""
        self._viewer_scroll().scroll_page_down(animate=False)

    def action_scroll_home(self) -> None:
        """Scroll to the top of the transcript."""
        self._viewer_scroll().scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        """Scroll to the bottom of the transcript."""
        self._viewer_scroll().scroll_end(animate=False)

    def _ensure_transcript_loaded(self, conversation: Conversation) -> None:
        """Load transcript messages for the selected conversation once."""
        if conversation.transcript_loaded or not conversation.session_file:
            return

        meta, messages = parse_session_file(Path(conversation.session_file))
        conversation.messages = messages
        conversation.model = conversation.model or meta.get("model", "")
        conversation.cwd = conversation.cwd or meta.get("cwd", "")
        first_timestamp = next((m.timestamp for m in messages if m.timestamp), None)
        if first_timestamp:
            conversation.started_at = first_timestamp
        conversation.transcript_loaded = True

    def _message_local_date(self, message: Message) -> date | None:
        """Return the local date for a message timestamp."""
        if not message.timestamp:
            return None
        timestamp = (
            message.timestamp.astimezone()
            if message.timestamp.tzinfo
            else message.timestamp
        )
        return timestamp.date()

    def show_conversation(
        self,
        conversation: Conversation,
        focus_date: date | None = None,
    ) -> None:
        """Display a conversation's full transcript.

        A request renders immediately unless another arrived within the last
        RENDER_INTERVAL. Rapid requests (e.g. a held arrow key) are coalesced
        and only the latest is rendered once they pause.
        """
        if self._render_timer is not None:
            self._pending = (conversation, focus_date)
            self._render_timer.reset()
            return

        self._render_conversation(conversation, focus_date)
        self._render_timer = self.set_timer(
            self.RENDER_INTERVAL, self._flush_pending
        )

    def _flush_pending(self) -> None:
        """Render the latest coalesced request, if any."""
        self._render_timer = None
        if self._pending is not None:
            conversation, focus_date = self._pending
            self._pending = None
            self.show_conversation(conversation, focus_date)

    def _cancel_pending(self) -> None:
        """Drop any coalesced render request."""
        self._pending = None
        if self._render_timer is not None:
            self._render_timer.stop()
            self._render_timer = None

    def _render_conversation(
        self,
        conversation: Conversation,
        focus_date: date | None = None,
    ) -> None:
        """Replace the viewer contents with a conversation's transcript."""
        if conversation.has_transcript:
            self._ensure_transcript_loaded(conversation)

        header = self.query_one(ConversationHeader)
        header.show_conversation(conversation)
        header.display = True

        if not conversation.has_transcript:
            self._show_message(
                f"No session transcript file found for this chat.\n\n"
                f"The session was recorded in history.jsonl\n"
                f"but no rollout file exists under sessions/.\n\n"
                f"ID: {conversation.id}"
            )
            return

        if not conversation.messages:
            self._show_message("This conversation has no messages.")
            return

        messages = [
            msg for msg in conversation.messages if msg.content or msg.tool_calls
        ]
        if not messages:
            self._show_message("This conversation has no displayable messages.")
            return

        target_index: int | None = None
        if focus_date:
            for index, msg in enumerate(messages):
                if self._message_local_date(msg) == focus_date:
                    target_index = index

        scroll = self._viewer_scroll()
        transcript = self.query_one(TranscriptView)
        transcript.set_messages(messages)
        transcript.display = True
        self.query_one(EmptyState).display = False

        if target_index is not None:
            self.call_after_refresh(
                lambda: scroll.scroll_to(
                    y=transcript.block_offset(target_index), animate=False
                )
            )
        else:
            # The list is ordered by last activity, so open on the latest part.
            self.call_after_refresh(scroll.scroll_end, animate=False)

    def _show_message(self, message: str) -> None:
        """Show a placeholder message instead of a transcript."""
        transcript = self.query_one(TranscriptView)
        transcript.set_messages([])
        transcript.display = False
        empty = self.query_one(EmptyState)
        empty.update(message)
        empty.display = True
        self._viewer_scroll().scroll_home(animate=False)

    def show_empty(self) -> None:
        """Show the empty state."""
        self._cancel_pending()
        self.query_one(ConversationHeader).display = False
        self._show_message("Select a conversation to view its history")
