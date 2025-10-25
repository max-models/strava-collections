# Strava collections

This repo builds a webpage some collections of runs and rides from strava.

Link to the published webpage: https://max-models.github.io/strava-collections/

# Get the tokens

```
python update_strava_tokens.py
```

export the tokes as `STRAVA_REFRESH_TOKEN` and `STRAVA_ACCESS_TOKEN`.

# Build collection

Use strava activity IDs

```
strava-collections 1324271479 1325123423 1326744150 1327962669 1328949546 1330086898 1331713983 1332641515 1333971033 1336237609 -o docs/source/ -c "Taiwan"
```

Mainly for Github actions, but you can also do:

```
strava-collections -i examples/taiwan.yml
```

#TODO: The yaml reader should be simplified and all the collections run in the CI should be moved into `examples/`

# Build docs

```
make html
cd ../
open docs/build/html/index.html
```
