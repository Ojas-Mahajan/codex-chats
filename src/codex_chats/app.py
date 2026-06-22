"""Main Textual application for the Codex Chat History TUI."""

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

    def on_chat_list_open_session(self, event: ChatList.OpenSession) -> None:
        """Handle opening a session in Codex."""
        self._selected_conversation = event.conversation
        self.action_open_session()

    def action_open_session(self) -> None:
        """Open the selected conversation in Codex."""
        if self._selected_conversation:
            import shutil
            import subprocess
            from pathlib import Path
            
            cwd = self._selected_conversation.cwd or None
            if cwd and not Path(cwd).is_dir():
                cwd = None

            cmd_str = f"codex resume {self._selected_conversation.id}"
            
            terminals = [
                "x-terminal-emulator",
                "ghostty",
                "gnome-terminal",
                "konsole",
                "kitty",
                "alacritty",
                "terminator",
                "xterm"
            ]
            
            opened = False
            for term in terminals:
                if shutil.which(term):
                    try:
                        if term == "gnome-terminal":
                            subprocess.Popen([term, "--tab", "--", "bash", "-c", cmd_str], cwd=cwd)
                        elif term == "konsole":
                            subprocess.Popen([term, "--new-tab", "-e", "bash", "-c", cmd_str], cwd=cwd)
                        else:
                            # Standard -e for most emulators (including ghostty, xterm, etc.)
                            subprocess.Popen([term, "-e", "bash", "-c", cmd_str], cwd=cwd)
                        
                        opened = True
                        self.notify(f"Opened in new terminal: {term}")
                        break
                    except Exception:
                        continue
                        
            if not opened:
                self.notify("Failed to find a terminal emulator to open a new tab.", severity="error")

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
