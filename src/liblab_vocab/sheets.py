"""Reading and writing the Google Sheet.

Only GoogleSheet talks to Google; the sync logic works against the SheetSource
protocol so it can be tested with an in-memory sheet.
"""

from __future__ import annotations

from typing import Protocol

from .model import COLUMNS

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetSource(Protocol):
    def read_tabs(self) -> dict[str, list[list[str]]]:
        """Every tab's cell values as text, row by row. Row 1 is index 0."""

    def write_cells(self, tab: str, cells: list[tuple[int, int, str]]) -> None:
        """Write (row, column, value) cells, both 1-based, as plain text."""

    def read_header_notes(self, tab: str) -> list[str]:
        """The notes on row 1, one per vocabulary column ("" where there is none)."""

    def write_header_notes(self, tab: str, notes: dict[int, str]) -> None:
        """Set notes on row 1 by 1-based column; an empty string removes the note."""

    def url(self) -> str: ...


class GoogleSheet:
    """A Google Sheet, accessed with Application Default Credentials.

    In GitHub Actions these come from google-github-actions/auth (Workload
    Identity Federation); locally from `gcloud auth application-default login`.
    """

    def __init__(self, sheet_id: str):
        import google.auth
        import gspread

        credentials, _ = google.auth.default(scopes=SCOPES)
        self.sheet_id = sheet_id
        self._book = gspread.authorize(credentials).open_by_key(sheet_id)
        self._worksheets: dict = {}

    def _worksheet(self, tab: str):
        if tab not in self._worksheets:
            self._worksheets[tab] = self._book.worksheet(tab)
        return self._worksheets[tab]

    def read_tabs(self) -> dict[str, list[list[str]]]:
        self._worksheets = {ws.title: ws for ws in self._book.worksheets()}
        return {title: ws.get_all_values() for title, ws in self._worksheets.items()}

    def read_header_notes(self, tab: str) -> list[str]:
        from gspread.utils import rowcol_to_a1

        last = rowcol_to_a1(1, len(COLUMNS))
        rows = self._worksheet(tab).get_notes(grid_range=f"A1:{last}")
        notes = list(rows[0]) if rows else []
        return [n or "" for n in notes] + [""] * (len(COLUMNS) - len(notes))

    def write_header_notes(self, tab: str, notes: dict[int, str]) -> None:
        from gspread.utils import rowcol_to_a1

        worksheet = self._worksheet(tab)
        to_set = {rowcol_to_a1(1, col): text for col, text in notes.items() if text}
        to_clear = [rowcol_to_a1(1, col) for col, text in notes.items() if not text]
        if to_set:
            worksheet.update_notes(to_set)
        if to_clear:
            worksheet.clear_notes(to_clear)

    def write_cells(self, tab: str, cells: list[tuple[int, int, str]]) -> None:
        from gspread.utils import rowcol_to_a1

        if not cells:
            return
        worksheet = self._worksheet(tab)
        worksheet.batch_update(
            [{"range": rowcol_to_a1(row, col), "values": [[value]]} for row, col, value in cells],
            raw=True,  # store text as typed; never interpret it as a formula
        )

    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}"
