# Lab 2: 思考連鎖推論 — 追加プロンプト演習

Task.ipynb のコードセルに追加して実行できる日本語プロンプト集です。
スライドで紹介された以下のテクニックを、同じ `format_for_nova_lite` / `invoke_model` パターンで実際に試し、推論結果の違いを比較します。

| # | テーマ | 対応スライド |
|---|--------|-------------|
| 1 | 通常プロンプト vs 思考連鎖（CoT） | 思考連鎖推論の基礎 (p.16) |
| 2 | ステップバイステップ推論の構築 | ステップバイステップの推論プロンプト構築 (p.18) |
| 3 | 推論連鎖のエラー処理と検証 | 推論連鎖におけるエラー処理と検証 (p.20) |
| 4 | 条件付きロジックと分岐 | 条件付きロジックと分岐システム (p.28) |
| 5 | 動的プロンプト選択 | 動的プロンプト選択の実装 (p.29) |
| 6 | データ前処理とコンテキストエンリッチ化 | 統合と前処理のワークフロー / データの前処理と変換 (p.31-32) |
| 7 | 後処理の検証 | 後処理の検証とフォーマット (p.33) |

---

## 前提: 共通コード（Task.ipynb のセットアップセルの後に配置）

以下のヘルパー関数は Task.ipynb の既存セルで定義済みです。未実行の場合は先に実行してください。

```python
# 既存セルで定義済み:
# - bedrock_client
# - modelId = "amazon.nova-lite-v1:0"
# - format_for_nova_lite(prompt_text)
# - parse_nova_lite_response(response_body)
```

---

## 演習 1: 通常プロンプト vs 思考連鎖（CoT）の比較

スライド「思考連鎖推論の基礎」では、線形処理（入力→ブラックボックス→出力）と思考連鎖推論（初期分析→中間処理→合成と結論→推論軌跡付き最終応答）の違いが示されています。

同じ問題を「通常プロンプト」と「CoT プロンプト」で比較し、回答の質と透明性の差を観察します。

### セル 1-A: 通常プロンプト（ブラックボックス型）

```python
prompt_normal = """以下の質問に回答してください。

質問: ある EC サイトの月間売上が 1月: 800万円、2月: 950万円、3月: 1100万円、4月: 900万円、5月: 1300万円 でした。
季節要因を考慮した上で、6月の売上を予測し、在庫計画のアドバイスをしてください。

回答:"""

body = format_for_nova_lite(prompt_normal)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【通常プロンプト】")
print(parse_nova_lite_response(response_body))
```

### セル 1-B: 思考連鎖プロンプト（推論軌跡付き）

```python
prompt_cot = """以下の問題を段階的に分析してください。各ステップで思考過程を明示してください。

問題: ある EC サイトの月間売上が 1月: 800万円、2月: 950万円、3月: 1100万円、4月: 900万円、5月: 1300万円 でした。
季節要因を考慮した上で、6月の売上を予測し、在庫計画のアドバイスをしてください。

回答形式:
ステップ 1 [初期分析]: データの傾向を把握する（成長率、変動パターン）
ステップ 2 [中間処理]: 季節要因・外部要因を検討する
ステップ 3 [合成と結論]: 予測値を算出し、根拠を示す
最終応答: 推論軌跡を踏まえた在庫計画アドバイス"""

body = format_for_nova_lite(prompt_cot)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【思考連鎖プロンプト】")
print(parse_nova_lite_response(response_body))
```

### 比較ポイント

| 観察項目 | 通常プロンプト | 思考連鎖プロンプト |
|---------|--------------|------------------|
| 計算過程の可視性 | 結論のみ提示されがち | 各ステップの計算が明示 |
| 根拠の追跡可能性 | 低い | 高い（検証可能） |
| 計算ミスの発見 | 困難 | 容易（中間結果を確認できる） |
| 回答の長さ | 短い | 長い（トークン消費増） |

---

## 演習 2: ステップバイステップ推論の構築

スライド「ステップバイステップの推論プロンプト構築 (2/2)」のビジネスシナリオ例を参考に、構造化された推論を実装します。

