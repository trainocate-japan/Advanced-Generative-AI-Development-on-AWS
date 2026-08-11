# モジュール 10: エンタープライズ統合パターン - ハンズオン手順

## パート 1: API 統合パターン（20分）

### ステップ 1.1: REST API による AI サービス公開

```bash
cd ~/handson/M10-rag-knowledgebase
python3.12 enterprise_api_demo.py
```

API Gateway + Lambda + Bedrock のパターン：
```
外部システム → API Gateway → Lambda → Bedrock → レスポンス
              (認証・認可)   (ビジネスロジック)  (AI推論)
```

### ステップ 1.2: イベント駆動統合

EventBridge を使った非同期統合パターン：
```
ERP (注文作成) → EventBridge → Lambda → Bedrock (分析)
                                          ↓
                              DynamoDB (結果保存) → SNS (通知)
```

ユースケース：
- 新規注文の自動分類と優先度付け
- 顧客フィードバックのリアルタイム分析
- ドキュメント更新時の自動要約生成

### ステップ 1.3: WebSocket API（リアルタイム）

ストリーミング応答のための WebSocket 統合：
- チャットアプリケーションでのリアルタイム応答
- トークン単位でのストリーミング配信
- 接続管理とハートビート

---

## パート 2: セキュアアクセスと ID 管理（20分）

### ステップ 2.1: VPC エンドポイントによるプライベートアクセス

```bash
python3.12 vpc_endpoint_demo.py
```

Bedrock への VPC エンドポイント設定：
- パブリックインターネットを経由しない
- VPC 内からのみ Bedrock API にアクセス
- セキュリティグループによるアクセス制御

### ステップ 2.2: IAM フェデレーション

企業 IdP (Active Directory) との統合：
```
社員 → Corporate IdP → AWS STS (AssumeRoleWithSAML) → Bedrock API
```

ロールベースのモデルアクセス制御：
- 開発者: 開発環境のみ、Nova Lite のみ
- データサイエンティスト: 全モデルアクセス（開発/ステージング）
- 本番アプリ: 特定モデルのみ、レート制限付き

### ステップ 2.3: リソースポリシーと条件キー

```json
{
  "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": "arn:aws:bedrock:*:*:model/amazon.nova-*",
  "Condition": {
    "StringEquals": {"aws:PrincipalTag/Environment": "production"},
    "IpAddress": {"aws:SourceIp": "10.0.0.0/8"}
  }
}
```

---

## パート 3: マルチ環境デプロイ（15分）

### ステップ 3.1: CI/CD パイプライン設計

```
開発 → コードレビュー → テスト → ステージング → 承認 → 本番
  │                       │                          │
  └─ プロンプト変更 ───── └─ 自動評価 ────────────── └─ カナリアデプロイ
```

### ステップ 3.2: Infrastructure as Code

CDK/CloudFormation による環境別設定：
- 開発: 最小構成、低コストモデル
- ステージング: 本番相当、フル評価
- 本番: 高可用性、マルチAZ、自動スケーリング

### ステップ 3.3: プロンプトのバージョン管理

Git ベースのプロンプト管理：
```
prompts/
├── v1.0/
│   ├── support_persona.txt
│   └── sales_persona.txt
├── v1.1/
│   ├── support_persona.txt  # 改善版
│   └── sales_persona.txt
└── production.json  # 現在のデプロイバージョンを記録
```

---

## パート 4: ハイブリッドデプロイ（5分）

### ステップ 4.1: オンプレミス連携パターン

- **API ベース**: Direct Connect + VPC エンドポイント
- **データ同期**: S3 Transfer Family でオンプレデータをクラウドに同期
- **結果連携**: EventBridge でオンプレシステムに結果を返却

### ステップ 4.2: レイテンシー最適化

地理的に分散したユーザーへの対応：
- CloudFront でキャッシュ可能なレスポンスをエッジ配信
- リージョン別のエンドポイント配置
- Global Accelerator による最適ルーティング

---

## デモ手順

### デモ 1: API 統合（7分）
1. API Gateway のエンドポイントに curl でリクエスト送信
2. Lambda 経由で Bedrock が呼び出される流れを CloudWatch で追跡
3. 認証エラー時の動作（401）を確認
4. EventBridge イベントによる非同期処理フローを表示

### デモ 2: セキュリティ構成（5分）
1. VPC エンドポイント経由のアクセスを確認
2. 権限のないロールからのアクセス拒否を実演
3. CloudTrail で API 呼び出しの監査ログを表示

### デモ 3: CI/CD パイプライン（3分）
1. プロンプト変更をコミット
2. 自動テストが実行される流れを説明
3. 承認ゲート → 本番デプロイの流れ

---

## クリーンアップ

```bash
# 作成した AWS リソースを削除
aws cloudformation delete-stack --stack-name enterprise-ai-integration
```

---

## 発展課題

1. **マイクロサービス化**: 各 AI 機能を独立したサービスとして切り出す
2. **サービスメッシュ**: App Mesh によるサービス間通信の管理
3. **マルチリージョン**: アクティブ-アクティブのグローバルデプロイ設計
