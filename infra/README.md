# デモ環境インフラストラクチャ

## 概要

研修で使用するハンズオンデモ環境を EC2 上に構築するための CloudFormation テンプレートとセットアップスクリプトです。

## 構成

```
infra/
├── README.md              # このファイル
├── demo-ec2.yaml          # CloudFormation テンプレート
└── setup-demo-env.sh      # EC2 内部のセットアップスクリプト
```

## 運用フロー

```
┌─────────────────────────────────────────────────────────────┐
│  初回のみ                                                    │
│  1. CloudFormation でスタック作成                             │
│  2. EC2 が自動的にセットアップ（UserData）                   │
│  3. Bedrock モデルアクセスを有効化（コンソール）              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  研修前日                                                    │
│  1. aws ec2 start-instances でインスタンス起動               │
│  2. SSH で接続して動作確認                                   │
│  3. 必要に応じて git pull で最新コードを取得                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  研修当日                                                    │
│  1. SSH で接続                                               │
│  2. ./run-demo.sh で各モジュールのデモを実行                 │
│  3. 必要に応じて AWS コンソールも併用                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  研修後（自動）                                              │
│  - 毎日 23:00 JST にインスタンスが自動停止                   │
│  - 手動停止: aws ec2 stop-instances                          │
└─────────────────────────────────────────────────────────────┘
```

## デプロイ手順

### 1. スタックの作成

```bash
aws cloudformation create-stack \
  --stack-name handson-demo-env \
  --template-body file://infra/demo-ec2.yaml \
  --parameters \
    ParameterKey=KeyPairName,ParameterValue=YOUR_KEY_PAIR \
    ParameterKey=AllowedSSHCidr,ParameterValue=YOUR_IP/32 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### 2. スタック作成完了を待機

```bash
aws cloudformation wait stack-create-complete --stack-name handson-demo-env
```

### 3. 接続情報の確認

```bash
aws cloudformation describe-stacks --stack-name handson-demo-env \
  --query "Stacks[0].Outputs" --output table
```

### 4. SSH 接続

```bash
ssh -i YOUR_KEY_PAIR.pem ec2-user@<PublicIP>
```

### 5. セットアップ完了の確認

```bash
# UserData のログを確認
cat /var/log/user-data.log

# デモヘルパーの確認
./run-demo.sh all
```

## Bedrock モデルアクセスの有効化

EC2 のセットアップ後、AWS コンソールで以下のモデルを有効化してください：

1. AWS コンソール → Amazon Bedrock → Model access
2. 以下のモデルを有効化：
   - Amazon Nova Lite
   - Amazon Nova Pro
   - Amazon Titan Text Embeddings V2
   - Anthropic Claude 3.5 Sonnet（オプション）
   - Anthropic Claude 3 Haiku（オプション）

## デモの実行

```bash
# インタラクティブメニュー
./run-demo.sh

# 直接指定
./run-demo.sh M01    # モデルベンチマーク
./run-demo.sh M04    # プロンプトエンジニアリング
./run-demo.sh M05    # エージェント
```

## コスト

| リソース | 月間コスト（停止運用時） |
|---------|----------------------|
| EC2 t3.medium（1日8時間×5日/月） | ~$7 |
| EBS 30GB gp3 | ~$2.40 |
| Lambda (自動停止) | < $0.01 |
| Bedrock (デモ実行時) | $1-5/研修回 |
| **合計** | **~$10-15/月** |

※ 常時起動の場合: ~$30/月

## インスタンスの起動/停止

```bash
# 起動（研修前日）
aws ec2 start-instances --instance-ids <INSTANCE_ID>

# 停止（研修後 or 手動）
aws ec2 stop-instances --instance-ids <INSTANCE_ID>

# ステータス確認
aws ec2 describe-instances --instance-ids <INSTANCE_ID> \
  --query "Reservations[0].Instances[0].State.Name" --output text
```

## トラブルシューティング

### EC2 に SSH できない
- セキュリティグループの CIDR を確認（`AllowedSSHCidr`）
- インスタンスが `running` 状態か確認
- パブリック IP が変わっている可能性（停止/起動で変わる）

### Bedrock API エラー
- モデルアクセスが有効化されているか確認
- IAM ロールに `AmazonBedrockFullAccess` が付いているか確認
- リージョンが Bedrock 対応リージョンか確認

### UserData が完了しない
```bash
# ログを確認
sudo cat /var/log/user-data.log
```

## クリーンアップ

```bash
# 全リソースを削除
aws cloudformation delete-stack --stack-name handson-demo-env

# S3 バケットは別途削除（中身がある場合）
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 rb s3://legal-kb-demo-$ACCOUNT_ID --force
```
