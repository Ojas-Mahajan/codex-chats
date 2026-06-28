"""Chat viewer widget - displays a Codex conversation's full transcript."""

from __future__ import annotations

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
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


def _format_timestamp(msg: Message) -> str:
    """Format a message timestamp for display."""
    if msg.timestamp:
        return msg.timestamp.strftime("%b %d, %Y  %I:%M %p")
    return ""


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


class MessageBlock(Static):
    """A single message rendered as a styled block."""

    DEFAULT_CSS = """
    MessageBlock {
        margin: 0;
        padding: 1 2;
        border-bottom: solid #30363d;
        height: auto;
        color: #d7dde5;
    }
    MessageBlock.user-message {
        background: #202124;
    }
    MessageBlock.assistant-message {
        background: #171717;
    }
    MessageBlock.thinking-message {
        background: #15191d;
        color: #aeb6c2;
    }
    MessageBlock.tool-message {
        background: #141619;
        color: #9aa4af;
    }
    """

    def __init__(self, message: Message, **kwargs) -> None:
        self.message = message
        super().__init__(self._render_message(), markup=False, **kwargs)
        self._set_role_class()

    def _set_role_class(self) -> None:
        """Set CSS class based on message role and type."""
        msg = self.message
        if msg.msg_type == "reasoning":
            self.add_class("thinking-message")
        elif msg.msg_type in ("function_call", "function_call_output"):
            self.add_class("tool-message")
        elif msg.role == "user":
            self.add_class("user-message")
        elif msg.role == "assistant":
            self.add_class("assistant-message")
        else:
            self.add_class("tool-message")

    def _render_message(self) -> str:
        """Build a compact plain-text block for a message."""
        msg = self.message
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

        return "\n".join(lines)


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

    def __init__(self, conversation: Conversation, **kwargs) -> None:
        super().__init__(**kwargs)
        self.conversation = conversation

    def compose(self) -> ComposeResult:
        conv = self.conversation

        meta_parts = [
            f"Last active: {conv.last_modified.strftime('%b %d, %Y %I:%M %p')}",
        ]
        if conv.model:
            meta_parts.append(f"Model: {conv.model}")
        if conv.cwd:
            meta_parts.append(f"Dir: {conv.cwd}")
        if conv.message_count > 0:
            meta_parts.append(f"Messages: {conv.message_count}")

        with Vertical(id="header-content"):
            yield Static("Transcript", classes="viewer-label", markup=False)
            yield Static(f"📋  {conv.title}", classes="conv-title", markup=False)
            yield Static(f"ID: {conv.id}", classes="conv-id", markup=False)
            yield Static(
                "  •  ".join(meta_parts),
                classes="conv-meta",
                markup=False,
            )


class ChatViewer(Widget):
    """Right panel: displays the selected conversation's transcript."""

    can_focus = True

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

    def compose(self) -> ComposeResult:
        yield Vertical(id="viewer-header")
        yield HiddenVerticalScroll(
            EmptyState("Select a conversation to view its history"),
            id="viewer-scroll",
        )

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
        conversation.transcript_loaded = True

    def show_conversation(self, conversation: Conversation) -> None:
        """Display a conversation's full transcript."""
        header = self.query_one("#viewer-header", Vertical)
        scroll = self._viewer_scroll()
        header.remove_children()
        scroll.remove_children()

        if conversation.has_transcript:
            self._ensure_transcript_loaded(conversation)

        # Mount the header
        header.mount(ConversationHeader(conversation))

        if not conversation.has_transcript:
            scroll.mount(
                EmptyState(
                    f"No session transcript file found for this chat.\n\n"
                    f"The session was recorded in history.jsonl\n"
                    f"but no rollout file exists under sessions/.\n\n"
                    f"ID: {conversation.id}"
                )
            )
            return

        if not conversation.messages:
            scroll.mount(EmptyState("This conversation has no messages."))
            return

        # Mount message blocks.
        rendered_messages = 0
        for msg in conversation.messages:
            if msg.content or msg.tool_calls:
                scroll.mount(MessageBlock(msg))
                rendered_messages += 1

        if rendered_messages == 0:
            scroll.mount(EmptyState("This conversation has no displayable messages."))

        # Scroll to top
        scroll.scroll_home(animate=False)

    def show_empty(self) -> None:
        """Show the empty state."""
        header = self.query_one("#viewer-header", Vertical)
        scroll = self._viewer_scroll()
        header.remove_children()
        scroll.remove_children()
        scroll.mount(EmptyState("Select a conversation to view its history"))
