# モジュール 2: 高度なデータ処理と品質保証 - ハンズオン手順

## パート 1: データ検証と品質保証（15分）

### ステップ 1.1: プロジェクトの準備

```bash
cd ~/handson/M02-bedrock-converse-api
pip install boto3
```

### ステップ 1.2: 入力データ検証スクリプトの実行

`data_validation.py` を実行して、データ検証パイプラインの動作を確認します：

```bash
python3.12 data_validation.py
```

このスクリプトは以下の検証を実行します：
- **完全性チェック**: 必須フィールドの存在確認
- **形式検証**: データ型、文字数、エンコーディングの検証
- **PII 検出**: Amazon Comprehend による個人情報の自動検出とマスキング
- **コンテンツ安全性**: 不適切なコンテンツのフィルタリング

### ステップ 1.3: PII 検出結果の確認

出力で以下を確認します：
- 検出された PII エンティティ（氏名、電話番号、メールアドレス等）
- マスキング処理前後のテキスト比較
- 検出の信頼度スコア

### ステップ 1.4: 品質スコアリング

データ品質ダッシュボードのメトリクスを確認します：
- 完全性スコア（%）
- 正確性スコア（%）
- 適時性スコア（データの鮮度）

---

## パート 2: マルチモーダルデータ処理（15分）

### ステップ 2.1: テキスト + 画像のマルチモーダル処理

`multimodal_processing.py` を実行します：

```bash
python3.12 multimodal_processing.py
```

このスクリプトは以下を実行します：
- サンプル画像（診断書）の Base64 エンコード
- Bedrock Converse API へのマルチモーダルリクエスト送信
- テキストと画像の統合分析結果の取得

### ステップ 2.2: 処理フローの確認

**マルチモーダル処理パイプライン:**
1. 画像の形式検証（JPEG/PNG、サイズ上限確認）
2. Base64 エンコーディング
3. テキストコンテキストとの統合
4. Converse API 呼び出し（画像 + テキスト）
5. 構造化レスポンスの生成

### ステップ 2.3: 同期処理パターンの比較

3つの処理パターンを比較します：
- **順次処理**: テキスト → 画像 → 統合（安全だが遅い）
- **並列処理**: テキストと画像を同時に処理（高速だが同期が必要）
- **ハイブリッド**: 独立処理は並列、依存関係があるものは順次

---

## パート 3: 入力最適化とコンテキスト管理（10分）

### ステップ 3.1: トークン効率化の実践

`context_optimization.py` を実行します：

```bash
python3.12 context_optimization.py
```

以下の最適化技術を実践します：

**プロンプト圧縮:**
- 冗長な表現の削除（トークン数 30-50% 削減）
- 構造化フォーマットの活用

**スライディングウィンドウ:**
- 会話履歴の要約と最近メッセージの保持
- コンテキストウィンドウ内でのトークン配分最適化

### ステップ 3.2: スライディングウィンドウの動作確認

20ターンの会話をシミュレーションし、以下を比較します：
- 全履歴保持: トークン数、コスト、レスポンス品質
- スライディングウィンドウ（最近5ターン + 要約）: トークン数、コスト、レスポンス品質

### ステップ 3.3: 動的バッチサイジング

キュー深度に応じたバッチサイズの自動調整を確認します：
- 低負荷（<50リクエスト）: バッチサイズ 5（低レイテンシー優先）
- 中負荷（50-500リクエスト）: バッチサイズ 25（バランス）
- 高負荷（>500リクエスト）: バッチサイズ 50（スループット優先）

### ステップ 3.4: プロンプトキャッシュの実践

`prompt_caching_demo.py` を実行して、プロンプトキャッシュの効果を確認します：

```bash
python3.12 prompt_caching_demo.py
```

このスクリプトは以下を実行します：
- 長いシステムプロンプト（保険約款）に対して4つの質問を送信
- キャッシュなし（通常）とキャッシュあり（`cachePoint` 使用）を比較
- `cacheReadInputTokens` / `cacheWriteInputTokens` の値を確認
- レイテンシーとコストの削減効果を表示