### セル 2-A: 導入前（従来のアプローチ）

```python
prompt_before = """当社（従業員50名のSaaS企業）は新しいAIカスタマーサポートツールを導入すべきでしょうか？
月額費用は80万円です。

回答:"""

body = format_for_nova_lite(prompt_before)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【導入前: 単純質問】")
print(parse_nova_lite_response(response_body))
```

### セル 2-B: 導入後（思考連鎖による構造化推論）

```python
prompt_after = """以下のビジネス上の問題を構造化して分析してください。

ビジネス上の問題: 当社（従業員50名のSaaS企業、月間サポート問い合わせ3000件）は新しいAIカスタマーサポートツールを導入すべきか

以下のフレームワークに従って回答してください:

1. 問題分析
   - 現状の課題を整理する
   - 導入目的を明確にする

2. コンテキスト評価
   - 現在のサポートコスト（人件費: サポート担当5名×月給35万円）
   - AIツールのコスト: 月額80万円
   - 期待される自動化率: 40-60%

3. オプション評価
   - オプション A: 即座に全面導入
   - オプション B: 段階的導入（まずFAQ対応のみ）
   - オプション C: 6ヶ月間の試用期間を設ける

4. 決定のロジック
   - ROI の計算
   - リスク評価
   - 既存チームへの影響

5. 確信度評価
   - データの信頼性
   - 推定の不確実性

6. 推奨事項
   - 最適なオプションと根拠"""

body = format_for_nova_lite(prompt_after)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【導入後: ステップバイステップ推論】")
print(parse_nova_lite_response(response_body))
```

### 比較ポイント

導入前のプロンプトでは「導入すべき／すべきでない」という単純な結論が返りがちです。導入後は ROI 計算、リスク分析、代替案の比較が明示され、意思決定者が判断材料として使える回答になります。

---

## 演習 3: 推論連鎖のエラー処理と検証

スライド「推論連鎖におけるエラー処理と検証」のフローチャート（ロジックの一貫性→証拠の有効性→推測の妥当性→代替案の有無を検証）を実装します。

### セル 3: 自己検証チェックポイント付き推論

```python
prompt_verification = """あなたは論理検証の専門家です。以下の主張を4段階のチェックポイントで検証してください。

主張: 「当社のWebサイトのページ読み込み速度を2秒から1秒に改善すれば、
コンバージョン率が50%向上し、年間売上が2億円増加する。
したがって、5000万円のインフラ投資は即座に回収できる。」

チェックポイント 1 [ロジックの一貫性]:
- 前提から結論への論理に飛躍がないか確認する
- 因果関係の妥当性を評価する

チェックポイント 2 [証拠の有効性]:
- 引用されているデータや事実の信頼性を評価する
- 欠落している証拠がないか指摘する

チェックポイント 3 [推測に問題はないか]:
- 隠れた仮定を洗い出す
- その仮定が妥当かどうか判断する

チェックポイント 4 [代替案は検討されているか]:
- 同じ目標を達成する別のアプローチを提示する
- コスト対効果の比較を行う

最終判定:
- 主張の妥当性スコア (1-10)
- 修正が必要な箇所
- エラーリカバリ（修正版の主張）"""

body = format_for_nova_lite(prompt_verification)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【エラー処理と検証: 4段階チェックポイント】")
print(parse_nova_lite_response(response_body))
```

### 観察ポイント

- チェックポイントの順序が重要: ロジックの一貫性が崩れている場合、それ以降の検証結果も信頼できない
- スライドの「いいえ」パスに対応: 各チェックで問題を発見した場合、エラーリカバリ→再検証のフローに入る
- 実務では、このパターンを使って AI 生成コンテンツの品質ゲートを構築できる

---

## 演習 4: 条件付きロジックと分岐システム

スライド「条件付きロジックと分岐システム - 概要」に基づき、コンテンツ分析・ユーザーコンテキスト・システム状態・ビジネスルールを考慮した分岐ロジックを実装します。

### セル 4: 動的ルーティングプロンプト

