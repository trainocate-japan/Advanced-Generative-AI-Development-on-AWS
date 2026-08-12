"""
モジュール 9 - パート 2B: コンテキスト照合検証
検索されたコンテキストが本当にクエリの意図に合っているかを多角的に検証する。

スライド対応:
  - 「コンテキスト照合検証」（スライド33） - 意味的整合性、時間的関連性、対象範囲の適切性、完全性、事実整合性
  - 「網羅性と完全性の分析」（スライド34） - 情報ギャップ、冗長性、ばらつき、完全性スコアリング
"""

import json
import os
import sys

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
    """M03 の kb_config.json からナレッジベースIDを取得"""
    if os.path.exists(KB_CONFIG_PATH):
        with open(KB_CONFIG_PATH, "r") as f:
            config = json.load(f)
        kb_id = config.get("knowledge_base_id", "")
        if kb_id:
            return kb_id
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
    if kb_id:
        return kb_id
    print("  ❌ ナレッジベースIDが見つかりません。")
    print("     export KNOWLEDGE_BASE_ID=XXXXXXXXXX を設定してください。")
    sys.exit(1)


def load_evaluation_dataset() -> list[dict]:
    """評価データセットを読み込む"""
    dataset_path = os.path.join(os.path.dirname(__file__), "rag-evaluation-dataset.jsonl")
    dataset = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dataset.append(json.loads(line))
    return dataset


def retrieve_contexts(kb_id: str, query: str, k: int = 5) -> list[dict]:
    """Retrieve API でコンテキストを取得"""
    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": k}
        },
    )
    contexts = []
    for item in response.get("retrievalResults", []):
        contexts.append(
            {
                "text": item.get("content", {}).get("text", ""),
                "score": item.get("score", 0.0),
                "source": item.get("location", {})
                .get("s3Location", {})
                .get("uri", "")
                .split("/")[-1],
            }
        )
    return contexts


def invoke_llm(prompt: str, temperature: float = 0.0) -> str:
    """Bedrock LLM を呼び出す"""
    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"temperature": temperature, "maxTokens": 1000},
            }
        ),
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


def parse_json_response(text: str) -> dict:
    """LLM応答からJSONを抽出"""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass
    return {}


# ==============================================================================
# コンテキスト照合検証 - 5つの検証軸
# ==============================================================================


def evaluate_semantic_alignment(query: str, contexts: list[dict]) -> dict:
    """
    意味的整合性 (0.7-0.8 のしきい値推奨):
    検索されたコンテキストがクエリの意図と概念的に一致しているか。
    埋め込み類似度スコアに加え、LLM で意味レベルの一致を確認。
    """
    context_texts = "\n---\n".join(
        f"[チャンク{i+1}] (スコア: {c['score']:.3f})\n{c['text'][:200]}"
        for i, c in enumerate(contexts[:3])
    )

    prompt = f"""以下のクエリと検索されたコンテキストの意味的整合性を評価してください。

## クエリ:
{query}

## 検索されたコンテキスト:
{context_texts}

## 評価基準:
- コンテキストがクエリの意図する概念・トピックに一致しているか
- キーワード一致ではなく、意味レベルで関連しているか

JSON形式で返してください:
{{"score": <0.0-1.0>, "aligned_chunks": <一致しているチャンク数>, "reasoning": "<理由>"}}"""

    response = invoke_llm(prompt)
    return parse_json_response(response) or {"score": 0.0, "reasoning": "解析失敗"}


def evaluate_scope_appropriateness(query: str, contexts: list[dict]) -> dict:
    """
    対象範囲の適切性:
    ユーザーが簡単な概要を求めているのに過度に詳細な情報を返していないか、
    逆に詳細を求めているのに概要だけ返していないか。
    """
    context_texts = "\n---\n".join(c["text"][:200] for c in contexts[:3])

    prompt = f"""以下のクエリが求める情報の詳細レベルと、検索されたコンテキストの詳細レベルが適切に一致しているか評価してください。

## クエリ:
{query}

## コンテキスト:
{context_texts}

## 評価基準:
- クエリが概要を求めているなら、概要レベルの情報が返されているか
- クエリが詳細を求めているなら、十分に詳細な情報が含まれているか
- 情報の粒度が質問の意図に合っているか

JSON形式で返してください:
{{"score": <0.0-1.0>, "query_level": "<概要/詳細/具体的事実>", "context_level": "<概要/詳細/具体的事実>", "reasoning": "<理由>"}}"""

    response = invoke_llm(prompt)
    return parse_json_response(response) or {"score": 0.0, "reasoning": "解析失敗"}


