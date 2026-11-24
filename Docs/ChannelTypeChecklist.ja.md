# C6 チャンネル種別チェックリスト

基準 C6（チャンネル種別）を人が判定するためのチェックリストです。判定が必要なのは、自動フラグによって C6 が `PENDING` になった候補だけです（[ChannelPolicy.ja.md](ChannelPolicy.ja.md) を参照）。

- 英語版（正）: [ChannelTypeChecklist.md](ChannelTypeChecklist.md)

## 判定が必要になる場合

`ChannelTypeScreener` は、チャンネル名またはハンドルに次のどちらかのキーワードが含まれるとフラグを立てます。

- `Config/ChannelPolicy.yaml` の `channel_type.clip_keywords`
- 同じく `channel_type.official_keywords`

`madeForKids` が設定されたチャンネルは、動画のチャットが無効なので、C6 を自動で不合格（`FAIL`）とします。

## 質問（順に答え、最初に「はい」となった項目で決まります）

1. **切り抜き・転載チャンネルか?** アップロードの大半が、*他人*の配信の切り抜き、転載、まとめのどれかである → `FAIL`
2. **企業・パブリッシャー・チームのチャンネルか?** 個人の配信者や VTuber 本人ではなく、ゲーム会社、プラットフォーム、メディア企業、e スポーツチームが製品やイベントの宣伝のために運営している → `FAIL`
   - VTuber 事務所に所属するタレント個人のチャンネルは、企業チャンネルには**含めません**。事務所の公式グループチャンネルは企業チャンネルです。
3. **上記のどれでもない**(個人配信者、VTuber タレント、または自分たちのライブ配信を主なコンテンツとするクリエイターユニット) → `PASS`

判定には、公開情報(チャンネルページ、概要欄、最近のアップロード)だけを使います。登録者数や人気は使いません。

## 判定の記録

`Config/ChannelTypeReviews.csv` に 1 行追加します。

| 列            | 内容                                            |
| ------------- | ----------------------------------------------- |
| `channel_id`  | `UC…`                                           |
| `decision`    | `PASS` または `FAIL`                            |
| `reason`      | 質問番号と短い理由(例: `Q2: publisher channel`) |
| `reviewer`    | 判定者の名前またはイニシャル                    |
| `reviewed_at` | `YYYY-MM-DD`                                    |

記録したら、次の 2 つのコマンドを順に実行します。

```bash
uv run collector channels apply-reviews --reference-date <date>
```

```bash
uv run collector channels report --reference-date <date>
```
