# モジュール 9: テスト、検証、継続的な改善 - ハンズオン手順

## パート 1: AI 評価フレームワークの構築（15分）

### ステップ 1.1: 評価ディメンションの定義

```bash
cd ~/handson/M09-testing-validation
python3.12 evaluation_framework.py
```

AI 品質の4つの評価軸：
1. **正確性**: 回答が事実に基づいているか
2. **関連性**: 質問に対して適切に回答しているか
3. **完全性**: 必要な情報が網羅されているか
4. **安全性**: 有害な内容を含んでいないか

### ステップ 1.2: LLM-as-Judge パターン

別のLLMを「審査員」として使用して品質を自動評価：

```python
judge_prompt = """
以下の質問と回答のペアを評価してください。

質問: {question}
回答: {answer}
参照情報: {reference}

評価基準（各1-5点）:
- 正確性: 事実に基づいているか
- 関連性: 質問に答えているか
- 完全性: 情報が十分か
- 明瞭性: わかりやすいか

JSON形式で評価を返してください。
"""
```

### ステップ 1.3: 評価データセットの準備

テストケースの構成：
- 正解付き質問セット（50問）
- エッジケース（曖昧な質問、範囲外の質問）
- 攻撃的入力（安全性テスト）

---

## パート 2: 実践的な RAG 評価の実装（30分）

> **前提条件**: M03（ナレッジベースのセットアップ）を完了していること。
> M03 で作成した `legal-knowledge-base-demo` を評価対象として使用します。
> 未実施の場合は `export KNOWLEDGE_BASE_ID=<your_kb_id>` を設定してください。

### RAG 評価の課題

従来のソフトウェアテストとは本質的に異なる課題がある：

| 従来のソフトウェアテスト | RAG システムの評価 |
|---|---|
| ✓ 決定論的（固定的な出力） | ⚠ 確率的（複数が有効） |
| ✓ 単一のコンポーネント（単体テスト） | ⚠ 複数のコンポーネント（複雑なパイプライン） |
| ✓ 客観的なメトリクス（合格/不合格） | ⚠ 主観的（品質の測定） |

### RAG システムコンポーネントと評価ポイント

```
ユーザーのクエリ入力
    ↓
[クエリ処理]           → クエリの理解の正解率、意図の分類、あいまいさの処理
    ↓
[取得システム]          → 関連性スコア、網羅率メトリクス、Precision@k、再現率
    ↓
[コンテキストのアセンブリ] → 情報の完全性、コヒーレンススコア、重複排除の有効性
    ↓
[生成]                 → 正解率の測定、流暢スコア、忠実度チェック、ハルシネーション検出
    ↓
[最終出力]             → ユーザー満足度、タスク完了スコア、応答時間
```

---

### ステップ 2.1: 検索品質評価 - 中核のメトリクス

```bash
cd ~/handson/M09-testing-validation
python3.12 rag_retrieval_metrics.py
```

M03 のナレッジベースに対して Retrieve API を実行し、Ground Truth データセットと照合して検索品質を測定します。

**実装するメトリクス:**

| メトリクス | 説明 |
|---|---|
| **Precision@K** | 上位K件のうち関連ドキュメントの割合 |
| **Recall@K（再現率）** | 全関連ドキュメントのうち検索された割合 |
| **MRR** | 最初の正解が何番目に現れるかの逆数 |
| **NDCG@K** | ランキング品質（上位に正解があるほど高スコア） |
| **MAP** | 全クエリの Average Precision の平均（総合指標） |

**確認ポイント:**
- MAP ≥ 0.8 で「優秀」、≥ 0.6 で「良好」
- 難易度別（easy/medium/hard）のスコア差を確認
- MRR が低い場合 → ランキング改善（チャンキング見直し）が必要

---

### ステップ 2.1b: Re-ranking による検索品質の改善

```bash
python3.12 rag_reranking.py
```

