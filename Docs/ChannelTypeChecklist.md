# C6 Channel Type Checklist

This checklist is used to decide criterion C6 (channel type) by hand. A decision is needed only for candidates that the automatic flags mark as `PENDING` on C6 (see [ChannelPolicy.md](ChannelPolicy.md)).

- Japanese version: [ChannelTypeChecklist.ja.md](ChannelTypeChecklist.ja.md)

## When a Decision Is Needed

`ChannelTypeScreener` raises a flag when the channel title or handle contains a keyword from `channel_type.clip_keywords` or `channel_type.official_keywords` in `Config/ChannelPolicy.yaml`. A channel marked `madeForKids` fails C6 automatically, because chat is disabled on its videos.

## Questions (answer in order; the first "yes" decides)

1. **Clip or re-upload channel?** Are most of the uploads edited excerpts of *another* person's streams (切り抜き), re-uploads or compilations? → `FAIL`
2. **Company, publisher or team channel?** Is the channel run by a game publisher, platform, media company or esports team to promote products or events, rather than by an individual streamer or a VTuber talent? → `FAIL`
   - The talent channels of a VTuber agency (for example, an individual member's channel) are **not** company channels. The agency's own group channel is a company channel.
3. **Otherwise** (an individual streamer, a VTuber talent or a creator unit whose live streams are its own content) → `PASS`

Use only public information: the channel page, the "About" text and the most recent uploads. Do not use the subscriber count or popularity.

## Logging the Decision

Add one row to `Config/ChannelTypeReviews.csv`:

| Column | Content |
| --- | --- |
| `channel_id` | `UC…` |
| `decision` | `PASS` or `FAIL` |
| `reason` | The question number and a short reason, for example `Q2: publisher channel` |
| `reviewer` | Reviewer's name or initials |
| `reviewed_at` | `YYYY-MM-DD` |

Then run `uv run collector channels apply-reviews --reference-date <date>` and `uv run collector channels report --reference-date <date>`.
