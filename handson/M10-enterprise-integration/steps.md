# モジュール 10: エンタープライズ統合パターン - ハンズオン手順

## パート 1: API 統合パターン（20分）

### ステップ 1.1: REST API による AI サービス公開

CloudFormation テンプレートを使って API Gateway + Lambda + Bedrock の統合スタックをデプロイします。

```bash
cd ~/handson/M10-enterprise-integration

# テンプレートの内容を確認
cat cfn-enterprise-api.yaml

# スタックをデプロイ（開発環境）
aws cloudformation deploy \
  --template-file cfn-enterprise-api.yaml \
  --stack-name enterprise-ai-api-dev \
  --parameter-overrides Environment=dev ModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM

# デプロイ完了後、出力値を確認
aws cloudformation describe-stacks \
  --stack-name enterprise-ai-api-dev \
  --query "Stacks[0].Outputs" \
  --output table
```

テンプレートで構成されるアーキテクチャ：
```
外部システム → API Gateway (IAM認証, スロットリング) → Lambda → Bedrock → レスポンス
```

テンプレートのポイント：
- **IAM 認証** (`AuthorizationType: AWS_IAM`): API キーではなく IAM ベースの認証
- **環境別スロットリング**: `Mappings` で dev/staging/prod のレート制限を管理
- **Bedrock 最小権限**: Lambda ロールに特定モデルの `InvokeModel` のみ付与

### ステップ 1.2: API のテスト呼び出し

```bash
# API Gateway のテスト呼び出し（AWS CLI 経由）
API_ID=$(aws cloudformation describe-stacks \
  --stack-name enterprise-ai-api-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text | grep -oP '[a-z0-9]+(?=\.execute-api)')

RESOURCE_ID=$(aws apigateway get-resources \
  --rest-api-id $API_ID \
  --query "items[?pathPart=='invoke'].id" \
  --output text)

aws apigateway test-invoke-method \
  --rest-api-id $API_ID \
  --resource-id $RESOURCE_ID \
  --http-method POST \
  --body '{"message": "注文 #12345 の内容を要約してください"}'
```

### ステップ 1.3: イベント駆動統合

テンプレートに含まれる EventBridge ルールの確認：

```bash
# EventBridge ルールの確認
aws events describe-rule \
  --name enterprise-ai-api-dev-ai-processing

# テストイベントの送信
aws events put-events --entries '[
  {
    "Source": "enterprise.erp",
    "DetailType": "OrderCreated",
    "Detail": "{\"orderId\": \"ORD-2025-001\", \"customer\": \"Acme Corp\", \"amount\": 150000}"
  }
]'

# Lambda のログで処理結果を確認
aws logs tail /aws/lambda/enterprise-ai-api-dev-invoke-bedrock --since 1m
```

EventBridge を使った非同期統合パターン：
```
ERP (注文作成) → EventBridge → Lambda → Bedrock (分析)
                                          ↓
                              CloudWatch Logs (結果記録)
```

ユースケース：
- 新規注文の自動分類と優先度付け
- 顧客フィードバックのリアルタイム分析
- ドキュメント更新時の自動要約生成

### ステップ 1.4: WebSocket API（リアルタイム）

ストリーミング応答のための WebSocket 統合（概念説明）：
- チャットアプリケーションでのリアルタイム応答
- トークン単位でのストリーミング配信（`ConverseStream` API）
- 接続管理とハートビート

---

## パート 2: セキュアアクセスと ID 管理（20分）

### ステップ 2.1: VPC エンドポイントによるプライベートアクセス

CloudFormation テンプレートを使って VPC + Bedrock VPC エンドポイントをデプロイします。

```bash
# テンプレートの内容を確認
cat cfn-vpc-endpoint.yaml

# スタックをデプロイ
aws cloudformation deploy \
  --template-file cfn-vpc-endpoint.yaml \
  --stack-name bedrock-vpc-endpoint \
  --capabilities CAPABILITY_NAMED_IAM

# デプロイ完了後、出力値を確認
aws cloudformation describe-stacks \
  --stack-name bedrock-vpc-endpoint \
  --query "Stacks[0].Outputs" \
  --output table
```

テンプレートで構成されるアーキテクチャ：
```
[Lambda in Private Subnet]
  --> [ENI (Lambda SG: port 443 outbound)]
    --> [VPC Endpoint ENI (VPCE SG: port 443 inbound from VPC CIDR)]
      --> [Bedrock Runtime Service (via AWS PrivateLink)]

* インターネットゲートウェイ / NAT ゲートウェイ不要
* Private DNS 有効 → 通常の bedrock-runtime.{region}.amazonaws.com で自動ルーティング
```

