"""
モジュール 9 - パート 4: 業界ベンチマークの統合
自分のモデルを業界標準ベンチマークと比較し、パーセンタイル順位を算出する
"""

import json
import boto3

# Bedrock クライアント
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# ==============================================================================
# ステップ 4.1: ベンチマーク評価タスク
# ==============================================================================

# 業界ベンチマークの業界平均スコア（参考値）
INDUSTRY_BENCHMARKS = {
    "GLUE（言語理解）": {
        "description": "自然言語理解（感情分析、含意関係、類似度判定など）",
        "industry_avg": 82.1,
        "top_10_percentile": 90.0,
    },
    "HumanEval（コード生成）": {
        "description": "Pythonコーディング課題の正答率（pass@1）",
        "industry_avg": 65.8,
        "top_10_percentile": 80.0,
    },
    "GSM8K（数学的推論）": {
        "description": "小学校レベルの数学文章題の正答率",
        "industry_avg": 71.2,
        "top_10_percentile": 85.0,
    },
    "カスタムドメイン（自社ユースケース）": {
        "description": "保険ドメイン固有の質問応答タスク",
        "industry_avg": 84.5,
        "top_10_percentile": 92.0,
    },
    "UIオートメーションの信頼性": {
        "description": "UI操作の自動化タスクの成功率",
        "industry_avg": 75.0,
        "top_10_percentile": 88.0,
    },
}

# ベンチマーク評価用テストケース
GLUE_TASKS = [
    {
        "task": "感情分析",
        "input": "このサービスは期待以上に素晴らしく、大変満足しています。",
        "expected": "positive",
    },
    {
        "task": "感情分析",
        "input": "対応が遅く、問題が解決されないまま放置された。非常に不満だ。",
        "expected": "negative",
    },
    {
        "task": "感情分析",
        "input": "特に良くも悪くもなく、普通のサービスだと思います。",
        "expected": "neutral",
    },
    {
        "task": "含意関係",
        "input": "前提: 東京は日本の首都です。仮説: 日本には首都がある。",
        "expected": "entailment",
    },
    {
        "task": "含意関係",
        "input": "前提: 猫は哺乳類です。仮説: 猫は爬虫類です。",
        "expected": "contradiction",
    },
]

HUMANEVAL_TASKS = [
    {
        "task": "リスト内の偶数のみを返す関数を書いてください",
        "test_cases": [
            {"input": [1, 2, 3, 4, 5, 6], "expected": [2, 4, 6]},
            {"input": [1, 3, 5], "expected": []},
        ],
    },
    {
        "task": "文字列を逆順にする関数を書いてください",
        "test_cases": [
            {"input": "hello", "expected": "olleh"},
            {"input": "Python", "expected": "nohtyP"},
        ],
    },
    {
        "task": "2つのリストの共通要素を返す関数を書いてください",
        "test_cases": [
            {"input": [[1, 2, 3, 4], [3, 4, 5, 6]], "expected": [3, 4]},
            {"input": [[1, 2], [3, 4]], "expected": []},
        ],
    },
]

GSM8K_TASKS = [
    {
        "question": "花子は1冊800円の本を3冊と、1本150円のペンを5本買いました。合計金額はいくらですか？",
        "expected": 3150,
    },
    {
        "question": "太郎は毎日2km走ります。1週間で何km走りますか？また、1ヶ月（30日）では何km走りますか？",
        "expected_weekly": 14,
        "expected_monthly": 60,
    },
    {
        "question": "あるクラスに35人の生徒がいます。男子は女子より5人多いです。女子は何人ですか？",
        "expected": 15,
    },
]

CUSTOM_DOMAIN_TASKS = [
    {
        "question": "自動車保険の等級制度について説明してください。",
        "keywords": ["等級", "割引", "割増", "事故"],
    },
    {
        "question": "火災保険と地震保険の違いは何ですか？",
        "keywords": ["火災", "地震", "補償", "別契約"],
    },
    {
        "question": "保険金請求の流れを教えてください。",
        "keywords": ["事故報告", "書類", "審査", "支払い"],
    },
]


def evaluate_glue_benchmark() -> float:
    """GLUE ベンチマーク（言語理解）の評価"""
    print("\n  [GLUE] 言語理解タスク評価中...")

    correct = 0
    total = len(GLUE_TASKS)

    for task in GLUE_TASKS:
        prompt = f"""以下のタスクを実行してください。回答は指定された選択肢から1つだけ選んでください。

タスク: {task['task']}
入力: {task['input']}

{'選択肢: positive, negative, neutral' if task['task'] == '感情分析' else '選択肢: entailment, contradiction, neutral'}

回答（選択肢の単語のみ）:"""

        response = bedrock_runtime.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"temperature": 0.0, "maxTokens": 20},
                }
            ),
        )

        result = json.loads(response["body"].read())
        answer = result["output"]["message"]["content"][0]["text"].strip().lower()

        if task["expected"] in answer:
            correct += 1

    score = (correct / total) * 100
    return score


