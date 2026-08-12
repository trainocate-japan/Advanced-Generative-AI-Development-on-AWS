#!/bin/bash
# ============================================================================
# M01-M10 全リソースクリーンアップスクリプト
# なければスキップ、あれば削除
# ============================================================================
set -o pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)

if [ -z "$ACCOUNT_ID" ]; then
    echo "❌ AWS 認証情報が設定されていません"
    exit 1
fi

echo "=============================================="
echo "  ハンズオン全リソースクリーンアップ"
echo "  Account: $ACCOUNT_ID"
echo "  Region:  $REGION"
echo "=============================================="
echo ""

# --------------------------------------------------------------------------
# ヘルパー関数
# --------------------------------------------------------------------------

delete_cfn_stack() {
    local stack_name="$1"
    local status
    status=$(aws cloudformation describe-stacks --stack-name "$stack_name" \
        --query "Stacks[0].StackStatus" --output text 2>/dev/null)
    if [ $? -eq 0 ] && [ "$status" != "DELETE_COMPLETE" ]; then
        echo "  🗑  CloudFormation スタック削除: $stack_name (status: $status)"
        aws cloudformation delete-stack --stack-name "$stack_name" --region "$REGION"
        echo "     → 削除開始（バックグラウンドで進行）"
    else
        echo "  ⏭  スキップ (存在しない): $stack_name"
    fi
}

wait_cfn_stack() {
    local stack_name="$1"
    local status
    status=$(aws cloudformation describe-stacks --stack-name "$stack_name" \
        --query "Stacks[0].StackStatus" --output text 2>/dev/null)
    if [ $? -eq 0 ] && [ "$status" != "DELETE_COMPLETE" ]; then
        echo "     ⏳ $stack_name の削除完了を待機中..."
        aws cloudformation wait stack-delete-complete --stack-name "$stack_name" --region "$REGION" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "     ✅ $stack_name 削除完了"
        else
            echo "     ⚠️  $stack_name 削除に問題あり（手動確認してください）"
        fi
    fi
}

delete_s3_bucket() {
    local bucket="$1"
    if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
        echo "  🗑  S3 バケット削除: $bucket"
        aws s3 rb "s3://$bucket" --force 2>/dev/null
        echo "     ✅ 削除完了"
    else
        echo "  ⏭  スキップ (存在しない): s3://$bucket"
    fi
}

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M01: Model Selection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# SAM スタック
delete_cfn_stack "m01"

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M02: Data Processing"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

delete_cfn_stack "data-processing-demo"
delete_cfn_stack "stepfunctions-pipeline-demo"
delete_cfn_stack "glue-data-quality-demo"

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M03: RAG Knowledge Base"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ナレッジベース削除
KB_ID=$(aws bedrock-agent list-knowledge-bases --query \
    "knowledgeBaseSummaries[?name=='legal-knowledge-base-demo'].knowledgeBaseId | [0]" \
    --output text --region "$REGION" 2>/dev/null)

if [ -n "$KB_ID" ] && [ "$KB_ID" != "None" ]; then
    # データソース削除
    DS_IDS=$(aws bedrock-agent list-data-sources --knowledge-base-id "$KB_ID" \
        --query "dataSourceSummaries[].dataSourceId" --output text --region "$REGION" 2>/dev/null)
    for ds_id in $DS_IDS; do
        echo "  🗑  データソース削除: $ds_id"
        aws bedrock-agent delete-data-source --knowledge-base-id "$KB_ID" \
            --data-source-id "$ds_id" --region "$REGION" 2>/dev/null
    done
    echo "  🗑  ナレッジベース削除: $KB_ID"
    aws bedrock-agent delete-knowledge-base --knowledge-base-id "$KB_ID" --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): legal-knowledge-base-demo"
fi

# S3 Vectors
if aws s3vectors get-vector-bucket --vector-bucket-name legal-vectors-demo --region "$REGION" 2>/dev/null | grep -q "vectorBucketArn"; then
    echo "  🗑  S3 Vectors インデックス削除: legal-docs-index"
    aws s3vectors delete-index --vector-bucket-name legal-vectors-demo \
        --index-name legal-docs-index --region "$REGION" 2>/dev/null
    sleep 5
    echo "  🗑  S3 Vectors バケット削除: legal-vectors-demo"
    aws s3vectors delete-vector-bucket --vector-bucket-name legal-vectors-demo --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): legal-vectors-demo"
fi

# S3 バケット（ドキュメント）
delete_s3_bucket "legal-kb-demo-$ACCOUNT_ID"

# IAM ロール
if aws iam get-role --role-name AmazonBedrockKBRole-LegalDemo 2>/dev/null | grep -q "RoleName"; then
    echo "  🗑  IAM ロール削除: AmazonBedrockKBRole-LegalDemo"
    aws iam delete-role-policy --role-name AmazonBedrockKBRole-LegalDemo \
        --policy-name BedrockKBPolicy-S3Vectors 2>/dev/null
    aws iam delete-role --role-name AmazonBedrockKBRole-LegalDemo 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): AmazonBedrockKBRole-LegalDemo"