確認ポイント：
- 1回目: `cache_write` > 0（キャッシュ書き込み）
- 2回目以降: `cache_read` > 0（キャッシュヒット → コスト90%削減）
- TTL は 5分（5分以内に次のリクエストを送るとヒットする）

---

## パート 4: 統合パフォーマンス測定（10分）

### ステップ 4.1: エンドツーエンドパイプラインの実行

```bash
python3.12 pipeline_demo.py
```

パイプライン全体を通して以下を測定します：
- 検証ステージのレイテンシー
- 処理ステージのレイテンシー
- トークン使用量の最適化効果
- 総コストの比較（最適化前 vs 最適化後）

### ステップ 4.2: サーバーレスパイプラインのデプロイ

`data-processing-demo.yaml` をデプロイして、SQS → Lambda → DynamoDB の本番構成を構築します：

```bash
aws cloudformation create-stack \
  --stack-name data-processing-demo \
  --template-body file://data-processing-demo.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

スタック作成完了を待ちます（2〜3分）：

```bash
aws cloudformation wait stack-create-complete --stack-name data-processing-demo
```

### ステップ 4.3: テストメッセージの送信

SQS キューにテストメッセージを送信し、Lambda が処理することを確認します：

```bash
# キュー URL を取得
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name data-processing-demo \
  --query "Stacks[0].Outputs[?OutputKey=='QueueUrl'].OutputValue" \
  --output text)

# テストメッセージ送信
aws sqs send-message \
  --queue-url $QUEUE_URL \
  --message-body '{"id":"test-001","content":"田中太郎です。電話番号は090-1234-5678です。検査結果を教えてください。","category":"medical_inquiry","language":"ja"}'
```

### ステップ 4.4: 処理結果の確認

DynamoDB テーブルから処理結果を確認します：

```bash
aws dynamodb scan \
  --table-name data-processing-results \
  --region us-east-1
```

確認ポイント：
- `pii_count`: PII が検出された件数
- `masked_content`: PII がマスキングされたテキスト
- `analysis`: Bedrock による分析結果

### ステップ 4.5: CloudWatch ダッシュボードの確認

以下の URL でパイプラインのメトリクスを確認できます：

```bash
echo "https://us-east-1.console.aws.amazon.com/cloudwatch/home#dashboards:name=DataProcessingPipeline"
```

確認するメトリクス：
- Lambda 処理レイテンシー（P50、P95）
- SQS キュー深度
- Lambda 実行回数とエラー数
- DynamoDB 書き込みキャパシティ

### ステップ 4.6: クリーンアップ

```bash
aws cloudformation delete-stack --stack-name data-processing-demo
```

---

## パート 4b: Step Functions によるオーケストレーション（15分）

### ステップ 4b.1: Step Functions パイプラインのデプロイ

Step Functions を使って、検証 → PII マスク → Bedrock 分析 → 保存のパイプラインをオーケストレーションします：

```bash
aws cloudformation create-stack \
  --stack-name stepfunctions-pipeline-demo \
  --template-body file://stepfunctions-pipeline-demo.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

スタック作成完了を待ちます（3〜4分）：

```bash
aws cloudformation wait stack-create-complete --stack-name stepfunctions-pipeline-demo
```

### ステップ 4b.2: パイプラインの構造を確認

ステートマシンの処理フロー：

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Validate │───▶│ PII Mask │───▶│ Bedrock  │───▶│  Save    │
│          │    │          │    │ Analyze  │    │ (DynDB)  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     │
     │ 検証失敗
     ▼