```python
# シナリオ: カスタマーサポートへの問い合わせを適切にルーティングする
customer_inquiry = "昨日注文した商品がまだ届きません。すでに3回目の遅延です。至急対応してください。契約をキャンセルします。"

prompt_routing = f"""あなたはインテリジェントなサポートルーティングシステムです。
以下の問い合わせを分析し、最適な対応方針を決定してください。

## 問い合わせ内容
{customer_inquiry}

## 分析フレームワーク

### 1. コンテンツ分析
- センチメント（positive/neutral/negative/angry）を判定
- トピック（配送/技術/請求/一般）を分類
- 複雑さ（low/medium/high）を評価

### 2. ユーザーコンテキスト推定
- 過去の問い合わせ履歴の手がかり（「3回目」等）
- 緊急度（low/medium/high/critical）
- 解約リスク（low/medium/high）

### 3. ビジネスルール適用
- コンプライアンス要件: 解約意思表示には24時間以内に上位者が対応
- エスカレーションポリシー: 3回以上の同一問題は自動エスカレーション

### 4. ルーティング決定
以下のJSON形式で結論を出力してください:
```json
{{
  "sentiment": "...",
  "topic": "...",
  "complexity": "...",
  "urgency": "...",
  "churn_risk": "...",
  "route_to": "...",
  "escalation": true/false,
  "sla_hours": ...,
  "recommended_action": "...",
  "reasoning": "..."
}}
```"""

body = format_for_nova_lite(prompt_routing)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【条件付きロジック: 動的ルーティング】")
print(parse_nova_lite_response(response_body))
```

### 追加演習: 別のセンチメントで試す

以下の問い合わせに差し替えて再実行し、ルーティング結果の違いを確認してください:

```python
# パターン A: ポジティブ × 一般
customer_inquiry = "御社のサービスがとても気に入っています。プレミアムプランへのアップグレード方法を教えてください。"

# パターン B: ニュートラル × 技術
customer_inquiry = "APIのレートリミットについて確認したいのですが、現在のプランでの上限値を教えてください。"
```

---

## 演習 5: 動的プロンプト選択

スライド「動的プロンプト選択の実装」の選択基準テーブル（複雑さ、センチメント、分野、出力スタイル）に基づき、入力に応じてプロンプトを動的に切り替えるパターンを実装します。

### セル 5: 入力分類 → テンプレート選択 → 応答生成

```python
# ステップ 1: 入力を分類するプロンプト
user_query = "本番環境のデータベースが応答しなくなりました。ユーザーからのアクセスができない状態です。"

classify_prompt = f"""以下のユーザー入力を分析し、JSON形式で分類結果を出力してください。

ユーザー入力: {user_query}

分類基準:
- complexity: "high"（技術的・専門知識必要）/ "medium"（手順説明で解決）/ "low"（FAQ参照で解決）
- sentiment: "neutral"（中立）/ "empathetic"（共感が必要）/ "positive"（肯定的）
- domain: "technical"（IT・技術）/ "customer"（顧客対応）/ "mixed"（混在）
- output_style: "structured"（構造化レポート）/ "conversational"（会話型）/ "concise"（簡潔）

JSON出力:"""

body = format_for_nova_lite(classify_prompt)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
classification = parse_nova_lite_response(response_body)
print("【ステップ 1: 分類結果】")
print(classification)
```

```python
# ステップ 2: 分類結果に基づいて適切なプロンプトテンプレートを選択
# (ここでは技術×高複雑度の場合のテンプレートを使用)

response_prompt = f"""あなたはシニアインフラエンジニアです。

## 対応方針
- 出力スタイル: 構造化（優先度付きの手順）
- トーン: 冷静かつ緊急性を反映
- 詳細度: 高（コマンド例を含む）

## ユーザーの問題
{user_query}

## 回答フォーマット

### 即座に確認すべき項目（30秒以内）
1. ...
2. ...

### 原因切り分け手順（5分以内）
1. ...
2. ...

### 復旧手順
1. ...

### エスカレーション基準
- 条件: ...
- 連絡先: ..."""

body = format_for_nova_lite(response_prompt)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("\n【ステップ 2: 動的に選択されたテンプレートでの応答】")
print(parse_nova_lite_response(response_body))
```

