# Strava collections

This repo builds a webpage some collections of runs and rides from strava.

Link to the published webpage: https://max-models.github.io/strava-collections/

# Get the tokens

## Strava

```
python update_strava_tokens.py
```

The script prints commands you can copy and paste to export
`STRAVA_REFRESH_TOKEN` and `STRAVA_ACCESS_TOKEN`.

## Mapbox

Map image export uses Plotly/Kaleido with Mapbox styles, so you also need a
Mapbox access token.

1. Open https://console.mapbox.com/account/access-tokens/
2. Sign in or create a Mapbox account.
3. Copy your `Default public token`, or create a new public token for this
   project. Public Mapbox tokens start with `pk`.
4. Export it before building collections:

```
export MAPBOX_TOKEN="pk..."
```

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

The static webpage is built with Astro. The Python command generates collection
`.astro` pages plus maxplotlib elevation plots rendered as Plotly HTML assets
for the collection and each individual activity, alongside Plotly map assets
under `docs/source/`; the Astro sync step copies those generated pages into the
Astro app and still falls back to legacy collection markdown when needed.

```
strava-collections -i examples/taiwan.yml
cd docs/astro
npm ci
npm run dev
```

The dev server automatically re-syncs `docs/source/` into the Astro app when
the generated markdown or figures change, so you can rerun
`strava-collections -i examples/taiwan.yml` in another terminal and refresh the
page without manually re-syncing.

To produce a static build instead:

```
npm ci
npm run build:from-generated
npm run preview
```

The built site is written to `docs/astro/dist/`.
The default Astro base path is `/strava-collections/` for GitHub Pages. To test
generated content at the local server root instead, run the sync step with:

```
ASTRO_BASE_PATH=/ npm run sync:generated
```

For CI, the cached Strava activities are loaded from the
`temporary-strava-activities` submodule via `STRAVA_CACHE_DIR`. Because the
submodule uses the SSH URL, GitHub Actions needs an SSH deploy key secret named
`STRAVA_ACTIVITIES_DEPLOY_KEY` with access to
`git@github.com:max-models/temporary-strava-activities.git`.