┌──────────┐
│ Skipped  │
└──────────┘
```

ポイント：
- **Map ステート**: 複数レコードを並列処理（MaxConcurrency=3）
- **Choice ステート**: 検証結果に応じて分岐
- **Retry**: Bedrock 呼び出し失敗時に自動リトライ（最大2回、指数バックオフ）
- **Catch**: エラー時はスキップして他のレコード処理を継続

### ステップ 4b.3: パイプラインの実行

デモスクリプトを実行します：

```bash
python3.12 stepfunctions_demo.py
```

または、AWS CLI で直接実行：

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name stepfunctions-pipeline-demo \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
  --output text)

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --input '{"records":[{"id":"rec-001","timestamp":"2024-11-15T10:30:00Z","content":"田中太郎です。電話番号は090-1234-5678です。","category":"medical_inquiry","language":"ja"}]}'
```

### ステップ 4b.4: コンソールで実行フローを確認

Step Functions コンソールでステートマシンの実行状態を可視化します：

```bash
echo "https://us-east-1.console.aws.amazon.com/states/home"
```

確認ポイント：
- 各ステートの成功/失敗が色分けで表示される
- 検証失敗したレコード（rec-004）が「Skipped」に分岐している
- 入出力データが各ステートで確認できる

### ステップ 4b.5: SQS 方式との比較

| 観点 | SQS + Lambda（パート4） | Step Functions（パート4b） |
|------|------------------------|--------------------------|
| 処理フロー | 単一 Lambda 内で順次 | ステートごとに独立 Lambda |
| 可視化 | CloudWatch ログのみ | コンソールでリアルタイム |
| エラー処理 | コード内で実装 | 宣言的（Retry/Catch） |
| 並列制御 | Lambda 同時実行数 | Map の MaxConcurrency |
| 適したケース | 高スループット | 複雑なワークフロー |

### ステップ 4b.6: クリーンアップ

```bash
aws cloudformation delete-stack --stack-name stepfunctions-pipeline-demo
```

---

---

## パート 5: AWS Glue Data Quality による自動検証（15分）

### ステップ 5.1: デモ環境のデプロイ

CloudFormation スタックをデプロイして、Glue Data Catalog と S3 バケットを準備します：

```bash
aws cloudformation create-stack \
  --stack-name glue-data-quality-demo \
  --template-body file://glue-data-quality-demo.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

スタック作成完了を待ちます（3〜4分）：

```bash
aws cloudformation wait stack-create-complete --stack-name glue-data-quality-demo
```

### ステップ 5.2: サンプルデータの確認

`sample-data/customers.csv` には意図的な品質問題を含む12件の顧客データがあります：

| 問題 | レコード | 内容 |
|------|----------|------|
| 欠損値 | C005 | email が空 |
| 範囲外 | C008 | age = 150（18〜120 の範囲外） |
| 欠損値 | C009 | name が空 |
| 無効値 | C011 | membership_type = "gold"（想定外の値） |

### ステップ 5.3: DQDL ルールの確認

以下の DQDL（Data Quality Definition Language）ルールで品質を検証します：

```
Rules = [
    ColumnCount = 6,
    IsComplete "customer_id",
    ColumnDataType "email" = "STRING",
    IsUnique "customer_id",
    ColumnValues "age" between 18 and 120
]
```

各ルールの意味：
- **ColumnCount = 6**: テーブルのカラム数が6であること
- **IsComplete "customer_id"**: customer_id に NULL がないこと
- **ColumnDataType "email" = "STRING"**: email カラムが文字列型であること
- **IsUnique "customer_id"**: customer_id に重複がないこと
- **ColumnValues "age" between 18 and 120**: 年齢が18〜120の範囲内であること

### ステップ 5.4: Glue Data Quality 評価の実行

デモスクリプトを実行します（評価ジョブの起動に 2〜5 分かかります）：

```bash
python3.12 glue_data_quality_demo.py
```

スクリプトは以下を実行します：
1. CloudFormation スタックの出力確認
2. DQDL ルールセットの作成
3. ルール評価ジョブの開始
4. 評価完了待機
5. 結果表示（各ルールの合格/不合格、総合スコア）

### ステップ 5.5: 評価結果の確認

出力で以下を確認します：
- `ColumnValues "age" between 18 and 120` → **FAIL**（C008 の age=150 が違反）
- その他のルール → **PASS**
- 総合品質スコア（0〜1.0）

### ステップ 5.6: Glue ETL ジョブでの Data Quality 評価（ダッシュボード確認）

スタックに含まれる Glue ETL ジョブを実行して、コンソールの Data Quality ダッシュボードを確認します：

```bash
# ジョブ実行
aws glue start-job-run --job-name dq-customers-quality-check --region us-east-1
```

ジョブの完了を待ちます（約2〜3分）：

```bash
# 実行状態の確認
aws glue get-job-runs --job-name dq-customers-quality-check --region us-east-1 \
  --query "JobRuns[0].{Status:JobRunState,Duration:ExecutionTime}"