ベクトル検索の結果を **Re-ranking モデル**（Cohere Rerank v3.5）で再スコアリングし、検索品質の改善を定量評価します。

**Re-ranking とは:**

```
クエリ → [ベクトル検索: 高速に候補を広く取得] → 候補 10〜20 件
                                                       ↓
        [Re-ranking: Cross-Encoder で精密に再順位付け] → 上位 3〜5 件
```

- ベクトル検索（Bi-Encoder）: 高速だがクエリと文書の細かい関係を見落とすことがある
- Re-ranking（Cross-Encoder）: クエリと各文書を直接比較し正確にスコアリング

**ハンズオン内容（3パート構成）:**

| パート | 内容 | 学習ポイント |
|---|---|---|
| 1 | Rerank API の直接呼び出し | API の使い方、レスポンス構造の理解 |
| 2 | KB Retrieve API + rerankingConfiguration | Re-ranking 前後のメトリクス比較 |
| 3 | パラメータチューニング | 候補数とレイテンシー・精度のトレードオフ |

**パート 1: Rerank API の直接呼び出し**

```python
# Bedrock Rerank API の呼び出し例
response = bedrock_agent_runtime.rerank(
    queries=[{"type": "TEXT", "textQuery": {"text": "契約書の解除条件"}}],
    sources=[
        {"type": "INLINE", "inlineDocumentSource": {
            "type": "TEXT",
            "textDocument": {"text": "文書テキスト..."}
        }}
    ],
    rerankingConfiguration={
        "type": "BEDROCK_RERANKING_MODEL",
        "bedrockRerankingConfiguration": {
            "modelConfiguration": {
                "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"
            },
            "numberOfResults": 5
        }
    }
)
```

**パート 2: Knowledge Base Retrieve API に Re-ranking を統合**

```python
# vectorSearchConfiguration 内に rerankingConfiguration を追加
response = bedrock_agent_runtime.retrieve(
    knowledgeBaseId=kb_id,
    retrievalQuery={"text": query},
    retrievalConfiguration={
        "vectorSearchConfiguration": {
            "numberOfResults": 10,  # 初期候補数（広めに取得）
            "rerankingConfiguration": {
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"
                    },
                    "numberOfRerankedResults": 5  # Re-ranking 後の最終結果数
                }
            }
        }
    }
)
```

**パート 3: パラメータチューニングの指針**

| 初期候補数 | 適用シーン | トレードオフ |
|---|---|---|
| 5 | リアルタイム応答必須 | レイテンシー最小 / 効果限定的 |
| 10 | 一般的な RAG（推奨） | バランス型 |
| 20 | 正確性最重要（法律・医療） | 精度最大 / コスト・レイテンシー増加 |

**確認ポイント:**
- Re-ranking 前後での MRR, NDCG の改善幅を確認
- レイテンシー増加がユースケースの許容範囲内か
- 候補数 > 20 で精度改善が飽和する傾向を確認
- Cohere Rerank v3.5 モデルのアクセスが有効化されているか（Bedrock コンソール）

> **前提条件**: Bedrock コンソールで `Cohere Rerank v3.5` モデルアクセスを有効化しておくこと。
> 未有効化の場合でもモックモードで動作を確認できます。

---

### ステップ 2.2: コンテキスト照合検証

```bash
python3.12 rag_context_validation.py
```

検索されたコンテキストが本当にクエリの意図に合っているかを **5つの軸** で検証します。

| 検証軸 | 内容 | 推奨しきい値 |
|---|---|---|
| 意味的整合性 | 埋め込み類似度に加え概念レベルの一致 | 0.7-0.8 |
| 対象範囲の適切性 | 情報の粒度がクエリに適合しているか | 0.7 |
| 完全性の評価 | クエリの全要素をカバーしているか | 0.8 |
| 冗長性の識別 | 重複コンテンツがないか（低い=良い） | 0.7 |
| 事実整合性 | チャンク間の矛盾がないか | 0.9 |

