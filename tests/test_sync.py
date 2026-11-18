import copy

import pytest

from liblab_vocab.model import COLUMNS
from liblab_vocab.sync import SyncError, report, sync

from .conftest import term, vocabs

HEADER = list(COLUMNS)


class FakeSheet:
    """An in-memory sheet. on_read can change the tabs between reads."""

    def __init__(self, tabs, notes=None):
        self.tabs = tabs
        self.notes = notes or {}  # tab -> list of header notes
        self.note_writes = []
        self.writes = []
        self.reads = 0
        self.on_read = None

    def read_tabs(self):
        self.reads += 1
        if self.on_read:
            self.on_read(self)
        return copy.deepcopy(self.tabs)

    def write_cells(self, tab, cells):
        self.writes.append((tab, cells))
        for row, col, value in cells:
            line = self.tabs[tab][row - 1]
            line += [""] * (col - len(line))
            line[col - 1] = value

    def read_header_notes(self, tab):
        notes = list(self.notes.get(tab, []))
        return notes + [""] * (len(COLUMNS) - len(notes))

    def write_header_notes(self, tab, notes):
        self.note_writes.append((tab, dict(notes)))
        current = self.read_header_notes(tab)
        for col, text in notes.items():
            current[col - 1] = text
        self.notes[tab] = current

    def url(self):
        return "https://docs.google.com/spreadsheets/d/test"


def row(id="", label="", definition="", synonyms="", parent="", status="active", replaced="", mapping=""):
    return [id, label, definition, synonyms, parent, status, replaced, mapping]


def current():
    return vocabs(term("stain", id="LIBLAB:0000001", label="nuclear stain"))


def test_new_rows_get_ids_written_back(config):
    sheet = FakeSheet({
        "README": [["How to edit this sheet"]],
        "stain": [
            HEADER,
            row("LIBLAB:0000001", "nuclear stain", "Definition of nuclear stain."),
            [],  # blank rows keep the row numbering
            row("", "DAPI", "A blue DNA stain.", parent="nuclear stain"),
        ],
        "dye": [HEADER, row("", "eosin", "A pink stain.")],
    })
    result = sync(sheet, config, current())

    assert result.errors == []
    assert result.ignored_tabs == ["README"]
    # IDs follow on from main, vocabularies in name order.
    assert [(t.label, t.id) for t in result.assigned] == [("eosin", "LIBLAB:0000002"), ("DAPI", "LIBLAB:0000003")]
    assert sheet.tabs["stain"][3][0] == "LIBLAB:0000003"
    assert sheet.tabs["stain"][3][4] == "LIBLAB:0000001"  # parent label replaced by its ID
    assert sheet.tabs["dye"][1][0] == "LIBLAB:0000002"
    assert result.vocabs["stain"][1].parent_id == "LIBLAB:0000001"


def test_ids_never_reuse_numbers_from_baselines(config):
    release = vocabs(term("stain", id="LIBLAB:0000001", label="nuclear stain"), term("stain", id="LIBLAB:0000050", label="gone"))
    sheet = FakeSheet({"stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", "x"), row("", "new", "y")]})
    result = sync(sheet, config, current(), [("v1.0.0", release)])
    assert result.assigned[0].id == "LIBLAB:0000051"
    # The deleted released term is reported, not silently accepted.
    assert any("LIBLAB:0000050" in str(i) and "v1.0.0" in str(i) for i in result.errors)


def test_validation_errors_are_reported_not_fatal(config):
    sheet = FakeSheet({"stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", ""), row("", "x", "y", status="maybe")]})
    result = sync(sheet, config, current())
    text = "\n".join(str(i) for i in result.errors)
    assert "definition is empty" in text and "status is 'maybe'" in text
    # IDs are still assigned and written back.
    assert sheet.tabs["stain"][2][0] == "LIBLAB:0000002"
    body = report(result, current(), sheet.url())
    assert "problem(s) to fix in the sheet" in body
    assert "ERROR stain.tsv:2 [LIBLAB:0000001]: definition is empty" in body


def test_line_breaks_are_cleaned(config):
    sheet = FakeSheet({"stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", "Stains\nnuclei.\t")]})
    result = sync(sheet, config, current())
    assert result.vocabs["stain"][0].definition == "Stains nuclei."
    assert result.cleaned == ["stain row 2, definition: line breaks or tabs replaced by spaces"]


