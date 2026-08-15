# モジュール 3: ベクトルデータベースと検索拡張（RAG） - ハンズオン手順

## パート 1: ナレッジベースのセットアップ（20分）

### ステップ 1.1: サンプルドキュメントの準備

```bash
cd ~/handson/M03-rag-knowledgebase

# サンプル法律文書用の S3 バケットを作成
aws s3 mb s3://legal-kb-demo-$(aws sts get-caller-identity --query Account --output text)

# サンプルドキュメントをアップロード
aws s3 cp sample-docs/ s3://legal-kb-demo-$(aws sts get-caller-identity --query Account --output text)/documents/ --recursive
```

サンプルドキュメント（`sample-docs/`）には以下が含まれます：
- `contract_template.txt` - 契約書テンプレート
- `privacy_regulation.txt` - 個人情報保護規制ガイドライン
- `employment_law.txt` - 労働法の概要

### ステップ 1.2: Amazon S3 Vectors の理解

このハンズオンでは、ベクトルストアとして **Amazon S3 Vectors** を使用します。

| 特徴 | S3 Vectors | OpenSearch Serverless |
|------|-----------|---------------------|
| コスト | 最大90%削減 | ベースライン |
| スケール | 20億ベクトル | 数百万ベクトル |
| 管理 | サーバーレス（インフラ管理不要） | コレクション管理が必要 |
| レイテンシー | サブ秒（コールド）〜100ms（ウォーム） | 低レイテンシー |
| Bedrock KB統合 | ネイティブ対応 | ネイティブ対応 |
| 最適ユースケース | RAG、大規模ベクトル保存 | 高QPS、ハイブリッド検索 |

### ステップ 1.3: ナレッジベースの作成（S3 Vectors）

スクリプトを実行して、S3 Vectors ベースのナレッジベースを作成します：

```bash
python setup_knowledgebase.py
```

スクリプトは以下を順番に実行します：
1. **IAM ロールの作成** - `s3vectors:*` 権限を含むロール
2. **S3 ベクトルバケットの作成** - ベクトル格納用の専用バケット
3. **ベクトルインデックスの作成** - 1024次元、cosine距離、float32
4. **ナレッジベースの作成** - `storageConfiguration.type = "S3_VECTORS"`
5. **S3 データソースの設定** - 階層型チャンキング
6. **データソースの同期（Sync）** - ドキュメントのインジェスション

実行完了後、`kb_config.json` にナレッジベース ID 等が保存されます。

### ステップ 1.4: S3 Vectors の構造確認

```bash
# ベクトルバケットの確認
aws s3vectors get-vector-bucket --vector-bucket-name legal-vectors-demo

# ベクトルインデックスの確認
aws s3vectors get-index --vector-bucket-name legal-vectors-demo --index-name legal-docs-index
```

確認ポイント：
- `dimension`: 1024（Titan Embeddings V2 の出力次元）
- `distanceMetric`: cosine（テキスト類似度に最適）
- `dataType`: float32（標準精度）

---

## パート 2: 検索の実装と最適化（20分）

### ステップ 2.1: 基本的な RetrieveAndGenerate

```bash
python rag_basic.py
```

以下のクエリで動作を確認します：
- 「契約書の解除条件について教えてください」
- 「個人情報の第三者提供に関する規制は？」
- 「従業員の残業規制について説明してください」

**確認ポイント：**
- 引用付きの回答が生成されること
- 引用元ドキュメントが表示されること
- レスポンス時間（通常 1-3 秒）

### ステップ 2.2: Retrieve API による検索結果の詳細確認

```bash
python rag_retrieve.py
```

Retrieve API で返される情報を詳細に確認します：

**デモ 1: 基本検索**
- 検索されたチャンクのテキスト内容
- 関連度スコア（relevance score: 0.0〜1.0）
- ソースドキュメントの S3 URI
- メタデータ（ドキュメントタイプ、カテゴリ）

**デモ 2: S3 Vectors の検索タイプと制限事項**
- S3 Vectors ではセマンティック検索のみ対応
- ハイブリッド検索（BM25 + ベクトル）は OpenSearch でのみ利用可能
- ベクトルストア選択の判断基準

**デモ 3: numberOfResults パラメータの影響**
- 3件: 高品質チャンクのみ（精度重視）
- 5件: バランス型（標準推奨）
- 10件: 網羅性重視（低関連チャンク混入リスク）

**デモ 4: メタデータフィルタリング**
- カテゴリ指定検索（`equals` フィルタ）
- 部署別アクセス制御のパターン

### ステップ 2.3: 検索タイプについて（S3 Vectors の制限事項）

