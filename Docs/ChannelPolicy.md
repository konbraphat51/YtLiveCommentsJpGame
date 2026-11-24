# Channel Policy: Inclusion Criteria and Priority Rules

This document gives the exact, quantitative definition of which YouTube channels enter the dataset (criteria C1–C6) and in which order Data API work is done (lanes and priority rules). It is the specification behind `Config/ChannelPolicy.yaml`, `Config/ApiQuota.yaml` and the code in `Src/GameChatCollector/Selection/` and `Src/GameChatCollector/Operations/`.

- Policy version: **1.0.0** (reference date of the first cohort: 2026-11-24)
- Japanese version: [ChannelPolicy.ja.md](ChannelPolicy.ja.md)
- Overview in the system design: [SystemDesign.md](SystemDesign.md) sections 4.2 and 4.3
- Literature behind the choices: [ResearchNotes/20261124_ChannelSelectionCriteria.md](../ResearchNotes/20261124_ChannelSelectionCriteria.md)

## 1. Principles

1. **One rule for every candidate.** How a candidate was found never decides whether it is included. Every candidate is measured by the same procedure and judged by the same thresholds.
2. **Versioned.** Any change to a threshold, window, keyword list or frame parameter is a new `policy_version`. Each dataset version uses the cohort of exactly one `(policy_version, reference_date)`.
3. **No popularity in priorities.** Popularity can be an inclusion threshold (C4), but it never decides the order of work, so a run that stops early is not biased toward large channels.
4. **Everything is recorded.** Every candidate's measured values and outcome are stored, including excluded ones, so the population can be described and thresholds can be varied afterwards (sensitivity analysis).

## 2. Definitions

All times are UTC unless stated otherwise.

| Term | Definition |
| --- | --- |
| Reference date `R` | The date the cohort is fixed on. The window ends at `R` 00:00 UTC. |
| Observation window `W` | `[R − 180 days, R)` (`window_days: 180`). |
| Live stream | A public upload whose `liveStreamingDetails` has both `actualStartTime` and `actualEndTime`, whose `actualStartTime ∈ W`, and whose actual length `actualEndTime − actualStartTime` is **at least 15 minutes** (`min_live_duration_minutes`). The length rule drops test streams and most premieres (premieres also carry `liveStreamingDetails`). |
| Game stream | A live stream whose `snippet.categoryId ∈ {20}` (Gaming, `game_category_ids`). YouTube shows the game card only in the Gaming category, so every stream with a game card is counted. |
| Kana title | A title containing at least one character in U+3041–U+3096 (hiragana) or U+30A1–U+30FA (katakana). The middle dot `・` and the prolonged sound mark `ー` are excluded, because they also appear in non-Japanese text. |
| Uploads read | The uploads playlist (`UU…`, derived from `UC…`) is read newest first until an item older than `W.start − 14 days` appears (`playlist_buffer_days`), or 20 pages (1,000 items) have been read (`max_playlist_pages`). The buffer exists because a stream's playlist date is when it was scheduled, which can be days before it starts. |

## 3. Candidate Frame

### 3.1 Search Frame (`search`)

Candidates come mainly from `search.list` calls with fixed parameters: `type=video`, `eventType=completed`, `videoCategoryId=20`, `regionCode=JP`, `relevanceLanguage=ja`, `order=date`, `maxResults=50`.

**Search points.** Point `i` (i = 0, 1, 2, …) searches `[T_i − 6 h, T_i)` (`lookback_hours`) with query term `q_i`.

- `T_i = R − F + ⌊vdc(i+1) · F⌋ days + ((7 · i) mod 24) hours`, where `F = 28` days (`frame_days`) and `vdc` is the base-2 van der Corput sequence (1/2, 1/4, 3/4, 1/8, …).
- `q_i = terms[i mod 4]`, with `terms = ["", "配信", "実況", "ゲーム"]` (`""` means no keyword).

Why this shape:

- **28 days, not 180.** Videos drop out of search results 20–60 days after publication (Rieder, Padilla & Coromina 2025). Searching only the recent past keeps the frame stable. The cost is that a channel which stopped streaming more than about 4 weeks before `R` cannot be found by search.
- **van der Corput days and a 7-hour step.** Any prefix of the sequence is spread evenly over the days of the frame, and because 7 is coprime with 24, the hours cycle through all 24 values. A run that stops after any number of points has therefore covered the frame evenly.
- **Rotating query terms.** Time slicing alone does not fix the instability of search results (Efstratiou 2025). Rotating terms adds a second, independent axis.
- `order=date` returns the newest 50 videos before `T_i`, so each point is a snapshot of the streams published just before that moment. A channel's chance of being found grows with how often it streams in the Gaming category. That matches what C2 requires anyway, and it is documented as a bias.

