# モジュール 1: 基盤モデルの選択と設定 - ハンズオン手順

## パート 1: モデル評価とベンチマーク（10分）

### ステップ 1.1: プロジェクトの準備

```bash
sudo su - ec2-user
cd ~/handson/M01-model-selection
```

### ステップ 1.2: モデルベンチマーク比較の実行

```bash
python3.12 benchmark.py
```

このスクリプトは以下を測定します：
- **レイテンシー**: 合計応答時間
- **トークン使用量**: 入力/出力トークン数
- **コスト**: モデルごとの推定コスト
- **応答長**: 生成されたテキストの文字数

### ステップ 1.3: 結果の確認

出力される比較テーブルを確認し、以下を議論します：
- どのモデルがどのユースケースに最適か
- コストとパフォーマンスのトレードオフ
- レイテンシー要件に基づくモデル選定基準

---

## パート 2: 動的モデル選択 API のデプロイ（15分）

### ステップ 2.1: SAM テンプレートの確認

`template.yaml` で以下のリソースが定義されています：
- API Gateway REST API
- Lambda ルーティング関数（サーキットブレーカー内蔵）
- IAM ロール（Bedrock アクセス権限付き）
- CloudWatch ダッシュボード

### ステップ 2.2: ルーティングロジックの確認

`lambda/router.py` に実装されているルーティング戦略：

1. **リクエスト分類**: クエリの文字数・キーワードに基づいて複雑度を判定
2. **モデル選択**: 複雑度に応じてモデルを割り当て
   - `simple` → Amazon Nova Lite（安価・高速）
   - `medium` → Amazon Nova Pro（バランス）
   - `complex` → Claude Sonnet 4.5（高品質）
3. **サーキットブレーカー**: 障害発生時に自動フォールバック
4. **コスト管理**: 予算超過時に低コストモデルへ自動切り替え

### ステップ 2.3: デプロイ

```bash
sam build
sam deploy --stack-name m01 --resolve-s3 --capabilities CAPABILITY_IAM --no-confirm-changeset
```

デプロイ完了後、出力される API Gateway のエンドポイント URL をメモします：

```bash
aws cloudformation describe-stacks --stack-name m01 \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
```

### ステップ 2.4: 負荷テスト

100件のクエリ（simple=40, medium=30, complex=30）を一括送信して動的ルーティングの動作を確認します：

```bash
python3.12 load_test.py <API_URL>
```

出力される結果：
- 各クエリのルーティング先モデルとレイテンシー
- 複雑度別の成功率・平均レイテンシー・主なルーティング先
- モデル別の呼び出し回数と平均レイテンシー
- フォールバック発生回数

---

## パート 3: サーキットブレーカーと障害シミュレーション（15分）

### ステップ 3.1: ヘルスチェックの確認

```bash
API_URL=<デプロイ時に取得したURL>
curl -s $API_URL/health | python3.12 -m json.tool
```

レスポンス例：
```json
{
    "status": "healthy",
    "circuit_breakers": {},
    "timestamp": "2026-08-11T10:00:00"
}
```

### ステップ 3.2: 通常動作の確認

```bash
# simple → Nova Lite にルーティングされることを確認
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "S3とは？", "complexity": "simple"}' | python3.12 -m json.tool

# complex → Claude Sonnet にルーティングされることを確認
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "マルチリージョンDR設計をRTO5分RPO1分で提案してください", "complexity": "complex"}' | python3.12 -m json.tool
```

### ステップ 3.3: 障害シミュレーション（プロバイダー障害を発生させる）

```bash
# Anthropic (Claude) に timeout 障害をシミュレート
curl -s -X POST $API_URL/admin/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "failure_type": "timeout"}' | python3.12 -m json.tool
```

### ステップ 3.4: フォールバック動作の確認

障害シミュレーション中に complex クエリを送信：

```bash
# 通常なら Claude に行くクエリだが、Nova Pro にフォールバックする
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "金融規制コンプライアンスのリスク評価を行ってください", "complexity": "complex"}' | python3.12 -m json.tool
```

レスポンスで以下を確認：
- `"fallback_used": true` になっている
- `"fallback_reason"` にサーキットブレーカーの情報
- `"model_used"` がフォールバック先モデルになっている

### ステップ 3.5: サーキットブレーカー状態の確認

```bash
curl -s $API_URL/health | python3.12 -m json.tool
```

`circuit_breakers` フィールドに `"OPEN"` 状態が表示されることを確認。

### ステップ 3.6: 障害の解除と回復確認

```bash
# 障害を解除
curl -s -X POST $API_URL/admin/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "failure_type": "none"}' | python3.12 -m json.tool

# 30秒後（CB タイムアウト後）に complex クエリを送信 → Claude に復帰
sleep 35
curl -s -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"query": "マイクロサービスのCI/CD設計を提案してください", "complexity": "complex"}' | python3.12 -m json.tool
```

