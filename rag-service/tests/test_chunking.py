from finrag.corpus import DocMeta
from finrag.ingest import chunking

META = DocMeta("ACME_2022_10K", "Acme", "10-K", 2022, None, None, "Industrials")


def _block(kind, text, section="Item 8. Financial Statements"):
    return {"kind": kind, "text": text, "section": section, "subsection": None}


def _table(rows):
    lines = ["| (Millions) | 2022 | 2021 |", "|---|---|---|"]
    lines += [f"| Line item number {i} with a fairly long label | {i},000 | {i},500 |" for i in range(rows)]
    return "\n".join(lines)


def test_structure_chunks_stay_on_one_page_and_keep_heading_with_content():
    pages = [
        {"page_idx": 0, "blocks": [_block("heading", "Revenue"), _block("text", "Revenue grew. " * 20)]},
        {"page_idx": 1, "blocks": [_block("text", "Costs fell. " * 20)]},
    ]
    chunks = chunking.structure_chunks(META, pages)
    assert [c.pages for c in chunks] == [[0], [1]]
    assert chunks[0].text.startswith("Revenue\n\n")
    assert chunks[0].embed_text.startswith("Acme 10-K FY2022 | Item 8. Financial Statements\n")


def test_large_table_split_by_rows_with_header_repeated():
    pages = [{"page_idx": 3, "blocks": [_block("table", _table(60))]}]
    chunks = chunking.structure_chunks(META, pages)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.startswith("| (Millions) | 2022 | 2021 |\n|---|---|---|")
        assert c.n_tokens <= chunking.CHUNK_TOKENS
        assert c.has_table


def test_fixed_chunks_overlap_and_record_pages():
    pages = [{"page_idx": i, "blocks": [_block("text", f"Page {i} sentence. " * 120)]} for i in range(3)]
    chunks = chunking.fixed_chunks(META, pages)
    assert len(chunks) >= 3
    assert all(c.n_tokens <= chunking.CHUNK_TOKENS + 2 for c in chunks)
    assert any(len(c.pages) > 1 for c in chunks)  # windows cross page boundaries