> **重要**: Amazon S3 Vectors はハイブリッド検索（BM25 + ベクトル）に対応していません。
> `overrideSearchType: "HYBRID"` を指定しても、S3 Vectors ではセマンティック検索にフォールバックします。

| 検索タイプ | S3 Vectors | OpenSearch Serverless |
|-----------|-----------|---------------------|
| セマンティック検索（ベクトル類似度） | ✅ 対応 | ✅ 対応 |
| ハイブリッド検索（BM25 + ベクトル） | ❌ 非対応 | ✅ ネイティブ対応 |
| メタデータフィルタリング | ✅ 基本対応 | ✅ 高度な DSL |

**ハイブリッド検索が必要な場合:**
- `M03-opensearch-vectorsearch/` ハンズオンで OpenSearch Serverless を使った
  BM25 + k-NN のネイティブハイブリッド検索を体験できます
- S3 Vectors を長期保存用、OpenSearch を高性能クエリ用とする**ティアード構成**も可能

```bash
# ハイブリッド検索の実践は OpenSearch ハンズオンで実施
cd ~/handson/M03-opensearch-vectorsearch
python hybrid_search.py --demo
```

---

## パート 3: 会話型ナレッジアシスタント（15分）

### ステップ 3.1: マルチターン会話の実装

```bash
python knowledge_assistant.py
```

**デモ 1: マルチターン会話**
- セッション ID によるコンテキスト管理
- 前の質問を参照した追加質問への対応（「その場合は？」「これらは？」）
- 引用付き回答でソースの透明性を確保

会話シナリオ例：
```
Turn 1: 「契約書の解除条件について教えてください」
Turn 2: 「その場合の損害賠償はどうなりますか」  ← "その場合" = 契約解除
Turn 3: 「解除の通知期間は何日前ですか」
Turn 4: 「これらの条件は雇用契約にも適用されますか」 ← "これら" = Turn1-3の条件
```

### ステップ 3.2: アクセス制御の実装

**デモ 2: ロールベースアクセス制御**

```python
# ロール別アクセス可能カテゴリ
ACCESS_MATRIX = {
    "partner":   ["contract", "employment_law", "privacy", "ip", "confidential"],
    "associate": ["contract", "employment_law", "privacy", "ip"],
    "paralegal": ["contract", "employment_law"],
    "intern":    ["contract"],
}
```

- 各ロールでの回答の違いを確認
- アクセス拒否時のメッセージ
- 実装パターン: メタデータフィルタリング / ポストフィルタリング / KB分割

### ステップ 3.3: 回答品質の制御

**デモ 3: パラメータによる品質制御**

| モード | numberOfResults | temperature | 特徴 |
|--------|----------------|-------------|------|
| 精密 | 3 | 0.1 | 簡潔、忠実、ハルシネーション最小 |
| バランス | 5 | 0.3 | 適度な詳細さ（標準推奨） |
| 創造 | 10 | 0.7 | 詳細だが冗長、推測混入リスク |

### ステップ 3.4: 対話モードの実行（オプション）

```bash
python knowledge_assistant.py --interactive
```

実際に質問を入力して、アシスタントと対話できます。

---

## パート 4: RAGAS 評価（15分）

### ステップ 4.1: RAGAS フレームワークの概要

RAGAS（RAG Assessment）は、RAG システムの品質を4つの指標で定量評価するフレームワークです。

```
┌─────────────────────────────────────────────────────────────────┐
│  RAGAS の 4 指標                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. Faithfulness（忠実性）                                       │
│     回答がソースに忠実か？ ハルシネーションの検出                │
│     低い場合: temperature↓, numberOfResults↓                    │
│                                                                   │
│  2. Answer Relevancy（回答関連性）                               │
│     回答が質問の意図に沿っているか？                             │
│     低い場合: プロンプト改善, クエリ拡張                         │
│                                                                   │
│  3. Context Precision（コンテキスト精度）                        │
│     検索結果は質問に関連しているか？ 上位の関連度は高いか？      │
│     低い場合: チャンキング変更, ハイブリッド検索                  │
│                                                                   │
│  4. Context Recall（コンテキスト再現率）                         │
│     必要な情報は全て検索されているか？ 取りこぼしはないか？      │
│     低い場合: numberOfResults↑, チャンクサイズ↑                 │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### ステップ 4.2: 評価の実行

```bash
python rag_evaluation.py
```

**評価パイプラインの処理フロー：**

1. **評価データセット（Ground Truth）の準備**
   - 代表的な質問 5 件 + 正解（期待する回答）
   - 期待されるソースドキュメント
   - カテゴリ分類

2. **RAG パイプラインの実行**
   - 各質問で Retrieve API → RetrieveAndGenerate API を実行
   - 検索結果（コンテキスト）と生成回答を記録

3. **LLM-as-a-Judge による自動評価**
   - 評価用 LLM（Nova Lite）で 4 指標を算出
   - 各指標のスコア（0.0〜1.0）+ 理由を JSON で取得
   - 1 質問あたり 4 回の LLM 呼び出し

4. **結果表示と改善提案**
   - 指標別スコア一覧
   - 品質判定（優秀 ≥0.8 / 良好 ≥0.6 / 要改善 <0.6）
   - スコアに基づく具体的な改善アクション

### ステップ 4.3: 評価結果の分析

出力例：
```
  質問                          忠実性   関連性   精度     再現率   総合
  ─────────────────────────────────────────────────────────────────
  契約書の解除条件について...   0.92     0.88     0.85     0.90     0.89
  解雇予告は何日前に...         0.95     0.91     0.88     0.85     0.90
  個人情報の第三者提供...       0.85     0.82     0.78     0.80     0.81
  ─────────────────────────────────────────────────────────────────
  平均                          0.90     0.87     0.81     0.84     0.85
