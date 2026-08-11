# モジュール 5: Amazon Bedrock AgentCore によるエージェンティック AI - ハンズオンシナリオ

## シナリオ概要

あなたは旅行会社のAIエンジニアです。顧客からの旅行プラン相談に対し、フライト検索、ホテル予約、現地アクティビティ提案を自律的に実行する「旅行プランニングエージェント」を構築します。

Strands Agents フレームワークを使用してエージェントを構築し、Amazon Bedrock AgentCore を使用して本番環境に安全にデプロイします。

要件：
- ツール呼び出し（フライト検索、ホテル検索、天気情報）を自律的に実行
- メモリ管理による会話コンテキストの保持
- AgentCore Runtime によるサーバーレスデプロイ
- AgentCore Identity によるセキュアなアクセス制御

## 学習目標

このハンズオンを完了すると、以下ができるようになります：

1. **エージェント設計**: ツール定義、メモリ管理を含むエージェントを設計する
2. **フレームワーク比較**: Strands Agents / LangGraph / CrewAI の違いを理解する
3. **AgentCore 活用**: Runtime、Gateway、Memory、Identity の機能を把握する
4. **本番デプロイ**: プロトタイプから本番環境へのギャップを理解し対策する

## アーキテクチャ

```
┌──────────────────────────────────────────────────────────┐
│                 Amazon Bedrock AgentCore                   │
│                                                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │
│  │  Runtime   │  │  Gateway   │  │     Identity       │  │
│  │(Serverless)│  │(Tool Disc.)│  │(Access Control)    │  │
│  └─────┬──────┘  └─────┬──────┘  └────────────────────┘  │
│        │                │                                  │
│  ┌─────▼──────┐  ┌─────▼──────────────────────────────┐  │
│  │   Memory   │  │          Tool Registry              │  │
│  │(Context)   │  │  ┌────────┐┌────────┐┌──────────┐  │  │
│  └────────────┘  │  │Flight  ││Hotel   ││Weather   │  │  │
│                   │  │Search  ││Search  ││API       │  │  │
│                   │  └────────┘└────────┘└──────────┘  │  │
│                   └────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐
│  Observability   │
│  & Evaluations   │
└──────────────────┘
```

## 使用する AWS サービス

- Amazon Bedrock AgentCore（Runtime、Gateway、Memory、Identity）
- Amazon Bedrock（基盤モデル: Nova Pro）
- AWS Lambda（ツール実装）
- Amazon DynamoDB（メモリストア）

## 所要時間

約 60 分

## 前提条件

- AWS CLI 設定済み
- Python 3.12+
- Amazon Bedrock で Nova Pro のアクセス有効化済み
- pip install strands-agents strands-agents-tools