def test_missing_tab_stops_the_sync(config):
    sheet = FakeSheet({"Sheet1": [HEADER]})
    with pytest.raises(SyncError, match="no tab in the sheet: stain"):
        sync(sheet, config, current())
    assert sheet.writes == []


def test_broken_header_on_existing_vocabulary_stops_the_sync(config):
    sheet = FakeSheet({"stain": [["id", "name", "definition"], row("LIBLAB:0000001", "nuclear stain", "x")]})
    with pytest.raises(SyncError, match="must start with the header row"):
        sync(sheet, config, current())


def test_extra_cells_stop_the_sync(config):
    sheet = FakeSheet({"stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", "x") + ["a note"]]})
    with pytest.raises(SyncError, match="more than 8 columns"):
        sync(sheet, config, current())


def test_rows_moved_during_sync_abort_without_writing(config):
    sheet = FakeSheet({"stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", "x"), row("", "DAPI", "y")]})

    def insert_row(s):
        if s.reads == 2:  # an editor inserts a row between our read and our write
            s.tabs["stain"].insert(2, row("", "Hoechst", "z"))

    sheet.on_read = insert_row
    with pytest.raises(SyncError, match="row 3 changed while syncing"):
        sync(sheet, config, current())
    assert sheet.writes == []


def test_no_write_back(config):
    sheet = FakeSheet({"stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", "x"), row("", "DAPI", "y")]})
    result = sync(sheet, config, current(), write_back=False)
    assert result.assigned[0].id == "LIBLAB:0000002"
    assert sheet.writes == []


def test_report_lists_changes_and_bump(config):
    sheet = FakeSheet({"stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", "Better."), row("", "DAPI", "y")]})
    result = sync(sheet, config, current())
    body = report(result, current(), sheet.url(), ("v1.0.0", current()))
    assert "✅ Validation passed" in body
    assert "`LIBLAB:0000002` DAPI (stain row 3)" in body
    assert "| minor | term added | stain |" in body
    assert "| patch | definition changed |" in body
    assert "needs a **minor** bump" in body


NOTES = ["Leave empty.", "Preferred name.", "", "Separate with |", "", "active or deprecated", "", ""]


def notes_sheet():
    return FakeSheet(
        {
            "TEMPLATE": [HEADER],
            "stain": [HEADER, row("LIBLAB:0000001", "nuclear stain", "x")],
            "dye": [HEADER],
        },
        notes={
            "TEMPLATE": NOTES,
            "stain": ["old note", "Preferred name.", "", "", "", "", "", "a stray note"],
        },
    )


def test_template_tab_is_ignored_and_its_notes_copied(config):
    sheet = notes_sheet()
    result = sync(sheet, config, current())
    assert "TEMPLATE" in result.ignored_tabs
    assert "TEMPLATE" not in result.vocabs
    assert sheet.read_header_notes("stain") == NOTES
    assert sheet.read_header_notes("dye") == NOTES
    assert result.notes_updated == ["dye", "stain"]
    # Only differing cells are written, and stray notes are cleared.
    stain_write = dict(sheet.note_writes)["stain"]
    assert stain_write == {1: "Leave empty.", 4: "Separate with |", 6: "active or deprecated", 8: ""}
    assert "Header notes copied from TEMPLATE to: dye, stain" in report(result, current(), sheet.url())


def test_notes_already_in_sync_are_not_rewritten(config):
    sheet = notes_sheet()
    sync(sheet, config, current())
    sheet.note_writes.clear()
    result = sync(sheet, config, current())
    assert sheet.note_writes == []
    assert result.notes_updated == []


def test_no_template_or_empty_template_changes_nothing(config):
    sheet = notes_sheet()
    sheet.notes["TEMPLATE"] = [""] * 8
    assert sync(sheet, config, current()).notes_updated == []
    del sheet.tabs["TEMPLATE"]
    assert sync(sheet, config, current()).notes_updated == []
    assert sheet.read_header_notes("stain")[0] == "old note"


def test_no_write_back_leaves_notes_alone(config):
    sheet = notes_sheet()
    sync(sheet, config, current(), write_back=False)
    assert sheet.note_writes == []
