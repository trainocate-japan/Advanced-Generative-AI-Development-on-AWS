#!/bin/bash
# =============================================================================
# ハンズオン資材を S3 にアップロードするスクリプト
# CloudFormation デプロイ前に実行してください
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HANDSON_DIR="$REPO_ROOT/handson"

# デフォルト設定
REGION="${AWS_REGION:-us-east-1}"
PREFIX="handson-assets"
STACK_NAME="handson-demo-env"

# バケット名の生成
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="handson-demo-assets-${ACCOUNT_ID}"

echo "=============================================="
echo " ハンズオン資材 S3 アップロード"
echo "=============================================="
echo ""
echo "  リージョン: $REGION"
echo "  バケット: $BUCKET_NAME"
echo "  プレフィックス: $PREFIX"
echo "  ソース: $HANDSON_DIR"
echo ""

# ------------------------------------------
# 1. S3 バケットの作成（なければ）
# ------------------------------------------
echo "[1/3] S3 バケットを確認中..."
if aws s3 ls "s3://$BUCKET_NAME" 2>/dev/null; then
    echo "  ✅ バケット既存: $BUCKET_NAME"
else
    echo "  バケットを作成中..."
    if [ "$REGION" = "us-east-1" ]; then
        aws s3 mb "s3://$BUCKET_NAME"
    else
        aws s3 mb "s3://$BUCKET_NAME" --region "$REGION"
    fi
    echo "  ✅ バケット作成: $BUCKET_NAME"
fi

# ------------------------------------------
# 2. handson フォルダを tar.gz にアーカイブ
# ------------------------------------------
echo "[2/3] ハンズオン資材をアーカイブ中..."
ARCHIVE_PATH="/tmp/handson.tar.gz"

tar -czf "$ARCHIVE_PATH" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    -C "$REPO_ROOT" handson/

ARCHIVE_SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)
echo "  ✅ アーカイブ作成: $ARCHIVE_SIZE"

# ------------------------------------------
# 3. S3 にアップロード
# ------------------------------------------
echo "[3/3] S3 にアップロード中..."
aws s3 cp "$ARCHIVE_PATH" "s3://$BUCKET_NAME/$PREFIX/handson.tar.gz" --region "$REGION"
rm -f "$ARCHIVE_PATH"
echo "  ✅ アップロード完了"

# ------------------------------------------
# 結果表示
# ------------------------------------------
echo ""
echo "=============================================="
echo " S3 アップロード完了!"
echo "=============================================="
echo ""
echo " S3 パス: s3://$BUCKET_NAME/$PREFIX/handson.tar.gz"
echo ""

# ------------------------------------------
# 4. 起動中の EC2 インスタンスの資材を更新
# ------------------------------------------
INSTANCE_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
    --output text 2>/dev/null || echo "")

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
    echo "[4/4] EC2 インスタンスが見つかりません（スタック未作成または削除済み）"
    echo "  → スタック作成コマンド:"
    echo ""
    echo "  aws cloudformation create-stack \\"
    echo "    --stack-name $STACK_NAME \\"
    echo "    --template-body file://infra/demo-ec2.yaml \\"
    echo "    --parameters \\"
    echo "      ParameterKey=AssetsBucket,ParameterValue=$BUCKET_NAME \\"
    echo "      ParameterKey=AssetsPrefix,ParameterValue=$PREFIX \\"
    echo "    --capabilities CAPABILITY_NAMED_IAM \\"
    echo "    --region $REGION"
    echo ""
    exit 0
fi

# インスタンスの状態を確認
INSTANCE_STATE=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query "Reservations[0].Instances[0].State.Name" \
    --output text 2>/dev/null || echo "unknown")

echo "[4/4] EC2 インスタンスの資材を更新中..."
echo "  Instance ID: $INSTANCE_ID"
echo "  状態: $INSTANCE_STATE"

if [ "$INSTANCE_STATE" != "running" ]; then
    echo "  ⚠️  インスタンスが running ではないため、資材更新をスキップします"
    echo "  → インスタンス起動後に Session Manager で接続し以下を実行:"
    echo "    aws s3 cp s3://$BUCKET_NAME/$PREFIX/handson.tar.gz /tmp/handson.tar.gz"
    echo "    tar xzf /tmp/handson.tar.gz -C /home/ssm-user/ && rm /tmp/handson.tar.gz"
    exit 0
fi

# SSM Run Command で資材更新コマンドを送信
echo "  SSM Run Command で資材更新を送信中..."
COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[
        'WORK_DIR=/home/ssm-user/handson',
        'aws s3 cp s3://$BUCKET_NAME/$PREFIX/handson.tar.gz /tmp/handson.tar.gz',
        'rm -rf \$WORK_DIR',
        'mkdir -p \$WORK_DIR',
        'tar -xzf /tmp/handson.tar.gz -C \$WORK_DIR --strip-components=1',
        'chown -R ssm-user:ssm-user \$WORK_DIR',
        'rm -f /tmp/handson.tar.gz',
        'echo Done: \$(date)'
    ]" \
    --region "$REGION" \
    --query "Command.CommandId" \
    --output text 2>/dev/null || echo "")

if [ -z "$COMMAND_ID" ]; then
    echo "  ⚠️  SSM コマンドの送信に失敗しました"
    echo "  → 手動で更新する場合は Session Manager で接続後に以下を実行:"
    echo "    aws s3 cp s3://$BUCKET_NAME/$PREFIX/handson.tar.gz /tmp/handson.tar.gz"
    echo "    tar xzf /tmp/handson.tar.gz -C /home/ssm-user/ && rm /tmp/handson.tar.gz"
    exit 0
fi

echo "  Command ID: $COMMAND_ID"
echo "  コマンド完了を待機中..."

# 完了を待機（最大60秒）
aws ssm wait command-executed \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$REGION" 2>/dev/null

# 結果を確認
STATUS=$(aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$REGION" \
    --query "Status" \
    --output text 2>/dev/null || echo "Unknown")

if [ "$STATUS" = "Success" ]; then
    echo "  ✅ EC2 インスタンスの資材更新完了"
else
    echo "  ⚠️  資材更新ステータス: $STATUS"
    echo "  → 詳細: aws ssm get-command-invocation --command-id $COMMAND_ID --instance-id $INSTANCE_ID --region $REGION"
fi

echo ""
echo "=============================================="
echo " 全て完了!"
echo "=============================================="
echo ""
