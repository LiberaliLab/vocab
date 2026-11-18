import copy

import pytest

from liblab_vocab.model import COLUMNS
from liblab_vocab.sync import SyncError, report, sync

from .conftest import term, vocabs

HEADER = list(COLUMNS)


class FakeSheet:
    """An in-memory sheet. on_read can change the tabs between reads."""

    def __init__(self, tabs):
        self.tabs = tabs
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
