# Strava collections

This repo builds a webpage some collections of runs and rides from strava.

Link to the published webpage: https://max-models.github.io/strava-collections/

# Get the tokens

```
python update_strava_tokens.py
```

export the tokes as `STRAVA_REFRESH_TOKEN` and `STRAVA_ACCESS_TOKEN`.

# Build docs

```
make html
cd ../
open docs/build/html/index.html
```
