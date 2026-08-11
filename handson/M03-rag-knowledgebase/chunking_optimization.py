"""
モジュール 3: チャンキング最適化
- 固定サイズ / 階層型 / セマンティック チャンキングの比較
- 各戦略のパラメータ調整と影響分析
- ドキュメントタイプに応じた最適戦略の選定
- Bedrock ナレッジベースでのチャンキング設定変更手順
"""

import boto3
import json
import time
import os

# AWS クライアント
bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# 設定読み込み
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "kb_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

config = load_config()
KNOWLEDGE_BASE_ID = config.get("knowledge_base_id", "YOUR_KB_ID")


# ═══════════════════════════════════════════════════════════════════════
#  チャンキング設定テンプレート
# ═══════════════════════════════════════════════════════════════════════

CHUNKING_CONFIGS = {
    "fixed_size_small": {
        "name": "固定サイズ（小）",
        "description": "300トークン / オーバーラップ20%",
        "config": {
            "chunkingStrategy": "FIXED_SIZE",
            "fixedSizeChunkingConfiguration": {
                "maxTokens": 300,
                "overlapPercentage": 20
            }
        },
        "best_for": ["FAQ", "短文ドキュメント", "Q&Aデータ"],
        "trade_offs": "精度高いが文脈が失われやすい"
    },
    "fixed_size_large": {
        "name": "固定サイズ（大）",
        "description": "1000トークン / オーバーラップ10%",
        "config": {
            "chunkingStrategy": "FIXED_SIZE",
            "fixedSizeChunkingConfiguration": {
                "maxTokens": 1000,
                "overlapPercentage": 10
            }
        },
        "best_for": ["長文ドキュメント", "技術文書", "レポート"],
        "trade_offs": "文脈保持できるが検索ノイズが増える"
    },
    "hierarchical": {
        "name": "階層型",
        "description": "親1500トークン / 子300トークン / オーバーラップ60トークン",
        "config": {
            "chunkingStrategy": "HIERARCHICAL",
            "hierarchicalChunkingConfiguration": {
                "levelConfigurations": [
                    {"maxTokens": 1500},
                    {"maxTokens": 300}
                ],
                "overlapTokens": 60
            }
        },
        "best_for": ["構造化文書", "法律文書", "マニュアル"],
        "trade_offs": "セクション構造を保持、設定が複雑"
    },
    "semantic": {
        "name": "セマンティック",
        "description": "意味的境界で分割 / 最大1000トークン",
        "config": {
            "chunkingStrategy": "SEMANTIC",
            "semanticChunkingConfiguration": {
                "maxTokens": 1000,
                "bufferSize": 0,
                "breakpointPercentileThreshold": 95
            }
        },
        "best_for": ["混合コンテンツ", "会話ログ", "ニュース記事"],
        "trade_offs": "最も自然な分割だがコスト高（埋め込みモデル使用）"
    },
    "none": {
        "name": "チャンキングなし",
        "description": "ドキュメント全体を1チャンクとして扱う",
        "config": {
            "chunkingStrategy": "NONE"
        },
        "best_for": ["短いドキュメント（< 500トークン）", "メタデータのみ"],
        "trade_offs": "長文には不適切（トークン制限超過の可能性）"
    }
}


# ═══════════════════════════════════════════════════════════════════════
#  チャンキング設定の適用
# ═══════════════════════════════════════════════════════════════════════

def create_data_source_with_chunking(kb_id, bucket_arn, chunking_key, ds_name_suffix=""):
    """
    指定したチャンキング設定でデータソースを作成

    注意: チャンキング設定はデータソース作成時にのみ指定可能。
    既存のデータソースのチャンキングは変更できない。
    比較する場合は、同一 KB に複数のデータソースを作成する。
    """
    chunking_config = CHUNKING_CONFIGS[chunking_key]["config"]
    ds_name = f"legal-docs-{chunking_key}{ds_name_suffix}"

    try:
        response = bedrock_agent.create_data_source(
            knowledgeBaseId=kb_id,
            name=ds_name,
            description=f"チャンキング比較: {CHUNKING_CONFIGS[chunking_key]['name']}",
            dataSourceConfiguration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": bucket_arn,
                    "inclusionPrefixes": ["documents/"]
                }
            },
            vectorIngestionConfiguration={
                "chunkingConfiguration": chunking_config
            }
        )

        ds_id = response['dataSource']['dataSourceId']
        print(f"  ✅ データソース作成: {ds_name} (ID: {ds_id})")
        return ds_id

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        return None


