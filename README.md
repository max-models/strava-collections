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

Strava refresh tokens rotate when the app refreshes access. `strava-collections`
now refreshes once per run and prints the replacement
`STRAVA_REFRESH_TOKEN` to stderr whenever Strava rotates it. Save that new token
before the next uncached download. In GitHub Actions, update the repository
secret with the printed value after a run downloads new activities.

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
strava-collections 1324271479 1325123423 1326744150 1327962669 1328949546 1330086898 1331713983 1332641515 1333971033 1336237609 -c "Taiwan"
```

Mainly for Github actions, but you can also do:

```
strava-collections -i examples/taiwan.yml
```

## YAML Configuration

The YAML files can include optional `places:` to mark specific locations on the map:

```yaml
collection_name: "Taiwan"
output_dir: "docs/source/"
places:
  - name: "Taipei"
    lat: 25.0330
    lon: 121.5654
  - name: "Taitung"
    lat: 22.7606
    lon: 121.1424
activity_ids:
  - "1324271479"
  - "1325123423"
```

Places are rendered as red markers on the collection map with hover tooltips showing the name and coordinates.

#TODO: The yaml reader should be simplified and all the collections run in the CI should be moved into `examples/`

# Build docs

By default, `strava-collections` now generates a complete Astro site under
`docs/`:

```
strava-collections -i examples/taiwan.yml
cd docs/astro
npm ci
npm run dev
```

The generated site layout is:

```
docs/
  astro/
  source/
```

where `source/` contains the generated collection `.astro` pages and Plotly
assets, and `astro/` is the copied Astro site template.

### Map Features

Collection maps include:
- **Map style dropdown** (top-left): Switch between different map styles (outdoors, streets, light, dark, satellite, etc.)
- **Places markers** (red dots): If places are defined in the YAML, they appear as red markers on the map with hover tooltips

To scaffold the same site structure somewhere else, pass `-o/--output`:

```
strava-collections -i 'examples/*.yml' -o /tmp/strava-site
cd /tmp/strava-site/astro
npm ci
npm run dev
```

The dev server automatically re-syncs `docs/source/` into the Astro app when
the generated collection files or figures change, so you can rerun
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
