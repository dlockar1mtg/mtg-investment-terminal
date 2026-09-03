from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

COLLECTOR_CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "mtg_collector_research_sidecar_schema_v1.json"
)

PRE_CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "mtg_precollector_research_sidecar_schema_v1.json"
)

OUT_DIR = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "research_sidecars"
)

COLLECTOR_PRODUCT_OUT = OUT_DIR / "mtg_collector_research.csv"

COLLECTOR_HORIZON_OUT = (
    OUT_DIR / "mtg_collector_forecast_horizon.csv"
)

PRE_PRODUCT_OUT = OUT_DIR / "mtg_precollector_research.csv"

PRE_SCENARIO_OUT = (
    OUT_DIR / "mtg_precollector_scenario_horizon.csv"
)

CERTIFIED_INPUTS = (
    Path.home()
    / "Downloads"
    / "UIP_MTG_Governance"
    / "Certified_Inputs"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)

    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Required file missing: {path}")


def require_hash(path: Path, expected: str) -> None:
    actual = sha256_file(path)

    if actual != expected.lower():
        raise RuntimeError(
            f"SHA mismatch for {path}: "
            f"expected={expected.lower()} actual={actual}"
        )


def load_json(path: Path) -> dict:
    require_file(path)

    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    require_file(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def index_unique(
    rows: list[dict[str, str]],
    key: str,
    label: str,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}

    for row in rows:
        value = row.get(key, "")

        if not value:
            raise RuntimeError(
                f"{label}: missing key {key}"
            )

        if value in result:
            raise RuntimeError(
                f"{label}: duplicate key {value}"
            )

        result[value] = row

    return result


def blank_row(fields: list[str]) -> dict[str, str]:
    return {field: "" for field in fields}


def write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict[str, str]],
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
            extrasaction="raise",
            lineterminator="\n",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    field: row.get(field, "")
                    for field in fields
                }
            )


def read_zip_csv_member(
    archive: zipfile.ZipFile,
    member_name: str,
    expected_sha: str,
) -> list[dict[str, str]]:

    matches = [
        info
        for info in archive.infolist()
        if Path(info.filename).name == member_name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one ZIP member "
            f"{member_name}; found {len(matches)}"
        )

    data = archive.read(matches[0])

    actual = sha256_bytes(data)

    if actual != expected_sha.lower():
        raise RuntimeError(
            f"ZIP member SHA mismatch: {member_name}"
        )

    text = data.decode("utf-8-sig")

    return list(
        csv.DictReader(
            io.StringIO(text)
        )
    )


def verify_same(
    *,
    left: str,
    right: str,
    label: str,
    allow_blank: bool = True,
) -> None:

    if allow_blank and (left == "" or right == ""):
        return

    if left != right:
        raise RuntimeError(
            f"Authority disagreement for {label}: "
            f"{left!r} != {right!r}"
        )


collector_contract = load_json(
    COLLECTOR_CONTRACT
)

pre_contract = load_json(
    PRE_CONTRACT
)

if (
    collector_contract["status"]
    != "AUTHORIZED_FOR_BOUNDED_SIDECAR_ASSEMBLY"
):
    raise RuntimeError(
        "Collector sidecar assembly not authorized."
    )

if (
    pre_contract["status"]
    != "AUTHORIZED_FOR_BOUNDED_SIDECAR_ASSEMBLY"
):
    raise RuntimeError(
        "Pre-Collector sidecar assembly not authorized."
    )

if (
    collector_contract["common_interface"]["mtg_v1_field_count"]
    != 23
):
    raise RuntimeError(
        "Collector common interface is not frozen at 23 fields."
    )

if (
    pre_contract["common_interface"]["mtg_v1_field_count"]
    != 23
):
    raise RuntimeError(
        "Pre-Collector common interface is not frozen at 23 fields."
    )


# ============================================================
# COLLECTOR
# ============================================================

collector_authority = collector_contract["authority"]

collector_paths: dict[str, Path] = {}

