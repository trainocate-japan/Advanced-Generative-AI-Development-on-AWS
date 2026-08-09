#!/bin/bash
# =============================================================================
# ハンズオンデモ環境セットアップスクリプト
# EC2 上でハンズオンの全デモを実行可能な状態にする
# =============================================================================

set -e

echo "=============================================="
echo " ハンズオンデモ環境セットアップ"
echo "=============================================="

REPO_DIR="$HOME/handson-repo"
HANDSON_DIR="$REPO_DIR/handson"

# -------------------------------------------
# 1. Python 依存関係のインストール
# -------------------------------------------
echo ""
echo "[1/5] Python ライブラリをインストール中..."

pip3 install --user \
    boto3 \
    streamlit \
    numpy \
    pandas

echo "  ✅ Python ライブラリインストール完了"

# -------------------------------------------
# 2. 各モジュールの事前検証
# -------------------------------------------
echo ""
echo "[2/5] 各モジュールの動作確認..."

# AWS 認証情報の確認（IAM ロール経由）
echo "  AWS 認証情報の確認..."
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "FAILED")
AWS_REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "us-east-1")

if [ "$AWS_ACCOUNT" = "FAILED" ]; then
    echo "  ❌ AWS 認証に失敗しました。IAM ロールを確認してください。"
    exit 1
fi

echo "  ✅ AWS アカウント: $AWS_ACCOUNT"
echo "  ✅ リージョン: $AWS_REGION"

# リージョン設定
aws configure set region "$AWS_REGION"

# -------------------------------------------
# 3. Bedrock モデルアクセスの確認
# -------------------------------------------
echo ""
echo "[3/5] Bedrock モデルアクセスの確認..."

MODELS_TO_CHECK=(
    "amazon.nova-lite-v1:0"
    "amazon.nova-pro-v1:0"
    "amazon.titan-embed-text-v2:0"
)

for model in "${MODELS_TO_CHECK[@]}"; do
    result=$(aws bedrock get-foundation-model --model-identifier "$model" --query "modelDetails.modelId" --output text 2>/dev/null || echo "UNAVAILABLE")
    if [ "$result" != "UNAVAILABLE" ]; then
        echo "  ✅ $model"
    else
        echo "  ⚠  $model (アクセス未確認 - コンソールで有効化してください)"
    fi
done

# -------------------------------------------
# 4. M03 ナレッジベース用 S3 バケット作成
# -------------------------------------------
echo ""
echo "[4/5] デモ用リソースの準備..."

KB_BUCKET="legal-kb-demo-${AWS_ACCOUNT}"

# S3 バケットの作成（既存の場合はスキップ）
if aws s3 ls "s3://$KB_BUCKET" 2>/dev/null; then
    echo "  ✅ S3 バケット既存: $KB_BUCKET"
else
    if [ "$AWS_REGION" = "us-east-1" ]; then
        aws s3 mb "s3://$KB_BUCKET"
    else
        aws s3 mb "s3://$KB_BUCKET" --region "$AWS_REGION"
    fi
    echo "  ✅ S3 バケット作成: $KB_BUCKET"
fi

# サンプルドキュメントのアップロード
if [ -d "$HANDSON_DIR/M03-data-automation/sample-docs" ]; then
    aws s3 sync "$HANDSON_DIR/M03-data-automation/sample-docs/" "s3://$KB_BUCKET/documents/" --quiet
    echo "  ✅ サンプルドキュメントをアップロード済み"
fi

# -------------------------------------------
# 5. デモ実行用のヘルパースクリプト作成
# -------------------------------------------
echo ""
echo "[5/5] ヘルパースクリプトの作成..."

cat > "$HOME/run-demo.sh" << 'DEMO_SCRIPT'
#!/bin/bash
# =============================================================================
# デモ実行ヘルパー
# 使い方: ./run-demo.sh M01  (モジュール番号を指定)
# =============================================================================

HANDSON_DIR="$HOME/handson-repo/handson"

