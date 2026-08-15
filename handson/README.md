# Advanced Generative AI Development on AWS - ハンズオンガイド

## コース概要

このハンズオンガイドは「Advanced Generative AI Development on AWS」研修コースの各モジュールに対応した実践的なシナリオと手順を提供します。各ハンズオンで作成したリソースやソリューションは、研修中のデモとして受講者に見せることができます。

## コースの日程構成

### 1日目
| モジュール | テーマ | ハンズオン時間 |
|-----------|--------|--------------|
| M01 | 基盤モデルの選択と設定（動的ルーティング・レジリエンス・コスト最適化） | 45分 |
| M02 | 基盤モデルの高度なデータ処理（検証・マルチモーダル・入力最適化） | 45分 |
| M03 | ベクトルデータベースと検索拡張（RAG・チャンキング・ハイブリッド検索） | 60分 |
| ラボ1 | Amazon Bedrock ナレッジベースを使用した RAG アプリケーション | - |

### 2日目
| モジュール | テーマ | ハンズオン時間 |
|-----------|--------|--------------|
| M04 | プロンプトエンジニアリングとガバナンス（CoT・プロンプトフロー・管理） | 45分 |
| ラボ2 | Amazon Bedrock API を使用した会話パターンの開発 | - |
| M05 | Amazon Bedrock AgentCore（エージェントフレームワーク・デプロイ・運用） | 60分 |
| M06 | AI の安全性とセキュリティ（Guardrails・PII保護・ゼロトラスト） | 45分 |

### 3日目
| モジュール | テーマ | ハンズオン時間 |
|-----------|--------|--------------|
| ラボ3 | Amazon Bedrock ガードレールによる安全で責任ある生成 AI の構築 | - |
| M07 | パフォーマンスの最適化とコスト管理（キャッシング・バッチ処理・スケーリング） | 45分 |
| M08 | 生成 AI のモニタリングとオブザーバビリティ（トークン追跡・品質測定・診断） | 45分 |
| M09 | テスト、検証、継続的な改善（評価フレームワーク・RAGAS・A/Bテスト） | 45分 |
| M10 | エンタープライズ統合パターン（API統合・セキュアアクセス・CI/CD） | 60分 |
| M11 | コースのまとめ | - |

## 前提条件

### 環境要件
- AWS アカウント（管理者アクセス）
- AWS CLI v2 設定済み
- Python 3.12+
- Node.js 18+
- AWS CDK / SAM CLI インストール済み
- Amazon Bedrock モデルアクセス有効化済み
  - Amazon Nova Lite / Pro
  - Amazon Titan Embeddings V2
  - Anthropic Claude Sonnet 4.5 / Haiku
  - Meta Llama 3

### リージョン
- 推奨: `us-east-1`（バージニア北部）または `us-west-2`（オレゴン）
- Bedrock の全機能が利用可能なリージョンを選択してください

## フォルダ構造

