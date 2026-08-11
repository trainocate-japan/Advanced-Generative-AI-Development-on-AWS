"""
モジュール 3: RAG 基本実装
- Amazon Bedrock ナレッジベース RetrieveAndGenerate API
- Retrieve API による検索結果の詳細確認
- ハイブリッド検索のデモ
"""

import boto3
import json
import time
import os

# AWS クライアント
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# 設定ファイルから読み込み（存在する場合）
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "kb_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

_config = load_config()

# ナレッジベース ID（setup_knowledgebase.py 実行後に kb_config.json から自動取得）
KNOWLEDGE_BASE_ID = _config.get("knowledge_base_id", "YOUR_KB_ID")
MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"

# テスト質問
TEST_QUERIES = [
    "契約書の解除条件について教えてください",
    "個人情報の第三者提供に関する規制を説明してください",
    "従業員の残業時間の上限規制について教えてください",
    "秘密保持義務の期間はどのくらいですか",
    "解雇予告は何日前に必要ですか",
]


def retrieve_and_generate(query, kb_id=KNOWLEDGE_BASE_ID):
    """
    RetrieveAndGenerate API: 検索 + 回答生成を一括で実行
    """
    try:
        response = bedrock_agent_runtime.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": 5
                        }
                    },
                    "generationConfiguration": {
                        "inferenceConfig": {
                            "textInferenceConfig": {
                                "temperature": 0.2,
                                "maxTokens": 1024
                            }
                        }
                    }
                }
            }
        )

        output = response['output']['text']
        citations = response.get('citations', [])

        return {
            "success": True,
            "answer": output,
            "citations": citations,
            "citation_count": len(citations)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def retrieve_only(query, kb_id=KNOWLEDGE_BASE_ID):
    """
    Retrieve API: 検索のみを実行し、チャンクの詳細を確認
    """
    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": 5
                }
            }
        )

        results = []
        for item in response.get('retrievalResults', []):
            results.append({
                "text": item['content']['text'][:200],
                "score": item.get('score', 0),
                "source": item.get('location', {}).get('s3Location', {}).get('uri', 'N/A'),
                "metadata": item.get('metadata', {})
            })

        return {"success": True, "results": results}

    except Exception as e:
        return {"success": False, "error": str(e)}


def demo_retrieve_and_generate():
    """RetrieveAndGenerate のデモ"""
    print("=" * 70)
    print("  RAG デモ: RetrieveAndGenerate API")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        print("\n  ⚠ ナレッジベース ID が設定されていません。")
        print("  setup_knowledgebase.py を実行してナレッジベースを作成してください。")
        print("  作成後、KNOWLEDGE_BASE_ID を更新してから再実行してください。")
        print("\n  代わりにシミュレーションモードで実行します...")
        demo_simulated()
        return

    for query in TEST_QUERIES:
        print(f"\n{'─' * 70}")
        print(f"  質問: {query}")
        print(f"{'─' * 70}")

        start_time = time.time()
        result = retrieve_and_generate(query)
        elapsed = time.time() - start_time

        if result["success"]:
            print(f"\n  回答:")
            print(f"  {result['answer'][:300]}...")
            print(f"\n  引用数: {result['citation_count']}")
            print(f"  レスポンス時間: {elapsed:.2f}秒")

            if result['citations']:
                print(f"\n  引用元:")
                for i, citation in enumerate(result['citations'][:3], 1):
                    refs = citation.get('retrievedReferences', [])
                    for ref in refs[:2]:
                        source = ref.get('location', {}).get('s3Location', {}).get('uri', 'N/A')
                        print(f"    [{i}] {source}")
        else:
            print(f"  エラー: {result['error']}")


def demo_retrieve():
    """Retrieve API のデモ"""
    print("\n\n" + "=" * 70)
    print("  RAG デモ: Retrieve API（検索結果の詳細）")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        print("\n  ⚠ シミュレーションモードで実行中...")
        return

    query = "契約の解除条件と損害賠償について"
    print(f"\n  検索クエリ: {query}")
    print(f"{'─' * 70}")

    result = retrieve_only(query)

    if result["success"]:
        for i, item in enumerate(result["results"], 1):
            print(f"\n  [{i}] スコア: {item['score']:.4f}")
            print(f"      ソース: {item['source']}")
            print(f"      テキスト: {item['text'][:150]}...")
    else:
        print(f"  エラー: {result['error']}")


def demo_simulated():
    """ナレッジベース未作成時のシミュレーションデモ"""
    print("\n" + "─" * 70)
    print("  シミュレーションモード: RAG の動作フローを解説")
    print("─" * 70)

    print("""
  RAG（Retrieval-Augmented Generation）の処理フロー:

  ┌─────────────────────────────────────────────────────────────────┐
  │ 1. ユーザーの質問を受信                                          │
  │    「契約書の解除条件について教えてください」                       │
  │                                                                   │
  │ 2. クエリの埋め込みベクトルを生成（Titan Embeddings V2）          │
  │    [0.123, -0.456, 0.789, ...] (1024次元)                        │
  │                                                                   │
  │ 3. ベクトルストアで類似度検索                                     │
  │    - チャンク A: スコア 0.92 (contract_template.txt 第7条)        │
  │    - チャンク B: スコア 0.85 (contract_template.txt 第8条)        │
  │    - チャンク C: スコア 0.71 (employment_law.txt 第3条)           │
  │                                                                   │
  │ 4. 検索結果をコンテキストとして生成モデルに送信                   │
  │    システム: 以下のコンテキストに基づいて回答してください          │
  │    コンテキスト: [チャンク A] [チャンク B] [チャンク C]           │
  │    質問: 契約書の解除条件について教えてください                    │
  │                                                                   │
  │ 5. 生成モデルが回答を生成（引用付き）                            │
  │    「契約書の解除条件は第7条に規定されており...」                  │
  └─────────────────────────────────────────────────────────────────┘
    """)

    print("  チャンキング戦略の比較:")
    print(f"  {'戦略':<15} {'チャンクサイズ':<15} {'精度':<10} {'適するケース'}")
    print(f"  {'─' * 60}")
    print(f"  {'固定サイズ':<15} {'300トークン':<15} {'中':<10} {'FAQ、短文'}")
    print(f"  {'階層型':<15} {'セクション単位':<15} {'高':<10} {'構造化文書'}")
    print(f"  {'セマンティック':<15} {'意味単位':<15} {'最高':<10} {'法律・技術文書'}")

    print(f"""
  ベクトルストア: Amazon S3 Vectors
  ┌──────────────────────────────────────────────────────────────┐
  │ Amazon S3 Vectors（このハンズオンで使用）                     │
  │   - OpenSearch Serverless 比で最大 90% のコスト削減          │
  │   - 20億ベクトルまでスケール可能                              │
  │   - Bedrock KB とネイティブ統合                               │
  │   - サーバーレス（インフラ管理不要）                          │
  │   - コールドクエリでもサブ秒レイテンシー                      │
  │                                                              │
  │ 他の選択肢（参考）:                                          │
  │   - OpenSearch Serverless: 高QPS、ハイブリッド検索に最適     │
  │   - Aurora PostgreSQL: pgvector + SQL統合                    │
  │   - Neptune Analytics: グラフ + ベクトル統合                  │
  └──────────────────────────────────────────────────────────────┘
    """)


if __name__ == "__main__":
    demo_retrieve_and_generate()
    demo_retrieve()
