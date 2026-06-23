"""Modal dialog to confirm session deletion."""

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmDeleteDialog(ModalScreen[bool]):
    """Modal dialog to confirm session deletion."""

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
                f"Are you sure you want to permanently delete this session?\n\n[b]{display_title}[/b]",
                id="question",
            )
            yield Button("Cancel", variant="primary", id="cancel")
            yield Button("Delete", variant="error", id="delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)
