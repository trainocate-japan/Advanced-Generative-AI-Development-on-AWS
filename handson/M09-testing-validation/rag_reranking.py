"""
モジュール 9 - パート 2B: Re-ranking による検索品質の改善
Bedrock の Rerank API および Knowledge Base の rerankingConfiguration を使用し、
Re-ranking 前後での検索品質の差を定量的に比較する。

目的:
  - Re-ranking の効果を Precision@K, MRR, NDCG で定量評価
  - Bedrock Rerank API（直接呼び出し）の使い方を学ぶ
  - Knowledge Base Retrieve API に rerankingConfiguration を組み込む方法を学ぶ
"""

import json
import math
import os
import sys
import time

import boto3

# ==============================================================================
# 設定
# ==============================================================================

REGION = "us-east-1"
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

# Cohere Rerank v3.5 モデル ARN
RERANK_MODEL_ARN = f"arn:aws:bedrock:{REGION}::foundation-model/cohere.rerank-v3-5:0"

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
# 検索品質メトリクス（rag_retrieval_metrics.py と同じ計算ロジック）
# ==============================================================================


def precision_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int) -> float:
    """Precision@K: 上位K件のうち関連ドキュメントの割合"""
    top_k = retrieved_docs[:k]
    if not top_k:
        return 0.0
    relevant_count = sum(1 for doc in top_k if doc in relevant_docs)
    return relevant_count / k


def recall_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int) -> float:
    """Recall@K: 全関連ドキュメントのうち上位K件に含まれる割合"""
    if not relevant_docs:
        return 0.0
    top_k = retrieved_docs[:k]
    found = sum(1 for doc in relevant_docs if doc in top_k)
    return found / len(relevant_docs)


def mrr(retrieved_docs: list[str], relevant_docs: list[str]) -> float:
    """MRR: 最初の関連ドキュメントの逆順位"""
    for i, doc in enumerate(retrieved_docs):
        if doc in relevant_docs:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int) -> float:
    """NDCG@K: 正規化割引累積利益"""
    top_k = retrieved_docs[:k]
    dcg = 0.0
    for i, doc in enumerate(top_k):
        rel = 1.0 if doc in relevant_docs else 0.0
        dcg += rel / math.log2(i + 2)
    ideal_count = min(len(relevant_docs), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))
    if idcg == 0:
        return 0.0
    return dcg / idcg


# ==============================================================================
# パート 1: Bedrock Rerank API の直接呼び出し
# ==============================================================================


