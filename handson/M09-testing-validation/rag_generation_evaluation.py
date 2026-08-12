"""
モジュール 9 - パート 2C: 生成評価 - LLM-as-Judge とバイアス検知
RAG の生成コンポーネントを評価: 正解率、忠実度、バイアス検出

スライド対応:
  - 「LLM-as-Judge の紹介」（スライド35） - スケーラビリティ、一貫性、コスト効率
  - 「自動評価の実装」（スライド36） - 評価基準定義→最低温度→人間に照らした検証→デプロイ
  - 「バイアスの検知と緩和」（スライド37） - 位置バイアス、確証バイアス、冗長性バイアス
  - 「一貫性のある評価にとって有効な手順の作成に関する評価プロンプトエンジニアリング」（スライド38）
"""

import json
import os
import sys
import random

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


def invoke_llm(prompt: str, temperature: float = 0.0, max_tokens: int = 1000) -> str:
    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens},
            }
        ),
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


def retrieve_and_generate(kb_id: str, query: str) -> dict:
    """RetrieveAndGenerate API で回答を生成"""
    response = bedrock_agent_runtime.retrieve_and_generate(
        input={"text": query},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": kb_id,
                "modelArn": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.nova-lite-v1:0",
            },
        },
    )
    answer = response.get("output", {}).get("text", "")
    citations = response.get("citations", [])

    # コンテキストの抽出
    contexts = []
    for citation in citations:
        for ref in citation.get("retrievedReferences", []):
            contexts.append(ref.get("content", {}).get("text", ""))

    return {"answer": answer, "contexts": contexts, "citations": citations}


def parse_json_response(text: str) -> dict:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass
    return {}


# ==============================================================================
# LLM-as-Judge 実装（スライド35-36対応）
# ==============================================================================

# 評価プロンプトエンジニアリング（スライド38対応）
# - 明確なスコアリングの評価基準の定義
# - アンカーの例（各スコアレベルの具体例）
# - 思考連鎖プロンプティング

JUDGE_PROMPT = """あなたは RAG システムの品質を評価する専門の審査員です。
以下の5つの評価基準に基づいて、生成された回答を厳密に評価してください。

## 入力
- クエリ: {query}
- 生成された回答: {answer}
- 検索されたコンテキスト: {context}
- 参照回答（Ground Truth）: {ground_truth}

## 評価基準（各 1-5 点）

### 1. 正解率（Correctness）
回答が Ground Truth と比較して事実的に正確か。
- 5: 完全に正確、Ground Truth と一致
- 4: ほぼ正確、軽微な省略あり
- 3: 部分的に正確、重要な情報の一部が欠落
- 2: 不正確な情報を含む
- 1: 大部分が不正確

### 2. 関連性（Relevance）
回答がクエリに直接答えているか。
- 5: 完全に質問に答えている
- 3: 部分的に答えているが脱線あり
- 1: 質問と無関係

### 3. 完全性（Completeness）
必要な情報が網羅されているか。
- 5: Ground Truth の全要素をカバー
- 3: 主要要素はカバーするが一部欠落
- 1: ほとんどカバーされていない

### 4. 明瞭性（Clarity）
回答がわかりやすく構造化されているか。
- 5: 非常に読みやすく構造化されている
- 3: 読めるが改善余地あり
- 1: 読みにくく理解困難

### 5. 忠実度（Faithfulness）
回答がコンテキストに基づいているか（ハルシネーションがないか）。
- 5: 全ての情報がコンテキストに裏付けられている
- 3: 一部コンテキストにない情報を含む
- 1: コンテキストと矛盾する情報を含む

## 出力形式
ステップバイステップで評価し、以下のJSON形式で返してください:
{{
  "correctness": <1-5>,
  "relevance": <1-5>,
  "completeness": <1-5>,
  "clarity": <1-5>,
  "faithfulness": <1-5>,
  "overall": <1-5の加重平均>,
  "reasoning": "<評価の根拠を2-3文で>"
}}"""


