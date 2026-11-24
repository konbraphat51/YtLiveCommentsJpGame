# GameChatCollector

A data-collection pipeline that builds a dataset of YouTube Live chat from Japanese game streamers. Each chat message is linked to the game title being played at that moment.

- Japanese: [README.ja.md](README.ja.md)
- Design: [Docs/SystemDesign.md](Docs/SystemDesign.md)
- Channel inclusion criteria and API priority rules: [Docs/ChannelPolicy.md](Docs/ChannelPolicy.md)

## Status

Channel selection is implemented: candidate discovery, measurement of criteria C1–C6, Data API quota lanes with priority rules, and the cohort report. The first list is in [Cohorts/Policy1.0.0_20261124/](Cohorts/Policy1.0.0_20261124/). Chat collection and game attribution are still at the design stage.

## Setup (first time)

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and a YouTube Data API v3 key.

```bash
git clone https://github.com/konbraphat51/YtLiveCommentsJpGame.git
```

```bash
cd YtLiveCommentsJpGame
```

```bash
uv sync
```

Copy `.env.example` to `.env` and set `YOUTUBE_API_KEY` (`YT_API` is also accepted).

## Running (second time and later)

Build or extend a cohort for a reference date. Each command stops cleanly when its quota lane is used up, so it can simply be run again on the next quota day (the day resets at midnight Pacific Time).

```bash
uv run collector channels discover --reference-date 2026-11-24 --max-calls 30 --profile bootstrap
```

```bash
uv run collector channels evaluate --reference-date 2026-11-24 --profile bootstrap
```

```bash
uv run collector channels check-chat --reference-date 2026-11-24
```

```bash
uv run collector channels report --reference-date 2026-11-24
```

`check-chat` reads watch pages and needs a network where YouTube serves them (cloud IP addresses get a bot check). After logging C6 decisions in `Config/ChannelTypeReviews.csv`, run `apply-reviews` and then `report` again.

## Important CLIs

| Command | Purpose |
| --- | --- |
| `collector channels discover` | Adds candidates from `Config/ChannelCandidates.csv` and from the `search.list` frame (lane L4) |
| `collector channels evaluate` | Measures candidates for C1–C4 and C6 (lane L3) |
| `collector channels check-chat` | Measures C5 (chat replay) from watch pages |
| `collector channels apply-reviews` | Re-judges stored evaluations after C6 review decisions (offline) |
| `collector channels report` | Writes `ChannelEligibility.csv`, `Cohort.csv` and `Summary.md` under `Cohorts/` |
| `collector status` | Shows Data API units spent and remaining per lane today |

## Development

```bash
uv run pytest
```

```bash
uv run mypy
```

```bash
uv run ruff check Src Tests
```

```bash
uv run black Src Tests
```
