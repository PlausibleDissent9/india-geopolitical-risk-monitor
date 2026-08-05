"""Corpus-depth receipts: anchor set arithmetic and channel assembly,
all against synthetic corpus structures (no network)."""
from __future__ import annotations

from src import receipts_ngrams


def _corpus():
    return {
        "n_docs_sampled": 1000,
        "n_samples": 4,
        "india": {"t1:1", "t1:2", "t1:4"},
        "matched": {
            "ch/q1": {"t1:1", "t1:3"},
            "ch/q2": {"t1:2"},
            "other/q1": {"t1:9"},
        },
        "meta": {
            "t1:1": {"url": "https://reuters.com/a", "title": "Border talks stall",
                     "date": "20260805"},
            "t1:2": {"url": "https://mill.example/b", "title": "Border talks stall",
                     "date": "20260805"},
            "t1:3": {"url": "javascript:alert(1)", "title": "Injected",
                     "date": "20260805"},
            "t1:9": {"url": "https://elsewhere.example/c",
                     "title": "A completely different headline",
                     "date": "20260805"},
        },
    }


SPECS = {
    "ch/q1": {"channel": "ch", "phrases": (("border", "talks"),), "anchor": "india"},
    "ch/q2": {"channel": "ch", "phrases": (("line", "of", "control"),),
              "anchor": "india"},
    "other/q1": {"channel": "other", "phrases": (("unrelated",),), "anchor": None},
}


def test_channel_doc_keys_applies_anchor_per_document():
    keys = receipts_ngrams.channel_doc_keys("ch", SPECS, _corpus())
    # t1:3 matched ch/q1 but never carried the india anchor token.
    assert keys == {"t1:1", "t1:2"}


def test_channel_doc_keys_without_anchor_takes_plain_union():
    keys = receipts_ngrams.channel_doc_keys("other", SPECS, _corpus())
    assert keys == {"t1:9"}


def test_assemble_channel_dedupes_syndication_and_labels_aptness():
    spec = {"label": "Test channel", "anchor": "india",
            "terms": ['"border talks"', '"line of control"']}
    block = receipts_ngrams.assemble_channel(
        "ch", spec, {"t1:1", "t1:2", "t1:3"}, _corpus(),
        tiers={"reuters.com": 1},
    )
    # javascript: scheme never renders; identical headlines collapse to
    # the best-tiered instance (reuters over the untiered mill).
    assert block["n_matched_in_corpus"] == 2
    assert block["n_pool_unique"] == 1
    assert [a["domain"] for a in block["articles"]] == ["reuters.com"]
    art = block["articles"][0]
    assert art["tier"] == 1
    assert art["lane"] == "corpus"
    assert art["match"] == "headline"  # "border talks" is in the title
    assert "_title_hit" not in art and "_rel" not in art
    assert block["pool_exhausted"] is True
    assert block["spike_quality_tier12_share"] == 1.0


def test_artlist_supplement_merges_deduped_and_lane_labeled():
    spec = {"label": "Test channel", "anchor": "india",
            "terms": ['"border talks"', '"line of control"']}
    supplement = [
        # Duplicate of a corpus URL: must not double-count.
        {"title": "Border talks stall", "domain": "reuters.com",
         "date": "20260805", "url": "https://reuters.com/a", "match": "headline"},
        # Genuinely new tier-1 wire original.
        {"title": "Line of Control shelling resumes", "domain": "apnews.com",
         "date": "20260805", "url": "https://apnews.com/x", "match": "headline"},
    ]
    block = receipts_ngrams.assemble_channel(
        "ch", spec, {"t1:1", "t1:2"}, _corpus(),
        tiers={"reuters.com": 1, "apnews.com": 1}, supplement=supplement,
    )
    assert block["n_matched_in_corpus"] == 2
    assert block["n_artlist_supplement"] == 1
    lanes = {a["url"]: a["lane"] for a in block["articles"]}
    assert lanes["https://reuters.com/a"] == "corpus"
    assert lanes["https://apnews.com/x"] == "artlist"


def test_assemble_channel_full_text_label_when_phrase_not_in_title():
    spec = {"label": "Test channel", "anchor": None,
            "terms": ['"unrelated"']}
    block = receipts_ngrams.assemble_channel(
        "other", spec, {"t1:9"}, _corpus(), tiers={},
    )
    assert block["articles"][0]["match"] == "full-text"
    assert block["articles"][0]["tier"] is None