```

### ステップ 4.4: 改善アクションの実施

評価結果に基づく改善サイクル：

```
測定 → 分析 → 改善 → 再測定
  ↑                      ↓
  └──────────────────────┘
```

| 指標が低い | 対策 |
|-----------|------|
| Faithfulness↓ | temperature を 0.1-0.2 に下げる、numberOfResults を 3-5 に制限 |
| Relevancy↓ | クエリ拡張（LLM でクエリ書き換え）、OpenSearch 連携でハイブリッド検索を導入 |
| Precision↓ | チャンキング戦略の変更（階層型/セマンティック）、メタデータフィルタ追加 |
| Recall↓ | numberOfResults を増やす（5→10）、チャンクサイズを大きくする |

---

### ステップ 4.5: Amazon Bedrock Evaluations による RAG 評価（コンソール）

マネジメントコンソールから Amazon Bedrock Evaluations の RAG 評価ジョブを作成し、
ナレッジベースの品質をビルトインメトリクスで自動評価します。

#### 1. テストデータのアップロード

評価用データセット（`rag-eval-dataset.jsonl`）を S3 にアップロードします：

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 cp rag-eval-dataset.jsonl s3://legal-kb-demo-${ACCOUNT_ID}/evaluation/rag-eval-dataset.jsonl
```

データセットのフォーマット（JSONL、各行が1つの評価ケース）：
```json
{
  "conversationTurns": [{
    "prompt": {"content": [{"text": "契約書の解除条件について教えてください"}]},
    "referenceResponses": [{"content": [{"text": "期待する正解回答..."}]}]
  }]
}
```

#### 2. コンソールから評価ジョブを作成

1. **Amazon Bedrock コンソール** → 左メニュー「Inference and Assessment」→「Evaluations」
2. **RAG evaluations** ペインで「Create」をクリック
3. **Evaluation details**:
   - Evaluation name: `legal-kb-rag-eval`
   - Evaluator model: `Amazon Nova Pro`（または `Meta Llama 3.1 70B`）
4. **Inference source**:
   - Select source: **Bedrock Knowledge Base**
   - Choose a Knowledge Base: `legal-knowledge-base-demo`（作成した KB を選択）
   - Evaluation type: **Retrieval and response generation**
   - Model for generation: `Amazon Nova Pro`
5. **Metrics**（評価指標を選択）:
   - `Correctness` — 回答の正確性（referenceResponses との一致度）
   - `Completeness` — 回答の完全性（重要な情報の網羅度）
   - `Faithfulness` — 忠実性（検索結果に基づいた回答か）
   - `Helpfulness` — 有用性（質問者にとって実用的か）
   - `Citation Coverage` — 引用カバー率（回答の根拠が引用で裏付けられているか）
   - `Citation Precision` — 引用精度（引用が回答内容に関連しているか）
6. **Datasets**:
   - Prompt dataset: `s3://legal-kb-demo-<ACCOUNT_ID>/evaluation/rag-eval-dataset.jsonl`
   - Output location: `s3://legal-kb-demo-<ACCOUNT_ID>/evaluation/results/`
7. **Service role**: 新規作成 or 既存のロールを選択
8. 「Create」をクリックして評価ジョブを開始

#### 3. 評価結果の確認

評価ジョブ完了後（通常 5-10 分）：

1. **Evaluations** 画面でジョブのステータスが「Completed」になったことを確認
2. ジョブ名をクリックして詳細を表示
3. **Results** タブで各メトリクスのスコアを確認：

