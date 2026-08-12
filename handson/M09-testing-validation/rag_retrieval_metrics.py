"""
モジュール 9 - パート 2A: 検索品質評価 - 中核のメトリクス
M03 で作成したナレッジベースの Retrieve API を使用し、
検索品質を Precision@K, Recall, MRR, NDCG, MAP で定量評価する。

スライド対応: 「検索品質評価 - 中核のメトリクス」（スライド32）
"""

import json
import math
import sys
import os

import boto3

# ==============================================================================
# 設定
# ==============================================================================

REGION = "us-east-1"
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

# M03 で作成したナレッジベースの設定を読み込む
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

    # 環境変数からフォールバック
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
    if kb_id:
        return kb_id

    print("  ❌ ナレッジベースIDが見つかりません。")
    print("     M03 のハンズオンを先に実行するか、環境変数 KNOWLEDGE_BASE_ID を設定してください。")
    print("     例: export KNOWLEDGE_BASE_ID=XXXXXXXXXX")
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


# ==============================================================================
# Retrieve API 呼び出し
# ==============================================================================


def retrieve_documents(kb_id: str, query: str, k: int = 5) -> list[dict]:
    """
    Bedrock Knowledge Base の Retrieve API を呼び出し、
    検索結果を取得する。
    """
    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": k}
        },
    )

    results = []
    for item in response.get("retrievalResults", []):
        # ソースドキュメントのファイル名を抽出
        location = item.get("location", {})
        s3_uri = ""
        if location.get("type") == "S3":
            s3_uri = location.get("s3Location", {}).get("uri", "")

        # ファイル名のみ抽出（パスの最後の部分）
        doc_name = s3_uri.split("/")[-1] if s3_uri else ""

        results.append(
            {
                "content": item.get("content", {}).get("text", ""),
                "score": item.get("score", 0.0),
                "source_uri": s3_uri,
                "doc_name": doc_name,
            }
        )

    return results


# ==============================================================================
# 検索品質メトリクス実装
# ==============================================================================


def precision_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int) -> float:
    """
    Precision@K: 上位K件の検索結果のうち、関連ドキュメントの割合

    検索した上位K件のドキュメントのうち、
    実際に関連性のあるドキュメントの割合を示す。
    """
    top_k = retrieved_docs[:k]
    if not top_k:
        return 0.0
    relevant_count = sum(1 for doc in top_k if doc in relevant_docs)
    return relevant_count / k


def recall_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int) -> float:
    """
    Recall@K（再現率）: 全関連ドキュメントのうち、上位K件に含まれる割合

    ナレッジベースに存在する全ての関連ドキュメントのうち、
    検索結果の上位K件で検出されたものの割合。
    """
    if not relevant_docs:
        return 0.0
    top_k = retrieved_docs[:k]
    found = sum(1 for doc in relevant_docs if doc in top_k)
    return found / len(relevant_docs)


def mrr(retrieved_docs: list[str], relevant_docs: list[str]) -> float:
    """
    MRR（Mean Reciprocal Rank: 平均逆順位）:
    最初の関連ドキュメントが何番目に現れるかの逆数。

    ユーザーが必要な情報をどれだけ早く見つけられるかに焦点を当てる。
    """
    for i, doc in enumerate(retrieved_docs):
        if doc in relevant_docs:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int) -> float:
    """
    NDCG@K（Normalized Discounted Cumulative Gain: 正規化割引累積利益）:
    関連性とランキング順位を結び付け、関連性の高いドキュメントが
    検索結果の上位に表示されるほどスコアが高くなる。

    対数割引を使用して上位の結果に高い重みを付ける。
    """
    top_k = retrieved_docs[:k]

    # DCG (Discounted Cumulative Gain)
    dcg = 0.0
    for i, doc in enumerate(top_k):
        rel = 1.0 if doc in relevant_docs else 0.0
        dcg += rel / math.log2(i + 2)  # log2(rank + 1), rank は 1-indexed

    # IDCG (Ideal DCG) - 全て関連する場合の最大値
    ideal_count = min(len(relevant_docs), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))

    if idcg == 0:
        return 0.0
    return dcg / idcg


