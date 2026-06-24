"""Main Textual application for the Codex Chat History TUI."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Input

from .models import Conversation
from .scanner import delete_session_data, scan_conversations
from .widgets.chat_list import ChatList
from .widgets.chat_viewer import ChatViewer
from .widgets.confirm_delete import ConfirmDeleteDialog
from .widgets.directory_list import DirectoryList


class CodexChatsApp(App):
    """A TUI app to browse and view Codex conversation history."""

    TITLE = "Codex Chat History"
    SUB_TITLE = "Browse your past conversations"

    CSS = """
    Screen {
        background: $surface;
    }

    * {
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 0;
    }

    #main-layout {
        height: 1fr;
    }

    #directory-panel {
        border-right: solid #242424;
    }

    #left-panel {
        width: 38;
        min-width: 30;
        max-width: 55;
        border-right: solid #242424;
        height: 1fr;
    }

    #right-panel {
        width: 1fr;
        height: 1fr;
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
        # Scan conversations
        self.conversations = scan_conversations(self.data_dir)

        with Horizontal(id="main-layout"):
            yield DirectoryList(self.conversations, id="directory-panel")
            yield ChatList(self.conversations, id="left-panel")
            yield ChatViewer(id="right-panel")

        yield Footer()

    def on_mount(self) -> None:
        """Start with keyboard focus on the conversation list."""
        self.action_focus_list()

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

    def on_directory_list_directory_selected(
        self, event: DirectoryList.DirectorySelected
    ) -> None:
        """Filter the conversation list by directory."""
        chat_list = self.query_one("#left-panel", ChatList)
        chat_list.set_directory_filter(event.directory)

    def action_open_session(self) -> None:
        """Open the selected conversation in Codex."""
        if self._selected_conversation:
            import subprocess
            from pathlib import Path

            with self.suspend():
                cwd = self._selected_conversation.cwd or None
                if cwd and not Path(cwd).is_dir():
                    cwd = None
                subprocess.run(
                    ["codex", "resume", self._selected_conversation.id],
                    cwd=cwd,
                )

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

    def action_focus_directory_panel(self) -> None:
        """Focus the directory sidebar."""
        try:
            directory_list = self.query_one("#directory-panel", DirectoryList)
            directory_list.focus()
        except Exception:
            pass

    def action_focus_right_panel(self) -> None:
        """Focus the transcript viewer."""
        try:
            viewer = self.query_one("#right-panel", ChatViewer)
            viewer.focus()
        except Exception:
            pass

    def _focused_pane_index(self) -> int:
        """Return the current pane index: directories, conversations, transcript."""
        focused = self.focused
        panes = [
            self.query_one("#directory-panel", DirectoryList),
            self.query_one("#left-panel", ChatList),
            self.query_one("#right-panel", ChatViewer),
        ]

        for index, pane in enumerate(panes):
            if focused is pane or (focused and pane in focused.ancestors_with_self):
                return index
        return 1

    def on_key(self, event) -> None:
        """Fallback pane navigation for h/l and left/right keys."""
        if isinstance(self.focused, Input):
            return

        if event.key in ("h", "left"):
            event.stop()
            self.action_focus_previous_pane()
        elif event.key in ("l", "right"):
            event.stop()
            self.action_focus_next_pane()

    def action_focus_previous_pane(self) -> None:
        """Move focus one pane to the left."""
        if isinstance(self.focused, Input):
            return

        pane_index = self._focused_pane_index()
        if pane_index == 2:
            self.action_focus_list()
        else:
            self.action_focus_directory_panel()

    def action_focus_next_pane(self) -> None:
        """Move focus one pane to the right."""
        if isinstance(self.focused, Input):
            return

        pane_index = self._focused_pane_index()
        if pane_index == 0:
            self.action_focus_list()
        else:
            self.action_focus_right_panel()

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

        target = self._selected_conversation

        def check_delete(delete: bool) -> None:
            if delete:
                chat_list = self.query_one("#left-panel", ChatList)
                fallback_index = chat_list.selected_index

                try:
                    result = delete_session_data(
                        self.data_dir,
                        target.id,
                        target.session_file,
                    )
                except OSError as exc:
                    self.notify(
                        str(exc),
                        title="Delete failed",
                        severity="error",
                    )
                    self.action_focus_list()
                    return

                self.conversations = scan_conversations(self.data_dir)
                directory_list = self.query_one("#directory-panel", DirectoryList)
                active_directory = directory_list.replace_conversations(
                    self.conversations
                )
                chat_list.replace_conversations(
                    self.conversations,
                    fallback_index=fallback_index,
                )
                chat_list.set_directory_filter(
                    active_directory,
                    fallback_index=fallback_index,
                )

                details = []
                if result.deleted_rollout_file:
                    details.append("rollout file")
                if result.removed_history_rows:
                    details.append(f"{result.removed_history_rows} history row(s)")
                suffix = f" Removed {', '.join(details)}." if details else ""
                self.notify(f"Session deleted.{suffix}", severity="information")
                self.action_focus_list()

        self.push_screen(
            ConfirmDeleteDialog(target.title),
            check_delete,
        )
