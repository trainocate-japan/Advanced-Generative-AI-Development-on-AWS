"""
モジュール 9 - パート 2D: エンドツーエンド RAG 評価
統合テスト、UX 検証、パフォーマンス測定、ナレッジベース品質メンテナンス

スライド対応:
  - 「本番稼働の準備状況に関するエンドツーエンド RAG システム検証の包括的なテスト」（スライド39）
  - 「コンポーネントの相互作用とデータフローを検証する統合テストフレームワーク」（スライド40）
  - 「現実世界のシステムの有効性を測定するユーザーエクスペリエンス検証」（スライド41）
  - 「長期的なシステムパフォーマンスを保証するナレッジベースの品質とメンテナンス」（スライド42）
"""

import json
import os
import sys
import time

import boto3

# ==============================================================================
# 設定
# ==============================================================================

REGION = "us-east-1"
bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

KB_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "M03-rag-knowledgebase", "kb_config.json"
)


def load_kb_id() -> str:
    if os.path.exists(KB_CONFIG_PATH):
        with open(KB_CONFIG_PATH, "r") as f:
            config = json.load(f)
        kb_id = config.get("knowledge_base_id", "")
        if kb_id:
            return kb_id
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
    if kb_id:
        return kb_id
    print("  ❌ KNOWLEDGE_BASE_ID が必要です。")
    sys.exit(1)


def load_evaluation_dataset() -> list[dict]:
    dataset_path = os.path.join(os.path.dirname(__file__), "rag-evaluation-dataset.jsonl")
    dataset = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                dataset.append(json.loads(line.strip()))
    return dataset


def invoke_llm(prompt: str, temperature: float = 0.0) -> str:
    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"temperature": temperature, "maxTokens": 500},
            }
        ),
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ==============================================================================
# テストピラミッド（スライド39）
# 単体テスト → 統合テスト → システムテスト → パフォーマンステスト → 回帰テスト
# ==============================================================================


def display_test_pyramid():
    """RAG テストピラミッドを表示"""
    print("""
              ╱╲       ← ユーザー受け入れテスト
             ╱  ╲         現実世界のシナリオとユーザー検証
            ╱ 回帰 ╲
           ╱────────╲    ← 回帰テスト: 既知クエリのスコア維持
          ╱パフォーマ╲
         ╱──ンステスト──╲  ← レイテンシー、スループット
        ╱ システムテスト ╲
       ╱────────────────╲  ← E2E品質（検索+生成の統合）
      ╱  統合テスト      ╲
     ╱────────────────────╲ ← コンポーネント間のデータフロー
    ╱    単体テスト        ╲
   ╱────────────────────────╲← 各コンポーネント個別の検証
    """)


# ==============================================================================
# 統合テスト（スライド40）: データフロー検証
# 入力 → 処理（埋め込み・変換） → ストレージ → 出力（取得・回答）
# ==============================================================================


def run_integration_tests(kb_id: str) -> list[dict]:
    """統合テスト: パイプライン全体のデータフロー検証"""
    results = []

    # テスト1: 入力フォーマットの検証
    print("    [1] 入力フォーマット検証...")
    test_queries = [
        {"query": "契約書の解除条件は？", "type": "normal", "expected": True},
        {"query": "", "type": "empty", "expected": False},
        {"query": "a" * 2000, "type": "long", "expected": True},  # 長いクエリ
    ]

    for tq in test_queries:
        try:
            if not tq["query"]:
                results.append({"test": f"入力({tq['type']})", "passed": True, "detail": "空クエリを適切に処理"})
                continue

            response = bedrock_agent_runtime.retrieve(
                knowledgeBaseId=kb_id,
                retrievalQuery={"text": tq["query"]},
                retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 3}},
            )
            has_results = len(response.get("retrievalResults", [])) > 0
            passed = has_results == tq["expected"]
            results.append({"test": f"入力({tq['type']})", "passed": passed, "detail": f"結果={has_results}"})
        except Exception as e:
            results.append({"test": f"入力({tq['type']})", "passed": tq["type"] == "empty", "detail": str(e)[:50]})

    # テスト2: レイテンシーの測定
    print("    [2] レイテンシー測定...")
    latencies = []
    test_query = "契約書の解除条件について教えてください"

    for _ in range(3):
        start = time.time()
        bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": test_query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
        )
        latencies.append(time.time() - start)

    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
    results.append({
        "test": "Retrieve レイテンシー",
        "passed": avg_latency < 3.0,
        "detail": f"avg={avg_latency:.2f}s, p95={p95_latency:.2f}s",
    })

    # テスト3: 整合性の確認（同じクエリで同じ結果が返るか）
    print("    [3] 整合性確認...")
    results_a = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": test_query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 3}},
    )
    results_b = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": test_query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 3}},
    )

    docs_a = [r.get("content", {}).get("text", "")[:50] for r in results_a.get("retrievalResults", [])]
    docs_b = [r.get("content", {}).get("text", "")[:50] for r in results_b.get("retrievalResults", [])]
    consistent = docs_a == docs_b
    results.append({"test": "検索結果の整合性", "passed": consistent, "detail": f"一致={'Yes' if consistent else 'No'}"})

    # テスト4: E2E 正解率アサート
    print("    [4] E2E 正解率アサート...")
    rag_response = bedrock_agent_runtime.retrieve_and_generate(
        input={"text": test_query},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": kb_id,
                "modelArn": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.nova-lite-v1:0",
            },
        },
    )
    answer = rag_response.get("output", {}).get("text", "")
    # 回答に期待するキーワードが含まれるか
    keywords = ["解除", "書面", "通知"]
    keyword_hits = sum(1 for kw in keywords if kw in answer)
    results.append({
        "test": "E2E正解率(キーワード)",
        "passed": keyword_hits >= 2,
        "detail": f"{keyword_hits}/{len(keywords)} キーワード検出",
    })

    return results