def demo_rerank_api_direct():
    """
    Rerank API を直接呼び出すデモ。
    ベクトル検索で取得したドキュメントリストを Re-ranking モデルで並べ替える。
    """
    print("=" * 70)
    print("  パート 1: Bedrock Rerank API の直接呼び出し")
    print("=" * 70)
    print()
    print("  Re-ranking とは:")
    print("    ベクトル検索（セマンティック検索）の結果を、より高精度な")
    print("    言語モデル（Cross-Encoder）で再スコアリング・並べ替えすること。")
    print()
    print("  なぜ必要か:")
    print("    - ベクトル検索は高速だが、クエリと文書の細かい関連性を見落とすことがある")
    print("    - Re-ranking は遅いが、クエリと各文書を直接比較して正確にスコアリング")
    print("    - 2段階パイプライン: 高速検索(候補生成) → Re-ranking(精密選別)")
    print()

    # サンプルクエリとドキュメント
    query = "契約書の解除条件について教えてください"
    documents = [
        "第7条（契約の解除）甲又は乙は、相手方が本契約に違反し、催告後30日以内に是正されない場合、本契約を解除することができる。天災等の不可抗力により履行不能となった場合も同様とする。",
        "第12条（秘密保持）甲及び乙は、本契約の履行に際して知り得た相手方の技術上又は営業上の秘密を第三者に漏洩してはならない。本条の規定は契約終了後5年間存続する。",
        "第8条（損害賠償）本契約に違反した当事者は、相手方に生じた損害を賠償する責任を負う。ただし、損害賠償の額は、本契約の契約金額を上限とする。",
        "第3条（契約期間）本契約の有効期間は、契約締結日から1年間とする。期間満了の3ヶ月前までに甲乙いずれからも書面による終了の意思表示がない場合、同一条件で1年間自動更新される。",
        "個人情報保護法第23条に基づき、個人データの第三者提供には原則として本人の同意が必要である。ただし、法令に基づく場合はこの限りではない。",
    ]

    print(f"  クエリ: {query}")
    print(f"  候補ドキュメント数: {len(documents)}")
    print()

    # Rerank API 呼び出し
    print("  ── Rerank API 呼び出し ──")
    print()

    sources = []
    for doc in documents:
        sources.append({
            "type": "INLINE",
            "inlineDocumentSource": {
                "type": "TEXT",
                "textDocument": {"text": doc},
            },
        })

    try:
        start_time = time.time()
        response = bedrock_agent_runtime.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": query}}],
            sources=sources,
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {"modelArn": RERANK_MODEL_ARN},
                    "numberOfResults": len(documents),
                },
            },
        )
        elapsed = time.time() - start_time

        print(f"  レスポンス時間: {elapsed:.3f}秒")
        print(f"  モデル: Cohere Rerank v3.5")
        print()
        print(f"  {'順位':<4} {'元の位置':<8} {'関連度スコア':<14} {'テキスト（先頭60文字）'}")
        print(f"  {'─' * 65}")

        for rank, result in enumerate(response["results"], 1):
            idx = result["index"]
            score = result["relevanceScore"]
            text_preview = documents[idx][:60].replace("\n", " ")
            print(f"  {rank:<4} [{idx+1}]      {score:<14.6f} {text_preview}...")

        print()
        print("  解説:")
        print("    - 元の位置 [1] の「契約の解除」に関する文書が最上位に")
        print("    - 元の位置 [3] の「損害賠償」も解除と関連するため上位")
        print("    - 「個人情報保護法」は解除条件と無関係なため最下位")
        print()

    except Exception as e:
        print(f"  ❌ Rerank API エラー: {e}")
        print()
        print("  考えられる原因:")
        print("    - Cohere Rerank v3.5 モデルへのアクセス権限がない")
        print("    - リージョンでモデルが利用できない")
        print("    - Bedrock コンソールでモデルアクセスを有効化してください")
        print()
        demo_rerank_api_mock()


def demo_rerank_api_mock():
    """Rerank API のモック結果表示"""
    print("  ── モックモード: Rerank API の想定結果 ──")
    print()
    mock_results = [
        {"rank": 1, "original_pos": 1, "score": 0.987, "text": "第7条（契約の解除）甲又は乙は、相手方が本契約に違反し..."},
        {"rank": 2, "original_pos": 3, "score": 0.621, "text": "第8条（損害賠償）本契約に違反した当事者は..."},
        {"rank": 3, "original_pos": 4, "score": 0.312, "text": "第3条（契約期間）本契約の有効期間は..."},
        {"rank": 4, "original_pos": 2, "score": 0.089, "text": "第12条（秘密保持）甲及び乙は..."},
        {"rank": 5, "original_pos": 5, "score": 0.023, "text": "個人情報保護法第23条に基づき..."},
    ]
    print(f"  {'順位':<4} {'元の位置':<8} {'関連度スコア':<14} {'テキスト'}")
    print(f"  {'─' * 65}")
    for r in mock_results:
        print(f"  {r['rank']:<4} [{r['original_pos']}]      {r['score']:<14.3f} {r['text']}")
    print()


# ==============================================================================
# パート 2: Knowledge Base Retrieve API + Re-ranking
# ==============================================================================


def retrieve_without_reranking(kb_id: str, query: str, k: int = 10) -> list[dict]:
    """Re-ranking なしの通常の Retrieve API 呼び出し"""
    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": k}
        },
    )
    results = []
    for item in response.get("retrievalResults", []):
        location = item.get("location", {})
        s3_uri = location.get("s3Location", {}).get("uri", "") if location.get("type") == "S3" else ""
        doc_name = s3_uri.split("/")[-1] if s3_uri else ""
        results.append({
            "content": item.get("content", {}).get("text", ""),
            "score": item.get("score", 0.0),
            "source_uri": s3_uri,
            "doc_name": doc_name,
        })
    return results


