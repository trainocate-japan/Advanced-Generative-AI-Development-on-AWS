# モジュール 3: ベクトルデータベースと検索拡張（RAG） - ハンズオンシナリオ

## シナリオ概要

あなたは大手法律事務所のテクニカルリードです。数万件の法律文書（判例、契約書テンプレート、規制ガイドライン）を管理するナレッジベースシステムを構築し、弁護士が自然言語で質問すると関連文書を検索・要約して回答する「リーガルアシスタント」を実装します。

要件：
- Amazon Bedrock ナレッジベースによる RAG 実装
- **Amazon S3 Vectors** をベクトルストアとして使用（コスト効率・スケーラビリティ重視）
- 法律文書に適したチャンキング戦略の選定と最適化
- セマンティック検索による高品質な文書検索
- RAGAS フレームワークによる検索品質の定量評価
- アクセス制御付きの会話型ナレッジアシスタント

> **Note**: ハイブリッド検索（BM25 + ベクトル）は S3 Vectors では非対応のため、
> `M03-opensearch-vectorsearch/` ハンズオンで OpenSearch Serverless を使って体験します。

## 学習目標

このハンズオンを完了すると、以下ができるようになります：

1. **ベクトルDB設計**: Amazon S3 Vectors + Bedrock ナレッジベースのセットアップと最適化
2. **チャンキング戦略**: ドキュメントタイプに応じた適応型チャンキングの実装と比較評価
3. **セマンティック検索**: Retrieve API / RetrieveAndGenerate API による高品質検索
4. **RAGAS 評価**: RAG システムの品質を4指標で定量評価し、改善サイクルを回す
5. **会話型アシスタント**: コンテキスト管理 + アクセス制御付きのナレッジアシスタント構築

## アーキテクチャ

```
┌──────────────┐     ┌───────────────────┐     ┌──────────────────┐
│  Documents   │────▶│ Chunking Pipeline │────▶│  Amazon S3       │
│  (S3)        │     │ (Bedrock KB)      │     │  Vectors         │
└──────────────┘     └───────────────────┘     └────────┬─────────┘
                             │                           │
                    ┌────────▼────────┐                  │
                    │ Titan Embeddings│                  │
                    │ V2 (1024次元)   │                  │
                    └─────────────────┘                  │
                                                         │
┌──────────────┐     ┌───────────────────┐              │
│    User      │────▶│ Knowledge         │◀─────────────┘
│   Query      │     │ Assistant         │
└──────────────┘     └───────┬───────────┘
                             │
                      ┌──────▼───────┐
                      │   Amazon     │
                      │   Nova Pro   │
                      │  (生成モデル) │
                      └──────────────┘
```

**データフロー：**
1. ドキュメントを S3 にアップロード
2. Bedrock KB がチャンキング + 埋め込み生成
3. ベクトルを S3 Vectors に保存
4. ユーザーのクエリをベクトル化して類似度検索
5. 検索結果をコンテキストとして生成モデルに送信
6. 引用付きの回答を生成

## 使用する AWS サービス

| サービス | 用途 |
|---------|------|
| Amazon Bedrock ナレッジベース | RAG オーケストレーション（RetrieveAndGenerate / Retrieve API） |
| Amazon S3 Vectors | ベクトルストア（コスト効率、20億ベクトルスケール） |
| Amazon S3 | ドキュメントストレージ |
| Amazon Bedrock（Titan Embeddings V2） | 埋め込みモデル（1024次元） |
| Amazon Bedrock（Amazon Nova Pro） | 生成モデル（回答生成） |
| Amazon Bedrock（Amazon Nova Lite） | 評価用モデル（RAGAS 判定） |

## ファイル構成

```
M03-rag-knowledgebase/
├── scenario.md                 # このファイル（シナリオ説明）
├── steps.md                    # ハンズオン手順
├── setup_knowledgebase.py      # ナレッジベースセットアップ（S3 Vectors）
├── rag_basic.py                # RAG 基本実装（RetrieveAndGenerate）
├── rag_retrieve.py             # Retrieve API 詳細確認
├── knowledge_assistant.py      # 会話型アシスタント + アクセス制御
├── rag_evaluation.py           # RAGAS 評価（LLM-as-a-Judge）
├── chunking_optimization.py    # チャンキング最適化・比較
├── cleanup.py                  # リソースクリーンアップ
├── kb_config.json              # セットアップ後に生成される設定
└── sample-docs/                # サンプル法律文書
    ├── contract_template.txt
    ├── privacy_regulation.txt
    └── employment_law.txt
```

## 所要時間

約 60-80 分（RAGAS 評価・チャンキング最適化の詳細解説を含む）

| パート | 内容 | 時間 |
|--------|------|------|
| パート 1 | ナレッジベースのセットアップ | 20分 |
| パート 2 | 検索の実装と最適化 | 20分 |
| パート 3 | 会話型ナレッジアシスタント | 15分 |
| パート 4 | RAGAS 評価 | 15分 |
| パート 5 | チャンキング最適化 | 10分 |

## 前提条件

- AWS CLI 設定済み
- Python 3.12+
- boto3 最新版（S3 Vectors 対応）
- Amazon Bedrock で以下のモデルアクセス有効化済み：
  - Amazon Titan Embeddings V2
  - Amazon Nova Pro
  - Amazon Nova Lite
- Amazon Bedrock ナレッジベースの作成権限
- S3 Vectors の操作権限（`s3vectors:*`）