for authority_name in (
    "current_price",
    "forecast",
    "ranking",
    "purchase",
):
    spec = collector_authority[authority_name]

    path = ROOT / spec["path"]

    require_hash(
        path,
        spec["sha256"],
    )

    collector_paths[authority_name] = path


collector_price_rows = read_csv(
    collector_paths["current_price"]
)

collector_forecast_rows = read_csv(
    collector_paths["forecast"]
)

collector_ranking_rows = read_csv(
    collector_paths["ranking"]
)

collector_purchase_rows = read_csv(
    collector_paths["purchase"]
)


collector_price = index_unique(
    collector_price_rows,
    "canonical_product_id",
    "collector current-price authority",
)

collector_ranking = index_unique(
    collector_ranking_rows,
    "canonical_product_id",
    "collector ranking authority",
)

collector_purchase = index_unique(
    collector_purchase_rows,
    "canonical_product_id",
    "collector purchase authority",
)


if len(collector_price) != 50:
    raise RuntimeError(
        f"Expected 50 Collector price rows; "
        f"found {len(collector_price)}"
    )

if len(collector_ranking) != 49:
    raise RuntimeError(
        f"Expected 49 Collector ranking rows; "
        f"found {len(collector_ranking)}"
    )

if len(collector_purchase) != 49:
    raise RuntimeError(
        f"Expected 49 Collector purchase rows; "
        f"found {len(collector_purchase)}"
    )


collector_product_fields = (
    collector_contract["product_record"]["fields"]
)

collector_product_rows: list[dict[str, str]] = []


collector_forecast_ids = {
    row["canonical_product_id"]
    for row in collector_forecast_rows
}

collector_price_only_ids = (
    set(collector_price)
    - set(collector_ranking)
)

if collector_price_only_ids != {
    "MTG-CANON-TCGPLAYER-515906"
}:
    raise RuntimeError(
        "Collector current-price-only population changed: "
        f"{sorted(collector_price_only_ids)}"
    )


for canonical_id in sorted(
    collector_price.keys()
):

    price = collector_price[canonical_id]

    ranking = collector_ranking.get(
        canonical_id
    )

    purchase = collector_purchase.get(
        canonical_id
    )

    has_ranking = ranking is not None
    has_purchase = purchase is not None
    has_forecast = canonical_id in collector_forecast_ids

    if has_ranking != has_purchase:
        raise RuntimeError(
            f"Collector ranking/purchase authority mismatch: "
            f"{canonical_id}"
        )

    if has_ranking != has_forecast:
        raise RuntimeError(
            f"Collector analytical-authority mismatch: "
            f"{canonical_id}"
        )

    if canonical_id == "MTG-CANON-TCGPLAYER-515906":

        if has_ranking or has_purchase or has_forecast:
            raise RuntimeError(
                "Governed current-price-only Collector asset "
                "unexpectedly acquired analytical authority."
            )

    else:

        if not (
            has_ranking
            and has_purchase
            and has_forecast
        ):
            raise RuntimeError(
                f"Ranked Collector core incomplete: "
                f"{canonical_id}"
            )

    sources = [
        price,
    ]

    if ranking is not None:

        verify_same(
            left=price["product_name"],
            right=ranking["product_name"],
            label=f"{canonical_id} product name / ranking",
        )

        verify_same(
            left=price["current_price"],
            right=ranking["current_price"],
            label=f"{canonical_id} current price / ranking",
        )

        sources.append(
            ranking
        )

    if purchase is not None:

        verify_same(
            left=price["product_name"],
            right=purchase["product_name"],
            label=f"{canonical_id} product name / purchase",
        )

        verify_same(
            left=price["current_price"],
            right=purchase["current_price"],
            label=f"{canonical_id} current price / purchase",
        )

        sources.append(
            purchase
        )

    row = blank_row(
        collector_product_fields
    )

    for field in collector_product_fields:

        values = [
            source.get(field, "")
            for source in sources
            if source.get(field, "") != ""
        ]

        if not values:
            continue

        if len(set(values)) != 1:
            raise RuntimeError(
                f"Collector source disagreement "
                f"{canonical_id} field={field} "
                f"values={values}"
            )

        row[field] = values[0]

    collector_product_rows.append(row)


