"""Modal dialog to confirm session deletion."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmDeleteDialog(ModalScreen[bool]):
    """Modal dialog to confirm session deletion."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("d,delete", "confirm", "Delete", show=False),
        Binding("left,h", "focus_cancel", "Focus Cancel", show=False),
        Binding("right,l", "focus_delete", "Focus Delete", show=False),
    ]

    DEFAULT_CSS = """
    ConfirmDeleteDialog {
        align: center middle;
    }
    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }
    #question {
        column-span: 2;
        height: 1fr;
        width: 1fr;
        content-align: center middle;
        color: $text;
    }
    Button {
        width: 100%;
    }
    """

    def __init__(self, session_title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_title = session_title

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            # Truncate title if extremely long
            display_title = self.session_title
            if len(display_title) > 60:
                display_title = display_title[:57] + "..."
            yield Label(
                "Are you sure you want to permanently delete this session?"
                f"\n\n[b]{display_title}[/b]",
                id="question",
            )
            yield Button("Cancel", variant="primary", id="cancel")
            yield Button("Delete", variant="error", id="delete")

    def on_mount(self) -> None:
        """Focus Cancel first so pressing Enter never deletes by default."""
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Dismiss without deleting."""
        self.dismiss(False)

    def action_confirm(self) -> None:
        """Confirm deletion from the dialog."""
        self.dismiss(True)

    def action_focus_cancel(self) -> None:
        """Focus the cancel button."""
        self.query_one("#cancel", Button).focus()

    def action_focus_delete(self) -> None:
        """Focus the delete button."""
        self.query_one("#delete", Button).focus()
