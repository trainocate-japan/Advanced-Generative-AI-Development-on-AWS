"""
モジュール 3 補足: カスタムスコアリングの実装
- script_score によるカスタムスコアリング関数
- 時間減衰（Time Decay）スコアリング
- カテゴリブースト
- 複合スコアリング（k-NN + BM25 + メタデータ）
- フィルタリングとの組み合わせ
"""

import boto3
import json
import argparse
import os
import random
from datetime import datetime, timedelta
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

# サンプルドキュメントのパス（M03-data-automation のものを再利用）
SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "M03-data-automation", "sample-docs")


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
#  インデックスセットアップ（メタデータ付き）
# ═══════════════════════════════════════════════════════════════════════

def create_scored_index(client):
    """カスタムスコアリング用インデックスを作成（メタデータフィールド追加）"""
    index_body = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 512
            }
        },
        "mappings": {
            "properties": {
                "title": {"type": "keyword"},
                "content": {"type": "text", "analyzer": "standard"},
                "category": {"type": "keyword"},
                "section": {"type": "keyword"},
                "published_date": {"type": "date"},
                "view_count": {"type": "integer"},
                "importance": {"type": "float"},
                "content_vector": {
                    "type": "knn_vector",
                    "dimension": EMBEDDING_DIMENSIONS,
                    "method": {
                        "name": "hnsw",
                        "engine": "nmslib",
                        "space_type": "cosinesimil",
                        "parameters": {
                            "ef_construction": 512,
                            "m": 16
                        }
                    }
                }
            }
        }
    }

    if client.indices.exists(index=INDEX_NAME):
        client.indices.delete(index=INDEX_NAME)
        print(f"  🗑️  既存インデックス削除: {INDEX_NAME}")

    import time
    time.sleep(2)
    client.indices.create(index=INDEX_NAME, body=index_body)
    print(f"  ✅ インデックス作成: {INDEX_NAME}")
    print(f"     追加フィールド: published_date, view_count, importance")


def load_and_index_documents(client):
    """メタデータ付きでドキュメントをインデックス"""
    documents = [
        {"file": "contract_template.txt", "title": "業務委託契約書テンプレート", "category": "contract"},
        {"file": "employment_law.txt", "title": "労働法の概要", "category": "employment"},
        {"file": "privacy_regulation.txt", "title": "個人情報保護規制ガイドライン", "category": "privacy"},
    ]

    doc_id = 0
    now = datetime.now()

    for doc_info in documents:
        filepath = os.path.join(SAMPLE_DOCS_DIR, doc_info["file"])
        if not os.path.exists(filepath):
            print(f"  ⚠️  ファイルが見つかりません: {filepath}")
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # セクション分割
        sections = content.split("\n## ")
        for i, section in enumerate(sections):
            if not section.strip():
                continue

            lines = section.strip().split("\n")
            section_title = lines[0].replace("# ", "").strip()
            section_content = "\n".join(lines[1:]).strip()

            if not section_content or len(section_content) < 50:
                continue

            # メタデータ（デモ用にランダム生成）
            days_ago = random.randint(1, 365)
            published_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            view_count = random.randint(10, 500)
            importance = round(random.uniform(0.3, 1.0), 2)

            # ベクトル化
            embedding = get_embedding(section_content[:2000])

            doc = {
                "title": doc_info["title"],
                "content": section_content,
                "category": doc_info["category"],
                "section": section_title,
                "published_date": published_date,
                "view_count": view_count,
                "importance": importance,
                "content_vector": embedding
            }

            client.index(index=INDEX_NAME, body=doc, id=str(doc_id))
            doc_id += 1

        print(f"  📄 {doc_info['title']}: インデックス完了")

    import time
    time.sleep(2)
    client.indices.refresh(index=INDEX_NAME)
    print(f"\n  ✅ 合計 {doc_id} ドキュメントをインデックス")
    return doc_id


# ═══════════════════════════════════════════════════════════════════════
#  カスタムスコアリング検索
# ═══════════════════════════════════════════════════════════════════════

