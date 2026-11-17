"""Reading and writing the Google Sheet.

Only GoogleSheet talks to Google; the sync logic works against the SheetSource
protocol so it can be tested with an in-memory sheet.
"""

from __future__ import annotations

from typing import Protocol

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetSource(Protocol):
    def read_tabs(self) -> dict[str, list[list[str]]]:
        """Every tab's cell values as text, row by row. Row 1 is index 0."""

    def write_cells(self, tab: str, cells: list[tuple[int, int, str]]) -> None:
        """Write (row, column, value) cells, both 1-based, as plain text."""

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

    def read_tabs(self) -> dict[str, list[list[str]]]:
        return {ws.title: ws.get_all_values() for ws in self._book.worksheets()}

    def write_cells(self, tab: str, cells: list[tuple[int, int, str]]) -> None:
        from gspread.utils import rowcol_to_a1

        if not cells:
            return
        worksheet = self._book.worksheet(tab)
        worksheet.batch_update(
            [{"range": rowcol_to_a1(row, col), "values": [[value]]} for row, col, value in cells],
            raw=True,  # store text as typed; never interpret it as a formula
        )

    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}"