def retrieve_with_reranking(kb_id: str, query: str, k: int = 10, top_n: int = 5) -> list[dict]:
    """
    Re-ranking 付きの Retrieve API 呼び出し。
    vectorSearchConfiguration 内の rerankingConfiguration を使用。

    パラメータ:
        kb_id: ナレッジベースID
        query: 検索クエリ
        k: 初期検索で取得する候補数（Re-ranking の入力）
        top_n: Re-ranking 後に返す上位件数
    """
    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": k,
                "rerankingConfiguration": {
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {
                        "modelConfiguration": {
                            "modelArn": RERANK_MODEL_ARN,
                        },
                        "numberOfRerankedResults": top_n,
                    },
                },
            }
        },
    )
    results = []
    for item in response.get("retrievalResults", []):
        location = item.get("location", {})
        s3_uri = location.get("s3Location", {}).get("uri", "") if location.get("type") == "S3" else ""
        doc_name = s3_uri.split("/")[-1] if s3_uri else ""
        results.append({
            "content": item.get("content", {}).get("text", ""),
            "score": item.get("score", 0.0),
            "source_uri": s3_uri,
            "doc_name": doc_name,
        })
    return results


def demo_kb_reranking_comparison():
    """
    Knowledge Base の検索結果を Re-ranking あり/なしで比較し、
    メトリクスの改善を定量的に示す。
    """
    print("\n\n" + "=" * 70)
    print("  パート 2: Knowledge Base Retrieve API + Re-ranking 比較")
    print("=" * 70)
    print()
    print("  2段階検索パイプライン:")
    print("    ┌─────────────────────────────────────────────────────────┐")
    print("    │  Stage 1: ベクトル検索（高速・大量候補を取得）          │")
    print("    │    numberOfResults = 10〜20（候補を広めに取得）         │")
    print("    │                        ↓                                │")
    print("    │  Stage 2: Re-ranking（精密・上位を選別）                │")
    print("    │    numberOfRerankedResults = 3〜5（最終結果）           │")
    print("    └─────────────────────────────────────────────────────────┘")
    print()

    kb_id = load_kb_id()
    dataset = load_evaluation_dataset()
    eval_dataset = [d for d in dataset if d["query_intent"] != "out_of_scope"]

    print(f"  ナレッジベースID: {kb_id}")
    print(f"  評価データセット: {len(eval_dataset)} 件")
    print(f"  比較条件:")
    print(f"    - ベースライン: Retrieve API（numberOfResults=5, Re-ranking なし）")
    print(f"    - Re-ranking: Retrieve API（numberOfResults=10 → Re-rank → 上位5件）")
    print()

    k = 5
    initial_candidates = 10  # Re-ranking の入力候補数

    results_baseline = []
    results_reranked = []

    print(f"{'─' * 70}")
    print(f"  {'クエリ':<30} {'ベースライン MRR':>14} {'Re-rank MRR':>12} {'改善':>6}")
    print(f"{'─' * 70}")

    for item in eval_dataset:
        query = item["query"]
        relevant_docs = item["relevant_doc_ids"]

        # ベースライン（Re-ranking なし）
        try:
            baseline_results = retrieve_without_reranking(kb_id, query, k=k)
            baseline_doc_names = [r["doc_name"] for r in baseline_results]
        except Exception as e:
            print(f"  ❌ ベースライン検索エラー: {e}")
            return

        # Re-ranking あり
        try:
            reranked_results = retrieve_with_reranking(
                kb_id, query, k=initial_candidates, top_n=k
            )
            reranked_doc_names = [r["doc_name"] for r in reranked_results]
        except Exception as e:
            print(f"  ⚠ Re-ranking エラー（モデルアクセス確認）: {e}")
            print("    → モックモードに切り替えます")
            demo_kb_reranking_mock()
            return

        # メトリクス計算
        b_mrr = mrr(baseline_doc_names, relevant_docs)
        r_mrr = mrr(reranked_doc_names, relevant_docs)

        results_baseline.append({
            "query": query,
            "precision_at_k": precision_at_k(baseline_doc_names, relevant_docs, k),
            "recall_at_k": recall_at_k(baseline_doc_names, relevant_docs, k),
            "mrr": b_mrr,
            "ndcg_at_k": ndcg_at_k(baseline_doc_names, relevant_docs, k),
        })
        results_reranked.append({
            "query": query,
            "precision_at_k": precision_at_k(reranked_doc_names, relevant_docs, k),
            "recall_at_k": recall_at_k(reranked_doc_names, relevant_docs, k),
            "mrr": r_mrr,
            "ndcg_at_k": ndcg_at_k(reranked_doc_names, relevant_docs, k),
        })

        q_display = query[:28] + ".." if len(query) > 30 else query
        improvement = r_mrr - b_mrr
        arrow = "↑" if improvement > 0 else ("→" if improvement == 0 else "↓")
        print(f"  {q_display:<30} {b_mrr:>10.3f}     {r_mrr:>8.3f}   {arrow} {improvement:+.3f}")

        time.sleep(0.5)  # API レート制限対策

    # サマリー
    print_comparison_summary(results_baseline, results_reranked, k)


