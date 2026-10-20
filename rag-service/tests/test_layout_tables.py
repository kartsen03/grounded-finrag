from finrag.ingest.layout import Cell, group_lines, split_cells
from finrag.ingest.tables import detect_tables

from helpers import line_words, word


def test_group_lines_orders_words_by_line_then_x():
    words = [word("b", 50, 100), word("a", 10, 101), word("c", 10, 120)]
    lines = group_lines(words)
    assert [line.text for line in lines] == ["a b", "c"]


def test_split_cells_on_wide_gaps_and_dollar_joins_number():
    line = group_lines(line_words(100, (10, "Net income"), (200, "$"), (240, "5,363")))[0]
    cells = split_cells(line)
    assert [c.text for c in cells] == ["Net income", "$ 5,363"]
    assert cells[1].numeric and cells[1].value == "5,363"


def test_numeric_cells_include_negatives_percent_and_dashes():
    for text in ["(1,577)", "5.5%", "2018", "—", "-3.2"]:
        assert Cell(text, 0, 1).numeric, text
    for text in ["(a)", "Note", "1,57,7x"]:
        assert not Cell(text, 0, 1).numeric, text


def _statement_lines():
    words = []
    words += line_words(80, (10, "(Millions)"), (300, "2018"), (360, "2017"))
    words += line_words(95, (10, "Cash Flows from Operating Activities"))
    words += line_words(110, (10, "Net income"), (290, "$"), (305, "5,363"), (365, "4,869"))
    words += line_words(125, (10, "Depreciation"), (305, "1,488"), (365, "1,544"))
    words += line_words(140, (10, "Inventories"), (310, "(509)"), (370, "—"))
    return group_lines(words)


def test_detect_statement_table_with_year_header():
    tables = detect_tables(_statement_lines(), page_width=612)
    assert len(tables) == 1
    md = tables[0].markdown.split("\n")
    assert md[0] == "| (Millions) | 2018 | 2017 |"
    assert "| Cash Flows from Operating Activities |  |  |" in md
    assert "| Net income | 5,363 | 4,869 |" in md
    assert "| Inventories | (509) | — |" in md
    assert tables[0].n_cols == 2


def test_prose_with_numbers_is_not_a_table():
    words = []
    words += line_words(100, (10, "Revenue was $2 million and $10 million during the quarter, respectively."))
    words += line_words(115, (10, "In 2022 and 2021 we sold 5 units and 7 units in total across regions."))
    assert detect_tables(group_lines(words), page_width=612) == []


def test_wrapped_label_lines_are_joined():
    words = []
    words += line_words(80, (10, "Item"), (300, "2018"), (360, "2017"))
    words += line_words(95, (10, "Adjustments to reconcile net income"))
    words += line_words(110, (10, "provided by operations"), (305, "1,488"), (365, "1,544"))
    words += line_words(125, (10, "Other"), (305, "1"), (365, "2"))
    words += line_words(140, (10, "Property, net of depreciation of"))
    words += line_words(155, (10, "$13,663 and $12,995"), (305, "15,742"), (365, "15,337"))
    md = detect_tables(group_lines(words), page_width=612)[0].markdown
    assert "| Adjustments to reconcile net income provided by operations | 1,488 | 1,544 |" in md
    assert "| Property, net of depreciation of $13,663 and $12,995 | 15,742 | 15,337 |" in md
