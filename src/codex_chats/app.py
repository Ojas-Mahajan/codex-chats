"""Main Textual application for the Antigravity Chat History TUI."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header

from .models import Conversation
from .scanner import scan_conversations
from .widgets.chat_list import ChatList
from .widgets.chat_viewer import ChatViewer


class CodexChatsApp(App):
    """A TUI app to browse and view Antigravity conversation history."""

    TITLE = "Antigravity Chat History"
    SUB_TITLE = "Browse your past conversations"

    CSS = """
    Screen {
        background: $surface;
    }

    #main-layout {
        height: 1fr;
    }

    #left-panel {
        width: 36;
        min-width: 30;
        max-width: 50;
        border-right: solid $primary 30%;
        height: 1fr;
    }

    #right-panel {
        width: 1fr;
        height: 1fr;
    }

    Header {
        background: $primary;
        color: $text;
    }

    Footer {
        background: $surface-lighten-1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("slash", "focus_search", "Search", show=True),
        Binding("escape", "unfocus_search", "Back", show=False),
        Binding("c", "copy_id", "Copy ID", show=True),
    ]

    def __init__(self, data_dir: str | Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = Path(data_dir)
        self.conversations: list[Conversation] = []
        self._selected_conversation: Conversation | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # Scan conversations
        self.conversations = scan_conversations(self.data_dir)

        with Horizontal(id="main-layout"):
            yield ChatList(self.conversations, id="left-panel")
            yield ChatViewer(id="right-panel")

        yield Footer()

    def on_chat_list_conversation_selected(
        self, event: ChatList.ConversationSelected
    ) -> None:
        """Handle conversation selection from the list."""
        self._selected_conversation = event.conversation
        viewer = self.query_one("#right-panel", ChatViewer)
        viewer.show_conversation(event.conversation)

    def action_focus_search(self) -> None:
        """Focus the search input."""
        try:
            search = self.query_one("#search-input")
            search.focus()
        except Exception:
            pass

    def action_unfocus_search(self) -> None:
        """Unfocus the search input and return focus to the list."""
        try:
            chat_list = self.query_one("#left-panel", ChatList)
            chat_list.focus()
        except Exception:
            pass

    def action_copy_id(self) -> None:
        """Copy the selected conversation's ID to clipboard."""
        if self._selected_conversation:
            try:
                self.copy_to_clipboard(self._selected_conversation.id)
                self.notify(
                    f"Copied: {self._selected_conversation.id}",
                    title="ID Copied",
                    severity="information",
                )
            except Exception:
                # Fallback if clipboard not available
                self.notify(
                    f"ID: {self._selected_conversation.id}",
                    title="Conversation ID",
                    severity="information",
                )
