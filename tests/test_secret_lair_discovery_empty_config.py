from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.discovery.contracts import (
    DISCOVERY_CONTRACTS,
)
from terminal2.secret_lair.discovery.engine import (
    discover_secret_lairs,
    has_enabled_discovery_sources,
)


class EmptyDiscoveryConfigTests(unittest.TestCase):
    def test_empty_config_has_valid_contract_schemas(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "discovery.csv"
            pd.DataFrame(
                columns=[
                    "source_name",
                    "connector_type",
                    "endpoint",
                    "enabled",
                    "priority",
                    "parser_name",
                    "timeout_seconds",
                    "max_retries",
                    "cache_ttl_hours",
                    "source_quality",
                    "query_json",
                    "notes",
                ]
            ).to_csv(config, index=False)

            result = discover_secret_lairs(config)

            self.assertFalse(
                has_enabled_discovery_sources(config)
            )
            self.assertEqual(len(result.datasets), 7)

            for name, contract in DISCOVERY_CONTRACTS.items():
                frame = result.datasets[name]
                missing = (
                    set(contract.required_columns)
                    - set(frame.columns)
                )
                self.assertEqual(
                    missing,
                    set(),
                    msg=f"{name} missing {sorted(missing)}",
                )


if __name__ == "__main__":
    unittest.main()