`"fallback_used": false` で元のモデルに復帰したことを確認。

---

## パート 4: CloudWatch ダッシュボードでの可視化（5分）

### ステップ 4.1: ダッシュボード URL の取得

```bash
aws cloudformation describe-stacks --stack-name m01 \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" --output text
```

### ステップ 4.2: ダッシュボードの確認

AWS コンソールで CloudWatch ダッシュボード（`GenAI-Model-Selection`）を開き確認：
- モデルごとの呼び出し回数
- レイテンシーの推移
- サーキットブレーカー状態
- 推定コスト

---

## パート 5: Bedrock モデル評価ジョブの実行（15分）

Amazon Bedrock のモデル評価機能を使用して、定量的（Programmatic）および定性的（LLM as a Judge）な評価を実行します。

### 評価データセットの確認

評価用データセットは以下に配置済みです：

```
入力: s3://handson-demo-assets-079700436326/evaluation/evaluation-dataset.jsonl
出力: s3://handson-demo-assets-079700436326/evaluation/results/
```

データセットは JSONL 形式で、各行に `prompt` と `referenceResponse`（期待される回答）が含まれています。

---

### ステップ 5.1: Automatic: Programmatic 評価の実行

プログラム的評価では、Toxicity（有害性）や Accuracy（正確性）などを自動計算メトリクスで測定します。

1. **Bedrock コンソール** → 左メニュー「Assessment & deployment」→「Model evaluation」を開く

2. **Create** ボタンをクリックし、**Automatic: Programmatic** を選択

3. 評価ジョブの設定：
   - **Evaluation name**: `m01-programmatic-eval`
   - **Description**（任意）: `Module 1 ハンズオン - プログラム的モデル評価`

4. **評価対象モデルの選択**:
   - 比較したいモデルを選択（例: Amazon Nova Lite、Amazon Nova Pro、Claude Sonnet）

5. **Task type（タスクタイプ）の選択**:
   - **General text generation** を選択
   - その他の選択肢: Text summarization、Question and answer、Text classification

6. **Metrics and datasets（メトリクスとデータセット）の設定**:

   メトリクスごとにデータセットを紐づけて設定します。

   **メトリクス 1: Toxicity（有害性）**
   - Metric ドロップダウンから **Toxicity** を選択
     - 有害・攻撃的・不適切なコンテンツを生成する傾向を測定
   - Choose a prompt dataset: **Available built-in datasets** を選択
   - 以下のビルトインデータセットにチェック：
     - ✅ **Real Toxicity** — 人種差別・性差別などの有害言語を測定するデータセット
     - ✅ **BOLD** — 職業・性別・人種・宗教・政治的イデオロギーの5領域で公平性を測定するデータセット（23,679プロンプト）

   **メトリクス 2: Accuracy（正確性）**
   - Metric ドロップダウンから **Accuracy** を選択
     - 実世界の事実知識をエンコードする能力を測定
   - Choose a prompt dataset: **Use your own prompt dataset** を選択
   - **Input S3 URI**: `s3://handson-demo-assets-079700436326/evaluation/evaluation-dataset.jsonl`

   ※ メトリクスを追加するには画面下部の「Add metric」をクリックします。不要なメトリクスは「Remove」ボタンで削除できます。

7. **Output S3 URI の指定**:
   - `s3://handson-demo-assets-079700436326/evaluation/results/`

8. **Create** をクリックして評価を開始

9. 評価完了後（数分〜十数分）、結果を確認：
   - 各モデルのメトリクススコア比較
   - 強み・弱みの可視化

---

### ステップ 5.2: Automatic: LLM as a Judge 評価の実行

LLM as a Judge では、別のLLM（審査員モデル）が応答品質を評価します。人間の判断に近い定性的な評価が可能です。

1. **Bedrock コンソール** → 左メニュー「Assessment & deployment」→「Model evaluation」を開く

2. **Create** ボタンをクリックし、**Automatic: LLM as a judge** を選択

3. 評価ジョブの設定：
   - **Evaluation name**: `m01-llm-judge-eval`
   - **Description**（任意）: `Module 1 ハンズオン - LLM as a Judge モデル評価`

4. **評価対象モデルの選択**:
   - 比較したいモデルを選択（例: Amazon Nova Lite、Amazon Nova Pro、Claude Sonnet）

5. **Judge モデルの選択**:
   - 審査員として使用するモデルを選択（例: Claude Sonnet 4 など高性能モデルを推奨）

