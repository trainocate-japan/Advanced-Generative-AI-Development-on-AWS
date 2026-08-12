"""
モジュール 9 - パート 3: A/B テストと継続的改善
プロンプトバリアントの効果測定と統計的有意性の検証
"""

import json
import time
import random
import math
import boto3

# Bedrock クライアント
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# ==============================================================================
# ステップ 3.1: プロンプト A/B テスト
# ==============================================================================

# バリアント A: 現行プロンプト（シンプル）
VARIANT_A = {
    "name": "Variant A（現行）",
    "system_prompt": "あなたはAWSの専門家です。ユーザーの質問に正確に回答してください。",
    "template": "{question}",
}

# バリアント B: 改善版プロンプト（Chain-of-Thought 追加）
VARIANT_B = {
    "name": "Variant B（CoT改善版）",
    "system_prompt": """あなたはAWSの専門家です。以下のルールに従って回答してください：
1. まず質問の要点を整理する
2. ステップバイステップで論理的に考える
3. 具体例を含めて説明する
4. 最後に要点をまとめる""",
    "template": """質問: {question}

上記の質問について、ステップバイステップで考えて回答してください。""",
}

# テスト用質問セット
TEST_QUESTIONS = [
    "Lambda関数のコールドスタートを軽減する方法は？",
    "S3のバケットポリシーとIAMポリシーの違いは？",
    "RAGシステムでハルシネーションを減らす方法は？",
    "マイクロサービスでサービス間通信の信頼性を高めるには？",
    "Bedrock Guardrailsの活用シーンを教えてください",
    "VPCエンドポイントを使うメリットは？",
    "プロンプトキャッシングでコストを削減するには？",
    "生成AIのA/Bテストで注意すべき点は？",
    "Amazon Bedrockでモデルを選択する基準は？",
    "DynamoDBのキャパシティモード選択の判断基準は？",
]


def invoke_variant(variant: dict, question: str) -> dict:
    """特定のバリアントでモデルを呼び出し、回答とメトリクスを返す"""
    prompt_text = variant["template"].format(question=question)

    start_time = time.time()

    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt_text}]}],
                "system": [{"text": variant["system_prompt"]}],
                "inferenceConfig": {"temperature": 0.7, "maxTokens": 1024},
            }
        ),
    )

    latency = time.time() - start_time
    result = json.loads(response["body"].read())

    answer = result["output"]["message"]["content"][0]["text"]
    usage = result.get("usage", {})
    input_tokens = usage.get("inputTokens", 0)
    output_tokens = usage.get("outputTokens", 0)

    return {
        "answer": answer,
        "latency_sec": round(latency, 3),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def evaluate_quality(question: str, answer: str) -> float:
    """LLM-as-Judge で回答品質を 1-5 でスコアリング"""
    judge_prompt = f"""以下の回答の品質を1-5点で評価してください。

質問: {question}
回答: {answer}

評価基準:
- 正確性、関連性、完全性、わかりやすさを総合的に判断

数値のみを返してください（例: 4）"""

    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": judge_prompt}]}],
                "inferenceConfig": {"temperature": 0.0, "maxTokens": 10},
            }
        ),
    )

    result = json.loads(response["body"].read())
    response_text = result["output"]["message"]["content"][0]["text"].strip()

    try:
        # 数字を抽出
        score = float("".join(c for c in response_text if c.isdigit() or c == "."))
        return min(max(score, 1.0), 5.0)
    except ValueError:
        return 3.0


def run_ab_test(num_questions: int = 5):
    """A/B テストを実行"""
    print("=" * 60)
    print("プロンプト A/B テスト実行")
    print("=" * 60)
    print(f"\n  バリアント A: {VARIANT_A['name']}")
    print(f"  バリアント B: {VARIANT_B['name']}")
    print(f"  テスト質問数: {num_questions}")
    print(f"  トラフィック分割: 50/50")

    questions = TEST_QUESTIONS[:num_questions]
    results_a = []
    results_b = []

    for i, question in enumerate(questions):
        print(f"\n{'─' * 50}")
        print(f"[{i+1}/{num_questions}] {question}")

        # バリアント A 実行
        result_a = invoke_variant(VARIANT_A, question)
        score_a = evaluate_quality(question, result_a["answer"])
        result_a["quality_score"] = score_a

        # バリアント B 実行
        result_b = invoke_variant(VARIANT_B, question)
        score_b = evaluate_quality(question, result_b["answer"])
        result_b["quality_score"] = score_b

        print(f"  Variant A: スコア={score_a:.1f}, "
              f"レイテンシー={result_a['latency_sec']:.2f}s, "
              f"トークン={result_a['total_tokens']}")
        print(f"  Variant B: スコア={score_b:.1f}, "
              f"レイテンシー={result_b['latency_sec']:.2f}s, "
              f"トークン={result_b['total_tokens']}")

        winner = "A" if score_a > score_b else "B" if score_b > score_a else "引分"
        print(f"  → 勝者: Variant {winner}")

        results_a.append(result_a)
        results_b.append(result_b)

    return results_a, results_b