def evaluate_with_judge(query: str, answer: str, context: str, ground_truth: str) -> dict:
    """LLM-as-Judge で生成品質を評価"""
    prompt = JUDGE_PROMPT.format(
        query=query,
        answer=answer,
        context=context[:1500],  # コンテキストを制限
        ground_truth=ground_truth,
    )

    # 最低温度で一貫したスコアリング（スライド36対応）
    response = invoke_llm(prompt, temperature=0.1)
    result = parse_json_response(response)

    if not result:
        return {
            "correctness": 0,
            "relevance": 0,
            "completeness": 0,
            "clarity": 0,
            "faithfulness": 0,
            "overall": 0,
            "reasoning": "評価失敗",
        }

    # overall がない場合は計算
    if "overall" not in result or result["overall"] == 0:
        scores = [
            result.get("correctness", 0),
            result.get("relevance", 0),
            result.get("completeness", 0),
            result.get("clarity", 0),
            result.get("faithfulness", 0),
        ]
        valid = [s for s in scores if s > 0]
        result["overall"] = sum(valid) / len(valid) if valid else 0

    return result


# ==============================================================================
# バイアス検知（スライド37対応）
# ==============================================================================


def detect_position_bias(kb_id: str, query: str) -> dict:
    """
    位置バイアス: 評価ツールによる解答の評価がリスト内の位置によって変わるか検出。
    同じ回答を異なる位置で評価し、スコアの変動を確認する。
    """
    # 同じクエリで回答を生成
    result = retrieve_and_generate(kb_id, query)
    answer = result["answer"]

    # 回答のセグメントを順番を変えて評価
    segments = answer.split("。")
    if len(segments) < 2:
        return {"bias_detected": False, "variance": 0.0, "note": "セグメント不足"}

    scores = []
    for _ in range(3):
        # シャッフルしたコンテキストで評価
        shuffled = segments.copy()
        random.shuffle(shuffled)
        shuffled_answer = "。".join(shuffled)

        eval_prompt = f"""以下の回答を1-5で評価してください。質問: {query}\n回答: {shuffled_answer}\n数値のみ返してください。"""
        response = invoke_llm(eval_prompt, temperature=0.0)
        try:
            score = float("".join(c for c in response if c.isdigit() or c == "."))
            scores.append(min(max(score, 1), 5))
        except ValueError:
            scores.append(3.0)

    variance = max(scores) - min(scores) if scores else 0
    return {
        "bias_detected": variance > 1.0,
        "variance": round(variance, 2),
        "scores": scores,
    }


def detect_verbosity_bias(kb_id: str, query: str) -> dict:
    """
    冗長性バイアス: より長い回答を系統的に優遇していないか検出。
    同じ内容の短い版と長い版を比較。
    """
    result = retrieve_and_generate(kb_id, query)
    original_answer = result["answer"]

    # 短縮版を生成
    short_prompt = f"以下を2文以内に要約してください:\n{original_answer}"
    short_answer = invoke_llm(short_prompt)

    # 両方を同じ基準で評価
    eval_prompt_template = """以下の回答の品質を1-5で評価してください（内容の正確さと有用性のみで判断）。
質問: {query}
回答: {answer}
数値のみ返してください。"""

    score_long = 3.0
    score_short = 3.0

    try:
        resp = invoke_llm(eval_prompt_template.format(query=query, answer=original_answer))
        score_long = float("".join(c for c in resp if c.isdigit() or c == "."))
    except ValueError:
        pass

    try:
        resp = invoke_llm(eval_prompt_template.format(query=query, answer=short_answer))
        score_short = float("".join(c for c in resp if c.isdigit() or c == "."))
    except ValueError:
        pass

    bias_score = score_long - score_short
    return {
        "bias_detected": bias_score > 1.5,
        "long_score": round(score_long, 1),
        "short_score": round(score_short, 1),
        "difference": round(bias_score, 1),
        "long_length": len(original_answer),
        "short_length": len(short_answer),
    }


# ==============================================================================
# メイン実行
# ==============================================================================


