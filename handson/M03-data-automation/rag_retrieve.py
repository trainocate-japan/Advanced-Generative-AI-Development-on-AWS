"""
モジュール 3: Retrieve API による検索結果の詳細確認
- Retrieve API を使用してチャンク単位の検索結果を取得
- 関連度スコア、ソースドキュメント、メタデータの詳細表示
- 検索パラメータ（numberOfResults, searchType）の比較
"""

import boto3
import json
import time
import os

# AWS クライアント
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

# 設定ファイルから読み込み（存在する場合）
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "kb_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

config = load_config()
KNOWLEDGE_BASE_ID = config.get("knowledge_base_id", "YOUR_KB_ID")


# ═══════════════════════════════════════════════════════════════════════
#  検索クエリセット
# ═══════════════════════════════════════════════════════════════════════

QUERIES = {
    "specific": [
        "契約書の解除条件について教えてください",
        "解雇予告は何日前に必要ですか",
        "秘密保持義務の期間はどのくらいですか",
    ],
    "broad": [
        "従業員の権利について",
        "個人情報保護に関する全般的な規制",
        "知的財産権の帰属",
    ],
    "keyword_heavy": [
        "労働基準法 第20条 解雇予告手当",
        "個人情報保護法 第三者提供 同意",
        "特許法 職務発明 相当の利益",
    ]
}


# ═══════════════════════════════════════════════════════════════════════
#  Retrieve API ラッパー関数
# ═══════════════════════════════════════════════════════════════════════

def retrieve(query, kb_id=None, num_results=5, search_type="SEMANTIC"):
    """
    Retrieve API を使用して検索のみを実行

    Parameters:
        query: 検索クエリ
        kb_id: ナレッジベース ID
        num_results: 取得するチャンク数 (1-100)
        search_type: SEMANTIC（S3 Vectors はセマンティック検索のみ対応）

    Returns:
        検索結果のリスト（スコア、テキスト、ソース情報を含む）

    Note:
        S3 Vectors ではハイブリッド検索（BM25 + ベクトル）は非対応。
        HYBRID を指定しても SEMANTIC にフォールバックされます。
        ハイブリッド検索は M03-opensearch-vectorsearch で体験できます。
    """
    kb_id = kb_id or KNOWLEDGE_BASE_ID

    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": num_results,
            "overrideSearchType": search_type
        }
    }

    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration=retrieval_config
        )

        results = []
        for item in response.get('retrievalResults', []):
            content = item.get('content', {})
            location = item.get('location', {})
            s3_location = location.get('s3Location', {})

            results.append({
                "text": content.get('text', ''),
                "score": item.get('score', 0.0),
                "source_uri": s3_location.get('uri', 'N/A'),
                "location_type": location.get('type', 'N/A'),
                "metadata": item.get('metadata', {})
            })

        return {"success": True, "results": results, "query": query}

    except Exception as e:
        return {"success": False, "error": str(e), "query": query}


def retrieve_with_filter(query, filter_config, kb_id=None, num_results=5):
    """
    メタデータフィルター付きの Retrieve API

    Parameters:
        query: 検索クエリ
        filter_config: メタデータフィルター条件
        例: {"equals": {"key": "category", "value": "employment_law"}}
    """
    kb_id = kb_id or KNOWLEDGE_BASE_ID

    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": num_results,
            "overrideSearchType": "SEMANTIC",
            "filter": filter_config
        }
    }

    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration=retrieval_config
        )

        results = []
        for item in response.get('retrievalResults', []):
            results.append({
                "text": item.get('content', {}).get('text', ''),
                "score": item.get('score', 0.0),
                "source_uri": item.get('location', {}).get('s3Location', {}).get('uri', 'N/A'),
                "metadata": item.get('metadata', {})
            })

        return {"success": True, "results": results}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
#  デモ関数
# ═══════════════════════════════════════════════════════════════════════

