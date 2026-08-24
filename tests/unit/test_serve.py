from unittest.mock import patch

from strava_collections.main import main


def test_serve_with_host():
    with patch("strava_collections.main.subprocess.run") as run, patch(
        "sys.argv",
        ["strava-collections", "serve", "--host", "-o", "/tmp/strava-test-site"],
    ):
        main()

    commands = [call.args[0] for call in run.call_args_list]
    assert ["npm", "ci"] in commands
    assert ["npm", "run", "dev", "--", "--host"] in commands
