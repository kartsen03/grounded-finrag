from finrag.eval import metrics


def test_ranked_pages_dedupes_in_order():
    hits = [{"doc_name": "D", "page_idx": 3}, {"doc_name": "D", "page_idx": 3}, {"doc_name": "D", "page_idx": 9}]
    assert metrics.ranked_pages(hits) == [("D", 3), ("D", 9)]


def test_hits_and_mrr_from_first_gold_rank():
    pages = [("D", 1), ("D", 2), ("E", 7)]
    rank = metrics.first_gold_rank(pages, {("E", 7), ("D", 9)})
    assert rank == 3
    m = metrics.question_metrics(rank)
    assert (m["hit@1"], m["hit@3"], m["hit@5"]) == (0.0, 1.0, 1.0)
    assert abs(m["mrr@10"] - 1 / 3) < 1e-9
    assert metrics.question_metrics(None)["mrr@10"] == 0.0
    assert metrics.question_metrics(11)["hit@10"] == 0.0


def test_bootstrap_ci_brackets_mean_and_is_seeded():
    values = [1.0] * 30 + [0.0] * 70
    lo, hi = metrics.bootstrap_ci(values, seed=1)
    assert lo < 0.3 < hi
    assert metrics.bootstrap_ci(values, seed=1) == (lo, hi)


def test_percentile_interpolates():
    assert metrics.percentile([10, 20, 30, 40], 0.5) == 25.0
    assert metrics.percentile([5], 0.95) == 5.0
