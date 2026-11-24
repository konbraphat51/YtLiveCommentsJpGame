# チャンネル採用基準 C1–C6 と候補枠組みの文献レビュー

- 日付: 2026-11-24
- 目的: `Config/ChannelPolicy.yaml`（policy 1.0.0）の閾値と、候補発見の枠組みの根拠を整理する。
- 凡例:
  - 【確認】本文またはページを読んで確かめたもの。
  - 【未確認】二次情報しか見ていないもの。
  - 【推論】文献にはなく、本プロジェクト側で推論したもの。

## 1. 先行するライブチャット研究のチャンネル選定

| 研究                                                                                                             | 選定方法                                                                                                          | 数値閾値         | 本設計との関係                                                                             |
| ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------ |
| Ringer, Nicolaou & Walker, "TwitchChat: A Dataset for Exploring Livestream Chat", AIIDE 2020【確認】             | 人気上位20ゲームの、その時点で最も人気のチャンネルを順に記録。英語のみ。666配信者・1,951配信                      | なし（人気順）   | 人気順の選定は大規模チャンネルに偏る。本設計が人気を優先度に使わない理由を対比として示せる |
| Nakandala, Ciampaglia, Su & Ahn, "Gendered Conversation in a Social Game-Streaming Platform", ICWSM 2017【確認】 | Twitch の全公開チャットを収集。チャット量の上位1,000と、1,000〜16,000位の無作為抽出。英語以外のプロフィールは除外 | チャット量で層別 | 規模でチャットの性質が変わる（短文化、エモート増）。C4 の感度分析と規模別の層別分析の根拠  |
| Rappaz, McAuley & Aberer, RecSys 2021【確認】                                                                    | 配信中の全ストリームを定期的に列挙する悉皆収集                                                                    | なし             | 悉皆収集は Twitch API だから可能。YouTube には同等の手段がない                             |
| Gao et al., "LiveChat", ACL 2023【確認】                                                                         | Douyin の「代表的な」配信者351人                                                                                  | 記載なし         | 選定基準を明文化していない例                                                               |
| Zhao et al., "Who Reaps All the Superchats?", arXiv 2503.00825【確認】                                           | Virtual YouTuber Fandom Wiki に載っていて YouTube リンクがある 1,923 人                                           | なし             | 名簿依存の枠組み                                                                           |
| Wei & Tyson, WWW 2025【確認】                                                                                    | Bilibili の索引サイトに載っている全件                                                                             | なし             | 名簿依存の枠組み                                                                           |

**結論**【推論】

- ライブチャット研究で数値閾値を明文化した例は少ない。
- 人気順で選ぶか、名簿に依存するかがほとんど。
- 発見経路に依存しない一律の基準を定めて、その感度分析を公開すること自体に、方法上の新規性がある。

## 2. search.list を標本抽出の枠組みとして使うときの偏り

- Rieder, Matamoros-Fernández & Coromina, "From ranking algorithms to 'ranking cultures'", Convergence 24(1), 2018【確認】
  - 関連度順の上位結果は、人気指標と単純には対応しない。
- Rieder, Padilla & Coromina, "Forgetful by design?", Information, Communication & Society, 2025【確認】
  - 1 クエリあたり最大 500 件。
  - 動画は公開後 20〜60 日で検索に出なくなっていく。
  - 推奨される対策は、早期の収集、1 日単位の時間区切り、同じ検索の反復、チャンネル起点の収集の併用、検索条件の公開。
- Efstratiou, "On YouTube Search API Use in Research", IMC 2025【確認】
  - 時間で区切る方法は思ったほど有効ではない。
  - 語やサブトピックで分割することと、`pageInfo.totalResults` を記録することを推奨している。
  - 短く人気の高い動画ほど返されやすい傾向がある。
- McGrady et al., "Dialing for Videos: A Random Sample of YouTube", Journal of Quantitative Description: Digital Media 3, 2023【確認】
  - API では無作為標本を取れない。
  - 無作為標本では、チャンネル登録者数の中央値は 61。

