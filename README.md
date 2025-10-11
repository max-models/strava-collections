# Strava collections

# Install

Create and activate python environment

```
python -m venv env
source env/bin/activate
pip install --upgrade pip
```

Install the code and requirements with pip

```
pip install -e .
```

# Get the tokens

```
python update_strava_tokens.py
```

export the tokes as `STRAVA_REFRESH_TOKEN` and `STRAVA_ACCESS_TOKEN`.

# Build docs

```
make html
cd ../
open docs/_build/html/index.html
```