# ==============================================================================
# UX 検証（スライド41）: タスク完了率、応答時間、ユーザー満足度
# ==============================================================================


def run_ux_validation(kb_id: str) -> dict:
    """ユーザーエクスペリエンス検証"""
    dataset = load_evaluation_dataset()
    eval_data = [d for d in dataset if d["query_intent"] != "out_of_scope"]

    ux_results = {
        "task_completion": [],
        "response_times": [],
        "satisfaction_scores": [],
    }

    for item in eval_data[:5]:
        query = item["query"]
        ground_truth = item["ground_truth"]

        # タスク完了率: 回答が質問に実質的に答えているか
        start = time.time()
        try:
            rag_response = bedrock_agent_runtime.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": kb_id,
                        "modelArn": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.nova-lite-v1:0",
                    },
                },
            )
            answer = rag_response.get("output", {}).get("text", "")
            response_time = time.time() - start

            # タスク完了判定（LLM で判定）
            judge_prompt = f"""質問に対して回答が実質的に答えているか判定してください。
質問: {query}
回答: {answer}
「yes」または「no」のみで答えてください。"""
            completion = invoke_llm(judge_prompt).strip().lower()
            task_completed = "yes" in completion

            # 満足度スコア推定
            sat_prompt = f"""ユーザーの質問に対する回答の満足度を1-5で評価してください。
質問: {query}
回答: {answer}
数値のみ返してください。"""
            sat_response = invoke_llm(sat_prompt)
            try:
                satisfaction = float("".join(c for c in sat_response if c.isdigit() or c == "."))
                satisfaction = min(max(satisfaction, 1), 5)
            except ValueError:
                satisfaction = 3.0

            ux_results["task_completion"].append(task_completed)
            ux_results["response_times"].append(response_time)
            ux_results["satisfaction_scores"].append(satisfaction)

        except Exception as e:
            ux_results["task_completion"].append(False)
            ux_results["response_times"].append(0)
            ux_results["satisfaction_scores"].append(1.0)

    return ux_results


# ==============================================================================
# ナレッジベース品質メンテナンス（スライド42）
# モニタリング → 分析 → 更新 → 検証 の継続的改善ループ
# ==============================================================================


def assess_kb_health(kb_id: str) -> dict:
    """ナレッジベースの品質状態を評価"""
    dataset = load_evaluation_dataset()
    # 制御クエリ（既知の正解があるクエリ）で品質ドリフトを検出
    control_queries = [d for d in dataset if d["difficulty"] == "easy"][:3]

    health_metrics = {
        "drift_detected": False,
        "control_query_scores": [],
        "freshness_concerns": [],
        "coverage_gaps": [],
    }

    for item in control_queries:
        query = item["query"]
        ground_truth = item["ground_truth"]

        # Retrieve API で検索
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 3}},
        )

        results = response.get("retrievalResults", [])
        if results:
            top_score = results[0].get("score", 0)
            health_metrics["control_query_scores"].append(
                {"query": query[:30], "score": top_score}
            )
            # ドリフト検出: スコアが急激に低い場合
            if top_score < 0.3:
                health_metrics["drift_detected"] = True

    # 範囲外クエリで網羅率ギャップを特定
    out_of_scope = [d for d in dataset if d["query_intent"] == "out_of_scope"]
    for item in out_of_scope:
        health_metrics["coverage_gaps"].append(
            {"query": item["query"], "note": "ナレッジベース範囲外"}
        )

    return health_metrics


# ==============================================================================
# メイン実行
# ==============================================================================


