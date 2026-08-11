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
tar -czf "$ARCHIVE_PATH" -C "$REPO_ROOT" handson/
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
echo " 完了!"
echo "=============================================="
echo ""
echo " S3 パス: s3://$BUCKET_NAME/$PREFIX/handson.tar.gz"
echo ""
echo " 次のステップ: CloudFormation スタックの作成"
echo ""
echo " aws cloudformation create-stack \\"
echo "   --stack-name handson-demo-env \\"
echo "   --template-body file://infra/demo-ec2.yaml \\"
echo "   --parameters \\"
echo "     ParameterKey=AssetsBucket,ParameterValue=$BUCKET_NAME \\"
echo "     ParameterKey=AssetsPrefix,ParameterValue=$PREFIX \\"
echo "   --capabilities CAPABILITY_NAMED_IAM \\"
echo "   --region $REGION"
echo ""
echo " 接続方法（スタック作成完了後）:"
echo "   aws ssm start-session --target <INSTANCE_ID> --region $REGION"
echo ""