fi

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M04: Prompt Engineering"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Bedrock マネージドプロンプト（コンソールで手動作成された場合）
PROMPT_ID=$(aws bedrock list-prompts --query \
    "promptSummaries[?name=='customer-support-persona-v1'].id | [0]" \
    --output text --region "$REGION" 2>/dev/null)

if [ -n "$PROMPT_ID" ] && [ "$PROMPT_ID" != "None" ]; then
    echo "  🗑  Bedrock プロンプト削除: customer-support-persona-v1 ($PROMPT_ID)"
    aws bedrock delete-prompt --prompt-identifier "$PROMPT_ID" --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): customer-support-persona-v1"
fi

echo "  ℹ️  M04 はローカル実行のためリソース少（自動削除済み）"

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M05: AgentCore"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# AgentCore リソース（--cleanup オプション）
HANDSON_DIR="$HOME/handson"
if [ -d "$HANDSON_DIR/M05-agentcore" ]; then
    cd "$HANDSON_DIR/M05-agentcore"
    echo "  🗑  AgentCore Gateway クリーンアップ..."
    python3.12 agentcore_gateway_demo.py --cleanup 2>/dev/null && echo "     ✅ 完了" || echo "     ⏭  スキップ"
    echo "  🗑  AgentCore Memory クリーンアップ..."
    python3.12 agentcore_memory_demo.py --cleanup 2>/dev/null && echo "     ✅ 完了" || echo "     ⏭  スキップ"
    echo "  🗑  AgentCore Identity クリーンアップ..."
    python3.12 agentcore_identity_demo.py --cleanup 2>/dev/null && echo "     ✅ 完了" || echo "     ⏭  スキップ"
    echo "  🗑  AgentCore Runtime 削除..."
    agentcore destroy 2>/dev/null && echo "     ✅ 完了" || echo "     ⏭  スキップ"
    python3.12 agentcore_runtime_deploy.py --cleanup 2>/dev/null && echo "     ✅ 完了" || echo "     ⏭  スキップ"
    cd - > /dev/null
else
    echo "  ⏭  スキップ (ディレクトリなし): $HANDSON_DIR/M05-agentcore"
fi

# CloudFormation スタック
delete_cfn_stack "agentcore-travel-tools"

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M06: Safety Guardrails"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Bedrock Guardrail
GUARDRAIL_ID=$(aws bedrock list-guardrails --query \
    "guardrails[?name=='health-chatbot-guardrail'].id | [0]" \
    --output text --region "$REGION" 2>/dev/null)

if [ -n "$GUARDRAIL_ID" ] && [ "$GUARDRAIL_ID" != "None" ]; then
    echo "  🗑  Bedrock Guardrail 削除: health-chatbot-guardrail ($GUARDRAIL_ID)"
    aws bedrock delete-guardrail --guardrail-identifier "$GUARDRAIL_ID" --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): health-chatbot-guardrail"
fi

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M07: Cost Optimization"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "  ℹ️  M07 はローカル実行のみ。AWS リソースなし。"

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M08: Monitoring"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# CloudWatch アラーム
for alarm in "Bedrock-HighLatency-P95" "Bedrock-HighErrorRate" "Bedrock-HighHallucinationRate" "Bedrock-CostSpike"; do
    if aws cloudwatch describe-alarms --alarm-names "$alarm" --query "MetricAlarms[0].AlarmName" --output text 2>/dev/null | grep -q "$alarm"; then
        echo "  🗑  CloudWatch アラーム削除: $alarm"
        aws cloudwatch delete-alarms --alarm-names "$alarm" --region "$REGION" 2>/dev/null
    else
        echo "  ⏭  スキップ (存在しない): $alarm"
    fi
done

# CloudWatch Anomaly Detectors
echo "  🗑  CloudWatch Anomaly Detectors 削除 (GenAI/Bedrock)..."
DETECTORS=$(aws cloudwatch describe-anomaly-detectors \
    --namespace "GenAI/Bedrock" --query "AnomalyDetectors" \
    --output json --region "$REGION" 2>/dev/null)
if [ -n "$DETECTORS" ] && [ "$DETECTORS" != "[]" ]; then
    echo "$DETECTORS" | python3.12 -c "