# ==============================================================================
# ステップ 3.2: 統計的有意性の確認
# ==============================================================================


def calculate_statistics(results_a: list, results_b: list):
    """統計的有意性を検証"""
    print("\n" + "=" * 60)
    print("統計的有意性の検証")
    print("=" * 60)

    scores_a = [r["quality_score"] for r in results_a]
    scores_b = [r["quality_score"] for r in results_b]

    n = len(scores_a)

    # 基本統計量
    mean_a = sum(scores_a) / n
    mean_b = sum(scores_b) / n

    var_a = sum((x - mean_a) ** 2 for x in scores_a) / (n - 1) if n > 1 else 0
    var_b = sum((x - mean_b) ** 2 for x in scores_b) / (n - 1) if n > 1 else 0

    std_a = math.sqrt(var_a)
    std_b = math.sqrt(var_b)

    print(f"\n  Variant A: 平均={mean_a:.2f}, 標準偏差={std_a:.2f}")
    print(f"  Variant B: 平均={mean_b:.2f}, 標準偏差={std_b:.2f}")
    print(f"  差分: {mean_b - mean_a:+.2f}")

    # t検定（Welchのt検定）
    if var_a + var_b > 0 and n > 1:
        se = math.sqrt(var_a / n + var_b / n)
        t_stat = (mean_b - mean_a) / se if se > 0 else 0

        # 近似自由度（Welch-Satterthwaite）
        if var_a / n + var_b / n > 0:
            df_num = (var_a / n + var_b / n) ** 2
            df_den = (var_a / n) ** 2 / (n - 1) + (var_b / n) ** 2 / (n - 1)
            df = df_num / df_den if df_den > 0 else n - 1
        else:
            df = n - 1

        print(f"\n  t統計量: {t_stat:.3f}")
        print(f"  自由度: {df:.1f}")

        # 簡易的なp値推定（t分布の近似）
        # |t| > 2.0 で概ね p < 0.05
        if abs(t_stat) > 2.576:
            significance = "p < 0.01 (高い有意性)"
        elif abs(t_stat) > 1.96:
            significance = "p < 0.05 (統計的に有意)"
        elif abs(t_stat) > 1.645:
            significance = "p < 0.10 (弱い有意性)"
        else:
            significance = "p >= 0.10 (有意差なし)"

        print(f"  有意性: {significance}")
    else:
        print(f"\n  ※ サンプルサイズが小さいため統計検定は参考値です")
        t_stat = 0
        significance = "判定不能（サンプル不足）"

    # レイテンシー比較
    latency_a = sum(r["latency_sec"] for r in results_a) / n
    latency_b = sum(r["latency_sec"] for r in results_b) / n

    # トークン効率比較
    tokens_a = sum(r["total_tokens"] for r in results_a) / n
    tokens_b = sum(r["total_tokens"] for r in results_b) / n

    print(f"\n  レイテンシー比較:")
    print(f"    Variant A: 平均 {latency_a:.2f}s")
    print(f"    Variant B: 平均 {latency_b:.2f}s")
    print(f"    差: {latency_b - latency_a:+.2f}s")

    print(f"\n  トークン効率比較:")
    print(f"    Variant A: 平均 {tokens_a:.0f} トークン")
    print(f"    Variant B: 平均 {tokens_b:.0f} トークン")
    print(f"    差: {tokens_b - tokens_a:+.0f} トークン")

    # 総合判定
    print(f"\n{'─' * 50}")
    print(f"  総合判定:")

    if mean_b > mean_a and abs(t_stat) > 1.96:
        print(f"  ✓ Variant B が統計的に有意に優れています")
        print(f"    → Variant B へのトラフィック移行を推奨")
    elif mean_a > mean_b and abs(t_stat) > 1.96:
        print(f"  ✓ Variant A が統計的に有意に優れています")
        print(f"    → 現行プロンプト（Variant A）を継続")
    else:
        print(f"  △ 有意差が確認されませんでした")
        print(f"    → サンプルサイズを増やしてテストを継続してください")
        print(f"    → 推奨サンプルサイズ: {calculate_sample_size()} 件以上")

    return {
        "mean_a": mean_a,
        "mean_b": mean_b,
        "std_a": std_a,
        "std_b": std_b,
        "t_stat": t_stat,
        "significance": significance,
        "latency_a": latency_a,
        "latency_b": latency_b,
        "tokens_a": tokens_a,
        "tokens_b": tokens_b,
    }