def demo_basic_retrieve():
    """基本的な Retrieve API のデモ"""
    print("=" * 70)
    print("  デモ 1: Retrieve API - 基本検索")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        print("\n  ⚠ ナレッジベース ID が設定されていません。")
        print("  setup_knowledgebase.py を実行後、kb_config.json が生成されます。")
        demo_simulated_retrieve()
        return

    for query in QUERIES["specific"]:
        print(f"\n{'─' * 70}")
        print(f"  クエリ: {query}")
        print(f"{'─' * 70}")

        start_time = time.time()
        result = retrieve(query, num_results=5)
        elapsed = time.time() - start_time

        if result["success"]:
            print(f"  検索時間: {elapsed:.3f}秒 | 結果数: {len(result['results'])}")
            print()

            for i, item in enumerate(result["results"], 1):
                score = item['score']
                # スコアに基づく視覚的インジケータ
                bar_length = int(score * 20)
                bar = "█" * bar_length + "░" * (20 - bar_length)

                print(f"  [{i}] スコア: {score:.4f} [{bar}]")
                print(f"      ソース: {item['source_uri'].split('/')[-1] if item['source_uri'] != 'N/A' else 'N/A'}")

                # テキストの先頭を表示（改行を削除して整形）
                text_preview = item['text'][:150].replace('\n', ' ').strip()
                print(f"      テキスト: {text_preview}...")

                if item['metadata']:
                    print(f"      メタデータ: {json.dumps(item['metadata'], ensure_ascii=False)[:80]}")
                print()
        else:
            print(f"  ❌ エラー: {result['error']}")


def demo_search_type_comparison():
    """S3 Vectors での検索タイプの制限について解説"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: S3 Vectors の検索タイプと制限事項")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_search_comparison()
        return

    # セマンティック検索のみ有効
    test_query = "労働基準法 第20条 解雇予告手当"
    print(f"\n  テストクエリ: {test_query}")

    print(f"\n  ── SEMANTIC 検索（S3 Vectors で利用可能）──")
    result = retrieve(test_query, search_type="SEMANTIC", num_results=3)

    if result["success"]:
        for i, item in enumerate(result["results"], 1):
            print(f"    [{i}] スコア: {item['score']:.4f} | {item['text'][:80]}...")
    else:
        print(f"    エラー: {result['error']}")

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  S3 Vectors の検索タイプ制限                                     │
  │                                                                   │
  │  ✅ SEMANTIC（セマンティック検索）:                               │
  │    - S3 Vectors で利用可能                                       │
  │    - 意味的に類似したドキュメントを検索                          │
  │    - ベクトル類似度（cosine）に基づくランキング                  │
  │                                                                   │
  │  ❌ HYBRID（ハイブリッド検索）:                                   │
  │    - S3 Vectors では非対応（SEMANTIC にフォールバック）          │
  │    - BM25 キーワード検索にはテキストインデックスが必要           │
  │    - OpenSearch Serverless / RDS / MongoDB でのみ利用可能        │
  │                                                                   │
  │  → ハイブリッド検索の実践:                                       │
  │    M03-opensearch-vectorsearch/ ハンズオンで体験できます         │
  │    cd ~/handson/M03-opensearch-vectorsearch                       │
  │    python3.12 hybrid_search.py --demo                             │
  └──────────────────────────────────────────────────────────────────┘
    """)


