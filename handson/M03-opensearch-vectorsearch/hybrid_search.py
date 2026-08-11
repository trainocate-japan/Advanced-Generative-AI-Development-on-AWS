"""
モジュール 3 補足: ハイブリッド検索の実装
- キーワード検索（BM25）の実行
- セマンティック検索（k-NN）の実行
- ハイブリッド検索（BM25 + k-NN スコア統合）の実行
- 重み付けパラメータによる検索精度の比較
- クエリタイプ別の最適検索戦略デモ
"""

import boto3
import json
import argparse
import os
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# AWS クライアント
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
session = boto3.Session(region_name='us-east-1')
credentials = session.get_credentials()

# 設定
REGION = 'us-east-1'
INDEX_NAME = "legal-docs"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024


def load_config():
    """OpenSearch 設定ファイルを読み込む"""
    config_path = os.path.join(os.path.dirname(__file__), "opensearch_config.json")
    if not os.path.exists(config_path):
        print("❌ opensearch_config.json が見つかりません。")
        print("   先に setup_opensearch.py を実行してください。")
        exit(1)
    with open(config_path) as f:
        return json.load(f)


def get_opensearch_client(endpoint):
    """OpenSearch Serverless クライアントを取得"""
    creds = credentials.get_frozen_credentials()
    awsauth = AWS4Auth(
        creds.access_key,
        creds.secret_key,
        REGION,
        'aoss',
        session_token=creds.token
    )
    host = endpoint.replace("https://", "")
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60
    )
    return client


def get_embedding(text):
    """Titan Embeddings V2 でテキストをベクトル化"""
    response = bedrock_runtime.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text,
            "dimensions": EMBEDDING_DIMENSIONS,
            "normalize": True
        })
    )
    result = json.loads(response['body'].read())
    return result['embedding']


# ═══════════════════════════════════════════════════════════════════════
#  検索関数
# ═══════════════════════════════════════════════════════════════════════

