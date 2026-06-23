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
        height: auto;
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
            content = msg.content
            if len(content) > 3000:
                content = content[:3000] + "\n\n...content truncated for display..."
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
        color: $text-muted;
        text-style: italic;
    }
    """


class ConversationHeader(Static):
    """Header showing conversation title, ID, and metadata."""

    DEFAULT_CSS = """
    ConversationHeader {
        height: 4;
        padding: 0 1;
        background: $surface-lighten-1;
        border-bottom: solid #333333;
    }
    ConversationHeader #header-content {
        width: 1fr;
        height: 4;
    }
    ConversationHeader .conv-title {
        height: 1;
        text-style: bold;
        color: $text;
    }
    ConversationHeader .conv-id {
        height: 1;
        color: $text-muted;
    }
    ConversationHeader .conv-meta {
        height: 2;
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
    ChatViewer #viewer-header {
        height: 4;
    }
    ChatViewer #viewer-scroll {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 0 0;
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
        scroll = self.query_one("#viewer-scroll", VerticalScroll)
        header.remove_children()
        scroll.remove_children()
        scroll.mount(EmptyState("Select a conversation to view its history"))