def sync_and_wait(kb_id, ds_id):
    """データソースを同期して完了を待機"""
    try:
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id
        )
        job_id = response['ingestionJob']['ingestionJobId']

        while True:
            status_resp = bedrock_agent.get_ingestion_job(
                knowledgeBaseId=kb_id,
                dataSourceId=ds_id,
                ingestionJobId=job_id
            )
            status = status_resp['ingestionJob']['status']
            if status in ['COMPLETE', 'FAILED']:
                break
            time.sleep(5)

        if status == 'COMPLETE':
            stats = status_resp['ingestionJob'].get('statistics', {})
            return {
                "success": True,
                "documents_scanned": stats.get('numberOfDocumentsScanned', 0),
                "documents_indexed": stats.get('numberOfNewDocumentsIndexed', 0),
                "chunks_created": stats.get('numberOfMetadataDocumentsModified', 0)
            }
        return {"success": False, "status": status}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
#  チャンキング比較評価
# ═══════════════════════════════════════════════════════════════════════

def evaluate_chunking_quality(query, kb_id=None, num_results=5):
    """
    検索品質メトリクスを計算

    - Precision@K: 上位K件中の関連チャンク割合
    - 平均スコア: 検索結果の平均類似度スコア
    - スコア分散: スコアのばらつき（低い方が安定）
    """
    kb_id = kb_id or KNOWLEDGE_BASE_ID

    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": num_results,
                    "overrideSearchType": "SEMANTIC"
                }
            }
        )

        results = response.get('retrievalResults', [])
        scores = [r.get('score', 0) for r in results]

        if not scores:
            return {"avg_score": 0, "max_score": 0, "min_score": 0, "std_dev": 0}

        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        # テキスト長の統計
        text_lengths = [len(r.get('content', {}).get('text', '')) for r in results]
        avg_length = sum(text_lengths) / len(text_lengths) if text_lengths else 0

        return {
            "avg_score": avg_score,
            "max_score": max_score,
            "min_score": min_score,
            "std_dev": std_dev,
            "avg_chunk_length": avg_length,
            "num_results": len(results)
        }

    except Exception as e:
        return {"error": str(e)}


def run_chunking_comparison(queries, kb_id=None):
    """
    複数クエリで検索品質を測定し、チャンキング設定の効果を比較

    注意: 実際の比較には、異なるチャンキング設定で作成した
    複数のデータソースまたはナレッジベースが必要
    """
    kb_id = kb_id or KNOWLEDGE_BASE_ID
    all_metrics = []

    for query in queries:
        metrics = evaluate_chunking_quality(query, kb_id)
        metrics["query"] = query
        all_metrics.append(metrics)

    # 集計
    if all_metrics and "avg_score" in all_metrics[0]:
        overall = {
            "avg_score": sum(m["avg_score"] for m in all_metrics) / len(all_metrics),
            "avg_max_score": sum(m["max_score"] for m in all_metrics) / len(all_metrics),
            "avg_std_dev": sum(m["std_dev"] for m in all_metrics) / len(all_metrics),
            "avg_chunk_length": sum(m.get("avg_chunk_length", 0) for m in all_metrics) / len(all_metrics),
        }
        return overall, all_metrics

    return {}, all_metrics


# ═══════════════════════════════════════════════════════════════════════
#  最適化推奨エンジン
# ═══════════════════════════════════════════════════════════════════════