6. **評価基準（メトリクス）の選択**:

   **Quality（品質）メトリクス（9種類）** - 生成された応答の品質と正確性を評価:
   - **Helpfulness**（有用性）: 回答がどれだけ有用で包括的か
   - **Correctness**（正確性）: 回答がどれだけ正しいか
   - **Faithfulness**（忠実性）: 元の入力情報との整合性
   - **Professional style and tone**（専門的スタイル・トーン）: 対象ジャンルに適したスタイル・書式・トーンか
   - **Completeness**（完全性）: すべてのリクエストを解決しているか
   - **Coherence**（一貫性）: 回答内の論理的ギャップや矛盾がないか
   - **Relevance**（関連性）: 質問に対する回答の関連度
   - **Following instructions**（指示遵守）: 指示のすべての明示的部分を尊重しているか
   - **Readability**（可読性）: テキストの用語的・言語的な複雑さ

   **Responsible AI メトリクス（3種類）** - 生成コンテンツの安全性を評価:
   - **Harmfulness**（無害性）: ヘイト・侮辱・暴力などの有害コンテンツを避けているか
   - **Refusal**（拒否）: 質問への回答を回避し代替トピックを提示する回避的コンテンツの評価
   - **Stereotyping**（ステレオタイプ）: 特定グループに対する過度に単純化された信念や偏見の評価

   **品質のディメンション（参考）**:
   | 流暢性 | コヒーレンス | 関連性 | 正解率 |
   |--------|------------|--------|--------|
   | 自然言語の流れと読みやすさ | 回答間の論理的一貫性 | 入力プロンプトとコンテキストの整合性 | 提供された情報の正確性 |

   今回のハンズオンでは以下を選択します：
   - **Helpfulness**（有用性）✅
   - **Harmfulness**（無害性）✅

7. **データセットの指定**:
   - **Input S3 URI**: `s3://handson-demo-assets-079700436326/evaluation/evaluation-dataset.jsonl`
   - **Output S3 URI**: `s3://handson-demo-assets-079700436326/evaluation/results/`

8. **Create** をクリックして評価を開始

9. 評価完了後、結果を確認：
   - Judge モデルによる各応答のスコアと評価理由
   - モデル間の品質比較

---

### ステップ 5.3: 評価結果の比較と考察

両方の評価が完了したら、以下を議論します：

| 観点 | Programmatic | LLM as a Judge |
|------|-------------|----------------|
| 評価速度 | 高速（自動計算） | やや遅い（LLM推論） |
| 評価コスト | 低い | Judge モデルの推論コストが発生 |
| 評価の深さ | 定量的メトリクス | 定性的・ニュアンスのある評価 |
| 適したケース | 大規模バッチ評価 | 品質の詳細分析 |

**考察ポイント**:
- Programmatic 評価で高スコアだが LLM Judge で低評価のケースはあるか？
- どのモデルが総合的にベストか？
- コストパフォーマンスを考慮した最適なモデル選定は？

---

## デモ手順

### デモ 1: 動的ルーティングの動作（7分）

1. `python3.12 load_test.py <API_URL>` を実行
2. リアルタイムで各クエリのルーティング先が表示される
3. 完了後のサマリーで以下を説明：
   - simple は Nova Lite、complex は Claude にルーティングされた
   - コスト差（Nova Lite: $0.00003 vs Claude: $0.005）
   - レイテンシー差（Nova Lite: ~1秒 vs Claude: ~3秒）
4. 「ユースケースに応じて最適なモデルを自動選択 → コスト削減 + 品質確保」

### デモ 2: 障害時のレジリエンス（7分）

1. `curl $API_URL/health` で全プロバイダー正常を確認
2. complex クエリを送信 → Claude で応答されることを確認
3. `curl -X POST $API_URL/admin/simulate-failure -d '{"provider":"anthropic","failure_type":"timeout"}'` で障害発生
4. 同じ complex クエリを送信 → Nova Pro にフォールバック（`fallback_used: true`）
5. `curl $API_URL/health` でサーキットブレーカー OPEN を確認
6. 障害解除 → 30秒後に再送信 → Claude に復帰
7. CloudWatch ダッシュボードでメトリクスの変化を確認

### デモ 3: コスト比較（3分）

1. `python3.12 benchmark.py` の月間コスト試算を表示
2. 全リクエストを Claude で処理した場合 vs 動的ルーティングのコスト比較
3. 「70%のリクエストは簡単な質問 → Nova Lite で十分 → コスト90%削減」

---

## クリーンアップ

```bash
cd ~/handson
./cleanup_all.sh
```

全モジュール（M01-M10）のリソースを一括削除します。存在しないリソースは自動スキップされます。

---

## 発展課題

1. **Canary デプロイ**: 新しいモデルバージョンを5%のトラフィックでテストするロジックを追加
2. **マルチリージョン**: us-east-1 と us-west-2 でのフェイルオーバー構成を設計
3. **カスタムメトリクス**: ドメイン固有の品質スコアに基づくルーティングを実装
