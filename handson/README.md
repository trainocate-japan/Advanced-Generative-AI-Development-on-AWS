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
├── M03-data-automation/            # ベクトルDB と RAG
│   ├── scenario.md
│   ├── steps.md
│   ├── setup_knowledgebase.py      # ナレッジベースセットアップ
│   ├── rag_basic.py                # RAG基本実装
│   └── sample-docs/                # サンプル法律文書
├── M04-performance/                # プロンプトエンジニアリング
│   ├── scenario.md
│   ├── steps.md
│   └── prompt_personas.py          # ペルソナ・CoT・フロー
├── M05-prompt-management/          # AgentCore
│   ├── scenario.md
│   ├── steps.md
│   └── travel_agent.py             # 旅行プランニングエージェント
├── M06-prompt-caching/             # AI安全性・Guardrails
│   ├── scenario.md
│   └── steps.md
├── M07-guardrails/                 # パフォーマンス・コスト管理
│   ├── scenario.md
│   └── steps.md
├── M08-monitoring/                 # モニタリング・オブザーバビリティ
│   ├── scenario.md
│   └── steps.md
├── M09-agents/                     # テスト・検証・継続改善
│   ├── scenario.md
│   └── steps.md
└── M10-rag-knowledgebase/          # エンタープライズ統合
    ├── scenario.md
    └── steps.md
```

## 使い方

1. 各モジュールフォルダ内の `scenario.md` でシナリオと学習目標を確認
2. `steps.md` の手順に従ってハンズオンを実施
3. Python スクリプトがある場合は実行してデモ動作を確認
4. 各モジュールの「デモ手順」セクションで動作確認のポイントを把握
5. 終了後は各モジュールのクリーンアップ手順に従ってリソースを削除

## デモ手順について

各モジュールの `steps.md` には「デモ手順」セクションがあります。ハンズオンの主要な動作確認をまとめたものです：

1. **事前準備**: ハンズオン手順を一度実行し、動作確認済みの環境を準備
2. **デモ実行**: 「デモ手順」セクションに従い、ポイントを絞って動作を確認
3. **観察**: 各ステップで何が起きているかを確認・理解

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
