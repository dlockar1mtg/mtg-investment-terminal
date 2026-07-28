from pathlib import Path

from terminal2.delivery.governed_publisher import (
    PublishArtifact,
    csv_shape,
    validate_artifact,
)


def test_csv_shape_and_validation(tmp_path: Path):
    source = tmp_path / "sample.csv"
    source.write_text("id,value\nA,1\nB,2\n", encoding="utf-8")
    assert csv_shape(source) == (2, ["id", "value"])
    result = validate_artifact(
        PublishArtifact(source, "sample.csv", ("id",), 2)
    )
    assert result["row_count"] == 2
    assert len(result["sha256"]) == 64