def demo_num_results_impact():
    """numberOfResults パラメータの影響を検証"""
    print("\n" + "=" * 70)
    print("  デモ 3: 検索結果数（numberOfResults）の影響")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_num_results()
        return

    query = "契約書の解除条件と損害賠償"
    print(f"\n  クエリ: {query}")

    for num in [3, 5, 10]:
        start = time.time()
        result = retrieve(query, num_results=num)
        elapsed = time.time() - start

        if result["success"]:
            scores = [r['score'] for r in result['results']]
            avg_score = sum(scores) / len(scores) if scores else 0
            min_score = min(scores) if scores else 0
            max_score = max(scores) if scores else 0

            print(f"\n  numberOfResults = {num}")
            print(f"    取得数: {len(result['results'])} | 時間: {elapsed:.3f}秒")
            print(f"    スコア: 最高 {max_score:.4f} | 平均 {avg_score:.4f} | 最低 {min_score:.4f}")

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  numberOfResults の選択指針                                       │
  │                                                                   │
  │  3-5:  精度重視（高スコアのチャンクのみ使用）                    │
  │         → 簡潔な回答、ハルシネーション低減                      │
  │                                                                   │
  │  5-10: バランス型（標準的な RAG）                                 │
  │         → 十分なコンテキスト、適度な回答長                       │
  │                                                                   │
  │  10+:  網羅性重視（複雑な質問向け）                              │
  │         → 長い回答、低スコアチャンクの混入リスク                 │
  └──────────────────────────────────────────────────────────────────┘
    """)


def demo_metadata_filter():
    """メタデータフィルタリングのデモ"""
    print("\n" + "=" * 70)
    print("  デモ 4: メタデータフィルタリング")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_filter()
        return

    query = "従業員の権利と義務"

    # フィルタなし
    print(f"\n  クエリ: {query}")
    print(f"\n  ── フィルタなし ──")
    result_all = retrieve(query, num_results=5)
    if result_all["success"]:
        for i, item in enumerate(result_all["results"], 1):
            print(f"    [{i}] {item['score']:.4f} | {item['source_uri'].split('/')[-1]}")

    # カテゴリフィルタ
    print(f"\n  ── カテゴリ = employment_law ──")
    filter_config = {"equals": {"key": "category", "value": "employment_law"}}
    result_filtered = retrieve_with_filter(query, filter_config, num_results=5)
    if result_filtered["success"]:
        for i, item in enumerate(result_filtered["results"], 1):
            print(f"    [{i}] {item['score']:.4f} | {item['source_uri'].split('/')[-1]}")
    else:
        print(f"    ⚠ フィルタリング未対応（メタデータ設定が必要）")

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  メタデータフィルタリングの活用例                                  │
  │                                                                   │
  │  フィルタ条件:                                                    │
  │    equals:      完全一致                                          │
  │    notEquals:   除外                                              │
  │    greaterThan: 範囲指定（日付、バージョン等）                    │
  │    in:          複数値のいずれか                                  │
  │    andAll:      AND 条件の組み合わせ                              │
  │    orAll:       OR 条件の組み合わせ                               │
  │                                                                   │
  │  例: 部署 = 法務 AND 機密レベル <= 社内限定                      │
  └──────────────────────────────────────────────────────────────────┘
    """)


# ═══════════════════════════════════════════════════════════════════════
#  シミュレーションモード（KB 未作成時）
# ═══════════════════════════════════════════════════════════════════════

