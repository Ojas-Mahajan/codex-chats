"""Main Textual application for the Codex Chat History TUI."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header

from .models import Conversation
from .scanner import delete_session_data, scan_conversations
from .widgets.chat_list import ChatList
from .widgets.chat_viewer import ChatViewer
from .widgets.confirm_delete import ConfirmDeleteDialog


class CodexChatsApp(App):
    """A TUI app to browse and view Codex conversation history."""

    TITLE = "Codex Chat History"
    SUB_TITLE = "Browse your past conversations"

    CSS = """
    Screen {
        background: $surface;
    }

    #main-layout {
        height: 1fr;
    }

    #left-panel {
        width: 40;
        min-width: 34;
        max-width: 55;
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
        Binding("escape", "focus_list", "Back to List", show=True),
        Binding("c", "copy_id", "Copy ID", show=True),
        Binding("enter,o", "open_session", "Open in Codex", show=True),
        Binding("d,delete", "delete_session", "Delete", show=True),
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
        if event.conversation:
            viewer.show_conversation(event.conversation)
        else:
            viewer.show_empty()

    def on_chat_list_open_session(self, event: ChatList.OpenSession) -> None:
        """Handle opening a session in Codex."""
        self._selected_conversation = event.conversation
        self.action_open_session()

    def action_open_session(self) -> None:
        """Open the selected conversation in Codex."""
        if self._selected_conversation:
            import subprocess
            from pathlib import Path
            with self.suspend():
                cwd = self._selected_conversation.cwd or None
                if cwd and not Path(cwd).is_dir():
                    cwd = None
                subprocess.run(["codex", "resume", self._selected_conversation.id], cwd=cwd)

    def action_focus_search(self) -> None:
        """Focus the search input."""
        try:
            search = self.query_one("#search-input")
            search.focus()
        except Exception:
            pass

    def action_focus_list(self) -> None:
        """Return focus to the conversation list."""
        try:
            chat_list = self.query_one("#left-panel", ChatList)
            chat_list.focus()
        except Exception:
            pass

    def action_focus_right_panel(self) -> None:
        """Focus the Open in Codex button."""
        try:
            from textual.widgets import Button
            viewer = self.query_one("#right-panel", ChatViewer)
            btn = viewer.query_one("#open-codex-btn", Button)
            btn.focus()
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
                self.notify(
                    f"ID: {self._selected_conversation.id}",
                    title="Conversation ID",
                    severity="information",
                )

    def action_delete_session(self) -> None:
        """Prompt to delete the currently selected session."""
        if not self._selected_conversation:
            return

        def check_delete(delete: bool) -> None:
            if delete and self._selected_conversation:
                # Delete the data
                delete_session_data(
                    self.data_dir,
                    self._selected_conversation.id,
                    self._selected_conversation.session_file,
                )
                
                # Remove from ChatList and re-select
                chat_list = self.query_one("#left-panel", ChatList)
                chat_list.remove_conversation(self._selected_conversation.id)
                self.notify("Session deleted.", severity="information")

        self.push_screen(
            ConfirmDeleteDialog(self._selected_conversation.title), 
            check_delete
        )