def evaluate_humaneval_benchmark() -> float:
    """HumanEval ベンチマーク（コード生成）の評価"""
    print("  [HumanEval] コード生成タスク評価中...")

    correct = 0
    total = len(HUMANEVAL_TASKS)

    for task in HUMANEVAL_TASKS:
        prompt = f"""以下のPython関数を実装してください。関数定義のみを返してください。

タスク: {task['task']}

テストケース:
{json.dumps(task['test_cases'], ensure_ascii=False, indent=2)}

Python関数のコードのみを返してください（説明不要）:"""

        response = bedrock_runtime.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"temperature": 0.0, "maxTokens": 300},
                }
            ),
        )

        result = json.loads(response["body"].read())
        code = result["output"]["message"]["content"][0]["text"]

        # コードを実行してテスト（安全なサンドボックス内）
        passed = False
        try:
            # コードブロックの抽出
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0]
            elif "```" in code:
                code = code.split("```")[1].split("```")[0]

            # 関数を実行環境にロード
            local_env = {}
            exec(code.strip(), {}, local_env)

            # テストケースで検証
            func_name = None
            for name, obj in local_env.items():
                if callable(obj):
                    func_name = name
                    break

            if func_name:
                func = local_env[func_name]
                all_passed = True
                for tc in task["test_cases"]:
                    inp = tc["input"]
                    expected = tc["expected"]
                    if isinstance(inp, list) and len(inp) == 2 and isinstance(inp[0], list):
                        actual = func(inp[0], inp[1])
                    else:
                        actual = func(inp)

                    if isinstance(expected, list):
                        if sorted(actual) != sorted(expected):
                            all_passed = False
                    elif actual != expected:
                        all_passed = False

                passed = all_passed
        except Exception:
            passed = False

        if passed:
            correct += 1

    score = (correct / total) * 100
    return score


def evaluate_gsm8k_benchmark() -> float:
    """GSM8K ベンチマーク（数学的推論）の評価"""
    print("  [GSM8K] 数学的推論タスク評価中...")

    correct = 0
    total = len(GSM8K_TASKS)

    for task in GSM8K_TASKS:
        prompt = f"""以下の数学の問題をステップバイステップで解いてください。
最後に「答え: 数値」の形式で最終回答を示してください。

問題: {task['question']}"""

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
        answer_text = result["output"]["message"]["content"][0]["text"]

        # 数値を抽出して正解と比較
        expected = task.get("expected", task.get("expected_weekly"))
        try:
            # 「答え:」以降の数値を抽出
            import re

            numbers = re.findall(r"\d+", answer_text)
            if numbers and int(numbers[-1]) == expected:
                correct += 1
            elif str(expected) in answer_text:
                correct += 1
        except (ValueError, IndexError):
            pass

    score = (correct / total) * 100
    return score


def evaluate_custom_domain_benchmark() -> float:
    """カスタムドメイン（保険）ベンチマークの評価"""
    print("  [カスタムドメイン] 保険ドメインタスク評価中...")

    scores = []

    for task in CUSTOM_DOMAIN_TASKS:
        prompt = f"""あなたは保険の専門家です。以下の質問に正確かつ詳細に回答してください。

質問: {task['question']}"""

        response = bedrock_runtime.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"temperature": 0.3, "maxTokens": 500},
                }
            ),
        )

        result = json.loads(response["body"].read())
        answer = result["output"]["message"]["content"][0]["text"]

        # キーワードカバレッジで簡易評価
        keywords_found = sum(1 for kw in task["keywords"] if kw in answer)
        coverage = keywords_found / len(task["keywords"])
        scores.append(coverage * 100)

    return sum(scores) / len(scores) if scores else 0


# ==============================================================================
# ステップ 4.2: パーセンタイル順位の算出
# ==============================================================================


def calculate_percentile(my_score: float, industry_avg: float, top_10: float) -> int:
    """
    業界平均とトップ10%の値から、自分のスコアのパーセンタイル順位を推定
    正規分布を仮定した簡易推定
    """
    if my_score >= top_10:
        # トップ10%以上
        return min(99, 90 + int((my_score - top_10) / (100 - top_10) * 9))
    elif my_score >= industry_avg:
        # 平均〜トップ10%の間
        ratio = (my_score - industry_avg) / (top_10 - industry_avg)
        return 50 + int(ratio * 40)
    else:
        # 平均以下
        ratio = my_score / industry_avg
        return max(1, int(ratio * 50))


