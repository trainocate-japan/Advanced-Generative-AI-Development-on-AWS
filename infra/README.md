# デモ環境インフラストラクチャ

## 概要

Session Manager 経由で接続する EC2 デモ環境。SSH キー不要。
ハンズオン資材は S3 バケットに保管し、EC2 起動時に自動ダウンロード。

## デプロイ手順

### Step 1: 資材を S3 にアップロード

```bash
chmod +x infra/upload-assets.sh
./infra/upload-assets.sh
```

### Step 2: CloudFormation スタックの作成

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws cloudformation create-stack \
  --stack-name handson-demo-env \
  --template-body file://infra/demo-ec2.yaml \
  --parameters \
    ParameterKey=AssetsBucket,ParameterValue=handson-demo-assets-$ACCOUNT_ID \
    ParameterKey=AssetsPrefix,ParameterValue=handson-assets \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### Step 3: 完了を待機

```bash
aws cloudformation wait stack-create-complete --stack-name handson-demo-env
```

### Step 4: Session Manager で接続

```bash
# インスタンス ID を取得
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name handson-demo-env \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
  --output text)

# 接続
aws ssm start-session --target $INSTANCE_ID

# 接続後
sudo su - ec2-user
./run-demo.sh
```

### Step 5: Bedrock モデルアクセスを有効化

AWS コンソール → Bedrock → Model access で以下を有効化:
- Amazon Nova Lite / Pro
- Amazon Titan Text Embeddings V2
- (任意) Anthropic Claude 3.5 Sonnet / Haiku

## 運用フロー

```
初回:   upload-assets.sh → CFn create-stack → Bedrock有効化
前日:   aws ec2 start-instances --instance-ids <ID>
当日:   aws ssm start-session → ./run-demo.sh M01
夜間:   23:00 JST に自動停止（Lambda）
更新時: upload-assets.sh → EC2再起動（UserData再実行はしない。手動でS3から再取得）
```

## 資材の更新方法

ハンズオン内容を更新した場合:

```bash
# 1. S3 に最新版をアップロード
./infra/upload-assets.sh

# 2. EC2 内で再取得
aws ssm start-session --target <INSTANCE_ID>
sudo su - ec2-user
aws s3 cp s3://handson-demo-assets-<ACCOUNT_ID>/handson-assets/handson.tar.gz /tmp/
rm -rf ~/handson
mkdir ~/handson
tar -xzf /tmp/handson.tar.gz -C ~/handson --strip-components=1
```

## コスト見積もり

| リソース | 月間コスト（研修時のみ起動） |
|---------|--------------------------|
| EC2 t3.medium（1日8時間×5日） | ~$7 |
| EBS 30GB gp3 | ~$2.40 |
| S3（資材保管） | < $0.10 |
| Lambda（自動停止） | < $0.01 |
| Bedrock（デモ実行） | $1-5/研修回 |
| **合計** | **~$10-15/月** |

## クリーンアップ

```bash
# スタック削除
aws cloudformation delete-stack --stack-name handson-demo-env

# S3 バケット削除
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 rb s3://handson-demo-assets-$ACCOUNT_ID --force
aws s3 rb s3://legal-kb-demo-$ACCOUNT_ID --force
```