def search_basic_knn(client, query, size=5):
    """基本 k-NN 検索（ベースライン）"""
    query_vector = get_embedding(query)
    search_body = {
        "size": size,
        "query": {
            "knn": {
                "content_vector": {
                    "vector": query_vector,
                    "k": size
                }
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    return client.search(index=INDEX_NAME, body=search_body)


def search_with_recency_boost(client, query, size=10, decay_rate=0.01):
    """
    時間減衰付きスコアリング（クライアントサイド）

    OpenSearch Serverless では script_score が使用できないため、
    k-NN 検索結果をクライアントサイドでリスコアリングする方式で実装。
    本番環境では OpenSearch Service（マネージドドメイン）で script_score を使用可能。
    """
    import math
    from datetime import datetime

    query_vector = get_embedding(query)
    search_body = {
        "size": size,
        "query": {
            "knn": {
                "content_vector": {
                    "vector": query_vector,
                    "k": size
                }
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    response = client.search(index=INDEX_NAME, body=search_body)

    # クライアントサイドでリスコアリング
    # （注: legal-docs インデックスには published_date がないためシミュレーション）
    now = datetime.now()
    for hit in response['hits']['hits']:
        knn_score = hit['_score']
        # ドキュメント位置に基づく擬似的な時間減衰（デモ用）
        # 上位チャンクを「新しい」とみなしてスコア微調整
        idx = response['hits']['hits'].index(hit)
        days_diff = idx * 30  # 各ドキュメントを30日ずつ古いとみなす
        recency_factor = math.exp(-decay_rate * days_diff)
        hit['_score'] = knn_score * (0.7 + 0.3 * recency_factor)
        hit['_recency_factor'] = recency_factor

    # リスコア後にソート
    response['hits']['hits'].sort(key=lambda x: x['_score'], reverse=True)
    response['hits']['hits'] = response['hits']['hits'][:5]
    return response


def search_with_category_boost(client, query, boost_category, size=10, boost_factor=1.5):
    """
    カテゴリブースト（クライアントサイド）

    指定カテゴリに属するドキュメントのスコアを boost_factor 倍にする。
    """
    query_vector = get_embedding(query)
    search_body = {
        "size": size,
        "query": {
            "knn": {
                "content_vector": {
                    "vector": query_vector,
                    "k": size
                }
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    response = client.search(index=INDEX_NAME, body=search_body)

    # クライアントサイドでカテゴリブースト
    for hit in response['hits']['hits']:
        category = hit['_source'].get('category', '')
        if category == boost_category:
            hit['_score'] *= boost_factor
            hit['_boosted'] = True
        else:
            hit['_boosted'] = False

    response['hits']['hits'].sort(key=lambda x: x['_score'], reverse=True)
    response['hits']['hits'] = response['hits']['hits'][:5]
    return response


def search_with_popularity_boost(client, query, size=10):
    """
    人気度ブースト（クライアントサイド）

    閲覧回数に基づく加点をシミュレーション。
    """
    import math

    query_vector = get_embedding(query)
    search_body = {
        "size": size,
        "query": {
            "knn": {
                "content_vector": {
                    "vector": query_vector,
                    "k": size
                }
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    response = client.search(index=INDEX_NAME, body=search_body)

    # クライアントサイドで人気度ブースト（擬似データ使用）
    import random
    random.seed(42)
    for hit in response['hits']['hits']:
        knn_score = hit['_score']
        view_count = random.randint(10, 500)  # デモ用の擬似閲覧数
        popularity_factor = 1.0 + math.log1p(view_count) / 10.0
        hit['_score'] = knn_score * popularity_factor
        hit['_source']['view_count'] = view_count

    response['hits']['hits'].sort(key=lambda x: x['_score'], reverse=True)
    response['hits']['hits'] = response['hits']['hits'][:5]
    return response


def search_composite(client, query, size=10):
    """
    複合スコアリング（クライアントサイド）

    k-NN スコア × 0.6 + 時間減衰 × 0.15 + 人気度 × 0.1 + 重要度 × 0.15
    """
    import math
    import random
    random.seed(42)

    query_vector = get_embedding(query)
    search_body = {
        "size": size,
        "query": {
            "knn": {
                "content_vector": {
                    "vector": query_vector,
                    "k": size
                }
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    response = client.search(index=INDEX_NAME, body=search_body)

    for i, hit in enumerate(response['hits']['hits']):
        knn_score = hit['_score']
        days_diff = i * 20
        recency = math.exp(-0.005 * days_diff)
        views = random.randint(10, 500)
        popularity = math.log1p(views) / 10.0
        importance = random.uniform(0.5, 1.0)

        composite = knn_score * 0.6 + recency * 0.15 + popularity * 0.1 + importance * 0.15
        hit['_score'] = composite
        hit['_source']['view_count'] = views
        hit['_source']['importance'] = round(importance, 2)

    response['hits']['hits'].sort(key=lambda x: x['_score'], reverse=True)
    response['hits']['hits'] = response['hits']['hits'][:5]
    return response


def search_with_filter(client, query, category=None, size=5):
    """フィルタリング + k-NN 検索"""
    query_vector = get_embedding(query)

    # bool + knn + filter の組み合わせ
    search_body = {
        "size": size,
        "query": {
            "bool": {
                "must": {
                    "knn": {
                        "content_vector": {
                            "vector": query_vector,
                            "k": size
                        }
                    }
                },
                "filter": {
                    "term": {"category": category}
                } if category else {"match_all": {}}
            }
        },
        "_source": ["title", "content", "category", "section"]
    }
    return client.search(index=INDEX_NAME, body=search_body)


# ═══════════════════════════════════════════════════════════════════════
#  結果表示
# ═══════════════════════════════════════════════════════════════════════

def display_results(response, label):
    """検索結果を表示"""
    hits = response['hits']['hits']
    print(f"\n  {'━' * 55}")
    print(f"  📌 {label}")
    print(f"  {'━' * 55}")

    for i, hit in enumerate(hits[:5]):
        score = hit['_score']
        source = hit['_source']
        content_preview = source['content'][:80].replace('\n', ' ')
        print(f"\n  [{i + 1}] スコア: {score:.4f}")
        print(f"      カテゴリ: {source.get('category', 'N/A')} | セクション: {source.get('section', 'N/A')}")
        if 'view_count' in source:
            print(f"      閲覧数: {source.get('view_count', '-')} | 重要度: {source.get('importance', '-')}")
        print(f"      内容: {content_preview}...")

    return hits


# ═══════════════════════════════════════════════════════════════════════
#  比較デモ
# ═══════════════════════════════════════════════════════════════════════

def run_comparison(client, query):
    """全スコアリング方式を比較"""
    print(f"\n{'═' * 60}")
    print(f" カスタムスコアリング比較: 「{query}」")
    print(f"{'═' * 60}")

    # 1. 基本 k-NN
    resp = search_basic_knn(client, query)
    display_results(resp, "① 基本 k-NN スコア（ベースライン）")

    # 2. 時間減衰
    resp = search_with_recency_boost(client, query)
    display_results(resp, "② 時間減衰付き（新しいドキュメント優先）")

    # 3. 人気度ブースト
    resp = search_with_popularity_boost(client, query)
    display_results(resp, "③ 人気度ブースト（閲覧数考慮）")

    # 4. 複合スコアリング
    resp = search_composite(client, query)
    display_results(resp, "④ 複合スコアリング（k-NN + 時間 + 人気 + 重要度）")

    # まとめ
    print(f"\n\n{'═' * 60}")
    print(" 💡 スコアリング関数のまとめ")
    print(f"{'═' * 60}")
    print("""
  ┌─────────────────┬─────────────────────────────────────────────────┐
  │ 方式            │ スコア計算                                       │
  ├─────────────────┼─────────────────────────────────────────────────┤
  │ ① 基本 k-NN    │ score = cosineSimilarity(query, doc)             │
  │ ② 時間減衰     │ score = knn × (0.7 + 0.3 × exp(-λ × days))      │
  │ ③ 人気度       │ score = knn × (1 + log(views+1) / 10)            │
  │ ④ 複合         │ score = 0.6×knn + 0.15×recency + 0.1×pop + 0.15×imp │
  └─────────────────┴─────────────────────────────────────────────────┘

  ✅ OpenSearch の script_score で任意のスコアリング関数を定義可能
  ⚠️  OpenSearch Serverless では一部の Painless スクリプト機能に制限あり
     → フル機能が必要な場合は OpenSearch Service（マネージドドメイン）を推奨
    """)


def setup(client):
    """カスタムスコアリング用インデックスのセットアップ"""
    print("\n" + "=" * 60)
    print(" カスタムスコアリング用インデックスのセットアップ")
    print("=" * 60)

    print("\n📋 Step 1: インデックスの作成（メタデータフィールド付き）")
    create_scored_index(client)

    print("\n📋 Step 2: ドキュメントのベクトル化とインデックス投入")
    load_and_index_documents(client)

    print("\n" + "=" * 60)
    print(" ✅ セットアップ完了!")
    print("=" * 60)
    print("\n  次のステップ:")
    print('    python3.12 custom_scoring.py --query "障害対応" --boost-recent')
    print('    python3.12 custom_scoring.py --compare')
    print('    python3.12 custom_scoring.py --query "API設計" --filter-category privacy')
    print()


def main():
    parser = argparse.ArgumentParser(description="OpenSearch カスタムスコアリング")
    parser.add_argument("--setup", action="store_true",
                        help="カスタムスコアリング用インデックスのセットアップ")
    parser.add_argument("--query", type=str, help="検索クエリ")
    parser.add_argument("--boost-recent", action="store_true",
                        help="時間減衰スコアリングを適用")
    parser.add_argument("--boost-category", type=str,
                        help="ブーストするカテゴリ（contract/employment/privacy）")
    parser.add_argument("--boost-popularity", action="store_true",
                        help="人気度ブーストを適用")
    parser.add_argument("--composite", action="store_true",
                        help="複合スコアリングを適用")
    parser.add_argument("--filter-category", type=str,
                        help="カテゴリでフィルタリング（contract/employment/privacy）")
    parser.add_argument("--compare", action="store_true",
                        help="全スコアリング方式を比較")
    args = parser.parse_args()

    # OpenSearch クライアント初期化
    config = load_config()
    client = get_opensearch_client(config['endpoint'])

    if args.setup:
        setup(client)
        return

    if args.compare:
        query = args.query or "契約の解除と損害賠償"
        run_comparison(client, query)
        return

    if not args.query:
        parser.print_help()
        print("\n  使用例:")
        print('    python3.12 custom_scoring.py --setup')
        print('    python3.12 custom_scoring.py --query "解雇規制" --boost-recent')
        print('    python3.12 custom_scoring.py --query "秘密保持" --boost-category contract')
        print('    python3.12 custom_scoring.py --query "個人情報" --filter-category privacy')
        print('    python3.12 custom_scoring.py --compare')
        return

    query = args.query
    print(f"\n  🔍 クエリ: 「{query}」")

    if args.boost_recent:
        resp = search_with_recency_boost(client, query)
        display_results(resp, "時間減衰付きスコアリング")
    elif args.boost_category:
        resp = search_with_category_boost(client, query, args.boost_category)
        display_results(resp, f"カテゴリブースト: {args.boost_category}")
    elif args.boost_popularity:
        resp = search_with_popularity_boost(client, query)
        display_results(resp, "人気度ブースト")
    elif args.composite:
        resp = search_composite(client, query)
        display_results(resp, "複合スコアリング")
    elif args.filter_category:
        resp = search_with_filter(client, query, category=args.filter_category)
        display_results(resp, f"フィルタ: {args.filter_category} + カスタムスコアリング")
    else:
        # デフォルト: 基本 k-NN
        resp = search_basic_knn(client, query)
        display_results(resp, "基本 k-NN スコア")


if __name__ == "__main__":
    main()