def recommend_chunking_strategy(doc_characteristics):
    """
    ドキュメントの特性に基づいてチャンキング戦略を推奨

    Parameters:
        doc_characteristics: dict with keys:
            - doc_type: "structured" | "unstructured" | "mixed"
            - avg_length: ドキュメントの平均トークン数
            - has_sections: セクション構造があるか
            - content_type: "legal" | "technical" | "faq" | "conversation"
            - query_type: "specific" | "exploratory" | "mixed"
    """
    doc_type = doc_characteristics.get("doc_type", "mixed")
    avg_length = doc_characteristics.get("avg_length", 1000)
    has_sections = doc_characteristics.get("has_sections", False)
    content_type = doc_characteristics.get("content_type", "general")
    query_type = doc_characteristics.get("query_type", "mixed")

    recommendations = []

    # 構造化文書 + セクションあり → 階層型
    if doc_type == "structured" and has_sections:
        recommendations.append({
            "strategy": "hierarchical",
            "confidence": 0.9,
            "reason": "セクション構造を活かした階層型チャンキングが最適。"
                      "親チャンクで文脈を保持し、子チャンクで精密検索。"
        })

    # 法律文書 → 階層型 or セマンティック
    if content_type == "legal":
        recommendations.append({
            "strategy": "hierarchical",
            "confidence": 0.85,
            "reason": "法律文書は条文単位の構造があり、階層型チャンキングで"
                      "条文のまとまりを保持できる。"
        })
        recommendations.append({
            "strategy": "semantic",
            "confidence": 0.80,
            "reason": "セマンティックチャンキングにより、意味的に完結した"
                      "単位で分割。条文の途中で切れることを防止。"
        })

    # FAQ/短文 → 固定サイズ（小）
    if content_type == "faq" or avg_length < 500:
        recommendations.append({
            "strategy": "fixed_size_small",
            "confidence": 0.85,
            "reason": "短いドキュメントには小さな固定サイズチャンクが最適。"
                      "1つのQ&Aが1チャンクに収まる。"
        })

    # 長文 + 探索的クエリ → セマンティック
    if avg_length > 2000 and query_type == "exploratory":
        recommendations.append({
            "strategy": "semantic",
            "confidence": 0.80,
            "reason": "長文で探索的クエリが多い場合、セマンティックチャンキングにより"
                      "意味的に関連するセクションを一つのチャンクとして扱える。"
        })

    # デフォルト
    if not recommendations:
        recommendations.append({
            "strategy": "hierarchical",
            "confidence": 0.7,
            "reason": "一般的なドキュメントには階層型チャンキングが汎用的に有効。"
        })

    # 信頼度順にソート
    recommendations.sort(key=lambda x: x["confidence"], reverse=True)
    return recommendations


# ═══════════════════════════════════════════════════════════════════════
#  デモ関数
# ═══════════════════════════════════════════════════════════════════════

def demo_chunking_strategies():
    """チャンキング戦略の解説デモ"""
    print("=" * 70)
    print("  チャンキング最適化デモ 1: 戦略の比較")
    print("=" * 70)

    print(f"\n  Bedrock ナレッジベースで利用可能なチャンキング戦略:\n")

    for key, cfg in CHUNKING_CONFIGS.items():
        print(f"  ┌─ {cfg['name']} ({key}) ─────────────────")
        print(f"  │ 設定: {cfg['description']}")
        print(f"  │ 最適: {', '.join(cfg['best_for'])}")
        print(f"  │ トレードオフ: {cfg['trade_offs']}")
        print(f"  └{'─' * 55}\n")


def demo_chunking_comparison():
    """チャンキング比較のデモ"""
    print("\n" + "=" * 70)
    print("  チャンキング最適化デモ 2: 検索品質の比較")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_comparison()
        return

    queries = [
        "契約書の解除条件について教えてください",
        "解雇予告は何日前に必要ですか",
        "個人情報の第三者提供に関する規制",
    ]

    print(f"\n  現在のナレッジベース ({KNOWLEDGE_BASE_ID}) で品質測定...")
    overall, details = run_chunking_comparison(queries)

    if overall:
        print(f"\n  測定結果:")
        print(f"    平均スコア:       {overall['avg_score']:.4f}")
        print(f"    最高スコア平均:   {overall['avg_max_score']:.4f}")
        print(f"    スコア標準偏差:   {overall['avg_std_dev']:.4f}")
        print(f"    平均チャンク長:   {overall['avg_chunk_length']:.0f} 文字")