def print_comparison_summary(results_baseline: list, results_reranked: list, k: int):
    """ベースライン vs Re-ranking の比較サマリーを表示"""
    print(f"\n{'═' * 70}")
    print("  比較サマリー: ベースライン vs Re-ranking")
    print(f"{'═' * 70}")

    n = len(results_baseline)
    metrics = ["precision_at_k", "recall_at_k", "mrr", "ndcg_at_k"]
    metric_labels = {
        "precision_at_k": f"Precision@{k}",
        "recall_at_k": f"Recall@{k}",
        "mrr": "MRR",
        "ndcg_at_k": f"NDCG@{k}",
    }

    print(f"\n  {'メトリクス':<15} {'ベースライン':>10} {'Re-ranking':>10} {'差分':>8} {'改善率':>8}")
    print(f"  {'─' * 55}")

    for metric in metrics:
        base_avg = sum(r[metric] for r in results_baseline) / n
        rerank_avg = sum(r[metric] for r in results_reranked) / n
        diff = rerank_avg - base_avg
        improvement_pct = (diff / base_avg * 100) if base_avg > 0 else 0

        label = metric_labels[metric]
        arrow = "↑" if diff > 0 else ("→" if diff == 0 else "↓")
        print(
            f"  {label:<15} {base_avg:>10.3f} {rerank_avg:>10.3f} "
            f"{arrow} {diff:>+6.3f} {improvement_pct:>+7.1f}%"
        )

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  Re-ranking の効果まとめ                                          │
  │                                                                   │
  │  ✓ MRR の改善: 最初の正解が上位に来やすくなる                    │
  │  ✓ NDCG の改善: ランキング品質全体が向上                         │
  │  ✓ Precision の改善: 上位K件の関連率が向上                       │
  │                                                                   │
  │  トレードオフ:                                                    │
  │  ⚠ レイテンシー増加: Re-ranking モデル呼び出し分の追加時間       │
  │  ⚠ コスト増加: Re-ranking モデルの推論コスト                     │
  │  ⚠ 候補数の設定: 少なすぎると効果薄、多すぎるとコスト増         │
  │                                                                   │
  │  推奨設定:                                                        │
  │    初期候補（numberOfResults）: 10〜20                            │
  │    最終結果（numberOfRerankedResults）: 3〜5                      │
  └──────────────────────────────────────────────────────────────────┘
    """)


# ==============================================================================
# パート 3: Re-ranking パラメータのチューニング
# ==============================================================================


def demo_reranking_tuning():
    """
    Re-ranking の候補数パラメータを変えて効果を比較する。
    候補数が多いほど精度は上がるが、コストとレイテンシーも増加する。
    """
    print("\n" + "=" * 70)
    print("  パート 3: Re-ranking パラメータのチューニング")
    print("=" * 70)
    print()
    print("  初期候補数（numberOfResults）を変えた際の効果を検証:")
    print("    - 候補数が少ない: Re-ranking の効果が限定的")
    print("    - 候補数が多い: 精度向上するが、コスト・レイテンシー増加")
    print()

    kb_id = load_kb_id()
    dataset = load_evaluation_dataset()
    eval_dataset = [d for d in dataset if d["query_intent"] != "out_of_scope"]

    top_n = 3  # 最終結果の件数を固定
    candidate_counts = [5, 10, 20]  # 初期候補数を変化

    print(f"  最終結果数（numberOfRerankedResults）: {top_n} 固定")
    print(f"  初期候補数（numberOfResults）: {candidate_counts}")
    print()

    for num_candidates in candidate_counts:
        mrr_scores = []
        ndcg_scores = []
        total_time = 0

        for item in eval_dataset:
            query = item["query"]
            relevant_docs = item["relevant_doc_ids"]

            start = time.time()
            try:
                results = retrieve_with_reranking(
                    kb_id, query, k=num_candidates, top_n=top_n
                )
                elapsed = time.time() - start
                total_time += elapsed

                doc_names = [r["doc_name"] for r in results]
                mrr_scores.append(mrr(doc_names, relevant_docs))
                ndcg_scores.append(ndcg_at_k(doc_names, relevant_docs, top_n))

            except Exception as e:
                print(f"  ⚠ エラー（候補数={num_candidates}）: {e}")
                demo_reranking_tuning_mock()
                return

            time.sleep(0.3)

        avg_mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0
        avg_ndcg = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0
        avg_time = total_time / len(eval_dataset)

        print(f"  候補数 = {num_candidates:>2}: MRR={avg_mrr:.3f} | NDCG@{top_n}={avg_ndcg:.3f} | 平均レイテンシー={avg_time:.3f}秒")

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  パラメータ選択の指針                                              │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                   │
  │  候補数 5:  レイテンシー最小 / コスト最小 / 効果限定的            │
  │            → リアルタイム応答が必須の場合                         │
  │                                                                   │
  │  候補数 10: バランス型（推奨）                                    │
  │            → 一般的な RAG ユースケース                            │
  │                                                                   │
  │  候補数 20: 精度最大 / コスト・レイテンシー増加                   │
  │            → 正確性が最重要（法律、医療等）                      │
  │                                                                   │
  │  ※ 候補数 > 20 は精度改善の飽和が見られることが多い              │
  └──────────────────────────────────────────────────────────────────┘
    """)