def calculate_sample_size(
    effect_size: float = 0.5, alpha: float = 0.05, power: float = 0.8
) -> int:
    """必要サンプルサイズを計算（2群比較）"""
    # z値の近似
    z_alpha = 1.96 if alpha == 0.05 else 2.576  # 0.05 or 0.01
    z_beta = 0.84 if power == 0.8 else 1.28  # 0.8 or 0.9

    # サンプルサイズ公式: n = 2 * ((z_alpha + z_beta) / effect_size)^2
    n = 2 * ((z_alpha + z_beta) / effect_size) ** 2
    return math.ceil(n)


# ==============================================================================
# ステップ 3.3: 自動改善パイプライン
# ==============================================================================


def display_improvement_pipeline():
    """自動改善パイプラインの概要を表示"""
    print("\n" + "=" * 60)
    print("自動改善パイプライン")
    print("=" * 60)

    pipeline_steps = [
        {
            "step": "1. 継続的評価",
            "description": "本番トラフィックの一部をサンプリングし LLM-as-Judge で自動評価",
            "trigger": "定期実行（1時間ごと）",
        },
        {
            "step": "2. 低スコア検出",
            "description": "品質スコアが閾値（3.0/5.0）を下回るケースを特定",
            "trigger": "CloudWatch アラーム",
        },
        {
            "step": "3. 原因分析",
            "description": "低スコアパターンを分析（カテゴリ、質問タイプ、時間帯）",
            "trigger": "低スコア検出時",
        },
        {
            "step": "4. プロンプト修正",
            "description": "分析結果に基づきプロンプトの改善案を自動生成",
            "trigger": "原因特定時",
        },
        {
            "step": "5. A/B テスト",
            "description": "改善版プロンプトを少量トラフィックでテスト",
            "trigger": "プロンプト修正後",
        },
        {
            "step": "6. デプロイ判定",
            "description": "統計的有意差が確認されれば自動デプロイ",
            "trigger": "テスト完了時",
        },
    ]

    print("\n  パイプラインフロー:")
    print("  評価 → 低スコア検出 → 原因分析 → プロンプト修正 → A/Bテスト → デプロイ")
    print()

    for step_info in pipeline_steps:
        print(f"  {step_info['step']}")
        print(f"    内容: {step_info['description']}")
        print(f"    トリガー: {step_info['trigger']}")
        print()

    # 改善メトリクスのシミュレーション
    print("  " + "─" * 50)
    print("  改善サイクルのシミュレーション結果:")
    print()

    cycles = [
        {"cycle": 1, "score": 3.2, "action": "Few-shot例を追加"},
        {"cycle": 2, "score": 3.6, "action": "CoT指示を強化"},
        {"cycle": 3, "score": 3.9, "action": "出力フォーマットを明確化"},
        {"cycle": 4, "score": 4.1, "action": "エッジケース対応を追加"},
        {"cycle": 5, "score": 4.3, "action": "微調整（表現の簡潔化）"},
    ]

    print(f"  {'サイクル':>8} {'スコア':>8} {'改善アクション'}")
    print(f"  {'─' * 45}")
    for c in cycles:
        bar = "█" * int(c["score"] * 4)
        print(f"  {c['cycle']:>8} {c['score']:>8.1f} {bar} {c['action']}")

    print(f"\n  初期スコア: 3.2 → 最終スコア: 4.3 (+34% 改善)")


# ==============================================================================
# メイン実行
# ==============================================================================

if __name__ == "__main__":
    # A/B テスト実行
    results_a, results_b = run_ab_test(num_questions=5)

    # 統計的有意性の検証
    stats = calculate_statistics(results_a, results_b)

    # 自動改善パイプラインの説明
    display_improvement_pipeline()

    print("\n完了しました。")