**網羅性と完全性の分析（スクリプト内で実施）:**
- **情報ギャップの検出**: クエリの全要素に回答するための情報が揃っているか
- **冗長性の識別**: ドキュメント類似性 > 0.8 で冗長と判定
- **完全性スコアリング**: クエリの対応している要素の割合

---

### ステップ 2.3: 生成評価 - LLM-as-Judge とバイアス検知

```bash
python3.12 rag_generation_evaluation.py
```

**Part 1: LLM-as-Judge による多次元評価**

RAG の生成コンポーネントを5つのディメンションで評価：
- 正解率（Correctness）
- 関連性（Relevance）
- 完全性（Completeness）
- 明瞭性（Clarity）
- 忠実度（Faithfulness）— ハルシネーション検出

**自動評価の実装フロー:**
```
明確なスコアリングの → 最低温度の設定 → 人間の判断に → システムの
評価基準の定義         (temperature=0.1)   照らした検証    デプロイ
```

実装のポイント:
- **基準の定義**: 各スコア（1-5）にアンカーの例を明示
- **思考連鎖**: モデルに推論を段階的に説明させ、一貫性を向上
- **キャリブレーション目標**: 人間の評価との相関性 0.7 以上

**Part 2: バイアスの検知と緩和**

| バイアスの種類 | 内容 | 検出方法 |
|---|---|---|
| 位置バイアス | リスト内の位置で評価が変わる | 順序シャッフルでスコア変動を測定 |
| 冗長性バイアス | 長い回答を系統的に優遇 | 同内容の長短版を比較 |
| 確証バイアス | 学習データのパターンを優先 | 多様な回答形式でテスト |

**緩和戦略:**
- ランダム化 / アンサンブル評価 / プロンプトエンジニアリング
- 人間によるキャリブレーション / 定期的な検証（コーエンのκ係数 > 0.6）

---

### ステップ 2.4: エンドツーエンド RAG 評価

```bash
python3.12 rag_e2e_evaluation.py
```

**テストピラミッドに基づく包括的な検証:**

```
        ╱╲        ユーザー受け入れテスト
       ╱  ╲       回帰テスト
      ╱────╲      パフォーマンステスト
     ╱──────╲     システムテスト
    ╱────────╲    統合テスト
   ╱──────────╲   単体テスト
```

**統合テスト（データフロー検証）:**
```
入力(ドキュメント/クエリ) → 処理(埋め込み/変換) → ストレージ(ベクトルDB) → 出力(取得/回答)
       ↓                       ↓                      ↓                    ↓
  フォーマットの検証      レイテンシーの測定       整合性の確認         正解率のアサート
```

**ユーザーエクスペリエンス検証:**
- タスク完了率 85%超 → 成功の測定
- 情報提供までの時間 30秒未満 → 効率の最適化
- ユーザー満足度 NPS/CSAT → フィードバックの収集
- エンゲージメントメトリクス → 動作の分析

**ナレッジベースの品質とメンテナンス（継続的改善ループ）:**
```
モニタリング → 分析 → 更新 → 検証 → モニタリング...
```
- 鮮度スコア / クエリパターン / ドリフト検出
- 網羅率のギャップ / クエリの失敗 / 信頼度が低い
- コンテンツの更新 / 出典の確実性 / バージョン管理
- 品質メトリクス / 制御クエリ / ユーザーからの信頼

**本番稼働準備チェックリスト:**
- [ ] 統合テスト全件 PASS
- [ ] タスク完了率 ≥ 85%
- [ ] 応答時間 < 30秒
- [ ] 満足度 ≥ 3.5/5
- [ ] 品質ドリフトなし

---

## パート 3: A/B テストと継続的改善（10分）

### ステップ 3.1: プロンプト A/B テスト

```bash
python3.12 ab_testing.py
```

テスト設計：
- バリアント A: 現行プロンプト
- バリアント B: 改善版プロンプト（CoT追加）
- トラフィック分割: 50/50
- 評価期間: 100リクエスト

