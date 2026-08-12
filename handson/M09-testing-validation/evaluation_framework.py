"""
モジュール 9 - パート 1: AI 評価フレームワークの構築
LLM-as-Judge パターンを使用した多次元品質評価
"""

import json
import boto3

# Bedrock クライアント
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# ==============================================================================
# ステップ 1.1: 評価ディメンションの定義
# ==============================================================================

EVALUATION_DIMENSIONS = {
    "accuracy": {
        "name": "正確性",
        "description": "回答が事実に基づいているか",
        "weight": 0.3,
    },
    "relevance": {
        "name": "関連性",
        "description": "質問に対して適切に回答しているか",
        "weight": 0.3,
    },
    "completeness": {
        "name": "完全性",
        "description": "必要な情報が網羅されているか",
        "weight": 0.2,
    },
    "safety": {
        "name": "安全性",
        "description": "有害な内容を含んでいないか",
        "weight": 0.2,
    },
}


def print_evaluation_dimensions():
    """評価ディメンションを表示"""
    print("=" * 60)
    print("AI 品質評価フレームワーク - 評価ディメンション")
    print("=" * 60)
    for key, dim in EVALUATION_DIMENSIONS.items():
        print(f"\n  [{key}] {dim['name']} (重み: {dim['weight']})")
        print(f"    → {dim['description']}")
    print()


# ==============================================================================
# ステップ 1.2: LLM-as-Judge パターン
# ==============================================================================

JUDGE_PROMPT_TEMPLATE = """あなたはAIシステムの品質を評価する専門の審査員です。
以下の質問と回答のペアを厳密に評価してください。

## 評価対象
- 質問: {question}
- 回答: {answer}
- 参照回答（正解）: {reference}

## 評価基準（各1-5点）
- accuracy（正確性）: 回答が事実に基づいているか。参照回答と比較して誤りがないか。
- relevance（関連性）: 質問に対して適切に回答しているか。的外れでないか。
- completeness（完全性）: 必要な情報が網羅されているか。重要な点が抜けていないか。
- clarity（明瞭性）: わかりやすく構造化されているか。

## 出力形式
必ず以下のJSON形式のみで回答してください。説明文は不要です。
{{
  "accuracy": <1-5>,
  "relevance": <1-5>,
  "completeness": <1-5>,
  "clarity": <1-5>,
  "overall": <1-5>,
  "reasoning": "<評価の根拠を1-2文で>"
}}"""


def invoke_judge(question: str, answer: str, reference: str) -> dict:
    """LLM-as-Judge を呼び出して回答を評価する"""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        question=question, answer=answer, reference=reference
    )

    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"temperature": 0.0, "maxTokens": 500},
            }
        ),
    )

    result = json.loads(response["body"].read())
    response_text = result["output"]["message"]["content"][0]["text"]

    # JSON部分を抽出してパース
    try:
        # レスポンスからJSON部分を抽出
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            evaluation = json.loads(response_text[json_start:json_end])
        else:
            evaluation = json.loads(response_text)
    except json.JSONDecodeError:
        evaluation = {
            "accuracy": 0,
            "relevance": 0,
            "completeness": 0,
            "clarity": 0,
            "overall": 0,
            "reasoning": "評価結果のパースに失敗しました",
        }

    return evaluation


# ==============================================================================
# ステップ 1.3: テスト対象のAIシステム（評価対象モデルの呼び出し）
# ==============================================================================


def generate_answer(question: str) -> str:
    """評価対象のAIシステムから回答を生成する"""
    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": question}]}],
                "inferenceConfig": {"temperature": 0.7, "maxTokens": 1024},
            }
        ),
    )

    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ==============================================================================
# ステップ 1.4: 評価データセットの読み込みと評価実行
# ==============================================================================


def load_evaluation_dataset(filepath: str = "evaluation-dataset.jsonl") -> list:
    """評価データセットを読み込む"""
    dataset = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dataset.append(json.loads(line))
    return dataset


def calculate_weighted_score(evaluation: dict) -> float:
    """重み付きスコアを計算"""
    weights = {"accuracy": 0.3, "relevance": 0.3, "completeness": 0.2, "clarity": 0.2}
    total = 0.0
    for key, weight in weights.items():
        score = evaluation.get(key, 0)
        total += score * weight
    return round(total, 2)


def run_evaluation(num_samples: int = 5):
    """評価パイプラインを実行"""
    print("\n" + "=" * 60)
    print("LLM-as-Judge 評価パイプライン実行")
    print("=" * 60)

    # データセット読み込み
    dataset = load_evaluation_dataset()
    print(f"\n評価データセット: {len(dataset)} 件ロード済み")
    print(f"評価対象: 先頭 {num_samples} 件")

    results = []

    for i, item in enumerate(dataset[:num_samples]):
        question = item["prompt"]
        reference = item["referenceResponse"]
        category = item["category"]

        print(f"\n{'─' * 50}")
        print(f"[{i+1}/{num_samples}] カテゴリ: {category}")
        print(f"  質問: {question[:50]}...")

        # AIシステムから回答を生成
        answer = generate_answer(question)
        print(f"  回答: {answer[:80]}...")

        # LLM-as-Judge で評価
        evaluation = invoke_judge(question, answer, reference)
        weighted_score = calculate_weighted_score(evaluation)

        print(f"  評価結果:")
        print(f"    正確性: {evaluation.get('accuracy', 'N/A')}/5")
        print(f"    関連性: {evaluation.get('relevance', 'N/A')}/5")
        print(f"    完全性: {evaluation.get('completeness', 'N/A')}/5")
        print(f"    明瞭性: {evaluation.get('clarity', 'N/A')}/5")
        print(f"    総合スコア: {weighted_score}/5.0")
        print(f"    根拠: {evaluation.get('reasoning', 'N/A')}")

        results.append(
            {
                "question": question,
                "category": category,
                "answer": answer,
                "evaluation": evaluation,
                "weighted_score": weighted_score,
            }
        )

    # サマリー表示
    print("\n" + "=" * 60)
    print("評価サマリー")
    print("=" * 60)

    if results:
        avg_score = sum(r["weighted_score"] for r in results) / len(results)
        print(f"\n  評価件数: {len(results)}")
        print(f"  平均スコア: {avg_score:.2f}/5.0")

        # カテゴリ別スコア
        categories = {}
        for r in results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r["weighted_score"])

        print(f"\n  カテゴリ別平均スコア:")
        for cat, scores in categories.items():
            cat_avg = sum(scores) / len(scores)
            print(f"    {cat}: {cat_avg:.2f}/5.0")

        # 低スコアの検出
        low_scores = [r for r in results if r["weighted_score"] < 3.0]
        if low_scores:
            print(f"\n  ⚠ 低スコア検出: {len(low_scores)} 件（3.0未満）")
            for r in low_scores:
                print(f"    - {r['question'][:40]}... → {r['weighted_score']}")
        else:
            print(f"\n  ✓ すべての回答が基準スコア（3.0）以上")

    return results


# ==============================================================================
# メイン実行
# ==============================================================================

if __name__ == "__main__":
    print_evaluation_dimensions()
    results = run_evaluation(num_samples=5)
    print("\n完了しました。")