import json, sys, subprocess
detectors = json.load(sys.stdin)
for d in detectors:
    ns = d.get('Namespace','')
    mn = d.get('MetricName','')
    stat = d.get('Stat','')
    cmd = ['aws', 'cloudwatch', 'delete-anomaly-detector',
           '--namespace', ns, '--metric-name', mn, '--stat', stat, '--region', '$REGION']
    dims = d.get('Dimensions', [])
    if dims:
        dim_args = []
        for dim in dims:
            dim_args.append(f\"Name={dim['Name']},Value={dim['Value']}\")
        cmd.extend(['--dimensions'] + dim_args)
    subprocess.run(cmd, capture_output=True)
    print(f'     削除: {mn} ({stat})')
" 2>/dev/null
    echo "     ✅ 完了"
else
    echo "  ⏭  スキップ (存在しない): Anomaly Detectors"
fi

# CloudWatch ダッシュボード
if aws cloudwatch get-dashboard --dashboard-name "Bedrock-GenAI-Monitoring" --region "$REGION" 2>/dev/null | grep -q "DashboardBody"; then
    echo "  🗑  CloudWatch ダッシュボード削除: Bedrock-GenAI-Monitoring"
    aws cloudwatch delete-dashboards --dashboard-names "Bedrock-GenAI-Monitoring" --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): Bedrock-GenAI-Monitoring"
fi

# SNS トピック
TOPIC_ARN="arn:aws:sns:${REGION}:${ACCOUNT_ID}:bedrock-monitoring-alerts"
if aws sns get-topic-attributes --topic-arn "$TOPIC_ARN" 2>/dev/null | grep -q "TopicArn"; then
    echo "  🗑  SNS トピック削除: bedrock-monitoring-alerts"
    aws sns delete-topic --topic-arn "$TOPIC_ARN" --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): bedrock-monitoring-alerts"
fi

# CloudWatch Logs ロググループ
if aws logs describe-log-groups --log-group-name-prefix "/aws/bedrock/model-invocations" \
    --query "logGroups[?logGroupName=='/aws/bedrock/model-invocations']" \
    --output text --region "$REGION" 2>/dev/null | grep -q "model-invocations"; then
    echo "  🗑  CloudWatch Logs 削除: /aws/bedrock/model-invocations"
    aws logs delete-log-group --log-group-name "/aws/bedrock/model-invocations" --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): /aws/bedrock/model-invocations"
fi

# S3 バケット（モニタリングログ - 日付パターン）
echo "  🔍 モニタリング用 S3 バケット検索..."
MONITORING_BUCKETS=$(aws s3api list-buckets --query \
    "Buckets[?starts_with(Name, 'bedrock-monitoring-logs-${ACCOUNT_ID}')].Name" \
    --output text 2>/dev/null)
if [ -n "$MONITORING_BUCKETS" ]; then
    for bucket in $MONITORING_BUCKETS; do
        delete_s3_bucket "$bucket"
    done
else
    echo "  ⏭  スキップ (存在しない): bedrock-monitoring-logs-*"
fi

# Bedrock モデル呼び出しログ無効化
echo "  🗑  Bedrock モデル呼び出しログ無効化..."
aws bedrock delete-model-invocation-logging-configuration --region "$REGION" 2>/dev/null
echo "     ✅ 完了（または既に無効）"

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M09: Testing & Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

delete_cfn_stack "ai-evaluation-pipeline"

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  M10: Enterprise Integration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

delete_cfn_stack "enterprise-ai-api-dev"
delete_cfn_stack "enterprise-ai-api-staging"
delete_cfn_stack "enterprise-ai-api-prod"
delete_cfn_stack "bedrock-vpc-endpoint"

# DynamoDB テーブル
if aws dynamodb describe-table --table-name "semantic-conflict-demo" --region "$REGION" 2>/dev/null | grep -q "TableName"; then
    echo "  🗑  DynamoDB テーブル削除: semantic-conflict-demo"
    aws dynamodb delete-table --table-name "semantic-conflict-demo" --region "$REGION" 2>/dev/null
    echo "     ✅ 削除完了"
else
    echo "  ⏭  スキップ (存在しない): semantic-conflict-demo"
fi

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  CloudFormation スタック削除の待機"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 全 CloudFormation スタックの削除完了を待機
ALL_STACKS=(
    "m01"
    "data-processing-demo"
    "stepfunctions-pipeline-demo"
    "glue-data-quality-demo"
    "agentcore-travel-tools"
    "ai-evaluation-pipeline"
    "enterprise-ai-api-dev"
    "enterprise-ai-api-staging"
    "enterprise-ai-api-prod"
    "bedrock-vpc-endpoint"
)

for stack in "${ALL_STACKS[@]}"; do
    wait_cfn_stack "$stack"
done

# ============================================================================
echo ""
echo "=============================================="
echo "  ✅ クリーンアップ完了!"
echo ""
echo "  ⚠️  手動確認推奨:"
echo "    - Bedrock コンソール → Model evaluation jobs"
echo "    - CloudFormation コンソール → DELETE_FAILED のスタック"
echo "    - S3 コンソール → 残存バケット"
echo "=============================================="