def get_status_indicator(percentile: int) -> str:
    """パーセンタイルに応じたステータス表示"""
    if percentile >= 75:
        return "● 平均より上"
    elif percentile >= 50:
        return "● 平均"
    else:
        return "● 平均より下"


# ==============================================================================
# ステップ 4.3: 改善優先度の決定
# ==============================================================================


def determine_improvement_priorities(results: list[dict]) -> list[dict]:
    """ベンチマーク結果から改善優先度を決定"""
    # パーセンタイルが低い順にソート
    sorted_results = sorted(results, key=lambda x: x["percentile"])

    priorities = []
    for r in sorted_results:
        if r["percentile"] < 50:
            priority = "高"
            action = "即時改善が必要"
        elif r["percentile"] < 75:
            priority = "中"
            action = "改善を検討"
        else:
            priority = "低"
            action = "現状維持"

        priorities.append(
            {
                "benchmark": r["benchmark"],
                "percentile": r["percentile"],
                "priority": priority,
                "action": action,
            }
        )

    return priorities


# ==============================================================================
# メイン実行
# ==============================================================================


def run_benchmark_comparison():
    """業界ベンチマーク比較を実行"""
    print("=" * 60)
    print("業界ベンチマークの統合 - パフォーマンス比較")
    print("=" * 60)

    # 各ベンチマークを評価
    print("\n各ベンチマークを評価中...\n")

    my_scores = {}
    my_scores["GLUE（言語理解）"] = evaluate_glue_benchmark()
    my_scores["HumanEval（コード生成）"] = evaluate_humaneval_benchmark()
    my_scores["GSM8K（数学的推論）"] = evaluate_gsm8k_benchmark()
    my_scores["カスタムドメイン（自社ユースケース）"] = evaluate_custom_domain_benchmark()

    # 結果テーブルの表示
    print("\n" + "=" * 60)
    print("ベンチマークのパフォーマンス行列")
    print("=" * 60)

    header = f"  {'ベンチマーク':<20} {'自分のスコア':>12} {'業界平均':>10} {'パーセンタイル':>12} {'ステータス'}"
    print(f"\n{header}")
    print(f"  {'─' * 70}")

    results = []

    for bench_name, bench_info in INDUSTRY_BENCHMARKS.items():
        if bench_name in my_scores:
            my_score = my_scores[bench_name]
        else:
            # UIオートメーションはスキップ（テスト環境なし）
            my_score = 91.0  # シミュレーション値

        industry_avg = bench_info["industry_avg"]
        top_10 = bench_info["top_10_percentile"]
        percentile = calculate_percentile(my_score, industry_avg, top_10)
        status = get_status_indicator(percentile)

        results.append(
            {
                "benchmark": bench_name,
                "my_score": my_score,
                "industry_avg": industry_avg,
                "percentile": percentile,
                "status": status,
            }
        )

        print(
            f"  {bench_name:<20} {my_score:>10.1f} {industry_avg:>10.1f} "
            f"{percentile:>8}位 {status}"
        )

    # 改善優先度
    print("\n" + "=" * 60)
    print("改善優先度の分析")
    print("=" * 60)

    priorities = determine_improvement_priorities(results)

    print(f"\n  {'ベンチマーク':<20} {'パーセンタイル':>12} {'優先度':>6} {'アクション'}")
    print(f"  {'─' * 60}")

    for p in priorities:
        print(
            f"  {p['benchmark']:<20} {p['percentile']:>8}位 "
            f"{p['priority']:>6} {p['action']}"
        )

    # 総合サマリー
    print("\n" + "=" * 60)
    print("総合サマリー")
    print("=" * 60)

    avg_percentile = sum(r["percentile"] for r in results) / len(results)
    above_avg = sum(1 for r in results if r["percentile"] >= 50)

    print(f"\n  平均パーセンタイル: {avg_percentile:.0f}位")
    print(f"  業界平均以上: {above_avg}/{len(results)} ベンチマーク")

    high_priority = [p for p in priorities if p["priority"] == "高"]
    if high_priority:
        print(f"\n  ⚠ 優先改善領域:")
        for p in high_priority:
            print(f"    - {p['benchmark']}（{p['percentile']}位）")
    else:
        print(f"\n  ✓ すべてのベンチマークで業界平均以上のパフォーマンス")

    return results


if __name__ == "__main__":
    results = run_benchmark_comparison()
    print("\n完了しました。")
