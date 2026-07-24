from scripts.consolidate_ebay_resume_batch import merge_rows_by_product, select_listing_rows


def test_attempt_rows_replace_legacy_rows_by_product():
    merged, source = merge_rows_by_product(
        ["A", "B"],
        [
            {"canonical_product_id": "A", "coverage_state": "LIMITED_MATCH_COVERAGE"},
            {"canonical_product_id": "B", "coverage_state": "SOURCE_ERROR"},
        ],
        [{"canonical_product_id": "B", "coverage_state": "NO_MATCHES"}],
    )
    assert [row["coverage_state"] for row in merged] == ["LIMITED_MATCH_COVERAGE", "NO_MATCHES"]
    assert source == {"A": "legacy", "B": "attempt"}


def test_merge_preserves_expected_product_order():
    merged, _ = merge_rows_by_product(
        ["B", "A"],
        [{"canonical_product_id": "A"}],
        [{"canonical_product_id": "B"}],
    )
    assert [row["canonical_product_id"] for row in merged] == ["B", "A"]


def test_listing_selection_uses_governed_product_source():
    rows = [
        {"canonical_product_id": "A", "ebay_item_id": "1"},
        {"canonical_product_id": "B", "ebay_item_id": "2"},
    ]
    source = {"A": "legacy", "B": "attempt"}
    assert select_listing_rows(rows, source, "attempt") == [rows[1]]