collector_horizon_fields = (
    collector_contract["forecast_horizon_record"]["fields"]
)

authorized_horizons = {
    str(value)
    for value in collector_contract[
        "forecast_horizon_record"
    ]["authorized_horizons_days"]
}

collector_horizon_rows: list[dict[str, str]] = []

seen_collector_horizon_keys: set[tuple[str, str]] = set()


for source in collector_forecast_rows:

    canonical_id = source["canonical_product_id"]
    horizon = source["horizon_days"]

    if canonical_id not in collector_price:
        raise RuntimeError(
            f"Collector forecast contains unknown product: "
            f"{canonical_id}"
        )

    if horizon not in authorized_horizons:
        raise RuntimeError(
            f"Unauthorized Collector horizon: {horizon}"
        )

    key = (
        canonical_id,
        horizon,
    )

    if key in seen_collector_horizon_keys:
        raise RuntimeError(
            f"Duplicate Collector horizon key: {key}"
        )

    seen_collector_horizon_keys.add(key)

    price = collector_price[canonical_id]

    verify_same(
        left=price["current_price"],
        right=source["current_price"],
        label=f"{canonical_id}/{horizon} forecast current price",
    )

    verify_same(
        left=price["product_name"],
        right=source["product_name"],
        label=f"{canonical_id}/{horizon} forecast product name",
    )

    row = blank_row(
        collector_horizon_fields
    )

    for field in collector_horizon_fields:
        row[field] = source.get(
            field,
            "",
        )

    collector_horizon_rows.append(row)


collector_horizon_rows.sort(
    key=lambda row: (
        row["canonical_product_id"],
        int(row["horizon_days"]),
    )
)


if len(collector_product_rows) != 50:
    raise RuntimeError(
        f"Collector product output count != 50: "
        f"{len(collector_product_rows)}"
    )

if len(collector_horizon_rows) != 294:
    raise RuntimeError(
        f"Collector horizon output count != 294: "
        f"{len(collector_horizon_rows)}"
    )


write_csv(
    COLLECTOR_PRODUCT_OUT,
    collector_product_fields,
    collector_product_rows,
)

write_csv(
    COLLECTOR_HORIZON_OUT,
    collector_horizon_fields,
    collector_horizon_rows,
)


# ============================================================
# PRE-COLLECTOR
# ============================================================

pre_authority = pre_contract["authority"]

pre_package_path = (
    CERTIFIED_INPUTS
    / pre_authority["certified_package"]["name"]
)

pre_price_package_path = (
    CERTIFIED_INPUTS
    / pre_authority["current_price_package"]["name"]
)


require_hash(
    pre_package_path,
    pre_authority["certified_package"]["sha256"],
)

require_hash(
    pre_price_package_path,
    pre_authority["current_price_package"]["sha256"],
)


with zipfile.ZipFile(
    pre_package_path,
    "r",
) as archive:

    disposition_rows = read_zip_csv_member(
        archive,
        pre_authority["complete_disposition"]["member"],
        pre_authority["complete_disposition"]["sha256"],
    )

    scenario_rows_source = read_zip_csv_member(
        archive,
        pre_authority["forecast_and_risk"]["member"],
        pre_authority["forecast_and_risk"]["sha256"],
    )

    purchase_rows = read_zip_csv_member(
        archive,
        pre_authority["purchase_ranking"]["member"],
        pre_authority["purchase_ranking"]["sha256"],
    )

    model_rank_rows = read_zip_csv_member(
        archive,
        pre_authority["model_return_ranking"]["member"],
        pre_authority["model_return_ranking"]["sha256"],
    )

    high_confidence_rows = read_zip_csv_member(
        archive,
        pre_authority["high_confidence_subset"]["member"],
        pre_authority["high_confidence_subset"]["sha256"],
    )

    speculative_rows = read_zip_csv_member(
        archive,
        pre_authority["speculative_subset"]["member"],
        pre_authority["speculative_subset"]["sha256"],
    )


