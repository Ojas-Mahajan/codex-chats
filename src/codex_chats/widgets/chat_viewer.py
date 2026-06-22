"""Chat viewer widget — displays a conversation's full transcript in the right panel."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from ..models import Conversation, Message


def _format_timestamp(msg: Message) -> str:
    """Format a message timestamp for display."""
    if msg.created_at:
        return msg.created_at.strftime("%b %d, %Y  %I:%M %p")
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
            if len(val_str) > 80:
                val_str = val_str[:77] + "…"
            args_summary.append(f"    {k}: {val_str}")
        args_block = "\n".join(args_summary)
        lines.append(f"  🔧 {tc.name}\n{args_block}")

    return "\n".join(lines)


class MessageBlock(Static):
    """A single message rendered as a styled block."""

    DEFAULT_CSS = """
    MessageBlock {
        margin: 0 0 1 0;
        padding: 1 2;
        border-left: thick transparent;
    }
    MessageBlock.user-message {
        border-left: thick $primary;
        background: $primary 8%;
    }
    MessageBlock.model-message {
        border-left: thick $success;
        background: $success 8%;
    }
    MessageBlock.system-message {
        border-left: thick $warning;
        background: $warning 5%;
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
        margin-top: 1;
    }
    MessageBlock .msg-tools {
        color: $accent;
        margin-top: 1;
    }
    """

    def __init__(self, message: Message, **kwargs) -> None:
        super().__init__(**kwargs)
        self.message = message
        self._set_role_class()

    def _set_role_class(self) -> None:
        """Set CSS class based on message source."""
        if self.message.source == "USER_EXPLICIT":
            self.add_class("user-message")
        elif self.message.source == "MODEL":
            self.add_class("model-message")
        else:
            self.add_class("system-message")

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
            # Truncate very long content for display performance
            content = msg.content
            if len(content) > 3000:
                content = content[:3000] + "\n\n...content truncated for display..."
            yield Static(content, classes="msg-content", markup=False)

        if msg.tool_calls:
            tools_text = _format_tool_calls(msg)
            yield Static(tools_text, classes="msg-tools", markup=False)


class EmptyState(Static):
    """Shown when no conversation is selected or conversation has no logs."""

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
        padding: 1 2;
        background: $surface-lighten-1;
        border-bottom: solid $primary 50%;
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
        yield Static(f"📋  {conv.title}", classes="conv-title", markup=False)
        yield Static(f"ID: {conv.id}", classes="conv-id", markup=False)

        meta_parts = [
            f"Last modified: {conv.last_modified.strftime('%b %d, %Y %I:%M %p')}",
            f"Size: {conv.size_label}",
        ]
        if conv.has_logs:
            meta_parts.append(f"Messages: {conv.message_count}")
        if conv.artifacts:
            meta_parts.append(f"Artifacts: {', '.join(conv.artifacts)}")

        yield Static("  •  ".join(meta_parts), classes="conv-meta", markup=False)


class ChatViewer(Widget):
    """Right panel: displays the selected conversation's transcript."""

    DEFAULT_CSS = """
    ChatViewer {
        width: 1fr;
        height: 1fr;
    }
    ChatViewer #viewer-scroll {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            EmptyState("Select a conversation to view its history"),
            id="viewer-scroll",
        )

    def show_conversation(self, conversation: Conversation) -> None:
        """Display a conversation's full transcript."""
        scroll = self.query_one("#viewer-scroll", VerticalScroll)
        scroll.remove_children()

        # Mount the header
        scroll.mount(ConversationHeader(conversation))

        if not conversation.has_logs:
            scroll.mount(
                EmptyState(
                    f"No conversation logs available for this chat.\n\n"
                    f"The .pb file exists ({conversation.size_label}) but its content\n"
                    f"is encrypted and cannot be displayed.\n\n"
                    f"ID: {conversation.id}"
                )
            )
            return

        if not conversation.messages:
            scroll.mount(EmptyState("This conversation has no messages."))
            return

        # Mount message blocks — skip empty system messages for cleaner view
        for msg in conversation.messages:
            if msg.content or msg.tool_calls:
                scroll.mount(MessageBlock(msg))

        # Scroll to top
        scroll.scroll_home(animate=False)

    def show_empty(self) -> None:
        """Show the empty state."""
        scroll = self.query_one("#viewer-scroll", VerticalScroll)
        scroll.remove_children()
        scroll.mount(EmptyState("Select a conversation to view its history"))