# ==============================================================================
# モックモード
# ==============================================================================


def demo_kb_reranking_mock():
    """Re-ranking 比較のモック結果"""
    print()
    print("  ── モックモード: Re-ranking の想定改善効果 ──")
    print()
    print(f"  {'メトリクス':<15} {'ベースライン':>10} {'Re-ranking':>10} {'差分':>8} {'改善率':>8}")
    print(f"  {'─' * 55}")
    print(f"  {'Precision@5':<15} {'0.440':>10} {'0.560':>10} {'↑ +0.120':>8} {'+27.3%':>8}")
    print(f"  {'Recall@5':<15} {'0.857':>10} {'0.929':>10} {'↑ +0.072':>8} {'+8.4%':>8}")
    print(f"  {'MRR':<15} {'0.786':>10} {'0.929':>10} {'↑ +0.143':>8} {'+18.2%':>8}")
    print(f"  {'NDCG@5':<15} {'0.762':>10} {'0.891':>10} {'↑ +0.129':>8} {'+16.9%':>8}")
    print()
    print("  → Re-ranking により全メトリクスが改善（特に MRR と NDCG）")
    print()


def demo_reranking_tuning_mock():
    """チューニングのモック結果"""
    print()
    print("  ── モックモード: パラメータチューニング想定結果 ──")
    print()
    print(f"  候補数 =  5: MRR=0.857 | NDCG@3=0.810 | 平均レイテンシー=0.62秒")
    print(f"  候補数 = 10: MRR=0.929 | NDCG@3=0.891 | 平均レイテンシー=0.85秒")
    print(f"  候補数 = 20: MRR=0.952 | NDCG@3=0.912 | 平均レイテンシー=1.21秒")
    print()
    print("  → 候補数 10 がコストとパフォーマンスのバランスが良い")
    print()


# ==============================================================================
# メイン実行
# ==============================================================================


if __name__ == "__main__":
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  モジュール 9 - Re-ranking による検索品質の改善                     ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()

    # パート 1: Rerank API の直接呼び出し
    demo_rerank_api_direct()

    # パート 2: Knowledge Base + Re-ranking 比較
    try:
        demo_kb_reranking_comparison()
    except SystemExit:
        print("\n  フォールバック: モックモードで実行します。")
        demo_kb_reranking_mock()

    # パート 3: パラメータチューニング
    try:
        demo_reranking_tuning()
    except SystemExit:
        demo_reranking_tuning_mock()

    print("\n" + "=" * 70)
    print("  完了: Re-ranking ハンズオン")
    print("=" * 70)
    print()
    print("  次のステップ:")
    print("    → ステップ 2.2: コンテキスト照合検証 (rag_context_validation.py)")
    print("    → ステップ 2.3: 生成評価 (rag_generation_evaluation.py)")
    print()