with zipfile.ZipFile(
    pre_price_package_path,
    "r",
) as archive:

    current_price_rows = read_zip_csv_member(
        archive,
        pre_authority["current_price_member"]["member"],
        pre_authority["current_price_member"]["sha256"],
    )

    coverage_rows = read_zip_csv_member(
        archive,
        pre_authority["current_price_coverage"]["member"],
        pre_authority["current_price_coverage"]["sha256"],
    )

    gap_rows = read_zip_csv_member(
        archive,
        pre_authority["current_price_gaps"]["member"],
        pre_authority["current_price_gaps"]["sha256"],
    )


disposition = index_unique(
    disposition_rows,
    "canonical_product_id",
    "Pre-Collector disposition",
)

current_price = index_unique(
    current_price_rows,
    "canonical_product_id",
    "Pre-Collector current-price authority",
)

coverage = index_unique(
    coverage_rows,
    "canonical_product_id",
    "Pre-Collector current-price coverage",
)

purchase = index_unique(
    purchase_rows,
    "canonical_product_id",
    "Pre-Collector purchase ranking",
)

high_confidence = index_unique(
    high_confidence_rows,
    "canonical_product_id",
    "Pre-Collector high-confidence subset",
)

speculative = index_unique(
    speculative_rows,
    "canonical_product_id",
    "Pre-Collector speculative subset",
)

model_rank: dict[tuple[str, str], dict[str, str]] = {}

for model_rank_row in model_rank_rows:

    model_rank_key = (
        model_rank_row["canonical_product_id"],
        model_rank_row["monte_carlo_horizon_years"],
    )

    if model_rank_key in model_rank:
        raise RuntimeError(
            f"Duplicate Pre-Collector model-rank key: "
            f"{model_rank_key}"
        )

    model_rank[
        model_rank_key
    ] = model_rank_row


gap: dict[str, dict[str, str]] = {}

for row in gap_rows:

    canonical_id = row["canonical_product_id"]

    if not canonical_id:
        raise RuntimeError(
            "Pre-Collector current-price gap row has blank key."
        )

    if canonical_id in gap:
        raise RuntimeError(
            f"Duplicate Pre-Collector gap row: {canonical_id}"
        )

    gap[canonical_id] = row


if len(disposition) != 131:
    raise RuntimeError(
        f"Expected 131 Pre-Collector disposition rows; "
        f"found {len(disposition)}"
    )

if len(coverage) != 131:
    raise RuntimeError(
        f"Expected 131 Pre-Collector coverage rows; "
        f"found {len(coverage)}"
    )

if len(purchase) != 95:
    raise RuntimeError(
        f"Expected 95 Pre-Collector purchase rows; "
        f"found {len(purchase)}"
    )

if len(high_confidence) != 88:
    raise RuntimeError(
        f"Expected 88 Pre-Collector high-confidence rows; "
        f"found {len(high_confidence)}"
    )

if len(speculative) != 6:
    raise RuntimeError(
        f"Expected 6 Pre-Collector speculative rows; "
        f"found {len(speculative)}"
    )

if len(model_rank) != 190:
    raise RuntimeError(
        f"Expected 190 Pre-Collector model-rank rows; "
        f"found {len(model_rank)}"
    )

if not set(high_confidence).issubset(
    set(purchase)
):
    raise RuntimeError(
        "Pre-Collector high-confidence subset escaped "
        "purchase population."
    )

if not set(speculative).issubset(
    set(purchase)
):
    raise RuntimeError(
        "Pre-Collector speculative subset escaped "
        "purchase population."
    )


pre_product_fields = (
    pre_contract["product_record"]["fields"]
)

pre_product_rows: list[dict[str, str]] = []


