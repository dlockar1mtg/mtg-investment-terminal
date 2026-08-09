from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_CANONICAL = 131
EXPECTED_CERTIFIED_PRODUCTS = 111
EXPECTED_GAPS = 20
EXPECTED_SEMANTIC_RESOLVED = 89
EXPECTED_RESIDUAL_COLLISIONS = 5


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        return list(
            csv.DictReader(handle)
        )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: list[str],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        for block in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def load_universe(
    package: Path,
) -> list[dict[str, str]]:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        member = (
            "precollector_canonical_universe_v2.csv"
        )

        if member not in archive.namelist():
            fail(
                f"missing corrected universe member: {member}"
            )

        raw = archive.read(
            member
        ).decode(
            "utf-8-sig"
        )

    rows = list(
        csv.DictReader(
            raw.splitlines()
        )
    )

    if len(rows) != EXPECTED_CANONICAL:
        fail(
            f"canonical count {len(rows)} "
            f"!= {EXPECTED_CANONICAL}"
        )

    return rows


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--universe-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--identity-audit",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--semantic-collisions",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--stage15n-product-simulation",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--stage15n-seal-candidates",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--stage15n-residual-collisions",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--stage15n-summary",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--expected-identity-sha",
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    universe = load_universe(
        args.universe_package
    )

    canonical = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            row
        for row in universe
    }

    if len(canonical) != EXPECTED_CANONICAL:
        fail(
            "canonical IDs are not uniquely 131"
        )

    identity_material = "\n".join(
        f"{row['canonical_product_id']}|{row['product_name']}"
        for row in sorted(
            universe,
            key=lambda row: int(
                clean(
                    row[
                        "canonical_product_id"
                    ]
                ).split(":")[-1]
            ),
        )
    ) + "\n"

    identity_sha = hashlib.sha256(
        identity_material.encode(
            "utf-8"
        )
    ).hexdigest()

    if identity_sha != args.expected_identity_sha:
        fail(
            "corrected identity SHA mismatch"
        )

    identity_audit = read_csv(
        args.identity_audit
    )

    semantic = read_csv(
        args.semantic_collisions
    )

    simulation = read_csv(
        args.stage15n_product_simulation
    )

    seal_candidates = read_csv(
        args.stage15n_seal_candidates
    )

    residual_collisions = read_csv(
        args.stage15n_residual_collisions
    )

    stage15n_summary = json.loads(
        args.stage15n_summary.read_text(
            encoding="utf-8-sig"
        )
    )

    if len(simulation) != 131:
        fail(
            "Stage-15N product simulation is not 131 rows"
        )

    resolved_semantic = [
        row
        for row in semantic
        if clean(
            row[
                "simulation_resolution"
            ]
        )
        == "UNIQUE_SPECIFIC_CANONICAL_WINNER"
    ]

    if len(resolved_semantic) != EXPECTED_SEMANTIC_RESOLVED:
        fail(
            "semantic-resolution count drift"
        )

    if len(residual_collisions) != EXPECTED_RESIDUAL_COLLISIONS:
        fail(
            "residual collision count drift"
        )

    # ------------------------------------------------------------------------
    # Reconstruct admitted evidence from three evidence paths:
    #
    #   A. Stage-15I direct accepted listings
    #   B. Stage-15M semantic unique winners
    #   C. Stage-15N explicit sealed metadata listings
    #
    # Deduplicate by canonical product + ebay item id.
    # ------------------------------------------------------------------------

    admitted: dict[
        tuple[str, str],
        dict[str, object],
    ] = {}

    # A. Original Stage-15I accepted evidence
    for row in identity_audit:

        if clean(
            row.get(
                "identity_match_state"
            )
        ) != "PROVISIONAL_ACCEPTED":
            continue

        canonical_id = clean(
            row[
                "canonical_product_id"
            ]
        )

        item_id = clean(
            row[
                "ebay_item_id"
            ]
        )

        if canonical_id not in canonical:
            fail(
                "accepted listing references noncanonical product"
            )

        if not item_id:
            fail(
                "accepted listing has blank eBay item ID"
            )

        admitted[
            (
                canonical_id,
                item_id,
            )
        ] = {
            "canonical_product_id":
                canonical_id,

            "tcgplayer_product_id":
                canonical_id.split(":")[-1],

            "product_name":
                clean(
                    canonical[
                        canonical_id
                    ][
                        "product_name"
                    ]
                ),

            "ebay_item_id":
                item_id,

            "title":
                clean(
                    row.get(
                        "title"
                    )
                ),

            "landed_price":
                clean(
                    row.get(
                        "landed_price"
                    )
                ),

            "seller_hash":
                clean(
                    row.get(
                        "seller_hash"
                    )
                ),

            "condition":
                clean(
                    row.get(
                        "condition"
                    )
                ),

            "availability_evidence_path":
                "DIRECT_TITLE_SEALED_IDENTITY_MATCH",

            "identity_match_score":
                clean(
                    row.get(
                        "identity_match_score"
                    )
                ),

            "identity_token_coverage":
                clean(
                    row.get(
                        "identity_token_coverage"
                    )
                ),
        }

    # B. Semantic unique winners
    audit_by_item_product = {
        (
            clean(
                row.get(
                    "ebay_item_id"
                )
            ),
            clean(
                row.get(
                    "canonical_product_id"
                )
            ),
        ): row
        for row in identity_audit
        if clean(
            row.get(
                "ebay_item_id"
            )
        )
    }

    for resolution in resolved_semantic:

        item_id = clean(
            resolution[
                "ebay_item_id"
            ]
        )

        winner = clean(
            resolution[
                "resolved_winner_canonical_id"
            ]
        )

        if winner not in canonical:
            fail(
                "semantic winner is noncanonical"
            )

        source = audit_by_item_product.get(
            (
                item_id,
                winner,
            )
        )

        if source is None:
            fail(
                "could not reconstruct semantic winner listing"
            )

        admitted[
            (
                winner,
                item_id,
            )
        ] = {
            "canonical_product_id":
                winner,

            "tcgplayer_product_id":
                winner.split(":")[-1],

            "product_name":
                clean(
                    canonical[
                        winner
                    ][
                        "product_name"
                    ]
                ),

            "ebay_item_id":
                item_id,

            "title":
                clean(
                    source.get(
                        "title"
                    )
                ),

            "landed_price":
                clean(
                    source.get(
                        "landed_price"
                    )
                ),

            "seller_hash":
                clean(
                    source.get(
                        "seller_hash"
                    )
                ),

            "condition":
                clean(
                    source.get(
                        "condition"
                    )
                ),

            "availability_evidence_path":
                "SEMANTIC_MORE_SPECIFIC_CANONICAL_WINNER",

            "identity_match_score":
                clean(
                    source.get(
                        "identity_match_score"
                    )
                ),

            "identity_token_coverage":
                clean(
                    source.get(
                        "identity_token_coverage"
                    )
                ),
        }

    # C. Explicit eBay sealed-condition metadata
    for seal in seal_candidates:

        canonical_id = clean(
            seal[
                "canonical_product_id"
            ]
        )

        item_id = clean(
            seal[
                "ebay_item_id"
            ]
        )

        if canonical_id not in canonical:
            fail(
                "seal-metadata candidate is noncanonical"
            )

        source = audit_by_item_product.get(
            (
                item_id,
                canonical_id,
            )
        )

        if source is None:
            fail(
                "could not reconstruct sealed-metadata listing"
            )

        admitted[
            (
                canonical_id,
                item_id,
            )
        ] = {
            "canonical_product_id":
                canonical_id,

            "tcgplayer_product_id":
                canonical_id.split(":")[-1],

            "product_name":
                clean(
                    canonical[
                        canonical_id
                    ][
                        "product_name"
                    ]
                ),

            "ebay_item_id":
                item_id,

            "title":
                clean(
                    source.get(
                        "title"
                    )
                ),

            "landed_price":
                clean(
                    source.get(
                        "landed_price"
                    )
                ),

            "seller_hash":
                clean(
                    source.get(
                        "seller_hash"
                    )
                ),

            "condition":
                clean(
                    source.get(
                        "condition"
                    )
                ),

            "availability_evidence_path":
                "FULL_IDENTITY_PLUS_EXPLICIT_SEALED_CONDITION",

            "identity_match_score":
                clean(
                    source.get(
                        "identity_match_score"
                    )
                ),

            "identity_token_coverage":
                clean(
                    source.get(
                        "identity_token_coverage"
                    )
                ),
        }

    # ------------------------------------------------------------------------
    # Residual semantic collisions MUST NOT appear as admitted evidence for
    # any product/item pairing.
    # ------------------------------------------------------------------------

    residual_item_ids = {
        clean(
            row[
                "ebay_item_id"
            ]
        )
        for row in residual_collisions
    }

    residual_admitted = [
        key
        for key in admitted
        if key[1] in residual_item_ids
    ]

    if residual_admitted:
        fail(
            "residual unresolved collision entered admitted authority"
        )

    admitted_rows = list(
        admitted.values()
    )

    admitted_by_product: dict[
        str,
        list[dict[str, object]],
    ] = defaultdict(list)

    for row in admitted_rows:

        admitted_by_product[
            clean(
                row[
                    "canonical_product_id"
                ]
            )
        ].append(row)

    certified_products = {
        product_id
        for product_id, rows
        in admitted_by_product.items()
        if rows
    }

    if len(certified_products) != EXPECTED_CERTIFIED_PRODUCTS:
        fail(
            f"certified availability product count "
            f"{len(certified_products)} "
            f"!= {EXPECTED_CERTIFIED_PRODUCTS}"
        )

    gap_products = (
        set(canonical)
        - certified_products
    )

    if len(gap_products) != EXPECTED_GAPS:
        fail(
            f"availability gap count {len(gap_products)} "
            f"!= {EXPECTED_GAPS}"
        )

    # ------------------------------------------------------------------------
    # 131-row coverage ledger
    # ------------------------------------------------------------------------

    coverage_rows = []
    gap_rows = []

    for canonical_id in sorted(
        canonical,
        key=lambda value: int(
            value.split(":")[-1]
        ),
    ):

        identity = canonical[
            canonical_id
        ]

        evidence = admitted_by_product.get(
            canonical_id,
            [],
        )

        sellers = {
            clean(
                row[
                    "seller_hash"
                ]
            )
            for row in evidence
            if clean(
                row[
                    "seller_hash"
                ]
            )
        }

        positive_prices = []

        for row in evidence:

            raw = clean(
                row[
                    "landed_price"
                ]
            )

            try:
                value = float(
                    raw
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if value > 0:
                positive_prices.append(
                    value
                )

        evidence_paths = sorted(
            {
                clean(
                    row[
                        "availability_evidence_path"
                    ]
                )
                for row in evidence
            }
        )

        if evidence:

            coverage_rows.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        clean(
                            identity[
                                "product_name"
                            ]
                        ),

                    "availability_evidence_status":
                        "CERTIFIED_EBAY_AVAILABILITY_EVIDENCE",

                    "accepted_listing_count":
                        len(evidence),

                    "unique_seller_count":
                        len(sellers),

                    "positive_landed_price_count":
                        len(
                            positive_prices
                        ),

                    "evidence_paths":
                        "|".join(
                            evidence_paths
                        ),

                    "model_eligibility_automatically_changed":
                        "false",
                }
            )

        else:

            coverage_rows.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        clean(
                            identity[
                                "product_name"
                            ]
                        ),

                    "availability_evidence_status":
                        "NO_CERTIFIED_EBAY_AVAILABILITY_EVIDENCE",

                    "accepted_listing_count":
                        0,

                    "unique_seller_count":
                        0,

                    "positive_landed_price_count":
                        0,

                    "evidence_paths":
                        "",

                    "model_eligibility_automatically_changed":
                        "false",
                }
            )

            gap_rows.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        clean(
                            identity[
                                "product_name"
                            ]
                        ),

                    "gap_reason":
                        "NO_ADMISSIBLE_IDENTITY_SAFE_EBAY_AVAILABILITY_EVIDENCE",

                    "canonical_universe_membership":
                        "true",

                    "model_exclusion_authorized":
                        "false",

                    "prediction_exclusion_authorized":
                        "false",

                    "synthetic_availability_authorized":
                        "false",
                }
            )

    if len(coverage_rows) != 131:
        fail(
            "coverage ledger is not 131 rows"
        )

    if len(gap_rows) != 20:
        fail(
            "gap ledger is not 20 rows"
        )

    # ------------------------------------------------------------------------
    # Evidence-path counts
    # ------------------------------------------------------------------------

    path_counts = Counter(
        clean(
            row[
                "availability_evidence_path"
            ]
        )
        for row in admitted_rows
    )

    # ------------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------------

    output_root = (
        args.output_root.resolve()
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    authority_path = (
        output_root
        / "precollector_availability_authority_v1.csv"
    )

    coverage_path = (
        output_root
        / "precollector_availability_coverage_v1.csv"
    )

    gaps_path = (
        output_root
        / "precollector_availability_gaps_v1.csv"
    )

    unresolved_path = (
        output_root
        / "precollector_availability_unresolved_collisions_v1.csv"
    )

    summary_path = (
        output_root
        / "precollector_availability_authority_v1_summary.json"
    )

    manifest_path = (
        output_root
        / "precollector_availability_authority_v1_manifest.json"
    )

    authority_fields = [
        "canonical_product_id",
        "tcgplayer_product_id",
        "product_name",
        "ebay_item_id",
        "title",
        "landed_price",
        "seller_hash",
        "condition",
        "availability_evidence_path",
        "identity_match_score",
        "identity_token_coverage",
    ]

    write_csv(
        authority_path,
        sorted(
            admitted_rows,
            key=lambda row: (
                int(
                    clean(
                        row[
                            "canonical_product_id"
                        ]
                    ).split(":")[-1]
                ),
                clean(
                    row[
                        "ebay_item_id"
                    ]
                ),
            ),
        ),
        authority_fields,
    )

    write_csv(
        coverage_path,
        coverage_rows,
        [
            "canonical_product_id",
            "tcgplayer_product_id",
            "product_name",
            "availability_evidence_status",
            "accepted_listing_count",
            "unique_seller_count",
            "positive_landed_price_count",
            "evidence_paths",
            "model_eligibility_automatically_changed",
        ],
    )

    write_csv(
        gaps_path,
        gap_rows,
        [
            "canonical_product_id",
            "tcgplayer_product_id",
            "product_name",
            "gap_reason",
            "canonical_universe_membership",
            "model_exclusion_authorized",
            "prediction_exclusion_authorized",
            "synthetic_availability_authorized",
        ],
    )

    write_csv(
        unresolved_path,
        residual_collisions,
        list(
            residual_collisions[0].keys()
        )
        if residual_collisions
        else [
            "ebay_item_id",
        ],
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_AVAILABILITY_AUTHORITY_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "canonical_product_count":
            131,

        "corrected_identity_sha256":
            identity_sha,

        "certified_availability_product_count":
            111,

        "availability_gap_product_count":
            20,

        "admitted_listing_row_count":
            len(
                admitted_rows
            ),

        "semantic_collisions_tested":
            94,

        "semantic_collisions_resolved":
            89,

        "residual_unresolved_collision_count":
            5,

        "residual_unresolved_collisions_admitted":
            False,

        "explicit_sealed_metadata_candidate_rows":
            len(
                seal_candidates
            ),

        "evidence_path_counts":
            dict(
                path_counts
            ),

        "plain_new_accepted_as_sealed":
            False,

        "minimum_listing_count_threshold_used":
            False,

        "minimum_seller_count_threshold_used":
            False,

        "availability_gap_implies_model_exclusion":
            False,

        "model_execution_authorized":
            False,

        "authorized_next_stage":
            "BUILD_PRECOLLECTOR_EMPIRICAL_MODEL_ELIGIBILITY_DIAGNOSTICS",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    members = [
        authority_path,
        coverage_path,
        gaps_path,
        unresolved_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_availability_authority_v1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "corrected_identity_sha256":
            identity_sha,

        "source_identity_audit_sha256":
            sha256_file(
                args.identity_audit
            ),

        "source_semantic_collision_sha256":
            sha256_file(
                args.semantic_collisions
            ),

        "source_stage15n_summary_sha256":
            sha256_file(
                args.stage15n_summary
            ),

        "members": [
            {
                "file_name":
                    path.name,

                "byte_length":
                    path.stat().st_size,

                "sha256":
                    sha256_file(path),
            }
            for path in members
        ],
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "PASS_PRECOLLECTOR_AVAILABILITY_AUTHORITY_V1"
    )

    print(
        "CANONICAL_PRODUCT_COUNT=131"
    )

    print(
        "CERTIFIED_AVAILABILITY_PRODUCTS=111"
    )

    print(
        "AVAILABILITY_GAP_PRODUCTS=20"
    )

    print(
        f"ADMITTED_LISTING_ROWS={len(admitted_rows)}"
    )

    print(
        "SEMANTIC_COLLISIONS_RESOLVED=89"
    )

    print(
        "RESIDUAL_COLLISIONS_UNADMITTED=5"
    )

    print(
        "PLAIN_NEW_ACCEPTED_AS_SEALED=FALSE"
    )

    print(
        "FIXED_LISTING_THRESHOLD_USED=FALSE"
    )

    print(
        "FIXED_SELLER_THRESHOLD_USED=FALSE"
    )

    print(
        "AVAILABILITY_GAP_IMPLIES_MODEL_EXCLUSION=FALSE"
    )

    print(
        "MODEL_EXECUTION_AUTHORIZED=FALSE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())