def average_precision(retrieved_docs: list[str], relevant_docs: list[str]) -> float:
    """
    AP（Average Precision）: MAPの構成要素。
    各関連ドキュメントが見つかった位置でのPrecisionの平均。

    関連するドキュメントのランキング位置全体を考慮する。
    """
    if not relevant_docs:
        return 0.0

    hits = 0
    sum_precision = 0.0

    for i, doc in enumerate(retrieved_docs):
        if doc in relevant_docs:
            hits += 1
            sum_precision += hits / (i + 1)

    return sum_precision / len(relevant_docs)


def mean_average_precision(all_results: list[dict]) -> float:
    """
    MAP（Mean Average Precision: 平均平均適合率）:
    全クエリの Average Precision の平均。
    検索システム全体の品質を示す単一の数値。
    """
    aps = [r["average_precision"] for r in all_results]
    return sum(aps) / len(aps) if aps else 0.0


# ==============================================================================
# メイン実行
# ==============================================================================


def run_retrieval_evaluation(k: int = 5):
    """検索品質評価を実行"""
    print("=" * 65)
    print("検索品質評価 - 中核のメトリクス")
    print("=" * 65)
    print()
    print("  RAG評価の課題（従来のソフトウェアテストとの違い）:")
    print("    従来: 決定論的 / 単一コンポーネント / 客観的メトリクス")
    print("    RAG:  確率的   / 複数コンポーネント / 主観的な品質測定")
    print()

    kb_id = load_kb_id()
    print(f"  ナレッジベースID: {kb_id}")

    dataset = load_evaluation_dataset()
    # 範囲外クエリを除外（検索品質の評価には使わない）
    eval_dataset = [d for d in dataset if d["query_intent"] != "out_of_scope"]
    print(f"  評価データセット: {len(eval_dataset)} 件（範囲外除外）")
    print(f"  検索件数 K: {k}")

    all_results = []

    print(f"\n{'─' * 65}")
    print(f"  {'クエリ':<30} {'P@{k}':>6} {'R@{k}':>6} {'MRR':>6} {'NDCG':>6} {'AP':>6}")
    print(f"{'─' * 65}")

    for item in eval_dataset:
        query = item["query"]
        relevant_docs = item["relevant_doc_ids"]

        # Retrieve API 実行
        search_results = retrieve_documents(kb_id, query, k=k)
        retrieved_doc_names = [r["doc_name"] for r in search_results]

        # メトリクス計算
        p_at_k = precision_at_k(retrieved_doc_names, relevant_docs, k)
        r_at_k = recall_at_k(retrieved_doc_names, relevant_docs, k)
        mrr_score = mrr(retrieved_doc_names, relevant_docs)
        ndcg_score = ndcg_at_k(retrieved_doc_names, relevant_docs, k)
        ap_score = average_precision(retrieved_doc_names, relevant_docs)

        result = {
            "query": query,
            "category": item["category"],
            "difficulty": item["difficulty"],
            "retrieved_docs": retrieved_doc_names,
            "relevant_docs": relevant_docs,
            "precision_at_k": p_at_k,
            "recall_at_k": r_at_k,
            "mrr": mrr_score,
            "ndcg_at_k": ndcg_score,
            "average_precision": ap_score,
            "search_results": search_results,
        }
        all_results.append(result)

        # 表示（クエリを切り詰め）
        q_display = query[:28] + ".." if len(query) > 30 else query
        print(
            f"  {q_display:<30} {p_at_k:>6.2f} {r_at_k:>6.2f} "
            f"{mrr_score:>6.2f} {ndcg_score:>6.2f} {ap_score:>6.2f}"
        )

    # ==============================================================================
    # サマリー
    # ==============================================================================
    print(f"\n{'═' * 65}")
    print("  集計結果")
    print(f"{'═' * 65}")

    n = len(all_results)
    avg_p = sum(r["precision_at_k"] for r in all_results) / n
    avg_r = sum(r["recall_at_k"] for r in all_results) / n
    avg_mrr = sum(r["mrr"] for r in all_results) / n
    avg_ndcg = sum(r["ndcg_at_k"] for r in all_results) / n
    map_score = mean_average_precision(all_results)

    print(f"\n  {'メトリクス':<25} {'スコア':>8} {'説明'}")
    print(f"  {'─' * 60}")
    print(f"  {'Precision@' + str(k):<25} {avg_p:>8.3f}  上位{k}件の関連率")
    print(f"  {'Recall@' + str(k):<25} {avg_r:>8.3f}  関連文書の検索率")
    print(f"  {'MRR':<25} {avg_mrr:>8.3f}  最初の正解の順位（逆数）")
    print(f"  {'NDCG@' + str(k):<25} {avg_ndcg:>8.3f}  ランキング品質（位置考慮）")
    print(f"  {'MAP':<25} {map_score:>8.3f}  全体の検索精度（総合指標）")

    # 難易度別分析
    print(f"\n  難易度別スコア:")
    for difficulty in ["easy", "medium", "hard"]:
        subset = [r for r in all_results if r["difficulty"] == difficulty]
        if subset:
            d_map = sum(r["average_precision"] for r in subset) / len(subset)
            d_mrr = sum(r["mrr"] for r in subset) / len(subset)
            print(f"    {difficulty:<8}: MAP={d_map:.3f}, MRR={d_mrr:.3f} ({len(subset)}件)")

    # 品質判定
    print(f"\n  品質判定:")
    if map_score >= 0.8:
        print(f"    ✓ 検索品質: 優秀 (MAP={map_score:.3f} ≥ 0.8)")
    elif map_score >= 0.6:
        print(f"    △ 検索品質: 良好 (MAP={map_score:.3f} ≥ 0.6)")
        print(f"      → チャンキング戦略やnumberOfResults の調整を検討")
    else:
        print(f"    ✗ 検索品質: 要改善 (MAP={map_score:.3f} < 0.6)")
        print(f"      → 埋め込みモデル変更、ハイブリッド検索(OpenSearch)の導入を検討")

    return all_results