テンプレートのポイント：
- **PrivateDnsEnabled: true**: コード変更不要で VPC Endpoint 経由にルーティング
- **エンドポイントポリシー**: 自アカウントからのアクセスのみ許可、操作も制限
- **セキュリティグループ**: VPC CIDR からの HTTPS (443) のみ許可

### ステップ 2.2: VPC 内 Lambda からの Bedrock 呼び出しテスト

```bash
# VPC 内 Lambda を呼び出してプライベートアクセスを確認
aws lambda invoke \
  --function-name bedrock-vpc-endpoint-private-bedrock \
  --payload '{}' \
  /tmp/vpc-lambda-response.json

cat /tmp/vpc-lambda-response.json | python3 -m json.tool
```

### ステップ 2.3: IAM フェデレーション

企業 IdP (Active Directory) との統合パターン：
```
社員 → Corporate IdP → AWS STS (AssumeRoleWithSAML) → Bedrock API
```

ロールベースのモデルアクセス制御：
- 開発者: 開発環境のみ、Nova Lite のみ
- データサイエンティスト: 全モデルアクセス（開発/ステージング）
- 本番アプリ: 特定モデルのみ、レート制限付き

### ステップ 2.4: リソースポリシーと条件キー

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

VPC エンドポイント経由のアクセスに限定する条件キー：
```json
{
  "Effect": "Deny",
  "Action": "bedrock:*",
  "Resource": "*",
  "Condition": {
    "StringNotEquals": {
      "aws:sourceVpce": "vpce-xxxxxxxxxxxxxxxxx"
    }
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

### ステップ 3.2: Infrastructure as Code（環境別デプロイ）

同じ CFn テンプレートを異なるパラメータで環境別にデプロイ：

```bash
# ステージング環境（スロットリング上限が異なる）
aws cloudformation deploy \
  --template-file cfn-enterprise-api.yaml \
  --stack-name enterprise-ai-api-staging \
  --parameter-overrides Environment=staging ModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM

# 本番環境（さらに高いスロットリング上限）
aws cloudformation deploy \
  --template-file cfn-enterprise-api.yaml \
  --stack-name enterprise-ai-api-prod \
  --parameter-overrides Environment=prod ModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM
```

環境別の設定値（テンプレート内 Mappings で管理）：
| 環境 | レートリミット | バーストリミット |
|------|--------------|----------------|
| dev | 10 req/s | 5 |
| staging | 50 req/s | 25 |
| prod | 200 req/s | 100 |

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

## パート 5: セマンティック競合解決（15分）

分散システムで同じデータに複数の書き込みが競合した場合、AI（Bedrock）がコンテンツの意味とビジネスルールに基づいて最適な解決策を決定するパターンを実装します。

### アーキテクチャ

```
[CRM システム]           → 顧客レコード更新
                              ↓ 競合検出
[カスタマーサポート]     → 顧客レコード更新
                              ↓
                    DynamoDB（両バージョンを保持）
                              ↓
                    Amazon Bedrock（セマンティック分析）
                              ↓
                    解決結果を書き戻し + 監査ログ
```

### 従来の方式との違い

| 方式 | 判断基準 | 問題点 |
|------|----------|--------|
| 最終書き込み者優先 | タイムスタンプ | 重要な情報が失われる |
| ベクトルクロック | 因果関係 | 意味的な矛盾を解決できない |
| **セマンティック解決** | **内容の意味 + ビジネスルール** | AI 呼び出しのコスト/レイテンシ |

### ステップ 5.1: 競合を発生させる

```bash
cd ~/handson/M10-enterprise-integration

# Part 1: テーブル作成 → 初期データ投入 → 競合発生
python conflict_simulate.py
```

実行すると以下が行われます：
1. DynamoDB テーブル `semantic-conflict-demo` を作成
2. 初期顧客レコード（田中太郎）を投入
3. CRM とカスタマーサポートから矛盾する更新が同時に発生
4. 競合状態として両バージョンを DynamoDB に保存（`status: unresolved`）

### ステップ 5.2: 競合状態を確認する

スクリプト実行後、DynamoDB 上で競合が保持されている状態を確認します。

```bash
# 全レコードを確認（メインレコード + 競合レコード）
aws dynamodb query \
  --table-name semantic-conflict-demo \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk": {"S": "CUSTOMER#C-1001"}}' \
  --output json | python3 -m json.tool
```

確認ポイント：
- **メインレコード** (`SK: PROFILE`): まだ更新されていない（ベースバージョンのまま）
- **競合レコード** (`SK: CONFLICT#...`): `status: unresolved`、両バージョンの変更内容が保持されている