### 比較ポイント

同じ問題を「一般向けテンプレート」で生成した場合と比較すると、動的選択の効果がわかります:

```python
# 一般向けテンプレート（比較用）
generic_prompt = f"""以下の質問に回答してください。
質問: {user_query}
回答:"""

body = format_for_nova_lite(generic_prompt)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("\n【比較: 一般テンプレートでの応答】")
print(parse_nova_lite_response(response_body))
```

| 観察項目 | 一般テンプレート | 動的選択テンプレート |
|---------|---------------|-------------------|
| 即時性 | 一般論から始まる | 30秒以内のアクションを優先 |
| 技術レベル | 初心者向け説明が混在 | コマンド例を含む実務レベル |
| 構造 | 自由形式 | 時間軸に沿った構造化 |
| エスカレーション | 言及なし | 明確な基準を提示 |

---

## 演習 6: データ前処理とコンテキストエンリッチ化

スライド「統合と前処理のワークフロー」「データの前処理と変換」に基づき、raw データを検証・クリーニング・エンリッチ化してからプロンプトに渡すパターンを実装します。

### セル 6-A: 前処理なし（raw データをそのまま渡す）

```python
# 実際の問い合わせログ（ノイズあり、フォーマット不統一）
raw_data = """
2024/1/15 田中 - servr落ちてる??レスポンスなし。cstmer複数から連絡あり
2024-01-15 14:30 佐藤S: DBサーバーのCPUが95%。たぶんスロークエリ？
1/15 山田: お客様Aから電話。「画面が真っ白」とのこと。Chromeで確認したが再現せず
"""

prompt_raw = f"""以下のインシデントログから状況を分析してください。

ログ:
{raw_data}

分析:"""

body = format_for_nova_lite(prompt_raw)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【前処理なし: raw データをそのまま渡した場合】")
print(parse_nova_lite_response(response_body))
```

### セル 6-B: 前処理あり（検証→クリーニング→エンリッチ化→フォーマット）

```python
# 前処理パイプラインをプロンプト内で指示
prompt_preprocessed = f"""あなたはデータ前処理の専門家 兼 インシデント分析者です。
以下の raw ログデータを、段階的に処理してから分析してください。

## raw データ
{raw_data}

## 前処理パイプライン（各ステップの出力を明示すること）

### ステップ 1: 検証（スキーマ確認）
- 各行の日時・報告者・内容を識別
- 不明な略語や表記ゆれを特定する

### ステップ 2: クリーニング（ノイズ除去）
- 略語を展開する（servr→server、cstmer→customer）
- 日時フォーマットを統一する（ISO 8601: YYYY-MM-DD HH:MM）
- 欠落情報を [不明] と明示する

### ステップ 3: エンリッチ化（コンテキスト追加）
- 各報告の関連性を分析する（同一インシデントか複数か）
- 時系列を再構成する
- 影響範囲を推定する

### ステップ 4: フォーマット（構造化出力）
以下のJSON形式で整理した上で分析結果を出力する:
```json
{{
  "incident_id": "...",
  "timeline": [...],
  "root_cause_hypothesis": "...",
  "impact": "...",
  "recommended_actions": [...]
}}
```"""

body = format_for_nova_lite(prompt_preprocessed)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("【前処理あり: パイプライン適用後の分析】")
print(parse_nova_lite_response(response_body))
```

### 比較ポイント

| ステージ | 前処理なし | 前処理あり |
|---------|-----------|-----------|
| フォーマット | raw のまま解釈（混合） | 標準化され構造化 |
| 品質 | 略語・表記ゆれがそのまま | クリーン、検証済み |
| コンテキスト | 個別の記録として処理 | 関連性によりエンリッチ化 |
| 出力の再利用性 | テキストのみ | JSON で後続システムに渡せる |

---

## 演習 7: 後処理の検証とフォーマット

スライド「後処理の検証とフォーマット」に基づき、AI 出力に対してフォーマットチェック・コンテンツチェック・ビジネスルール・安全性フィルターを適用するパターンを実装します。

