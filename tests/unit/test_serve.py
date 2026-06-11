import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock missing dependencies to avoid NumPy errors or other issues
mock_modules = [
    "fastrdp",
    "stravalib",
    "polyline",
    "numpy",
    "pandas",
    "plotly",
    "plotly.colors",
    "plotly.graph_objects",
    "kaleido",
    "fitparse",
    "gpxpy",
    "maxplotlibx",
    "tikzfigure",
    "tabulate",
    "markdown",
]
for module in mock_modules:
    sys.modules[module] = MagicMock()

from strava_collections.main import main


class TestServe(unittest.TestCase):
    @patch("strava_collections.main.subprocess.run")
    @patch("strava_collections.main.sync_site")
    @patch("strava_collections.main.Collection")
    @patch("strava_collections.main.Activity")
    @patch("strava_collections.main.print_site_instructions")
    def test_serve_with_host(
        self, mock_print_instr, mock_activity, mock_collection, mock_sync_site, mock_run
    ):
        # Setup mocks
        mock_collection_instance = MagicMock()
        mock_collection_instance.output_dir = "some_dir"
        mock_collection.from_yaml.return_value = mock_collection_instance

        # We need to ensure site_root is not None
        # In main(), site_root is determined by:
        # site_root = Path(args.output_dir) if args.output_dir else Path(collection.output_dir)

        with patch(
            "sys.argv",
            ["strava-collections", "-i", "examples/taiwan.yml", "--serve", "--host"],
        ):
            try:
                main()
            except SystemExit:
                pass
            except Exception as e:
                print(f"Caught unexpected exception: {e}")

        # Check if subprocess.run was called with the correct arguments
        npm_calls = [call for call in mock_run.call_args_list if "npm" in call.args[0]]
        print(f"NPM calls found: {npm_calls}")

        # Expected call for dev server with host
        expected_dev_call = ["npm", "run", "dev", "--", "--host"]

        found_dev_call = False
        for call in npm_calls:
            if call.args[0] == expected_dev_call:
                found_dev_call = True
                break

        self.assertTrue(
            found_dev_call,
            f"Expected dev call {expected_dev_call} not found in {npm_calls}",
        )


if __name__ == "__main__":
    unittest.main()