for canonical_id in sorted(
    disposition.keys()
):

    disposition_row = disposition[canonical_id]

    if canonical_id not in coverage:
        raise RuntimeError(
            f"Pre-Collector coverage missing: {canonical_id}"
        )

    coverage_row = coverage[canonical_id]

    price_row = current_price.get(
        canonical_id
    )

    purchase_row = purchase.get(
        canonical_id
    )

    high_confidence_row = high_confidence.get(
        canonical_id
    )

    speculative_row = speculative.get(
        canonical_id
    )

    gap_row = gap.get(
        canonical_id
    )

    row = blank_row(
        pre_product_fields
    )

    row["canonical_product_id"] = canonical_id

    row["product_name"] = disposition_row.get(
        "product_name",
        "",
    )

    row["final_analysis_status"] = disposition_row.get(
        "final_analysis_status",
        "",
    )

    row["purchase_rank"] = disposition_row.get(
        "purchase_rank",
        "",
    )

    row["investment_tier"] = disposition_row.get(
        "investment_tier",
        "",
    )

    row["combined_purchase_score"] = disposition_row.get(
        "combined_purchase_score",
        "",
    )

    row["persistent_product_exclusion"] = disposition_row.get(
        "persistent_product_exclusion",
        "",
    )

    row["not_ranked_reason"] = disposition_row.get(
        "not_ranked_reason",
        "",
    )

    row["current_price_evidence_status"] = coverage_row.get(
        "current_price_evidence_status",
        "",
    )

    row["source_name"] = coverage_row.get(
        "source_name",
        "",
    )

    row["observation_date"] = coverage_row.get(
        "observation_date",
        "",
    )

    row["tcgplayer_product_id"] = coverage_row.get(
        "tcgplayer_product_id",
        "",
    )

    if price_row is not None:

        verify_same(
            left=row["product_name"],
            right=price_row.get("product_name", ""),
            label=f"{canonical_id} Pre-Collector price product name",
        )

        verify_same(
            left=coverage_row.get("selected_price", ""),
            right=price_row.get("selected_price", ""),
            label=f"{canonical_id} Pre-Collector selected price",
        )

        row["current_price"] = price_row.get(
            "selected_price",
            "",
        )

        if not row["source_name"]:
            row["source_name"] = price_row.get(
                "source_name",
                "",
            )

        if not row["observation_date"]:
            row["observation_date"] = price_row.get(
                "observation_date",
                "",
            )

        if not row["tcgplayer_product_id"]:
            row["tcgplayer_product_id"] = price_row.get(
                "tcgplayer_product_id",
                "",
            )

    if gap_row is not None:

        row["current_price_gap_reason"] = gap_row.get(
            "gap_reason",
            "",
        )

        if not row["tcgplayer_product_id"]:
            row["tcgplayer_product_id"] = gap_row.get(
                "tcgplayer_product_id",
                "",
            )

    if purchase_row is not None:

        verify_same(
            left=row["product_name"],
            right=purchase_row.get("product_name", ""),
            label=f"{canonical_id} Pre-Collector purchase product name",
        )

        if row["current_price"]:

            verify_same(
                left=row["current_price"],
                right=purchase_row.get("current_price", ""),
                label=f"{canonical_id} Pre-Collector purchase current price",
            )

        for field in (
            "purchase_rank",
            "investment_tier",
            "combined_purchase_score",
        ):
            verify_same(
                left=row[field],
                right=purchase_row.get(field, ""),
                label=f"{canonical_id} Pre-Collector {field}",
            )

        for field in pre_product_fields:

            value = purchase_row.get(
                field,
                "",
            )

            if not value:
                continue

            if row.get(field, ""):

                verify_same(
                    left=row[field],
                    right=value,
                    label=f"{canonical_id} Pre-Collector field {field}",
                )

            row[field] = value

    if high_confidence_row is not None:

        high_confidence_name = high_confidence_row.get(
            "product_name",
            "",
        )

        if high_confidence_name:
            verify_same(
                left=row["product_name"],
                right=high_confidence_name,
                label=(
                    f"{canonical_id} high-confidence "
                    f"product name"
                ),
            )

        row["high_confidence_rank"] = (
            high_confidence_row.get(
                "high_confidence_rank",
                "",
            )
        )

    if speculative_row is not None:

        speculative_name = speculative_row.get(
            "product_name",
            "",
        )

        if speculative_name:
            verify_same(
                left=row["product_name"],
                right=speculative_name,
                label=(
                    f"{canonical_id} speculative "
                    f"product name"
                ),
            )

        row["speculative_rank"] = (
            speculative_row.get(
                "speculative_rank",
                "",
            )
        )

    pre_product_rows.append(row)