# ==============================================================================
# モックモード（M03 未実施の場合）
# ==============================================================================


def run_mock_evaluation(k: int = 5):
    """M03 のナレッジベースが利用できない場合のモックデモ"""
    print("=" * 65)
    print("検索品質評価 - 中核のメトリクス（モックモード）")
    print("=" * 65)
    print("\n  ※ M03 のナレッジベースが利用できないため、モックデータで実行します。")

    # シミュレーション結果
    mock_results = [
        {
            "query": "契約書の解除条件について教えてください",
            "retrieved_docs": ["contract_template.txt", "contract_template.txt", "employment_law.txt"],
            "relevant_docs": ["contract_template.txt"],
            "precision_at_k": 0.40,
            "recall_at_k": 1.00,
            "mrr": 1.00,
            "ndcg_at_k": 1.00,
            "average_precision": 1.00,
        },
        {
            "query": "個人情報の第三者提供に関する規制は？",
            "retrieved_docs": ["privacy_regulation.txt", "privacy_regulation.txt", "contract_template.txt"],
            "relevant_docs": ["privacy_regulation.txt"],
            "precision_at_k": 0.40,
            "recall_at_k": 1.00,
            "mrr": 1.00,
            "ndcg_at_k": 1.00,
            "average_precision": 1.00,
        },
        {
            "query": "従業員の残業規制について説明してください",
            "retrieved_docs": ["employment_law.txt", "employment_law.txt", "contract_template.txt"],
            "relevant_docs": ["employment_law.txt"],
            "precision_at_k": 0.40,
            "recall_at_k": 1.00,
            "mrr": 1.00,
            "ndcg_at_k": 1.00,
            "average_precision": 1.00,
        },
        {
            "query": "個人情報保護法の罰則規定と契約違反時の損害賠償の関係",
            "retrieved_docs": ["privacy_regulation.txt", "contract_template.txt", "employment_law.txt"],
            "relevant_docs": ["privacy_regulation.txt", "contract_template.txt"],
            "precision_at_k": 0.40,
            "recall_at_k": 1.00,
            "mrr": 1.00,
            "ndcg_at_k": 0.88,
            "average_precision": 1.00,
        },
    ]

    n = len(mock_results)
    avg_p = sum(r["precision_at_k"] for r in mock_results) / n
    avg_mrr = sum(r["mrr"] for r in mock_results) / n
    map_score = sum(r["average_precision"] for r in mock_results) / n

    print(f"\n  Precision@{k}: {avg_p:.3f}")
    print(f"  MRR:          {avg_mrr:.3f}")
    print(f"  MAP:          {map_score:.3f}")
    print(f"\n  ✓ 検索品質: 優秀（モックデータ）")

    return mock_results


if __name__ == "__main__":
    try:
        results = run_retrieval_evaluation(k=5)
    except SystemExit:
        print("\n  フォールバック: モックモードで実行します。")
        results = run_mock_evaluation(k=5)

    print("\n完了しました。")