def run_e2e_evaluation():
    """E2E RAG 評価を実行"""
    print("=" * 65)
    print("エンドツーエンド RAG 評価")
    print("=" * 65)

    # テストピラミッド表示
    print("\n  RAG システム検証のテストピラミッド:")
    display_test_pyramid()

    kb_id = load_kb_id()

    # ==========================================================================
    # 1. 統合テスト
    # ==========================================================================
    print(f"{'═' * 65}")
    print("  1. 統合テスト - データフロー検証")
    print(f"{'═' * 65}")
    print("    入力 → 処理（埋め込み）→ ストレージ（ベクトルDB）→ 出力（取得・回答）")
    print()

    integration_results = run_integration_tests(kb_id)

    print(f"\n    {'テスト':<25} {'結果':>6} {'詳細'}")
    print(f"    {'─' * 55}")
    for r in integration_results:
        status = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"    {r['test']:<25} {status:>6} {r['detail']}")

    passed = sum(1 for r in integration_results if r["passed"])
    total = len(integration_results)
    print(f"\n    合格: {passed}/{total}")

    # ==========================================================================
    # 2. UX 検証
    # ==========================================================================
    print(f"\n{'═' * 65}")
    print("  2. ユーザーエクスペリエンス検証")
    print(f"{'═' * 65}")
    print("    タスク完了率 → 応答時間 → ユーザー満足度 → エンゲージメント")
    print()
    print("    評価中...")

    ux_results = run_ux_validation(kb_id)

    # タスク完了率
    completions = ux_results["task_completion"]
    task_rate = sum(1 for c in completions if c) / len(completions) * 100 if completions else 0
    print(f"\n    タスク完了率:      {task_rate:.0f}% (目標: 85%超)")

    # 応答時間
    times = ux_results["response_times"]
    if times:
        avg_time = sum(times) / len(times)
        print(f"    平均応答時間:      {avg_time:.1f}秒 (目標: 30秒未満)")

    # ユーザー満足度
    scores = ux_results["satisfaction_scores"]
    if scores:
        avg_sat = sum(scores) / len(scores)
        print(f"    満足度スコア:      {avg_sat:.1f}/5 (NPS/CSAT相当)")

    # UX判定
    print(f"\n    UX品質判定:")
    if task_rate >= 85 and avg_time < 30:
        print(f"      ✓ 良好 - 本番リリース基準を満たしています")
    elif task_rate >= 70:
        print(f"      △ 改善余地あり - プロンプト最適化を推奨")
    else:
        print(f"      ✗ 要改善 - 検索品質またはプロンプトの見直しが必要")

    # ==========================================================================
    # 3. ナレッジベース品質メンテナンス
    # ==========================================================================
    print(f"\n{'═' * 65}")
    print("  3. ナレッジベースの品質とメンテナンス")
    print(f"{'═' * 65}")
    print("    モニタリング → 分析 → 更新 → 検証（継続的改善ループ）")
    print()

    health = assess_kb_health(kb_id)

    print("    モニタリング指標:")
    print(f"      制御クエリスコア:")
    for cq in health["control_query_scores"]:
        status = "✓" if cq["score"] >= 0.3 else "⚠"
        print(f"        {status} {cq['query']}... → {cq['score']:.3f}")

    print(f"\n      品質ドリフト検出: {'⚠ あり' if health['drift_detected'] else '✓ なし'}")

    if health["coverage_gaps"]:
        print(f"\n      網羅率ギャップ（ナレッジ不足領域）:")
        for gap in health["coverage_gaps"]:
            print(f"        • {gap['query']}")

    print(f"\n    メンテナンスアクション:")
    print("      • 鮮度スコア: コンテンツの更新頻度をモニタリング")
    print("      • 網羅率のギャップ分析: 失敗クエリパターンから不足領域を特定")
    print("      • ドリフト検出: 制御クエリで定期的に品質を確認")
    print("      • バージョン管理: ドキュメント更新時の品質影響を追跡")

    # ==========================================================================
    # 総合レポート
    # ==========================================================================
    print(f"\n{'═' * 65}")
    print("  総合レポート - 本番稼働準備状況")
    print(f"{'═' * 65}")

    checks = [
        ("統合テスト", passed == total),
        ("タスク完了率 ≥ 85%", task_rate >= 85),
        ("応答時間 < 30秒", avg_time < 30 if times else False),
        ("満足度 ≥ 3.5/5", avg_sat >= 3.5 if scores else False),
        ("品質ドリフトなし", not health["drift_detected"]),
    ]

    print(f"\n    {'チェック項目':<25} {'ステータス'}")
    print(f"    {'─' * 40}")
    for name, passed_check in checks:
        status = "✓ PASS" if passed_check else "✗ FAIL"
        print(f"    {name:<25} {status}")

    all_passed = all(p for _, p in checks)
    print(f"\n    本番リリース判定: {'✓ GO' if all_passed else '✗ NO-GO（要改善）'}")

    return {
        "integration": integration_results,
        "ux": ux_results,
        "health": health,
        "production_ready": all_passed,
    }


if __name__ == "__main__":
    try:
        results = run_e2e_evaluation()
    except SystemExit:
        print("\n  M03 のナレッジベースが必要です。")

    print("\n完了しました。")