```
handson/
├── README.md                       # このファイル
├── run-demo.sh                     # デモ実行ヘルパー
├── M01-model-selection/            # 基盤モデルの選択と設定
│   ├── scenario.md                 # シナリオ説明
│   ├── steps.md                    # ハンズオン手順
│   ├── benchmark.py                # モデルベンチマーク比較
│   ├── template.yaml               # SAM テンプレート
│   └── lambda/router.py            # 動的ルーティング Lambda
├── M02-bedrock-converse-api/       # 高度なデータ処理
│   ├── scenario.md
│   ├── steps.md
│   ├── data_validation.py          # データ検証・PII検出
│   ├── multimodal_processing.py    # マルチモーダル処理
│   └── context_optimization.py     # コンテキスト最適化
├── M03-rag-knowledgebase/          # ベクトルDB と RAG
│   ├── scenario.md
│   ├── steps.md
│   ├── setup_knowledgebase.py      # ナレッジベースセットアップ
│   ├── rag_basic.py                # RAG基本実装
│   ├── rag_retrieve.py             # RAG検索
│   ├── chunking_optimization.py    # チャンキング最適化
│   ├── rag_evaluation.py           # RAG評価
│   ├── knowledge_assistant.py      # 会話型ナレッジアシスタント
│   └── sample-docs/                # サンプル法律文書
├── M03-opensearch-vectorsearch/    # OpenSearch ベクトル検索（補足）
│   ├── scenario.md
│   ├── steps.md
│   ├── setup_opensearch.py         # OpenSearch セットアップ
│   ├── vector_search.py            # ベクトル検索
│   ├── hybrid_search.py            # ハイブリッド検索
│   └── custom_scoring.py           # カスタムスコアリング
├── M04-prompt-engineering/         # プロンプトエンジニアリング
│   ├── scenario.md
│   ├── steps.md
│   ├── prompt_personas.py          # ペルソナ設計
│   ├── chain_of_thought.py         # 思考連鎖推論
│   └── prompt_flow_demo.py         # プロンプトフロー
├── M05-agentcore/                  # AgentCore エージェント
│   ├── scenario.md
│   ├── steps.md
│   └── travel_agent.py             # 旅行プランニングエージェント
├── M06-safety-guardrails/          # AI安全性・Guardrails
│   ├── scenario.md
│   └── steps.md
├── M07-cost-optimization/          # パフォーマンス・コスト管理
│   ├── scenario.md
│   └── steps.md
├── M08-monitoring/                 # モニタリング・オブザーバビリティ
│   ├── scenario.md
│   └── steps.md
├── M09-testing-validation/         # テスト・検証・継続改善
│   ├── scenario.md
│   ├── steps.md
│   └── evaluation-dataset.jsonl    # 評価データセット
├── M10-enterprise-integration/     # エンタープライズ統合
│   ├── scenario.md
│   └── steps.md
└── M11-serverless-webapp/          # サーバーレス Web アプリ
    ├── scenario.md
    └── steps.md
```

## 使い方

1. 各モジュールフォルダ内の `scenario.md` でシナリオと学習目標を確認
2. `steps.md` の手順に従ってハンズオンを実施
3. Python スクリプトがある場合は実行してデモ動作を確認
4. 終了後は下記クリーンアップ手順に従ってリソースを削除

## クリーンアップ

全モジュールで作成したリソースを一括で削除するスクリプトを用意しています。

### EC2 ハンズオン環境での実行

```bash
cd ~/handson
bash cleanup_all.sh
```

### 対象リソース一覧

| モジュール | 削除対象 |
|-----------|---------|
| M01 | CloudFormation スタック (`m01`)、Bedrock 評価ジョブ (`m01-*`) |
| M02 | CloudFormation スタック (`data-processing-demo`, `stepfunctions-pipeline-demo`, `glue-data-quality-demo`) |
| M03 | Knowledge Base、S3 Vectors、S3 バケット、IAM ロール、OpenSearch Serverless コレクション + ポリシー、RAG 評価ジョブ |
| M04 | Bedrock マネージドプロンプト (`customer-support-persona-v1`, `CustomerSupport-*`) |
| M05 | AgentCore リソース (Gateway/Memory/Identity/Runtime)、CloudFormation スタック、ロググループ、IAM ロール、S3 バケット |
| M06 | Bedrock Guardrail (`health-chatbot-guardrail`) |
| M07 | ローカル実行のみ（AWS リソースなし） |
| M08 | CloudWatch アラーム・ダッシュボード・Anomaly Detectors、SNS トピック、ロググループ、S3 バケット、IAM ロール (`BedrockLoggingRole`)、モデル呼び出しログ設定 |
| M09 | CloudFormation スタック (`ai-evaluation-pipeline`) |
| M10 | CloudFormation スタック (3環境 + VPC Endpoint)、DynamoDB テーブル |

### 注意事項

- スクリプトは冪等です（リソースが存在しなければスキップします）
- CloudFormation スタックの削除完了まで待機します
- 実行前に `aws sts get-caller-identity` で正しいアカウントか確認してください

## コスト管理

- 各ハンズオンの推定コスト: $1〜$5
- 使用後は必ずリソースを削除してください
- AWS Cost Explorer でコストを監視することを推奨します
- Bedrock のモデル呼び出しコストが主な費用です（Nova Lite は特に安価）

## トラブルシューティング

### Bedrock モデルアクセスエラー
```
AccessDeniedException: You don't have access to the model
```
→ AWS コンソール → Bedrock → Model access で該当モデルを有効化

### リージョン未対応エラー
→ `us-east-1` または `us-west-2` に変更してください

### トークン上限エラー
→ `maxTokens` パラメータを減らすか、入力プロンプトを短縮