def run_generation_evaluation():
    """生成評価を実行"""
    print("=" * 65)
    print("生成評価 - LLM-as-Judge とバイアス検知")
    print("=" * 65)
    print()
    print("  LLM-as-Judge の利点:")
    print("    • スケーラビリティ: 何千もの応答を一貫した基準で自動評価")
    print("    • 一貫性: 標準化された評価基準を適用")
    print("    • コスト効率: 人間による評価の 80-90% を削減")
    print("    • 迅速なイテレーション: リアルタイムフィードバック")
    print("    • 多次元評価: 複数の品質ディメンションを同時に評価")
    print()

    kb_id = load_kb_id()
    dataset = load_evaluation_dataset()
    eval_data = [d for d in dataset if d["query_intent"] != "out_of_scope"][:5]

    # ==========================================================================
    # Part 1: LLM-as-Judge 評価
    # ==========================================================================
    print(f"\n{'═' * 65}")
    print("  Part 1: LLM-as-Judge による多次元評価")
    print(f"{'═' * 65}")
    print(f"  評価モデル: amazon.nova-lite-v1:0 (temperature=0.1)")
    print(f"  評価対象: {len(eval_data)} クエリ")

    all_evaluations = []

    for i, item in enumerate(eval_data):
        query = item["query"]
        ground_truth = item["ground_truth"]

        print(f"\n  {'─' * 60}")
        print(f"  [{i+1}/{len(eval_data)}] {query[:50]}...")

        # RAG パイプライン実行
        rag_result = retrieve_and_generate(kb_id, query)
        answer = rag_result["answer"]
        context = "\n".join(rag_result["contexts"][:3])

        print(f"    回答: {answer[:80]}...")

        # LLM-as-Judge 評価
        evaluation = evaluate_with_judge(query, answer, context, ground_truth)

        print(f"    評価結果:")
        print(f"      正解率:   {evaluation.get('correctness', 0)}/5")
        print(f"      関連性:   {evaluation.get('relevance', 0)}/5")
        print(f"      完全性:   {evaluation.get('completeness', 0)}/5")
        print(f"      明瞭性:   {evaluation.get('clarity', 0)}/5")
        print(f"      忠実度:   {evaluation.get('faithfulness', 0)}/5")
        print(f"      総合:     {evaluation.get('overall', 0):.1f}/5")
        print(f"      根拠: {evaluation.get('reasoning', 'N/A')[:60]}")

        all_evaluations.append({"query": query, **evaluation})

    # サマリー
    print(f"\n{'═' * 65}")
    print("  LLM-as-Judge 評価サマリー")
    print(f"{'═' * 65}")

    n = len(all_evaluations)
    if n > 0:
        metrics = ["correctness", "relevance", "completeness", "clarity", "faithfulness"]
        print(f"\n  {'メトリクス':<12} {'平均':>6} {'目標':>6}")
        print(f"  {'─' * 30}")
        for m in metrics:
            avg = sum(e.get(m, 0) for e in all_evaluations) / n
            target = 4.0
            status = "✓" if avg >= target else "△" if avg >= 3.0 else "✗"
            print(f"  {m:<12} {avg:>6.1f} {target:>6.1f}  {status}")

        overall_avg = sum(e.get("overall", 0) for e in all_evaluations) / n
        print(f"  {'─' * 30}")
        print(f"  {'総合':<12} {overall_avg:>6.1f}")

    # ==========================================================================
    # Part 2: バイアス検知
    # ==========================================================================
    print(f"\n{'═' * 65}")
    print("  Part 2: バイアスの検知")
    print(f"{'═' * 65}")
    print()
    print("  検出対象のバイアス:")
    print("    • 位置バイアス: 回答の順序で評価が変わる")
    print("    • 冗長性バイアス: 長い回答を系統的に優遇する")
    print()

    # 位置バイアス検出
    test_query = eval_data[0]["query"]
    print(f"  位置バイアス検出: '{test_query[:30]}...'")
    position_result = detect_position_bias(kb_id, test_query)
    print(f"    スコア変動: {position_result['variance']}")
    print(f"    バイアス検出: {'⚠ あり' if position_result['bias_detected'] else '✓ なし'}")

    # 冗長性バイアス検出
    print(f"\n  冗長性バイアス検出: '{test_query[:30]}...'")
    verbosity_result = detect_verbosity_bias(kb_id, test_query)
    print(f"    長文スコア: {verbosity_result['long_score']} ({verbosity_result['long_length']}文字)")
    print(f"    短文スコア: {verbosity_result['short_score']} ({verbosity_result['short_length']}文字)")
    print(f"    スコア差: {verbosity_result['difference']}")
    print(f"    バイアス検出: {'⚠ あり' if verbosity_result['bias_detected'] else '✓ なし'}")

    # 緩和戦略
    print(f"\n  バイアス緩和戦略:")
    print("    • ランダム化: 評価時にコンテキストの順序をシャッフル")
    print("    • アンサンブル評価: 複数のモデルで評価し平均を取る")
    print("    • プロンプトエンジニアリング: 内容のみで判断するよう明示")
    print("    • 人間によるキャリブレーション: 定期的に人間の判断と照合")
    print("    • 定期的な検証: コーエンのκ係数で一致率を測定（目標>0.6）")

    return all_evaluations


if __name__ == "__main__":
    try:
        results = run_generation_evaluation()
    except SystemExit:
        print("\n  M03 のナレッジベースが必要です。")

    print("\n完了しました。")
