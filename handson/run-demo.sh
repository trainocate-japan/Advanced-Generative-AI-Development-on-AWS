#!/bin/bash
# デモ実行ヘルパー
HANDSON_DIR="$HOME/handson"

run_module() {
    case "$1" in
        M01|m01) cd "$HANDSON_DIR/M01-model-selection" && python3.12 benchmark.py ;;
        M02|m02) cd "$HANDSON_DIR/M02-bedrock-converse-api" && python3.12 data_validation.py && echo "" && python3.12 context_optimization.py ;;
        M03|m03) cd "$HANDSON_DIR/M03-rag-knowledgebase" && python3.12 rag_basic.py ;;
        M04|m04) cd "$HANDSON_DIR/M04-prompt-engineering" && python3.12 prompt_personas.py ;;
        M05|m05) cd "$HANDSON_DIR/M05-agentcore" && python3.12 travel_agent.py ;;
        M06|m06|M07|m07|M08|m08|M09|m09|M10|m10|M11|m11) echo "▶ $1: steps.md を参照してください" ;;
        all)
            echo "Python: $(python3.12 --version)"
            echo "Region: $(aws configure get region)"
            echo "Account: $(aws sts get-caller-identity --query Account --output text)"
            echo ""
            for d in "$HANDSON_DIR"/M*/; do
                echo "  $(basename "$d"): $(find "$d" -maxdepth 1 -name '*.py' | wc -l) scripts"
            done
            ;;
        quit|q) exit 0 ;;
        *) echo "使い方: ./run-demo.sh [M01|M02|M03|M04|M05|...|M11|all]" ;;
    esac
}

if [ -n "$1" ]; then
    run_module "$1"
else
    echo ""
    echo "=== ハンズオンデモ ==="
    echo "  M01 - モデル選択ベンチマーク"
    echo "  M02 - データ検証・コンテキスト最適化"
    echo "  M03 - RAG ナレッジベース"
    echo "  M04 - プロンプトエンジニアリング"
    echo "  M05 - AgentCore エージェント"
    echo "  M06 - AI安全性・Guardrails"
    echo "  M07 - パフォーマンス・コスト管理"
    echo "  M08 - モニタリング"
    echo "  M09 - テスト・検証・継続改善"
    echo "  M10 - エンタープライズ統合"
    echo "  M11 - サーバーレス Web アプリ"
    echo "  all - 環境確認"
    echo "  quit"
    echo ""
    read -p "モジュール: " c
    run_module "$c"
fi