```bash
# 競合レコードだけをフィルタして確認
aws dynamodb query \
  --table-name semantic-conflict-demo \
  --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \
  --expression-attribute-values '{":pk": {"S": "CUSTOMER#C-1001"}, ":sk": {"S": "CONFLICT#"}}' \
  --output json | python3 -m json.tool
```

この時点では AI による解決はまだ行われておらず、**矛盾する2つの更新が両方とも保持されている**ことがわかります。

### ステップ 5.3: Bedrock で競合を解決する

```bash
# Part 2: Bedrock がビジネスルールに基づいて競合を解決
python conflict_resolve.py
```

Bedrock が各フィールドについて：
- 更新 A（CRM）と更新 B（サポート）のどちらを採用するか判断
- ビジネスルールに基づく理由を提示
- 解決結果をメインレコードに反映

### ステップ 5.4: 解決後の状態を確認する

```bash
# メインレコード（解決後の状態）を確認
aws dynamodb get-item \
  --table-name semantic-conflict-demo \
  --key '{"PK": {"S": "CUSTOMER#C-1001"}, "SK": {"S": "PROFILE"}}' \
  --query "Item" \
  --output json | python3 -m json.tool

# 監査ログを確認（競合レコードに判断根拠が記録されている）
aws dynamodb query \
  --table-name semantic-conflict-demo \
  --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \
  --expression-attribute-values '{":pk": {"S": "CUSTOMER#C-1001"}, ":sk": {"S": "CONFLICT#"}}' \
  --output json | python3 -m json.tool
```

確認ポイント：
- メインレコードの `version` が 2 に更新されている
- `last_updated_by` が `semantic-resolution-ai` になっている
- 競合レコードの `status` が `resolved` に変わり、`resolution` フィールドに判断根拠が記録されている

### ステップ 5.5: ビジネスルールのカスタマイズ（オプション）

`conflict_resolve.py` 内の `BUSINESS_RULES` を変更して再実行すると、異なる解決結果が得られます：

```python
# 例: ルールを変更
BUSINESS_RULES = """
1. 連絡先情報: CRM システムの情報を常に優先する
2. 住所情報: 最新のタイムスタンプを優先する
...
"""
```

```bash
# テーブルを削除してやり直し
aws dynamodb delete-table --table-name semantic-conflict-demo
aws dynamodb wait table-not-exists --table-name semantic-conflict-demo

# 再度実行
python conflict_simulate.py
python conflict_resolve.py
```

### ポイント

- **両バージョン保持**: 競合検出時に即座に上書きせず、両方のバージョンを DynamoDB に保存
- **AI による意味的判断**: 「どちらが後か」ではなく「どちらが正しいか」を AI が判断
- **ビジネスルールの注入**: プロンプトにドメイン固有のルールを埋め込み、判断の一貫性を確保
- **追跡可能性**: 判断根拠を監査ログとして記録し、コンプライアンス要件に対応
- **冪等性**: 同じ競合を複数回解決しても結果が一貫する（temperature=0）

---

## デモ手順

### デモ 1: API 統合（7分）
1. CFn テンプレートの構造を説明（API Gateway + Lambda + Bedrock の関係）
2. スタックをデプロイし、Outputs からエンドポイント URL を取得
3. `test-invoke-method` で API を呼び出し、Bedrock の応答を確認
4. EventBridge にテストイベントを送信し、非同期処理フローを CloudWatch で追跡

### デモ 2: セキュリティ構成（5分）
1. VPC エンドポイントスタックのアーキテクチャを説明
2. VPC 内 Lambda を呼び出し、プライベートアクセスを実証
3. エンドポイントポリシーによるアクセス制限を説明
4. CloudTrail で API 呼び出しの監査ログを表示

### デモ 3: マルチ環境デプロイ（3分）
1. 同一テンプレートを `Environment` パラメータ違いでデプロイ
2. Mappings による環境別スロットリング設定の違いを説明
3. 承認ゲート → 本番デプロイの CI/CD パイプラインフローを説明

---

## クリーンアップ

```bash
cd ~/handson
./cleanup_all.sh
```

全モジュール（M01-M10）のリソースを一括削除します。存在しないリソースは自動スキップされます。

---

## 発展課題

1. **マイクロサービス化**: 各 AI 機能を独立したサービスとして切り出す
2. **サービスメッシュ**: App Mesh によるサービス間通信の管理
3. **マルチリージョン**: アクティブ-アクティブのグローバルデプロイ設計
