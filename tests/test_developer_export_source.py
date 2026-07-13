import unittest

from developer_export_source import sanitize_branch_name


class DeveloperExportSourceTests(unittest.TestCase):
    def test_sanitize_branch_name(self):
        self.assertEqual(
            sanitize_branch_name(
                "feature/terminal-2-5-1c-warehouse-migration"
            ),
            "feature-terminal-2-5-1c-warehouse-migration",
        )

    def test_empty_branch_name(self):
        self.assertEqual(
            sanitize_branch_name("///"),
            "unknown-branch",
        )


if __name__ == "__main__":
    unittest.main()