def demo_recommendation():
    """最適化推奨のデモ"""
    print("\n\n" + "=" * 70)
    print("  チャンキング最適化デモ 3: 最適戦略の推奨")
    print("=" * 70)

    scenarios = [
        {
            "name": "法律文書（構造化）",
            "characteristics": {
                "doc_type": "structured",
                "avg_length": 3000,
                "has_sections": True,
                "content_type": "legal",
                "query_type": "specific"
            }
        },
        {
            "name": "社内FAQ",
            "characteristics": {
                "doc_type": "unstructured",
                "avg_length": 200,
                "has_sections": False,
                "content_type": "faq",
                "query_type": "specific"
            }
        },
        {
            "name": "技術ドキュメント（長文）",
            "characteristics": {
                "doc_type": "structured",
                "avg_length": 5000,
                "has_sections": True,
                "content_type": "technical",
                "query_type": "exploratory"
            }
        },
    ]

    for scenario in scenarios:
        print(f"\n  ── {scenario['name']} ──")
        recommendations = recommend_chunking_strategy(scenario["characteristics"])
        for i, rec in enumerate(recommendations[:2], 1):
            strategy = CHUNKING_CONFIGS[rec["strategy"]]
            print(f"    推奨{i}: {strategy['name']} (信頼度: {rec['confidence']:.0%})")
            print(f"           理由: {rec['reason'][:60]}...")


def demo_parameter_tuning():
    """パラメータチューニングの解説"""
    print("\n\n" + "=" * 70)
    print("  チャンキング最適化デモ 4: パラメータチューニング")
    print("=" * 70)

    demo_simulated_tuning()


# ═══════════════════════════════════════════════════════════════════════
#  シミュレーションモード
# ═══════════════════════════════════════════════════════════════════════

def demo_simulated_comparison():
    """シミュレーション: チャンキング比較結果"""
    print(f"\n  📋 シミュレーション: チャンキング戦略の比較結果")
    print(f"{'─' * 70}")

    print(f"""
  テストクエリ: 「契約書の解除条件について教えてください」

  ┌──────────────────────────────────────────────────────────────────┐
  │  戦略別 検索品質メトリクス                                        │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                   │
  │  メトリクス        固定(小)  固定(大)  階層型    セマンティック   │
  │  ─────────────── ──────── ──────── ──────── ──────────────        │
  │  Precision@5       0.60      0.80      0.90      0.85             │
  │  Recall@5          0.70      0.85      0.85      0.90             │
  │  平均スコア        0.72      0.78      0.84      0.82             │
  │  最高スコア        0.88      0.91      0.95      0.93             │
  │  スコア標準偏差    0.15      0.10      0.08      0.09             │
  │  平均チャンク長    180文字   620文字   250文字   450文字          │
  │  レスポンス時間    0.42秒    0.55秒    0.48秒    0.51秒           │
  │                                                                   │
  └──────────────────────────────────────────────────────────────────┘

  分析:
  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                   │
  │  固定サイズ（小: 300トークン）:                                  │
  │    ✅ 高速レスポンス                                             │
  │    ❌ 文が途中で切れる → 文脈欠落                               │
  │    ❌ Precision低い（不完全なチャンクが多い）                    │
  │    例: 「第7条（契約の解除）甲又は乙は、相手方が本契約に」      │
  │         ← ここで切れてしまう                                     │
  │                                                                   │
  │  固定サイズ（大: 1000トークン）:                                 │
  │    ✅ 文脈を保持しやすい                                         │
  │    ⚠️ 無関係な内容も含まれやすい                                 │
  │    ⚠️ レスポンスやや遅い                                        │
  │    例: 第7条〜第9条が1チャンクに（解除+損害賠償+不可抗力）      │
  │                                                                   │
  │  階層型（親1500 / 子300）:                                       │
  │    ✅ Precision最高（子チャンクで精密検索）                      │
  │    ✅ 文脈保持（親チャンクで補完）                               │
  │    ✅ スコア安定（標準偏差最小）                                 │
  │    例: 子「第7条の解除条件」→ 親「第7条〜第8条の完全な文脈」   │
  │                                                                   │
  │  セマンティック:                                                  │
  │    ✅ Recall最高（意味的に完結した単位で分割）                   │
  │    ✅ 自然な分割（文の途中で切れない）                           │
  │    ⚠️ チャンクサイズが不均一                                    │
  │    例: 「解除条件」の全段落が1チャンクに自動分割                 │
  │                                                                   │
  └──────────────────────────────────────────────────────────────────┘

  結論: 法律文書には「階層型」が最適
    - 条文単位の精密検索（子チャンク）+ 前後の文脈参照（親チャンク）
    - 次点: セマンティック（Recall 重視の場合）
    """)