pre_scenario_fields = (
    pre_contract["scenario_horizon_record"]["fields"]
)

authorized_scenario_horizons = {
    str(value)
    for value in pre_contract[
        "scenario_horizon_record"
    ]["authorized_horizons_years"]
}

pre_scenario_rows: list[dict[str, str]] = []

seen_pre_scenario_keys: set[tuple[str, str]] = set()


for source in scenario_rows_source:

    canonical_id = source["canonical_product_id"]
    horizon = source["monte_carlo_horizon_years"]

    model_rank_row = model_rank.get(
        (
            canonical_id,
            horizon,
        )
    )

    if model_rank_row is None:
        raise RuntimeError(
            f"Missing Pre-Collector model rank: "
            f"{canonical_id}/{horizon}"
        )

    if canonical_id not in disposition:
        raise RuntimeError(
            f"Pre-Collector scenario contains unknown product: "
            f"{canonical_id}"
        )

    if horizon not in authorized_scenario_horizons:
        raise RuntimeError(
            f"Unauthorized Pre-Collector scenario horizon: {horizon}"
        )

    if source.get(
        "directly_backtested_at_this_horizon",
        "",
    ).lower() != "false":
        raise RuntimeError(
            f"Pre-Collector scenario unexpectedly marked "
            f"directly backtested: {canonical_id}/{horizon}"
        )

    expected_classification = {
        "3": "THREE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",
        "5": "FIVE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",
    }[horizon]

    if (
        source.get("scenario_classification", "")
        != expected_classification
    ):
        raise RuntimeError(
            f"Pre-Collector scenario semantic mismatch: "
            f"{canonical_id}/{horizon}"
        )

    key = (
        canonical_id,
        horizon,
    )

    if key in seen_pre_scenario_keys:
        raise RuntimeError(
            f"Duplicate Pre-Collector scenario key: {key}"
        )

    seen_pre_scenario_keys.add(key)

    row = blank_row(
        pre_scenario_fields
    )

    for field in pre_scenario_fields:
        row[field] = source.get(
            field,
            "",
        )

    row["model_rank"] = model_rank_row.get(
        "model_rank",
        "",
    )

    pre_scenario_rows.append(row)


pre_scenario_rows.sort(
    key=lambda row: (
        row["canonical_product_id"],
        int(row["monte_carlo_horizon_years"]),
    )
)


if len(pre_product_rows) != 131:
    raise RuntimeError(
        f"Pre-Collector product output count != 131: "
        f"{len(pre_product_rows)}"
    )

if len(pre_scenario_rows) != 190:
    raise RuntimeError(
        f"Pre-Collector scenario output count != 190: "
        f"{len(pre_scenario_rows)}"
    )


write_csv(
    PRE_PRODUCT_OUT,
    pre_product_fields,
    pre_product_rows,
)

write_csv(
    PRE_SCENARIO_OUT,
    pre_scenario_fields,
    pre_scenario_rows,
)


print("Collector product rows      :", len(collector_product_rows))
print("Collector horizon rows      :", len(collector_horizon_rows))
print("Pre-Collector product rows  :", len(pre_product_rows))
print("Pre-Collector scenario rows :", len(pre_scenario_rows))
print("Sidecar assembly            : COMPLETE")