測定メトリクス：
- 品質スコア（LLM-as-Judge）
- レイテンシー
- トークン効率（コスト）
- ユーザー満足度

### ステップ 3.2: 統計的有意性の確認

改善が統計的に有意かを判定：
- サンプルサイズの計算
- 信頼区間の算出
- p値による検定

### ステップ 3.3: 自動改善パイプライン

```
評価 → 低スコア検出 → 原因分析 → プロンプト修正 → A/Bテスト → デプロイ
```

---

## パート 4: 業界ベンチマークの統合（10分）

### ステップ 4.1: ベンチマーク評価の実行

```bash
python3.12 benchmark_comparison.py
```

自分のモデルを業界標準ベンチマークと比較：
- **GLUE（言語理解）**: 自然言語理解タスク
- **HumanEval（コード生成）**: コーディング課題の正答率
- **GSM8K（数学的推論）**: 数学問題の推論能力
- **カスタムドメイン**: 自社ユースケース固有の評価

### ステップ 4.2: パーセンタイル順位の算出

業界平均と比較し、自分のモデルが全体の何パーセンタイルに位置するかを算出：
- 85位以上: 業界トップクラス（平均より上）
- 50-84位: 業界平均レベル
- 50位未満: 改善が必要（平均より下）

### ステップ 4.3: 改善優先度の決定

ベンチマーク結果から、どの能力を優先的に改善すべきかを特定：
- パーセンタイルが低い領域 → 改善の優先度が高い
- ビジネス要件との照合 → 実際に重要な能力に注力

---

## パート 5: 自動評価パイプラインのアーキテクチャ（15分）

### ステップ 5.1: パイプラインの全体像

自動評価パイプラインの3層アーキテクチャ：

| 層 | 役割 | AWSサービス |
|---|---|---|
| トリガー | パイプラインの起動 | EventBridge |
| オーケストレーション | ワークフロー管理 | Step Functions |
| 実行 | テストの実施 | Bedrock API 直接呼び出し + Lambda（集計） |

設計のポイント：
- Step Functions から Bedrock `InvokeModel` を **SDK統合で直接呼び出し**（Lambda 不要）
- テスト結果の集計ロジックのみ Lambda を使用
- CloudWatch メトリクス送信・SNS アラートも Step Functions から直接実行

### ステップ 5.2: CloudFormation でパイプラインをデプロイ

```bash
cd ~/handson/M09-testing-validation

# スタックをデプロイ（メール通知が不要な場合は AlertEmail を空にする）
aws cloudformation deploy \
  --template-file evaluation-pipeline-cfn.yaml \
  --stack-name ai-evaluation-pipeline \
  --parameter-overrides \
    ModelId=amazon.nova-lite-v1:0 \
    AlertEmail="" \
    EvalPassThreshold=3.0 \
  --capabilities CAPABILITY_NAMED_IAM

# デプロイ確認
aws cloudformation describe-stacks \
  --stack-name ai-evaluation-pipeline \
  --query "Stacks[0].Outputs" \
  --output table
```

### ステップ 5.3: ステートマシンの手動実行

Step Functions コンソール、または CLI からテスト実行：

```bash
# ステートマシンのARNを取得
SM_ARN=$(aws cloudformation describe-stacks \
  --stack-name ai-evaluation-pipeline \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
  --output text)

# 実行（入力は EventBridge ルールに設定済みのものと同じ）
aws stepfunctions start-execution \
  --state-machine-arn $SM_ARN \
  --input file://evaluation-pipeline-input.json
```

実行フロー：
```
Parallel（4テスト並列実行）
  ├── AccuracyTests  → Bedrock InvokeModel × 3
  ├── BiasTests      → Bedrock InvokeModel × 3
  ├── SafetyTests    → Bedrock InvokeModel × 3
  └── CustomTests    → Bedrock InvokeModel × 3
        ↓
AggregateResults（Lambda: 集計・スコア算出）
        ↓
CheckThreshold（Choice: 合格/不合格）
  ├── 不合格 → PublishAlert（SNS通知）→ PublishMetrics
  └── 合格   → PublishMetrics（CloudWatch メトリクス送信）
        ↓
PipelineComplete
```