show_menu() {
    echo ""
    echo "=============================================="
    echo " ハンズオンデモ実行メニュー"
    echo "=============================================="
    echo ""
    echo "  M01 - 基盤モデル選択・ベンチマーク比較"
    echo "  M02 - データ検証・マルチモーダル処理"
    echo "  M03 - RAG・ナレッジベース"
    echo "  M04 - プロンプトエンジニアリング・CoT"
    echo "  M05 - エージェント（旅行プランニング）"
    echo "  M06 - Guardrails デモ"
    echo "  M07 - パフォーマンス・キャッシング"
    echo "  M08 - モニタリング・ハルシネーション検出"
    echo "  M09 - テスト・評価フレームワーク"
    echo "  M10 - エンタープライズ統合"
    echo ""
    echo "  all  - 全モジュールの環境確認"
    echo "  quit - 終了"
    echo ""
    read -p "  実行するモジュール: " choice
    run_module "$choice"
}

run_module() {
    local module="$1"
    case "$module" in
        M01|m01)
            echo "▶ M01: モデルベンチマーク実行中..."
            cd "$HANDSON_DIR/M01-model-selection"
            python3 benchmark.py
            ;;
        M02|m02)
            echo "▶ M02: データ検証パイプライン実行中..."
            cd "$HANDSON_DIR/M02-bedrock-converse-api"
            echo "  [1] データ検証:"
            python3 data_validation.py
            echo ""
            echo "  [2] コンテキスト最適化:"
            python3 context_optimization.py
            ;;
        M03|m03)
            echo "▶ M03: RAG デモ実行中..."
            cd "$HANDSON_DIR/M03-data-automation"
            python3 rag_basic.py
            ;;
        M04|m04)
            echo "▶ M04: プロンプトエンジニアリング実行中..."
            cd "$HANDSON_DIR/M04-performance"
            python3 prompt_personas.py
            ;;
        M05|m05)
            echo "▶ M05: 旅行プランニングエージェント実行中..."
            cd "$HANDSON_DIR/M05-prompt-management"
            python3 travel_agent.py
            ;;
        M06|m06)
            echo "▶ M06: Guardrails デモ..."
            echo "  (AWS コンソールで Guardrails を設定後に実行)"
            cd "$HANDSON_DIR/M06-prompt-caching"
            echo "  手順: steps.md を参照してください"
            ;;
        M07|m07)
            echo "▶ M07: パフォーマンス最適化..."
            cd "$HANDSON_DIR/M07-guardrails"
            echo "  手順: steps.md を参照してください"
            ;;
        M08|m08)
            echo "▶ M08: モニタリング..."
            cd "$HANDSON_DIR/M08-monitoring"
            echo "  手順: steps.md を参照してください"
            ;;
        M09|m09)
            echo "▶ M09: テスト・評価..."
            cd "$HANDSON_DIR/M09-agents"
            echo "  手順: steps.md を参照してください"
            ;;
        M10|m10)
            echo "▶ M10: エンタープライズ統合..."
            cd "$HANDSON_DIR/M10-rag-knowledgebase"
            echo "  手順: steps.md を参照してください"
            ;;
        all)
            echo "▶ 全モジュールの環境確認..."
            for dir in "$HANDSON_DIR"/M*/; do
                module=$(basename "$dir")
                py_files=$(find "$dir" -name "*.py" -maxdepth 1 | wc -l)
                echo "  $module: ${py_files} Python scripts"
            done
            ;;
        quit|q)
            echo "終了します"
            exit 0
            ;;
        *)
            echo "❌ 無効なモジュール: $module"
            show_menu
            ;;
    esac
}

if [ -n "$1" ]; then
    run_module "$1"
else
    show_menu
fi
DEMO_SCRIPT

chmod +x "$HOME/run-demo.sh"
echo "  ✅ ~/run-demo.sh を作成しました"

# -------------------------------------------
# 完了メッセージ
# -------------------------------------------
echo ""
echo "=============================================="
echo " セットアップ完了!"
echo "=============================================="
echo ""
echo " デモの実行方法:"
echo "   ./run-demo.sh        # メニューから選択"
echo "   ./run-demo.sh M01    # 直接指定"
echo ""
echo " ハンズオン資料:"
echo "   $HANDSON_DIR"
echo ""
echo " 注意事項:"
echo "   - Bedrock モデルアクセスは AWS コンソールで有効化が必要"
echo "   - M03 のナレッジベースは setup_knowledgebase.py で別途作成"
echo "   - M06 の Guardrails は AWS コンソールで作成"
echo "   - このインスタンスは毎日 23:00 JST に自動停止されます"
echo ""
