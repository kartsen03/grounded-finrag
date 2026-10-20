from collections import Counter

from finrag.ingest.text_repair import build_vocab, fix_glyphs, join_lines, repair_split_words

from helpers import word


def test_split_fragment_joined_when_whole_word_seen_elsewhere():
    vocab = build_vocab(["Cash", "Flows", "Flows", "Statement"])
    words = [word("Cash", 10, 0), word("Flow", 40, 0), word("s", 59, 0)]
    log: list[str] = []
    out = repair_split_words(words, vocab, log)
    assert [w["text"] for w in out] == ["Cash", "Flows"]
    assert log and log[0].startswith("Flow s -> Flows")


def test_two_real_words_are_not_joined():
    vocab = Counter({"to": 50, "day": 10, "today": 5})
    words = [word("to", 10, 0), word("day", 22, 0)]
    out = repair_split_words(words, vocab, [])
    assert [w["text"] for w in out] == ["to", "day"]


def test_dehyphenation_only_for_known_words():
    vocab = Counter({"revenue": 3})
    log: list[str] = []
    assert join_lines(["total reve-", "nue grew"], vocab, log) == "total revenue grew"
    assert join_lines(["a long-", "term loan"], vocab, []) == "a long-term loan"
    assert len(log) == 1


def test_fix_glyphs_apostrophe_vs_dash():
    assert fix_glyphs("company�s plans� obligation") == "company’s plans’ obligation"
    assert fix_glyphs("Note 4 � Segment") == "Note 4 — Segment"
