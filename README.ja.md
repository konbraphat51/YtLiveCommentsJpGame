# GameChatCollector

日本のゲーム配信者のYouTube Liveチャットを収集し、データセットを作るパイプラインです。各チャットメッセージを、その時点でプレイ中のゲームタイトルに紐づけます。

- 英語版(正): [README.md](README.md)
- 設計書: [Docs/SystemDesign.ja.md](Docs/SystemDesign.ja.md)
- チャンネルの包含基準とAPIの優先度ルール: [Docs/ChannelPolicy.ja.md](Docs/ChannelPolicy.ja.md)

## ステータス

チャンネル選定まで実装済みです。具体的には、候補の探索、基準 C1〜C6 の測定、Data API のクォータのレーンと優先度ルール、コホートの報告です。最初のリストは [Cohorts/Policy1.0.0_20261124/](Cohorts/Policy1.0.0_20261124/) にあります。チャットの収集とゲームの紐づけは、まだ設計段階です。

## セットアップ(初回)

必要なもの: Python 3.12 以上、[uv](https://docs.astral.sh/uv/)、YouTube Data API v3 のキー。

```bash
git clone https://github.com/konbraphat51/YtLiveCommentsJpGame.git
```

```bash
cd YtLiveCommentsJpGame
```

```bash
uv sync
```

`.env.example` を `.env` にコピーし、`YOUTUBE_API_KEY` を設定します(`YT_API` という名前でも読み込めます)。

## 実行(2回目以降)

基準日を指定して、コホートを作るか、作ったコホートを広げます。各コマンドは、担当するクォータのレーンを使い切ると安全に止まります。次のクォータ日にもう一度実行すれば、続きから進みます(クォータの日付は太平洋時間の0時に切り替わります)。

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

`check-chat` は視聴ページを読むので、YouTube が視聴ページを返すネットワークで実行してください。クラウドのIPアドレスでは、ボット確認の画面になります。C6 の判定を `Config/ChannelTypeReviews.csv` に記録したら、`apply-reviews` を実行してから、もう一度 `report` を実行します。

## 主なCLI

| コマンド | 用途 |
| --- | --- |
| `collector channels discover` | `Config/ChannelCandidates.csv` と `search.list` による探索の枠から候補を追加する(レーン L4) |
| `collector channels evaluate` | 候補の C1〜C4 と C6 を測定する(レーン L3) |
| `collector channels check-chat` | 視聴ページから C5(チャットリプレイ)を測定する |
| `collector channels apply-reviews` | C6 の人手判定を記録した後、保存済みの評価を判定し直す(通信なし) |
| `collector channels report` | `Cohorts/` の下に `ChannelEligibility.csv`、`Cohort.csv`、`Summary.md` を書き出す |
| `collector status` | 当日のレーンごとの Data API 消費量と残りを表示する |

## 開発

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