def demo_simulated_retrieve():
    """シミュレーション: Retrieve API の基本動作"""
    print("\n  📋 シミュレーションモード: Retrieve API の動作解説")
    print(f"{'─' * 70}")

    simulated_results = [
        {"score": 0.92, "source": "contract_template.txt", "text": "第7条（契約の解除）甲又は乙は、相手方が本契約に違反し、催告後30日以内に是正されない場合..."},
        {"score": 0.85, "source": "contract_template.txt", "text": "第8条（損害賠償）本契約に違反した当事者は、相手方に生じた損害を賠償する責任を負う..."},
        {"score": 0.71, "source": "employment_law.txt", "text": "第16条（解雇）解雇は、客観的に合理的な理由を欠き、社会通念上相当と認められない場合は..."},
        {"score": 0.63, "source": "privacy_regulation.txt", "text": "個人情報取扱事業者は、あらかじめ本人の同意を得ないで、個人データを第三者に提供してはならない..."},
        {"score": 0.45, "source": "ip_guidelines.txt", "text": "従業者等がした発明については、契約、勤務規則その他の定めにおいてあらかじめ使用者等に特許を..."},
    ]

    query = "契約書の解除条件について教えてください"
    print(f"\n  クエリ: {query}")
    print()

    for i, item in enumerate(simulated_results, 1):
        bar_length = int(item['score'] * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        print(f"  [{i}] スコア: {item['score']:.4f} [{bar}]")
        print(f"      ソース: {item['source']}")
        print(f"      テキスト: {item['text'][:100]}...")
        print()

    print(f"""
  Retrieve API のレスポンス構造:
  {{
    "retrievalResults": [
      {{
        "content": {{"text": "チャンクのテキスト..."}},
        "score": 0.92,                          ← 関連度スコア (0.0-1.0)
        "location": {{
          "type": "S3",
          "s3Location": {{
            "uri": "s3://bucket/documents/file.txt"  ← ソースファイル
          }}
        }},
        "metadata": {{                           ← カスタムメタデータ
          "category": "contract",
          "doc_type": "template"
        }}
      }}
    ]
  }}
    """)


def demo_simulated_search_comparison():
    """シミュレーション: S3 Vectors 検索タイプ制限"""
    print(f"\n  📋 シミュレーション: S3 Vectors の検索タイプ")
    print(f"{'─' * 70}")

    print(f"""
  テストクエリ: 「労働基準法 第20条 解雇予告手当」

  ── SEMANTIC 検索（S3 Vectors で利用可能）──
    [1] スコア: 0.78 | 「解雇する場合は少なくとも30日前に予告しなければならない...」
    [2] スコア: 0.72 | 「使用者は労働者を解雇しようとする場合においては...」
    [3] スコア: 0.65 | 「従業員の解雇に関する一般的な規定として...」

  → セマンティック検索は意味的に近い文書を取得可能
  → ただし「第20条」という正確な条文番号でのキーワードマッチは弱い

  ┌──────────────────────────────────────────────────────────────────┐
  │  ベクトルストア別 検索機能の比較                                   │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                   │
  │  S3 Vectors:                                                      │
  │    ✅ セマンティック検索（ベクトル類似度）                       │
  │    ✅ メタデータフィルタリング                                    │
  │    ❌ ハイブリッド検索（BM25 + ベクトル）                        │
  │    ❌ 全文テキスト検索                                           │
  │    💰 コスト: 最大 90% 削減                                      │
  │                                                                   │
  │  OpenSearch Serverless:                                           │
  │    ✅ セマンティック検索（k-NN）                                 │
  │    ✅ ハイブリッド検索（BM25 + k-NN）ネイティブ対応             │
  │    ✅ 全文テキスト検索（BM25）                                   │
  │    ✅ カスタムスコアリング                                       │
  │    💰 コスト: 高め（コンピュート + ストレージ）                  │
  │                                                                   │
  │  → M03-opensearch-vectorsearch/ でハイブリッド検索を体験        │
  └──────────────────────────────────────────────────────────────────┘
    """)


def demo_simulated_num_results():
    """シミュレーション: numberOfResults の影響"""
    print(f"\n  📋 シミュレーション: numberOfResults の影響")
    print(f"{'─' * 70}")

    print(f"""
  クエリ: 「契約書の解除条件と損害賠償」

  numberOfResults = 3
    取得数: 3 | 時間: 0.45秒
    スコア: 最高 0.92 | 平均 0.84 | 最低 0.78
    → 高品質なチャンクのみ取得

  numberOfResults = 5
    取得数: 5 | 時間: 0.52秒
    スコア: 最高 0.92 | 平均 0.76 | 最低 0.63
    → バランスの良いコンテキスト量

  numberOfResults = 10
    取得数: 10 | 時間: 0.61秒
    スコア: 最高 0.92 | 平均 0.62 | 最低 0.31
    → 低関連度チャンクが混入（ノイズ増加）
    """)


def demo_simulated_filter():
    """シミュレーション: メタデータフィルタリング"""
    print(f"\n  📋 シミュレーション: メタデータフィルタリング")
    print(f"{'─' * 70}")

    print(f"""
  クエリ: 「従業員の権利と義務」

  ── フィルタなし ──
    [1] 0.88 | employment_law.txt     ← 労働法
    [2] 0.79 | contract_template.txt  ← 契約書（雇用契約）
    [3] 0.72 | privacy_regulation.txt ← 個人情報（従業員の個人情報）
    [4] 0.65 | ip_guidelines.txt      ← 知的財産（職務発明）
    [5] 0.41 | contract_template.txt  ← 契約書（一般条項）

  ── カテゴリ = employment_law ──
    [1] 0.88 | employment_law.txt     ← 解雇・退職
    [2] 0.81 | employment_law.txt     ← 労働時間・残業
    [3] 0.76 | employment_law.txt     ← 休暇・有給
    [4] 0.69 | employment_law.txt     ← 安全衛生
    [5] 0.55 | employment_law.txt     ← 就業規則

  → フィルタにより同一カテゴリ内で深い検索が可能
  → 部署別アクセス制御にも活用可能
    """)


# ═══════════════════════════════════════════════════════════════════════
#  メイン実行
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    demo_basic_retrieve()
    demo_search_type_comparison()
    demo_num_results_impact()
    demo_metadata_filter()