`pageInfo.totalResults` and the result count of every point are stored (`search_points`) together with the raw responses.

### 3.2 Other Sources

- `csv:<label>`: curated lists in `Config/ChannelCandidates.csv` (`channel_id,source_label,note`), for example agency rosters. Not used in the 1.0.0 cohort.
- Collab snowballing (channels mentioned in included channels' descriptions) is planned and not implemented yet.

Every discovery is stored in `candidate_discoveries` with its source, so the composition of the frame by source can be reported. The source of each channel in the cohort is listed in the `sources` column.

## 4. Inclusion Criteria

A channel is in the cohort only if all six criteria are `PASS`.

| ID | Criterion | Measured value | Threshold (1.0.0) | Stable? |
| --- | --- | --- | --- | --- |
| C1 | Japanese language | Kana titles ÷ live streams in `W` | **≥ 0.80** | Yes |
| C2 | Game-streaming activity | Number of game streams in `W` | **≥ 8** (on average one every 22.5 days) | No |
| C3 | Game-streaming share | Game streams ÷ live streams in `W` | **≥ 0.30** | No |
| C4 | Size | `subscriberCount` from `channels.list` on the evaluation day; a hidden count fails | **≥ 10,000** | No |
| C5 | Chat available | Share of the C5 sample with chat replay available | **≥ 0.50** | No |
| C6 | Channel type | Not a clip, re-upload, company, publisher or team channel; not `madeForKids` | Must hold ([checklist](ChannelTypeChecklist.md)) | Yes |

Undefined values fail. If there are no live streams, C1 and C3 fail.

**C5 sample.** These are the `k = min(5, game streams)` game streams with the smallest `sha256(video_id + hash_salt)`. That makes a reproducible pseudo-random sample, not the newest streams. Availability is read from the watch page: the archive has chat replay if `ytInitialData.contents.twoColumnWatchNextResults.conversationBar.liveChatRenderer` exists. The same pages give `game_card_share`, which is recorded as a metric only.

**C6 automatic flags.** The checks look at the channel title and handle only, because descriptions mention "切り抜き" and "official" too often:

- `madeForKids` → `FAIL`.
- A keyword from `clip_keywords` or `official_keywords` → `PENDING` until a human decision is logged in `Config/ChannelTypeReviews.csv`.
- Otherwise → `PASS`.

### 4.1 Why These Thresholds

- **C1 (0.80).** Kana are specific to Japanese, while kanji are shared with Chinese. One title is too short for reliable statistical language identification (Jauhiainen et al. 2019). A share over all titles still admits channels with occasional titles that have no kana (for example `【APEX】rank`). In the measured candidates the share is bimodal: almost all are near 1, and the rest are near 0. The result hardly depends on the exact cut (section 8).
- **C2 (8 in 180 days).** No precedent was found. It is the smallest regular-activity requirement that still yields enough streams per channel for per-channel analysis (about one game stream every three weeks). In the measured data C2 binds only for a few channels (section 8).
- **C3 (0.30) and C4 (10,000).** These follow the closest precedent on YouTube, Ledwich & Zaitsev (2019): more than 10,000 subscribers and more than 30% of content on the topic. YouNiverse (Ribeiro & West 2021) also uses 10,000 subscribers. 10,000 is 10–20 times the YouTube Partner Program entry levels (500 / 1,000 subscribers), so it marks an established community rather than a monetization rule. Size changes the nature of chat (Nakandala et al. 2017), so C4 is the threshold that changes the cohort most. Its sensitivity is reported, and size bands remain available as a filter.
- **C5 (0.50).** The dataset needs chat replay. A channel that disables replay on most streams adds collection cost without data.

### 4.2 Evaluation Procedure and Status

Evaluation runs in stages, so expensive measurement is spent only where a pass is possible. Each candidate costs the following Data API units.

1. `channels.list` (batched 50 per call, about 0.02 units per candidate). The candidate stops here with stage `SCREENED` if any of these holds:
   - C6 already fails (`madeForKids`);
   - none of the channel title, the channel description and the discovered video titles contains kana (recorded as a C1 failure);
   - the subscriber count is hidden or below the **measurement floor of 5,000** (recorded as a C4 failure).

   The floor is half of the C4 threshold, so the sensitivity analysis can go down to 5,000.
2. Uploads playlist plus `videos.list` (about 1 unit per 50 uploads, twice). This gives stage `MEASURED`, and C1–C4 and C6 are judged.
3. Watch pages of the C5 sample (no Data API quota; at most 1 request per second, with jitter). C5 is judged.

Status: any `FAIL` → `FAILED`. Otherwise, any `PENDING` → `PENDING`. Otherwise → `PASSED`. A channel that no longer exists gets `NOT_FOUND`.

**Cohort.** The cohort is the channels with status `PASSED`. Until C5 and the flagged C6 cases are resolved, `Cohort.csv` lists `PASSED` and `PENDING` channels, with the open criteria named.

## 5. Data API Lanes

The Data API quota is 10,000 units per day, and the day is counted in Pacific Time (it resets at 00:00 PT, which is 17:00 JST in winter and 16:00 JST in summer). `QuotaBudget` charges every call **before** it is sent. A call that does not fit the lane's remaining budget is refused.

| Lane | `steady` share (units) | `bootstrap` share (units) | Work |
| --- | --- | --- | --- |
| L1 Operational | 30% (3,000) | 5% (500) | New videos of cohort channels, live checks, final refetch after streams |
| L2 Backfill | 40% (4,000) | 0% (0) | Past streams of cohort channels |
| L3 Eligibility | 20% (2,000) | 60% (6,000) | Measuring candidates (section 4.2) |
| L4 Discovery | 5% (500) | 30% (3,000) | `search.list` points (100 units each) |
| Reserve | 5% (500) | 5% (500) | Never spent automatically |

- `bootstrap` is used only while the first cohort is built, when there is no L1 or L2 work yet. In normal operation the profile is `steady`.
- **Release.** From 4 hours before the reset (`release_hours_before_reset`), unused shares are pooled. Any lane may then spend up to `9,500 − (units spent today)`. Lanes are served in order L1 → L4.
- **Exhaustion.** If the API answers `quotaExceeded`, every API lane stops until the next reset. Work that does not use the Data API continues.

## 6. Priority Rules (Within Each Lane)

Each rule is a sort key, and smaller keys run first. `h(x) = sha256(x + hash_salt)` is the reproducible pseudo-random tie-breaker. No key contains subscriber or view counts.

| Lane | Sort key | Runnable when |
| --- | --- | --- |
| L1 | `(tier, reference_time, h(video_id))`. tier 0: live, or scheduled to start within 15 min (`imminent_minutes`). tier 1: final metadata refetch at least 2 h after `actualEndTime` (`grace_hours`). tier 2: newly discovered video, ordered by discovery time | Tier 0 only from 15 min before the start; tier 1 only after the grace period |
| L2 | `(k, collected_game_hours, h(channel_id))`, where slice `k` covers `[now − 30(k+1) d, now − 30k d)` (`backfill_slice_days`) | Only channels whose next slice equals the lowest open slice across the cohort. Slice *k* starts only when every channel has finished slice *k*−1 |
| L3 | `(tier, r, source)`. tier 0: re-evaluation of cohort channels for the next version. tier 1: new candidates. tier 2: retries. `r` is the candidate's rank by `h(channel_id)` within its tier and primary source, so the sources take turns (round-robin) | A retry is runnable only after its cooldown: **180 days** if it failed a stable criterion (C1 or C6), **60 days** otherwise |
| L4 | `(times_searched, i)` | Points never searched come first, in sequence order |

Consequences:

- When quota runs out, L2 has covered every cohort channel back to about the same date.
- L3 gives every discovery source the same share of evaluations, whatever its size.
- L4 grows the frame evenly over time, hours and query terms.

## 7. Outputs

`collector channels report` writes `Cohorts/Policy<version>_<YYYYMMDD>/`:

| File | Content |
| --- | --- |
| `ChannelEligibility.csv` | Every evaluated candidate: status, stage, failed and pending criteria, measured values, C6 flags, sources |
| `Cohort.csv` | The rows with status `PASSED` or `PENDING` |
| `Summary.md` | Counts by stage, status and source; failure counts per criterion; quantiles of each metric; one-at-a-time sensitivity table |

CSV files are UTF-8 with a BOM, so Excel on Windows opens them correctly. The full measurements (`metrics_json`) and the raw API responses stay in `Data/` (git-ignored).

## 8. First Cohort (2026-11-24)

See [Cohorts/Policy1.0.0_20261124/Summary.md](../Cohorts/Policy1.0.0_20261124/Summary.md) for the full numbers. Highlights are in section 8.1.

### 8.1 Findings

(Filled in after the run; see the summary file.)

## 9. Known Limitations

- **Search frame.** The frame favors channels that stream often in the Gaming category and that the search ranking surfaces. Its coverage of the population is unknown. Adding the CSV roster source enables a capture–recapture estimate of coverage.
- **Category as the game signal.** Game streams labeled with another category are missed. Talk streams labeled Gaming are counted. `game_card_share` from the C5 sample measures how often the label is backed by a game card.
- **Premieres** longer than 15 minutes are counted as live streams.
- **Subscriber counts** are rounded by the API to three significant figures.
- **C5 needs watch pages.** YouTube answers cloud IP addresses with a bot check, so `check-chat` has to run from a network where watch pages load (for example, a university or home connection).