**本設計への反映（policy 1.0.0）**

- 検索点は基準日前の 28 日以内に限った（`frame_days: 28`）。消失の影響を受けにくくするため。
- 時刻は van der Corput 列と 7 時間刻みで分散させた。
- 検索語は `""`、`配信`、`実況`、`ゲーム` を順に回す。
- search.list は候補の生成にだけ使う。判定は ID ベースのエンドポイント（channels.list、playlistItems.list、videos.list）で行う。
- 発見経路はすべて記録する。

## 3. かなによる日本語判定

- Jauhiainen et al., "Automatic Language Identification in Texts: A Survey", JAIR 65, 2019【確認】
  - 25 文字程度の短文では、どの手法も精度が大きく落ちる。
  - 同じ文字体系を共有する言語どうしの識別が最も難しい。
- CLD2 の README【確認】
  - 文字体系が言語と 1 対 1 に対応する場合は、文字体系で判定する。
- Ribeiro & West, "YouNiverse", ICWSM 2021【確認】
  - チャンネルごとに動画 10 本のタイトルと説明文に言語判定をかけ、英語の確率 0.6 を超えるものを採用した。
  - 複数タイトルをチャンネル単位で集計する点は C1 と同じ。

**C1 の根拠**【推論】

- 漢字は中国語と共有するが、ひらがなとかなは日本語に特有。
- 1 本のタイトルは短いので、統計的な言語判定は弱い。
- かなを含むタイトルの割合で判定すれば、`【APEX】rank` のようなかなを含まないタイトルを、他のタイトルで吸収できる。
- 「かなの有無」を日本語判定の標準と明言した文献は見つからなかった。手動でラベル付けした標本で、fastText や CLD3 と一致率を比べて検証する余地がある。

## 4. 規模と活動量の閾値

- Ledwich & Zaitsev, "Algorithmic Extremism", arXiv 1912.11211【確認】
  - 「登録者 1 万人超」かつ「コンテンツの 30% 超が政治」で、816 チャンネルを選んだ。
  - **C4 と C3 とほぼ同じ構造の前例。**
- YouNiverse【確認】
  - 「英語で、登録者 1 万超、動画 10 本以上」で 136,470 チャンネル。
- YouTube パートナープログラム【確認】
  - 広告収益の条件は登録者 1,000 人以上（https://support.google.com/youtube/answer/72851 ）。
  - ファン支援（Super Chat を含む）の条件は登録者 500 人以上（https://support.google.com/youtube/answer/13429240 ）。
  - 1 万人は収益化の下限の 10〜20 倍。コミュニティが定着している目安として説明する。
- C2（180 日で 8 配信）について、該当する前例は見つからなかった。研究者が定めた値として扱い、感度分析で裏付ける。

## 5. 文書化

- Gebru et al., "Datasheets for Datasets", CACM 64(12), 2021【確認】
  - 次の問いに答えることを求めている。
    - 標本か全数か。標本なら母集合は何か。
    - 抽出戦略は何か。
    - 収集期間はいつか。
  - `Summary.md` のうち、発見経路別の内訳、除外理由の件数、感度分析表がこれらの問いへの回答になる。

## 6. 母集団の規模の目安

- ユーザーローカルによると、VTuber の数は 2020年11月に約1万3千人（https://www.userlocal.jp/press/20201109vi/ ）、2022年11月に2万人を突破した（KAI-YOU の報道、https://kai-you.net/article/85418 ）【確認】。
  - 休止中のチャンネルを含むと考えられる。
- 2025年第2四半期の活動中の VTuber は 6,000 人以上で、日本のシェアは 37%（Streams Charts、https://streamscharts.com/news/vtubers-q2-2025-report ）【確認】。
- 登録者 1 万人以上の日本の VTuber の数について、信頼できる最新値は見つからなかった【未確認】。

## 7. 実測（2026-11-24、policy 1.0.0）

実測の結果は `Cohorts/Policy1.0.0_20261124/Summary.md` を参照。