### ステップ 5.4: テスト結果の確認

```bash
# 最新の実行結果を確認
EXEC_ARN=$(aws stepfunctions list-executions \
  --state-machine-arn $SM_ARN \
  --max-results 1 \
  --query "executions[0].executionArn" \
  --output text)

aws stepfunctions describe-execution \
  --execution-arn $EXEC_ARN \
  --query "output" \
  --output text | python3.12 -m json.tool
```

### ステップ 5.5: ローカルでのパイプラインシミュレーション

CFnデプロイなしでパイプラインの動作を確認したい場合：

```bash
python3.12 automated_evaluation_pipeline.py
```

### ステップ 5.6: CloudWatch モニタリングとアラート

パイプラインが送信するメトリクス：
- `Custom/AIEvaluation/OverallScore` — 総合スコア

しきい値違反時のアラートフロー：
- `all_passed = false` → SNS トピックにアラート発行
- メール通知先を設定済みの場合は自動通知

---

## パート 6: 古典的メトリクス BLEU / ROUGE（10分）

### ステップ 6.1: BLEU スコア

```bash
python3.12 bleu_rouge_evaluation.py
```

BLEU（Bilingual Evaluation Understudy）:
- 機械翻訳のために開発された**精度ベース**のメトリクス
- 生成文の n-gram が参照文にどれだけ含まれるかを測定
- 1-gram〜4-gram 精度の幾何平均 + 短文ペナルティ（BP）

### ステップ 6.2: ROUGE スコア

ROUGE（Recall-Oriented Understudy for Gisting Evaluation）:
- 要約タスクのために開発された**再現率ベース**のメトリクス
- 参照文の n-gram が生成文にどれだけ含まれるかを測定

| メトリクス | 内容 |
|---|---|
| ROUGE-1 | unigram（単語レベル）の F1 |
| ROUGE-2 | bigram（フレーズレベル）の F1 |
| ROUGE-L | 最長共通部分列（LCS）ベースの F1 |

### ステップ 6.3: Bedrock モデル出力の評価

evaluation-dataset.jsonl の参照回答と、モデル生成回答を比較し BLEU/ROUGE を算出。

### ステップ 6.4: LLM-as-Judge との使い分け

| 観点 | BLEU/ROUGE | LLM-as-Judge |
|---|---|---|
| 評価の性質 | 表層的（n-gram一致） | 意味的（内容理解） |
| 計算コスト | 低い（ルールベース） | 高い（API呼出し） |
| 再現性 | 完全に再現可能 | ブレあり |
| 言い換え対応 | 弱い | 強い |
| 適したタスク | 翻訳、要約、定型応答 | QA、対話、創造的生成 |

推奨: CI/CD の高速チェックには BLEU/ROUGE、リリース前のゲートには LLM-as-Judge。両者を併用し乖離があれば人間レビュー。

---

## デモ手順

### デモ 1: LLM-as-Judge 評価（5分）
1. テスト質問セットを実行
2. 審査員 LLM が各回答を自動評価
3. スコアダッシュボードを表示
4. 低スコアの回答を分析

### デモ 2: A/B テスト結果（5分）
1. 2つのプロンプトバリアントの結果を比較
2. 統計的有意差を示す
3. 勝者バリアントの自動デプロイを説明

---

## クリーンアップ

```bash
cd ~/handson
./cleanup_all.sh
```

全モジュール（M01-M10）のリソースを一括削除します。存在しないリソースは自動スキップされます。

---

## 発展課題

1. **自動評価パイプライン**: Step Functions で定期的に評価を実行する仕組み
2. **レグレッションテスト**: モデル更新時に品質が低下しないことを保証する
3. **ユーザーフィードバック統合**: 実ユーザーの評価を学習に反映するループ