### セル 7: 出力検証パイプライン

```python
# まず AI に回答を生成させる
original_prompt = """あなたは保険のアドバイザーです。以下の顧客に最適な保険プランを提案してください。

顧客情報:
- 年齢: 35歳
- 家族構成: 配偶者、子供2人（5歳、3歳）
- 年収: 700万円
- 現在の保険: なし
- 懸念事項: 万が一の際の家族の生活費

提案:"""

body = format_for_nova_lite(original_prompt)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
ai_output = parse_nova_lite_response(response_body)
print("【元の AI 出力】")
print(ai_output)
print("\n" + "=" * 60)
```

```python
# 後処理: 4段階の検証パイプライン
validation_prompt = f"""あなたは AI 出力の品質管理専門家です。以下の AI 生成回答を4つの観点で検証してください。

## 検証対象の AI 出力
{ai_output}

## 検証パイプライン

### 1. フォーマットチェック
- 構造が適切か（見出し、箇条書き等）
- 情報の整理が論理的か
- 問題があれば修正案を示す

### 2. コンテンツチェック
- 精度: 保険に関する情報は正確か
- 完全性: 顧客の懸念事項に対して十分な回答があるか
- 不足している情報は何か

### 3. ビジネスルール適合性
- コンプライアンス: 「確実に」「絶対に」等の断定表現がないか
- ポリシー: 免責事項・注意書きが含まれているか
- 特定商品名を推奨していないか（中立性）

### 4. 安全性フィルター
- 個人情報の不適切な利用がないか
- リスク評価: 顧客に不利益を与える可能性のある記述はないか
- 修正が必要な表現のリスト

## 最終判定
- 総合品質スコア: X/10
- 公開可否: GO / 修正後GO / NG
- 必要な修正事項（あれば）"""

body = format_for_nova_lite(validation_prompt)
response = bedrock_client.invoke_model(
    body=json.dumps(body), modelId=modelId, accept=accept, contentType=contentType
)
response_body = json.loads(response.get('body').read())
print("\n【後処理: 4段階検証結果】")
print(parse_nova_lite_response(response_body))
```

### 観察ポイント

- 元の AI 出力が「断定表現」や「特定商品推奨」を含んでいた場合、ビジネスルールチェックで検出される
- 安全性フィルターは、金融・医療・法務などの規制業界で特に重要
- 実運用では、この検証パイプラインを自動化し、スコアが閾値未満の場合は人間レビューに回す

---

## まとめ: テクニック選択ガイド

| テクニック | 適した場面 | トレードオフ |
|-----------|-----------|-------------|
| 通常プロンプト | シンプルな質問、FAQ | 高速・低コストだが品質が不安定 |
| 線形 CoT | 計算・分析タスク | 精度向上、ただしトークン増加 |
| ステップバイステップ構造化 | ビジネス意思決定 | 網羅性が高い、出力が長くなる |
| エラー検証チェックポイント | 品質ゲート、監査 | 信頼性向上、レイテンシー増加 |
| 条件付きロジック | ルーティング、分類 | 柔軟だがプロンプト設計が複雑 |
| 動的プロンプト選択 | 多様な入力への対応 | 最適化された応答、2段階呼び出し必要 |
| 前処理パイプライン | ノイズの多いデータ | 出力品質向上、プロンプトが長くなる |
| 後処理検証 | 規制業界、公開コンテンツ | 安全性担保、追加のAPI呼び出しが必要 |

---

## 発展課題

1. **演習 1 と 2 の組み合わせ**: CoT + 構造化フレームワークを合体させ、Task.ipynb の車両メンテナンスシナリオに適用してみる
2. **演習 4 の拡張**: ルーティング結果を基に、自動で適切なペルソナのプロンプトに切り替える2段パイプラインを構築する
3. **演習 7 の自動化**: 検証スコアが 7/10 未満の場合に自動で修正版を生成するループを実装する
4. **コスト意識**: 各演習で使用したプロンプトの入力/出力トークン数を比較し、コスト対品質のトレードオフを検討する