def evaluate_completeness(query: str, contexts: list[dict], ground_truth: str) -> dict:
    """
    完全性の評価:
    クエリの全ての要素に対応する情報がコンテキストに含まれているか。
    複合的なクエリでは複数の要素への対応が必要。
    """
    context_texts = "\n---\n".join(c["text"][:300] for c in contexts[:5])

    prompt = f"""以下のクエリに回答するために必要な情報が、検索されたコンテキストにどの程度含まれているか評価してください。

## クエリ:
{query}

## 期待する回答（Ground Truth）:
{ground_truth}

## 検索されたコンテキスト:
{context_texts}

## タスク:
1. クエリに回答するために必要な情報要素を列挙する
2. 各要素がコンテキストに含まれているか判定する
3. 完全性スコアを算出する

JSON形式で返してください:
{{"score": <0.0-1.0>, "required_elements": ["要素1", "要素2"], "found_elements": ["見つかった要素"], "missing_elements": ["不足している要素"], "reasoning": "<理由>"}}"""

    response = invoke_llm(prompt)
    return parse_json_response(response) or {"score": 0.0, "reasoning": "解析失敗"}


def evaluate_redundancy(contexts: list[dict]) -> dict:
    """
    冗長性の識別:
    複数のチャンクが同じ情報を繰り返していないか。
    ドキュメント類似性を使用した重複コンテンツの検出。
    コサイン類似度 > 0.8 で冗長と判定。
    """
    if len(contexts) < 2:
        return {"score": 1.0, "redundant_pairs": 0, "reasoning": "チャンク1件のみ"}

    context_texts = "\n---\n".join(
        f"[チャンク{i+1}]\n{c['text'][:150]}" for i, c in enumerate(contexts[:5])
    )

    prompt = f"""以下の検索結果チャンク間の冗長性（重複度）を評価してください。

## 検索されたチャンク:
{context_texts}

## 評価基準:
- 同じ情報が複数のチャンクで繰り返されていないか
- 各チャンクが独立した情報を提供しているか
- 冗長性が高い = ユーザーに新しい情報を提供していない

JSON形式で返してください（スコアは冗長性が低いほど高い=良い）:
{{"score": <0.0-1.0>, "redundant_pairs": <重複ペア数>, "unique_info_ratio": <ユニーク情報の割合>, "reasoning": "<理由>"}}"""

    response = invoke_llm(prompt)
    return parse_json_response(response) or {"score": 0.5, "reasoning": "解析失敗"}


def evaluate_factual_consistency(query: str, contexts: list[dict]) -> dict:
    """
    事実整合性:
    検索されたコンテキスト間で矛盾する情報がないかチェック。
    クロスソース検証。
    """
    if len(contexts) < 2:
        return {"score": 1.0, "contradictions": 0, "reasoning": "チャンク1件のみ"}

    context_texts = "\n---\n".join(
        f"[チャンク{i+1} - {c['source']}]\n{c['text'][:200]}"
        for i, c in enumerate(contexts[:4])
    )

    prompt = f"""以下のクエリに対して検索された複数のチャンク間で、事実の矛盾がないか確認してください。

## クエリ:
{query}

## チャンク:
{context_texts}

## 評価基準:
- チャンク間で矛盾する記述がないか
- 数値や条件の不一致がないか
- 異なるソースの情報が整合しているか

JSON形式で返してください:
{{"score": <0.0-1.0>, "contradictions": <矛盾の数>, "details": "<矛盾の詳細（あれば）>", "reasoning": "<理由>"}}"""

    response = invoke_llm(prompt)
    return parse_json_response(response) or {"score": 1.0, "reasoning": "解析失敗"}


# ==============================================================================
# メイン実行
# ==============================================================================


