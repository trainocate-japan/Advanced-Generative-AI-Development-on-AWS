"""
モジュール 3 補足: ベクトル検索（k-NN）の実装
- インデックス作成（HNSW アルゴリズム設定）
- Titan Embeddings V2 によるドキュメントベクトル化
- k-NN ベクトル検索の実行
- k-NN アルゴリズムの比較解説
"""

import boto3
import json
import argparse
import os
import time
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# AWS クライアント
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
session = boto3.Session(region_name='us-east-1')
credentials = session.get_credentials()

# 設定読み込み
REGION = 'us-east-1'
INDEX_NAME = "legal-docs"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024

# サンプルドキュメントのパス（M03-rag-knowledgebase のものを再利用）
SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "M03-rag-knowledgebase", "sample-docs")


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

    # エンドポイントからホスト名を抽出
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


def create_index(client):
    """k-NN ベクトル検索用インデックスを作成"""
    index_body = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 512
            }
        },
        "mappings": {
            "properties": {
                "title": {
                    "type": "keyword"
                },
                "content": {
                    "type": "text",
                    "analyzer": "standard"
                },
                "category": {
                    "type": "keyword"
                },
                "section": {
                    "type": "keyword"
                },
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

    # 既存インデックスがあれば削除して再作成
    if client.indices.exists(index=INDEX_NAME):
        try:
            client.indices.delete(index=INDEX_NAME)
            print(f"  🗑️  既存インデックス削除: {INDEX_NAME}")
            time.sleep(2)
        except Exception as e:
            print(f"  ℹ️  既存インデックスをそのまま使用します（削除スキップ: {type(e).__name__}）")
            return

    try:
        client.indices.create(index=INDEX_NAME, body=index_body)
    except Exception as e:
        if "resource_already_exists" in str(e).lower():
            print(f"  ℹ️  インデックス既存: {INDEX_NAME}（そのまま使用）")
            return
        raise
    print(f"  ✅ インデックス作成: {INDEX_NAME}")
    print(f"     k-NN アルゴリズム: HNSW (nmslib)")
    print(f"     距離関数: cosinesimil（コサイン類似度）")
    print(f"     ef_construction: 512")
    print(f"     m: 16")
    print(f"     ベクトル次元: {EMBEDDING_DIMENSIONS}")


def chunk_document(text, title, category, chunk_size=500, overlap=100):
    """ドキュメントをチャンクに分割"""
    # セクション単位で分割
    sections = text.split("\n## ")
    chunks = []

    for i, section in enumerate(sections):
        if not section.strip():
            continue

        # セクションタイトルを抽出
        lines = section.strip().split("\n")
        section_title = lines[0].replace("# ", "").strip()
        section_content = "\n".join(lines[1:]).strip()

        if not section_content:
            continue

        # セクションが長い場合はさらに分割
        if len(section_content) > chunk_size:
            paragraphs = section_content.split("\n\n")
            current_chunk = ""
            for para in paragraphs:
                if len(current_chunk) + len(para) > chunk_size and current_chunk:
                    chunks.append({
                        "title": title,
                        "section": section_title,
                        "content": current_chunk.strip(),
                        "category": category
                    })
                    # オーバーラップ
                    current_chunk = current_chunk[-overlap:] + "\n\n" + para
                else:
                    current_chunk += "\n\n" + para if current_chunk else para

            if current_chunk.strip():
                chunks.append({
                    "title": title,
                    "section": section_title,
                    "content": current_chunk.strip(),
                    "category": category
                })
        else:
            chunks.append({
                "title": title,
                "section": section_title,
                "content": section_content,
                "category": category
            })

    return chunks


def load_and_chunk_documents():
    """サンプルドキュメントを読み込みチャンクに分割"""
    documents = [
        {"file": "contract_template.txt", "title": "業務委託契約書テンプレート", "category": "contract"},
        {"file": "employment_law.txt", "title": "労働法の概要", "category": "employment"},
        {"file": "privacy_regulation.txt", "title": "個人情報保護規制ガイドライン", "category": "privacy"},
    ]

    all_chunks = []
    for doc in documents:
        filepath = os.path.join(SAMPLE_DOCS_DIR, doc["file"])
        if not os.path.exists(filepath):
            print(f"  ⚠️  ファイルが見つかりません: {filepath}")
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        chunks = chunk_document(content, doc["title"], doc["category"])
        all_chunks.extend(chunks)
        print(f"  📄 {doc['title']}: {len(chunks)} チャンク")

    return all_chunks


def index_documents(client, chunks):
    """ドキュメントをベクトル化してインデックスに投入"""
    print(f"\n  📥 {len(chunks)} チャンクをインデックスに投入中...")
    print(f"     （Titan Embeddings V2 でベクトル化 → OpenSearch に格納）")

    for i, chunk in enumerate(chunks):
        # エンベディング生成
        embedding = get_embedding(chunk["content"])

        # ドキュメント投入
        doc = {
            "title": chunk["title"],
            "content": chunk["content"],
            "category": chunk["category"],
            "section": chunk["section"],
            "content_vector": embedding
        }

        client.index(
            index=INDEX_NAME,
            body=doc
        )

        if (i + 1) % 5 == 0 or i == len(chunks) - 1:
            print(f"     進捗: {i + 1}/{len(chunks)}")

    # OpenSearch Serverless は自動リフレッシュのため明示的な refresh 不要
    time.sleep(5)  # インデックス反映を少し待つ
    print(f"\n  ✅ インデックス投入完了: {len(chunks)} ドキュメント")


def search_knn(client, query, k=5):
    """k-NN ベクトル検索を実行"""
    # クエリをベクトル化
    query_vector = get_embedding(query)

    # k-NN 検索クエリ
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


def display_results(response, search_type="k-NN ベクトル検索"):
    """検索結果を表示"""
    hits = response['hits']['hits']
    total = response['hits']['total']['value']

    print(f"\n{'─' * 60}")
    print(f"  🔍 {search_type} 結果（{len(hits)} 件 / 合計 {total} 件）")
    print(f"{'─' * 60}")

    for i, hit in enumerate(hits):
        score = hit['_score']
        source = hit['_source']
        print(f"\n  【{i + 1}位】スコア: {score:.4f}")
        print(f"  📁 カテゴリ: {source['category']} | セクション: {source['section']}")
        print(f"  📄 タイトル: {source['title']}")
        # コンテンツの先頭 150 文字を表示
        content_preview = source['content'][:150].replace('\n', ' ')
        print(f"  📝 内容: {content_preview}...")

    print(f"\n{'─' * 60}")


def compare_algorithms():
    """k-NN アルゴリズムの比較解説を表示"""
    print("\n" + "=" * 60)
    print(" k-NN アルゴリズム比較")
    print("=" * 60)

    algorithms = [
        {
            "name": "HNSW (nmslib)",
            "engine": "nmslib",
            "description": "Hierarchical Navigable Small World",
            "pros": ["高速な検索", "高い精度", "動的なインデックス更新"],
            "cons": ["メモリ使用量が多い", "インデックス構築が遅い"],
            "params": {"ef_construction": "512（推奨: 100-512）", "m": "16（推奨: 8-64）"},
            "use_case": "リアルタイム検索、高精度が必要なケース"
        },
        {
            "name": "HNSW (faiss)",
            "engine": "faiss",
            "description": "Facebook AI Similarity Search + HNSW",
            "pros": ["高速な検索", "量子化によるメモリ削減（PQ対応）", "大規模データ対応"],
            "cons": ["nmslib より構築が遅い場合あり"],
            "params": {"ef_construction": "512", "m": "16", "encoder": "flat / pq"},
            "use_case": "大規模データ、メモリ効率を重視するケース"
        },
        {
            "name": "IVF (faiss)",
            "engine": "faiss",
            "description": "Inverted File Index",
            "pros": ["メモリ効率が良い", "大規模データに強い"],
            "cons": ["HNSW より精度が低い", "事前の学習（training）が必要"],
            "params": {"nlist": "クラスタ数", "nprobes": "検索するクラスタ数"},
            "use_case": "超大規模データ（数百万〜数十億ベクトル）"
        },
    ]

    for algo in algorithms:
        print(f"\n{'─' * 50}")
        print(f"  📌 {algo['name']}")
        print(f"     {algo['description']}")
        print(f"\n  ✅ メリット:")
        for pro in algo['pros']:
            print(f"     • {pro}")
        print(f"\n  ⚠️  注意点:")
        for con in algo['cons']:
            print(f"     • {con}")
        print(f"\n  ⚙️  主要パラメータ:")
        for key, val in algo['params'].items():
            print(f"     • {key}: {val}")
        print(f"\n  🎯 適するケース: {algo['use_case']}")

    print(f"\n{'─' * 50}")
    print("\n  💡 OpenSearch Serverless では HNSW (nmslib/faiss) が利用可能")
    print("     IVF は OpenSearch Service（マネージドドメイン）で利用可能")
    print()

    # マッピング例の表示
    print("\n  📝 インデックスマッピング例（本ハンズオンで使用）:")
    print("""
    {
      "content_vector": {
        "type": "knn_vector",
        "dimension": 1024,
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
    """)

    print("  📐 距離関数の選択:")
    print("     • cosinesimil: コサイン類似度（テキスト検索に推奨）")
    print("     • l2: ユークリッド距離（画像・音声に推奨）")
    print("     • innerproduct: 内積（正規化済みベクトルで高速）")
    print()


def setup(client):
    """セットアップ: インデックス作成 + ドキュメント投入"""
    print("\n" + "=" * 60)
    print(" ベクトル検索インデックスのセットアップ")
    print("=" * 60)

    # インデックス作成
    print("\n📋 Step 1: インデックスの作成")
    create_index(client)

    # ドキュメント読み込み
    print("\n📋 Step 2: サンプルドキュメントの読み込み")
    chunks = load_and_chunk_documents()

    if not chunks:
        print("  ❌ チャンクが生成されませんでした")
        return

    # インデックス投入
    print("\n📋 Step 3: ベクトル化とインデックス投入")
    index_documents(client, chunks)

    print("\n" + "=" * 60)
    print(" ✅ セットアップ完了!")
    print("=" * 60)
    print("\n  検索を試す:")
    print('    python3.12 vector_search.py --search "契約の解除条件"')
    print('    python3.12 vector_search.py --search "残業代の計算方法"')
    print('    python3.12 vector_search.py --search "個人情報の第三者提供"')
    print()


def main():
    parser = argparse.ArgumentParser(description="OpenSearch k-NN ベクトル検索")
    parser.add_argument("--setup", action="store_true", help="インデックス作成とドキュメント投入")
    parser.add_argument("--search", type=str, help="検索クエリ")
    parser.add_argument("--k", type=int, default=5, help="返却件数（デフォルト: 5）")
    parser.add_argument("--compare-algorithms", action="store_true", help="k-NN アルゴリズムの比較")
    args = parser.parse_args()

    if args.compare_algorithms:
        compare_algorithms()
        return

    # OpenSearch クライアント初期化
    config = load_config()
    client = get_opensearch_client(config['endpoint'])

    if args.setup:
        setup(client)
    elif args.search:
        print(f"\n  🔍 検索クエリ: 「{args.search}」")
        print(f"  📊 返却件数: {args.k}")
        response = search_knn(client, args.search, k=args.k)
        display_results(response)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