| メトリクス | 説明 | 目標値 |
|-----------|------|--------|
| Correctness | 正解との一致度 | ≥ 0.7 |
| Completeness | 情報の網羅性 | ≥ 0.7 |
| Faithfulness | ソースへの忠実性 | ≥ 0.8 |
| Helpfulness | 実用性 | ≥ 0.7 |
| Citation Coverage | 引用カバー率 | ≥ 0.6 |
| Citation Precision | 引用精度 | ≥ 0.7 |

4. 個別の質問ごとの結果を展開して、どの質問でスコアが低いかを特定

#### 4. LLM-as-a-Judge 評価との比較

| 観点 | Bedrock Evaluations | rag_evaluation.py（自作） |
|------|--------------------|-----------------------|
| セットアップ | コンソールで数クリック | コード実装が必要 |
| メトリクス | ビルトイン 10 種類 | カスタム定義可能 |
| スケール | 最大 1000 件 / ジョブ | 制限なし（コスト次第） |
| カスタマイズ | メトリクス選択のみ | プロンプト自由設計 |
| CI/CD 統合 | API / CLI で自動化可能 | 直接スクリプト実行 |
| 推奨用途 | 定期的な品質チェック | 開発中の細かい改善 |

---

## パート 5: チャンキング最適化（10分）

### ステップ 5.1: チャンキング戦略の比較

```bash
python chunking_optimization.py
```

**Bedrock ナレッジベースで利用可能な 5 つのチャンキング戦略：**

| 戦略 | 設定 | 最適ケース | トレードオフ |
|------|------|-----------|-------------|
| 固定サイズ（小） | 300トークン / 20%オーバーラップ | FAQ、短文 | 精度高いが文脈欠落 |
| 固定サイズ（大） | 1000トークン / 10%オーバーラップ | 技術文書、レポート | 文脈保持だがノイズ増 |
| 階層型 | 親1500/子300トークン | 法律文書、マニュアル | 最もバランス良い |
| セマンティック | 意味境界で分割、最大1000 | 混合コンテンツ | 自然だがコスト高 |
| なし | ドキュメント全体 | 短文のみ | 長文には不適切 |

### ステップ 5.2: パラメータチューニングの詳細

**階層型チャンキング（推奨設定）：**

```python
{
    "chunkingStrategy": "HIERARCHICAL",
    "hierarchicalChunkingConfiguration": {
        "levelConfigurations": [
            {"maxTokens": 1500},   # 親チャンク（セクション全体）
            {"maxTokens": 300}     # 子チャンク（検索単位）
        ],
        "overlapTokens": 60        # 子チャンク間の重複
    }
}
```

動作原理：
- **子チャンク**（300トークン）: ベクトル検索の単位。精密なマッチング。
- **親チャンク**（1500トークン）: 子チャンクにマッチした際の文脈補完。
- **オーバーラップ**（60トークン）: チャンク境界での情報欠落を防止。

**セマンティックチャンキング（代替設定）：**

```python
{
    "chunkingStrategy": "SEMANTIC",
    "semanticChunkingConfiguration": {
        "maxTokens": 1000,
        "bufferSize": 0,
        "breakpointPercentileThreshold": 95  # 上位5%の不連続点で分割
    }
}
```

動作原理：
1. 文ごとに埋め込みベクトルを計算
2. 隣接文間のコサイン類似度を計算
3. 類似度が閾値以下の箇所でチャンク分割
4. `threshold=95` → 非常に明確な意味的区切りのみで分割

### ステップ 5.3: 最適戦略の選定

ドキュメントタイプに応じた推奨：

```
法律文書（構造化・セクションあり）
  → 推奨1: 階層型（信頼度90%）
  → 推奨2: セマンティック（信頼度80%）

社内FAQ（短文・非構造化）
  → 推奨1: 固定サイズ小（信頼度85%）

技術ドキュメント（長文・構造化）
  → 推奨1: 階層型（信頼度85%）
  → 推奨2: セマンティック（信頼度80%）
```

### ステップ 5.4: 比較結果の確認

スクリプトが出力する比較結果のシミュレーション：

| メトリクス | 固定(小) | 固定(大) | 階層型 | セマンティック |
|-----------|---------|---------|--------|-------------|
| Precision@5 | 0.60 | 0.80 | **0.90** | 0.85 |
| Recall@5 | 0.70 | 0.85 | 0.85 | **0.90** |
| 平均スコア | 0.72 | 0.78 | **0.84** | 0.82 |
| スコア安定性 | 低 | 中 | **高** | 中〜高 |
| レスポンス時間 | 0.42秒 | 0.55秒 | 0.48秒 | 0.51秒 |

**結論**: 法律文書には「階層型」が最適（Precision最高 + スコア安定）

---