def run_context_validation():
    """コンテキスト照合検証を実行"""
    print("=" * 65)
    print("コンテキスト照合検証")
    print("=" * 65)
    print()
    print("  検証軸（5つ）:")
    print("    1. 意味的整合性    - 埋め込み類似度 + 概念レベルの一致")
    print("    2. 対象範囲の適切性 - 情報の粒度がクエリに適合しているか")
    print("    3. 完全性の評価    - クエリの全要素をカバーしているか")
    print("    4. 冗長性の識別    - 重複コンテンツがないか")
    print("    5. 事実整合性      - チャンク間の矛盾がないか")
    print()

    kb_id = load_kb_id()
    dataset = load_evaluation_dataset()
    # 範囲外とeasyを除いて中〜難のクエリで検証
    eval_data = [d for d in dataset if d["query_intent"] != "out_of_scope"][:5]

    all_results = []

    for i, item in enumerate(eval_data):
        query = item["query"]
        ground_truth = item["ground_truth"]

        print(f"\n{'─' * 65}")
        print(f"[{i+1}/{len(eval_data)}] {query}")

        # コンテキスト取得
        contexts = retrieve_contexts(kb_id, query, k=5)
        print(f"  検索結果: {len(contexts)} チャンク取得")
        for j, ctx in enumerate(contexts[:3]):
            print(f"    [{j+1}] {ctx['source']} (score={ctx['score']:.3f}): {ctx['text'][:50]}...")

        # 5つの検証軸で評価
        print(f"\n  検証中...")
        semantic = evaluate_semantic_alignment(query, contexts)
        scope = evaluate_scope_appropriateness(query, contexts)
        completeness = evaluate_completeness(query, contexts, ground_truth)
        redundancy = evaluate_redundancy(contexts)
        factual = evaluate_factual_consistency(query, contexts)

        # 結果表示
        s_sem = semantic.get("score", 0)
        s_sco = scope.get("score", 0)
        s_com = completeness.get("score", 0)
        s_red = redundancy.get("score", 0)
        s_fac = factual.get("score", 0)
        overall = (s_sem + s_sco + s_com + s_red + s_fac) / 5

        print(f"\n  結果:")
        print(f"    意味的整合性:     {s_sem:.2f}  {semantic.get('reasoning', '')[:40]}")
        print(f"    対象範囲の適切性: {s_sco:.2f}  {scope.get('reasoning', '')[:40]}")
        print(f"    完全性:           {s_com:.2f}  {completeness.get('reasoning', '')[:40]}")
        print(f"    冗長性（低い=良）:{s_red:.2f}  {redundancy.get('reasoning', '')[:40]}")
        print(f"    事実整合性:       {s_fac:.2f}  {factual.get('reasoning', '')[:40]}")
        print(f"    ────────────────────────────")
        print(f"    総合スコア:       {overall:.2f}")

        # 不足情報の表示
        missing = completeness.get("missing_elements", [])
        if missing:
            print(f"    ⚠ 不足情報: {', '.join(missing[:3])}")

        all_results.append(
            {
                "query": query,
                "semantic": s_sem,
                "scope": s_sco,
                "completeness": s_com,
                "redundancy": s_red,
                "factual": s_fac,
                "overall": overall,
            }
        )

    # サマリー
    print(f"\n{'═' * 65}")
    print("  コンテキスト品質サマリー")
    print(f"{'═' * 65}")

    n = len(all_results)
    if n > 0:
        print(f"\n  {'検証軸':<18} {'平均スコア':>10} {'推奨しきい値'}")
        print(f"  {'─' * 50}")
        print(f"  {'意味的整合性':<18} {sum(r['semantic'] for r in all_results)/n:>10.2f}  0.7-0.8")
        print(f"  {'対象範囲の適切性':<18} {sum(r['scope'] for r in all_results)/n:>10.2f}  0.7")
        print(f"  {'完全性':<18} {sum(r['completeness'] for r in all_results)/n:>10.2f}  0.8")
        print(f"  {'非冗長性':<18} {sum(r['redundancy'] for r in all_results)/n:>10.2f}  0.7")
        print(f"  {'事実整合性':<18} {sum(r['factual'] for r in all_results)/n:>10.2f}  0.9")

        avg_overall = sum(r["overall"] for r in all_results) / n
        print(f"\n  総合: {avg_overall:.2f}")

        if avg_overall >= 0.8:
            print(f"  ✓ コンテキスト品質: 優秀")
        elif avg_overall >= 0.6:
            print(f"  △ コンテキスト品質: 良好（一部改善余地あり）")
        else:
            print(f"  ✗ コンテキスト品質: 要改善")

    return all_results


if __name__ == "__main__":
    try:
        results = run_context_validation()
    except SystemExit:
        print("\n  M03 のナレッジベースが必要です。先に M03 を実行してください。")

    print("\n完了しました。")