def demo_simulated_tuning():
    """シミュレーション: パラメータチューニング"""
    print(f"\n  📋 パラメータチューニングガイド")
    print(f"{'─' * 70}")

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  固定サイズチャンキングのチューニング                              │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                   │
  │  maxTokens（チャンクサイズ）:                                     │
  │                                                                   │
  │    100-300:  FAQ、短文向け。精度高だが文脈欠落リスク             │
  │    300-500:  一般的なドキュメント（デフォルト推奨）               │
  │    500-1000: 長文、技術文書。文脈保持できるが検索ノイズ増        │
  │    1000+:    レポート全体の要約向け。RAG より要約タスク向き      │
  │                                                                   │
  │  overlapPercentage（オーバーラップ率）:                           │
  │                                                                   │
  │    0%:   チャンク間に重複なし。効率的だが境界で情報欠落         │
  │    10%:  最小限のオーバーラップ（デフォルト）                    │
  │    20%:  推奨。境界付近の情報を両方のチャンクに含める            │
  │    30%+: オーバーラップ過多。ストレージ・検索コスト増           │
  │                                                                   │
  │  チューニング例:                                                  │
  │    ┌─────────────────────────────────────────────┐              │
  │    │ maxTokens=300, overlap=20%                    │              │
  │    │                                               │              │
  │    │ チャンク1: [───────────────────]              │              │
  │    │ チャンク2:           [───────────────────]    │              │
  │    │                 ↑ 60トークン重複               │              │
  │    └─────────────────────────────────────────────┘              │
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  階層型チャンキングのチューニング                                  │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                   │
  │  親チャンク（levelConfigurations[0].maxTokens）:                 │
  │    1000-1500: セクション全体を含む（推奨）                       │
  │    1500-2000: 大きなセクション向け                                │
  │    → 検索時: 子チャンクでマッチ → 親チャンクの文脈を参照        │
  │                                                                   │
  │  子チャンク（levelConfigurations[1].maxTokens）:                 │
  │    200-300:   精密検索向け（推奨）                                │
  │    300-500:   やや粗い検索                                       │
  │    → 検索時: この単位でベクトル検索される                        │
  │                                                                   │
  │  overlapTokens:                                                   │
  │    30-60:    推奨（子チャンク間の重複）                           │
  │    → 文の途中切れ防止                                            │
  │                                                                   │
  │  構造例:                                                          │
  │    ┌─── 親チャンク（1500トークン）────────────┐                  │
  │    │ ┌─子1─┐ ┌─子2─┐ ┌─子3─┐ ┌─子4─┐      │                  │
  │    │ │ 300 │↔│ 300 │↔│ 300 │↔│ 300 │      │                  │
  │    │ └─────┘ └─────┘ └─────┘ └─────┘      │                  │
  │    │      ↑ 60トークン重複                          │                  │
  │    └───────────────────────────────────────────┘                  │
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  セマンティックチャンキングのチューニング                          │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                   │
  │  maxTokens:                                                       │
  │    500-1000: 推奨（セマンティック境界内の最大サイズ）             │
  │    → 意味的な区切りが大きい場合の上限制御                        │
  │                                                                   │
  │  bufferSize:                                                      │
  │    0: 隣接文を含めない（デフォルト）                             │
  │    1: 前後1文を含める（文脈補強）                                │
  │                                                                   │
  │  breakpointPercentileThreshold:                                   │
  │    90:  より細かく分割（多くのブレークポイント検出）              │
  │    95:  推奨（明確な意味的区切りのみ）                           │
  │    99:  大きなチャンク（非常に明確な区切りのみ）                 │
  │                                                                   │
  │  動作原理:                                                        │
  │    1. 文ごとに埋め込みベクトルを計算                              │
  │    2. 隣接文間のコサイン類似度を計算                              │
  │    3. 類似度が閾値以下 → ブレークポイント（チャンク境界）       │
  │    4. threshold=95 → 上位5%の不連続点でのみ分割                  │
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  最適化ワークフロー                                               │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                   │
  │  1. ベースライン測定                                              │
  │     - 現在の設定で RAGAS 評価を実行                               │
  │     - Precision@5, Recall@5, 平均スコアを記録                    │
  │                                                                   │
  │  2. パラメータ探索                                                │
  │     - 戦略を変更して新しいデータソースを作成                     │
  │     - 同期後、同一クエリセットで再評価                           │
  │     - 結果を比較                                                  │
  │                                                                   │
  │  3. A/B テスト                                                    │
  │     - 最有力候補 2-3 パターンを並行運用                          │
  │     - 実ユーザーのフィードバックで最終決定                       │
  │                                                                   │
  │  4. 継続的モニタリング                                            │
  │     - 新規ドキュメント追加時に品質を再測定                       │
  │     - スコアが閾値を下回ったらチューニング再実施                 │
  └──────────────────────────────────────────────────────────────────┘
    """)


def demo_bedrock_configuration():
    """Bedrock コンソールでの設定方法"""
    print("\n\n" + "=" * 70)
    print("  チャンキング最適化: Bedrock コンソールでの設定手順")
    print("=" * 70)

    print(f"""
  ■ AWS コンソールでのチャンキング設定変更手順:

  1. Amazon Bedrock コンソール → ナレッジベース → 対象の KB を選択
  2. データソース → 新規データソースの追加
  3. 「チャンキングとパース設定」セクション:

     ┌─────────────────────────────────────────────────────┐
     │  チャンキング戦略の選択:                              │
     │                                                       │
     │  ○ デフォルトチャンキング                            │
     │     → 固定サイズ 300トークン / 20% オーバーラップ    │
     │                                                       │
     │  ● カスタムチャンキング                              │
     │     → 戦略を選択:                                    │
     │       ○ 固定サイズ                                   │
     │       ○ 階層型                                       │
     │       ○ セマンティック                               │
     │       ○ なし                                         │
     └─────────────────────────────────────────────────────┘

  4. パラメータを設定
  5. データソースを作成 → 同期を実行

  ■ 注意事項:
  - チャンキング設定は既存データソースでは変更不可
  - 新しいデータソースを作成して同期する必要がある
  - 比較する場合: 同じ KB に複数のデータソースを作成可能
  - 本番切り替え時: 古いデータソースを削除して新しいもののみ残す

  ■ API（boto3）での設定変更:

  ```python
  # 新しいデータソースを階層型チャンキングで作成
  bedrock_agent.create_data_source(
      knowledgeBaseId="YOUR_KB_ID",
      name="legal-docs-hierarchical",
      dataSourceConfiguration={{
          "type": "S3",
          "s3Configuration": {{
              "bucketArn": "arn:aws:s3:::your-bucket"
          }}
      }},
      vectorIngestionConfiguration={{
          "chunkingConfiguration": {{
              "chunkingStrategy": "HIERARCHICAL",
              "hierarchicalChunkingConfiguration": {{
                  "levelConfigurations": [
                      {{"maxTokens": 1500}},   # 親チャンク
                      {{"maxTokens": 300}}     # 子チャンク
                  ],
                  "overlapTokens": 60
              }}
          }}
      }}
  )
  ```
    """)


# ═══════════════════════════════════════════════════════════════════════
#  メイン実行
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    demo_chunking_strategies()
    demo_chunking_comparison()
    demo_recommendation()
    demo_parameter_tuning()
    demo_bedrock_configuration()
