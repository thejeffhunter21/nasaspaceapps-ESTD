# Earth System Trend Detective

NASA Space Apps 2026. Pick a region and a NASA Earth science variable, see how it
changed month by month, and find out whether the trend is statistically significant,
explained in plain language.

## Quick start

```
git clone <repo-url>
cd <repo>
uv sync --locked
uv run pytest
```

## Who owns what

| Area | Owner |
|---|---|
| Repo, CI, Docker, Render, pipeline (`src/earth_system_trend/pipeline/`) | Syed (Avid-arch) |
| Contract, API, settings (`contract.py`, `config.py`, `api/`) | Jeff |
| Data (`data/processed/*.csv`) | Data team |
| Trend test + explanation functions | AI team |
| Dashboard | Frontend team |

If you need to change a file you don't own, say so in chat first.

## How it fits together
_(coming)_

## Build the results
_(coming)_

## API
_(coming: see docs/api.md)_

## Settings
_(coming)_

## Deploy
_(coming)_

## Tests
_(coming)_

## Data and credits
_(coming)_