def search_keyword(client, query, size=5):
    """キーワード検索（BM25）"""
    search_body = {
        "size": size,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["content^2", "title", "section"],
                "type": "best_fields"
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    response = client.search(index=INDEX_NAME, body=search_body)
    return response


def search_semantic(client, query, k=5):
    """セマンティック検索（k-NN）"""
    query_vector = get_embedding(query)
    search_body = {
        "size": k,
        "query": {
            "knn": {
                "content_vector": {
                    "vector": query_vector,
                    "k": k
                }
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    response = client.search(index=INDEX_NAME, body=search_body)
    return response


def search_hybrid(client, query, size=5, semantic_weight=0.6):
    """
    ハイブリッド検索（BM25 + k-NN スコア統合）

    OpenSearch の script_score を使って、k-NN スコアと BM25 スコアを
    重み付けして統合する。
    """
    query_vector = get_embedding(query)
    keyword_weight = 1.0 - semantic_weight

    # 方式: k-NN をベースに BM25 のブーストを加算
    # OpenSearch Serverless では bool クエリ + script_score の組み合わせで実現
    search_body = {
        "size": size,
        "query": {
            "bool": {
                "should": [
                    {
                        # セマンティック検索（k-NN）
                        "knn": {
                            "content_vector": {
                                "vector": query_vector,
                                "k": size
                            }
                        }
                    },
                    {
                        # キーワード検索（BM25）
                        "multi_match": {
                            "query": query,
                            "fields": ["content^2", "title", "section"],
                            "type": "best_fields",
                            "boost": keyword_weight / semantic_weight
                        }
                    }
                ]
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    response = client.search(index=INDEX_NAME, body=search_body)
    return response


# ═══════════════════════════════════════════════════════════════════════
#  結果表示
# ═══════════════════════════════════════════════════════════════════════

def display_results(response, search_type, query):
    """検索結果を表示"""
    hits = response['hits']['hits']
    max_score = response['hits'].get('max_score', 0) or 0

    print(f"\n  {'━' * 55}")
    print(f"  📌 {search_type}")
    print(f"  {'━' * 55}")
    print(f"  クエリ: 「{query}」")
    print(f"  ヒット数: {len(hits)} | 最高スコア: {max_score:.4f}")

    for i, hit in enumerate(hits[:5]):
        score = hit['_score']
        source = hit['_source']
        content_preview = source['content'][:100].replace('\n', ' ')
        print(f"\n  [{i + 1}] スコア: {score:.4f} | {source['category']} / {source['section']}")
        print(f"      {content_preview}...")

    return hits


def display_comparison(keyword_hits, semantic_hits, hybrid_hits, query):
    """3つの検索結果を比較表示"""
    print(f"\n\n{'═' * 60}")
    print(f" 検索結果比較: 「{query}」")
    print(f"{'═' * 60}")

    # 各検索のトップ3を表示
    results = [
        ("🔤 キーワード検索 (BM25)", keyword_hits),
        ("🧠 セマンティック検索 (k-NN)", semantic_hits),
        ("⚡ ハイブリッド検索 (BM25 + k-NN)", hybrid_hits),
    ]

    for label, hits in results:
        print(f"\n  {label}:")
        if not hits:
            print("      結果なし")
            continue
        for i, hit in enumerate(hits[:3]):
            source = hit['_source']
            score = hit['_score']
            content_preview = source['content'][:80].replace('\n', ' ')
            print(f"    {i + 1}. [{score:.4f}] {source['section']}: {content_preview}...")

    print(f"\n{'═' * 60}")


# ═══════════════════════════════════════════════════════════════════════
#  デモシナリオ
# ═══════════════════════════════════════════════════════════════════════

def run_demo(client):
    """
    クエリタイプ別のデモ: 各検索方式の強み・弱みを実演
    """
    print("\n" + "=" * 60)
    print(" ハイブリッド検索デモ: クエリタイプ別の最適検索戦略")
    print("=" * 60)

    demo_queries = [
        {
            "query": "第7条",
            "type": "keyword_heavy",
            "explanation": "条文番号 → キーワード検索が得意（正確な一致）",
            "expected_best": "キーワード検索"
        },
        {
            "query": "従業員を不当に解雇されないための保護制度",
            "type": "exploratory",
            "explanation": "概念的クエリ → セマンティック検索が得意（意味理解）",
            "expected_best": "セマンティック検索"
        },
        {
            "query": "個人情報 第三者提供 同意",
            "type": "mixed",
            "explanation": "固有名詞 + 概念の混合 → ハイブリッド検索が最適",
            "expected_best": "ハイブリッド検索"
        },
        {
            "query": "会社が倒産した場合の契約の扱い",
            "type": "exploratory",
            "explanation": "直接的な表現がないが意味的に関連 → セマンティック検索向き",
            "expected_best": "セマンティック検索"
        },
    ]

    for i, demo in enumerate(demo_queries):
        print(f"\n\n{'─' * 60}")
        print(f"  デモ {i + 1}: {demo['explanation']}")
        print(f"  クエリタイプ: {demo['type']}")
        print(f"  期待される最適方式: {demo['expected_best']}")
        print(f"{'─' * 60}")

        # 3種類の検索を実行
        keyword_resp = search_keyword(client, demo['query'])
        semantic_resp = search_semantic(client, demo['query'])
        hybrid_resp = search_hybrid(client, demo['query'])

        keyword_hits = keyword_resp['hits']['hits']
        semantic_hits = semantic_resp['hits']['hits']
        hybrid_hits = hybrid_resp['hits']['hits']

        display_comparison(keyword_hits, semantic_hits, hybrid_hits, demo['query'])

    # まとめ
    print("\n\n" + "=" * 60)
    print(" 💡 まとめ: クエリタイプと最適な検索方式")
    print("=" * 60)
    print("""
  ┌────────────────────────┬──────────────────┬─────────────────────────────┐
  │ クエリタイプ           │ 最適な検索方式   │ 例                          │
  ├────────────────────────┼──────────────────┼─────────────────────────────┤
  │ 正確な用語・番号       │ キーワード検索   │ 「第7条」「ERROR-5023」     │
  │ 概念的・探索的         │ セマンティック検索│ 「解雇の保護制度」          │
  │ 用語 + 概念の混合      │ ハイブリッド検索 │ 「個人情報 第三者提供 同意」│
  └────────────────────────┴──────────────────┴─────────────────────────────┘

  ✅ ハイブリッド検索は「既存のキーワード検索の強みを壊さずに
     セマンティック検索で弱点を補完する」戦略として推奨される
    """)


def run_weight_comparison(client, query, weights):
    """異なる重み付けでの検索結果を比較"""
    print(f"\n{'═' * 60}")
    print(f" 重み付け比較: 「{query}」")
    print(f"{'═' * 60}")

    for weight in weights:
        keyword_weight = 1.0 - weight
        print(f"\n  📊 セマンティック重み: {weight:.1f} / キーワード重み: {keyword_weight:.1f}")
        response = search_hybrid(client, query, semantic_weight=weight)
        hits = response['hits']['hits']
        for i, hit in enumerate(hits[:3]):
            source = hit['_source']
            score = hit['_score']
            content_preview = source['content'][:70].replace('\n', ' ')
            print(f"     {i + 1}. [{score:.4f}] {source['section']}: {content_preview}...")

    print(f"\n{'═' * 60}")
    print("  💡 セマンティック重みが高い → 概念的に近い結果を優先")
    print("     キーワード重みが高い → 文字列一致する結果を優先")
    print()


def main():
    parser = argparse.ArgumentParser(description="OpenSearch ハイブリッド検索")
    parser.add_argument("--query", type=str, help="検索クエリ")
    parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid", "all"],
                        default="all", help="検索モード（デフォルト: all で3種比較）")
    parser.add_argument("--semantic-weight", type=float, default=0.6,
                        help="ハイブリッド検索のセマンティック重み（0.0〜1.0、デフォルト: 0.6）")
    parser.add_argument("--demo", action="store_true",
                        help="クエリタイプ別のデモを実行")
    parser.add_argument("--compare-weights", action="store_true",
                        help="異なる重み付けでの結果を比較")
    args = parser.parse_args()

    # OpenSearch クライアント初期化
    config = load_config()
    client = get_opensearch_client(config['endpoint'])

    if args.demo:
        run_demo(client)
        return

    if not args.query and not args.demo:
        parser.print_help()
        print("\n  使用例:")
        print('    python3.12 hybrid_search.py --query "契約の解除条件" --mode all')
        print('    python3.12 hybrid_search.py --query "第三者提供" --mode keyword')
        print('    python3.12 hybrid_search.py --query "解雇の保護" --semantic-weight 0.8')
        print('    python3.12 hybrid_search.py --demo')
        return

    query = args.query

    if args.compare_weights:
        weights = [0.2, 0.4, 0.6, 0.8, 0.9]
        run_weight_comparison(client, query, weights)
        return

    print(f"\n  🔍 クエリ: 「{query}」")
    print(f"  ⚙️  モード: {args.mode}")
    if args.mode == "hybrid" or args.mode == "all":
        print(f"  ⚖️  セマンティック重み: {args.semantic_weight}")

    if args.mode == "keyword":
        response = search_keyword(client, query)
        display_results(response, "🔤 キーワード検索 (BM25)", query)

    elif args.mode == "semantic":
        response = search_semantic(client, query)
        display_results(response, "🧠 セマンティック検索 (k-NN)", query)

    elif args.mode == "hybrid":
        response = search_hybrid(client, query, semantic_weight=args.semantic_weight)
        display_results(response, "⚡ ハイブリッド検索 (BM25 + k-NN)", query)

    else:  # all
        keyword_resp = search_keyword(client, query)
        semantic_resp = search_semantic(client, query)
        hybrid_resp = search_hybrid(client, query, semantic_weight=args.semantic_weight)

        keyword_hits = keyword_resp['hits']['hits']
        semantic_hits = semantic_resp['hits']['hits']
        hybrid_hits = hybrid_resp['hits']['hits']

        display_comparison(keyword_hits, semantic_hits, hybrid_hits, query)


if __name__ == "__main__":
    main()