```

### ステップ 5.7: Data Quality ダッシュボードの確認

ジョブ完了後、コンソールで Data Quality ダッシュボードを確認します：

1. **AWS Glue コンソール** を開く
2. 左メニューから **Data Integration and ETL → ETL jobs** を選択
3. ジョブ一覧から **`dq-customers-quality-check`** をクリック
4. 上部タブの **「Data quality」** タブをクリック

ダッシュボードで確認できる項目：
- **DQ score**: 総合品質スコア（%）
- **Data quality trend**: スコアの時系列推移
- **Anomalies**: 異常検知グラフ
- **Rules タブ**: 各ルールの合格/不合格と評価メトリクス

ジョブを複数回実行するとトレンドグラフにデータが蓄積されます。

### ステップ 5.8: クリーンアップ

```bash
aws cloudformation delete-stack --stack-name glue-data-quality-demo
```

---

## デモ手順

### デモ 1: データ品質検証（5分）
1. 品質に問題のあるデータ（PII含有、不完全なフィールド）を入力
2. 検証パイプラインが問題を検出する過程を表示
3. PII マスキングの before/after を見せる
4. 品質スコアダッシュボードを表示

### デモ 2: マルチモーダル処理（5分）
1. テキストのみのクエリ結果を表示
2. 同じクエリに画像を追加した場合の結果を表示
3. 画像から抽出された情報がどう統合されるか説明
4. 処理パターン（順次 vs 並列 vs ハイブリッド）の比較

### デモ 3: コスト最適化効果（3分）
1. 20ターンの会話での全履歴保持コストを表示
2. スライディングウィンドウ適用後のコストを表示
3. 削減率（通常 60-70% 削減）を強調
4. 品質への影響が最小限であることを確認

### デモ 4: AWS Glue Data Quality（5分）
1. DQDL ルール定義を表示し各ルールの意味を解説
2. サンプルデータの品質問題（age=150、空の email）を確認
3. `glue_data_quality_demo.py` を実行（事前に評価を開始しておくと時短）
4. 合格/不合格の結果と総合スコアを表示
5. 本番では Glue ETL パイプラインに組み込み自動化されることを説明

### デモ 5: Step Functions パイプライン（5分）
1. ステートマシンの構造（検証→PII→Bedrock→保存）を説明
2. `stepfunctions_demo.py` を実行（事前にスタックデプロイ済み）
3. コンソールで実行フローを表示（成功/スキップ/エラーの色分け）
4. 検証失敗レコードが自動でスキップされる分岐を確認
5. SQS 方式との使い分けを説明

---

## クリーンアップ

```bash
cd ~/handson
./cleanup_all.sh
```

全モジュール（M01-M10）のリソースを一括削除します。存在しないリソースは自動スキップされます。

---

## 発展課題

1. **音声統合**: Amazon Transcribe を追加して音声入力も処理するパイプラインを設計
2. **品質アラート**: CloudWatch アラームで品質スコアが低下した場合に通知
3. **データリネージュ**: 処理の各ステージでの変換を追跡するメタデータ管理を実装
4. **Glue Data Quality 拡張**: IsComplete ルールを email カラムにも追加し、推奨ルール機能（`StartDataQualityRuleRecommendationRun`）を試す
