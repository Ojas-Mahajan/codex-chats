"""Chat viewer widget - displays a Codex conversation's full transcript."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from ..models import Conversation, Message


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


class MessageBlock(Static):
    """A single message rendered as a styled block."""

    DEFAULT_CSS = """
    MessageBlock {
        margin: 0;
        padding: 0 1;
        border-left: thick transparent;
    }
    MessageBlock.user-message {
        border-left: thick #555555;
        background: $surface-lighten-1;
    }
    MessageBlock.assistant-message {
        border-left: thick #444444;
        background: $surface;
    }
    MessageBlock.thinking-message {
        border-left: thick #333333;
        background: $surface;
    }
    MessageBlock.tool-message {
        border-left: thick #333333;
        background: $surface;
    }
    MessageBlock .msg-header {
        color: $text;
        text-style: bold;
    }
    MessageBlock .msg-timestamp {
        color: $text-muted;
    }
    MessageBlock .msg-content {
        color: $text;
        margin-top: 0;
    }
    MessageBlock .msg-tools {
        color: $accent;
        margin-top: 0;
    }
    """

    def __init__(self, message: Message, **kwargs) -> None:
        super().__init__(**kwargs)
        self.message = message
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

    def compose(self) -> ComposeResult:
        msg = self.message
        ts = _format_timestamp(msg)

        yield Static(
            f"{msg.role_icon}  {msg.role_label}  ─  {msg.display_type}",
            classes="msg-header",
            markup=False,
        )

        if ts:
            yield Static(f"   {ts}", classes="msg-timestamp", markup=False)

        if msg.content:
            content = msg.content
            if len(content) > 3000:
                content = content[:3000] + "\n\n...content truncated for display..."
            yield Static(content, classes="msg-content", markup=False)

        if msg.tool_calls:
            tools_text = _format_tool_calls(msg)
            yield Static(tools_text, classes="msg-tools", markup=False)


class EmptyState(Static):
    """Shown when no conversation is selected or has no transcript."""

    DEFAULT_CSS = """
    EmptyState {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """


class ConversationHeader(Static):
    """Header showing conversation title, ID, and metadata."""

    DEFAULT_CSS = """
    ConversationHeader {
        height: auto;
        padding: 0 1;
        background: $surface-lighten-1;
        border-bottom: solid #333333;
    }
    ConversationHeader #header-content {
        width: 1fr;
    }
    ConversationHeader .conv-title {
        text-style: bold;
        color: $text;
    }
    ConversationHeader .conv-id {
        color: $text-muted;
    }
    ConversationHeader .conv-meta {
        color: $text-disabled;
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
        Binding("left,h", "focus_left", "Focus Left", show=False),
    ]

    DEFAULT_CSS = """
    ChatViewer {
        width: 1fr;
        height: 1fr;
    }
    ChatViewer:focus {
        border: solid #555555;
    }
    ChatViewer #viewer-header {
        height: auto;
    }
    ChatViewer #viewer-scroll {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(id="viewer-header")
        yield VerticalScroll(
            EmptyState("Select a conversation to view its history"),
            id="viewer-scroll",
        )

    def action_focus_left(self) -> None:
        """Return focus to the list."""
        self.app.action_focus_list()

    def show_conversation(self, conversation: Conversation) -> None:
        """Display a conversation's full transcript."""
        header = self.query_one("#viewer-header", Vertical)
        scroll = self.query_one("#viewer-scroll", VerticalScroll)
        header.remove_children()
        scroll.remove_children()

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

        # Mount message blocks
        for msg in conversation.messages:
            if msg.content or msg.tool_calls:
                scroll.mount(MessageBlock(msg))

        # Scroll to top
        scroll.scroll_home(animate=False)

    def show_empty(self) -> None:
        """Show the empty state."""
        header = self.query_one("#viewer-header", Vertical)
        scroll = self.query_one("#viewer-scroll", VerticalScroll)
        header.remove_children()
        scroll.remove_children()
        scroll.mount(EmptyState("Select a conversation to view its history"))
