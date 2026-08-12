"""
モジュール 7: セマンティックキャッシュによるコスト削減デモ
- 従来キャッシュ（完全一致）vs セマンティックキャッシュ（意味類似度）
- Bedrock Embeddings を使ったベクトル類似度検索
- キャッシュヒット率と品質のトレードオフ
- キャッシュ無効化戦略の実装
"""

import boto3
import json
import time
import hashlib
import numpy as np
from datetime import datetime, timedelta

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "amazon.nova-pro-v1:0"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"


# ============================================================
# インメモリ セマンティックキャッシュ実装
# （本番環境では ElastiCache + OpenSearch を使用）
# ============================================================

class SemanticCache:
    """
    セマンティックキャッシュの実装

    本番環境では:
    - ベクトル保存: Amazon OpenSearch Serverless (k-NN)
    - レスポンスキャッシュ: Amazon ElastiCache (Redis)
    - 埋め込み生成: Amazon Bedrock Titan Embeddings

    このデモではインメモリで動作を再現します。
    """

    def __init__(self, similarity_threshold=0.85, ttl_seconds=300):
        self.cache = []  # [(embedding, query, response, timestamp), ...]
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_saved_cost": 0.0,
        }

    def get_embedding(self, text):
        """Bedrock Titan Embeddings でテキストのベクトルを取得"""
        response = bedrock.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            body=json.dumps({"inputText": text}),
            contentType="application/json"
        )
        result = json.loads(response['body'].read())
        return np.array(result['embedding'])

    def cosine_similarity(self, vec_a, vec_b):
        """コサイン類似度を計算"""
        dot_product = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def evict_expired(self):
        """TTL 切れのエントリを削除"""
        now = datetime.now()
        original_size = len(self.cache)
        self.cache = [
            entry for entry in self.cache
            if (now - entry[3]).total_seconds() < self.ttl_seconds
        ]
        evicted = original_size - len(self.cache)
        self.stats["evictions"] += evicted
        return evicted

    def lookup(self, query):
        """
        セマンティック検索でキャッシュを照合

        Returns:
            (hit, response, similarity) - ヒット時は応答と類似度を返す
        """
        self.evict_expired()

        query_embedding = self.get_embedding(query)

        best_match = None
        best_similarity = 0.0

        for embedding, cached_query, response, timestamp in self.cache:
            similarity = self.cosine_similarity(query_embedding, embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = (cached_query, response)

        if best_match and best_similarity >= self.similarity_threshold:
            self.stats["hits"] += 1
            return True, best_match[1], best_similarity, best_match[0]
        else:
            self.stats["misses"] += 1
            return False, None, best_similarity, None

    def store(self, query, response):
        """クエリと応答をキャッシュに保存"""
        embedding = self.get_embedding(query)
        self.cache.append((embedding, query, response, datetime.now()))

    def get_stats(self):
        """キャッシュ統計を返す"""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total * 100) if total > 0 else 0
        return {
            **self.stats,
            "total_requests": total,
            "hit_rate": hit_rate,
            "cache_size": len(self.cache),
        }


# ============================================================
# 従来キャッシュ（完全一致）の比較用実装
# ============================================================

class ExactMatchCache:
    """完全一致キャッシュ（比較用）"""

    def __init__(self):
        self.cache = {}
        self.stats = {"hits": 0, "misses": 0}

    def lookup(self, query):
        """完全一致でキャッシュを検索"""
        key = hashlib.md5(query.encode()).hexdigest()
        if key in self.cache:
            self.stats["hits"] += 1
            return True, self.cache[key]
        self.stats["misses"] += 1
        return False, None

    def store(self, query, response):
        key = hashlib.md5(query.encode()).hexdigest()
        self.cache[key] = response


# ============================================================
# Bedrock 呼び出し（キャッシュ統合）
# ============================================================

def call_bedrock(query):
    """Bedrock にクエリを送信して応答を取得"""
    system_prompt = (
        "あなたはECサイトのカスタマーサポートAIです。"
        "商品に関する質問、注文状況、返品手続きなどについて簡潔に回答してください。"
    )

    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[{
            "role": "user",
            "content": [{"text": query}]
        }],
        inferenceConfig={"temperature": 0.3, "maxTokens": 400}
    )

    usage = response['usage']
    answer = response['output']['message']['content'][0]['text']
    return answer, usage


# ============================================================
# デモ 1: 従来キャッシュ vs セマンティックキャッシュの比較
# ============================================================

def demo_comparison():
    """完全一致キャッシュとセマンティックキャッシュの比較"""
    print("=" * 70)
    print("  デモ 1: 従来キャッシュ vs セマンティックキャッシュ")
    print("=" * 70)
    print("""
  同じ意図のクエリを異なる表現で送信し、キャッシュヒット率を比較します。

  テストケース:
  ┌─────┬────────────────────────────────────────────┐
  │ Q1  │ パスワードをリセットする方法を教えてください │ ← 初回（キャッシュ書き込み）
  │ Q2  │ ログインパスワードの変更手順は？            │ ← 類似表現1
  │ Q3  │ パスワードを忘れたので再設定したい          │ ← 類似表現2
  │ Q4  │ 配送状況を確認したい                        │ ← 異なる意図
  └─────┴────────────────────────────────────────────┘
""")

    queries = [
        "パスワードをリセットする方法を教えてください",
        "ログインパスワードの変更手順は？",
        "パスワードを忘れたので再設定したい",
        "配送状況を確認したい",
    ]

    exact_cache = ExactMatchCache()
    semantic_cache = SemanticCache(similarity_threshold=0.85)

    print(f"{'─' * 70}")
    print(f"  {'クエリ':<30} │ {'完全一致':<10} │ {'セマンティック':<14} │ {'類似度'}")
    print(f"{'─' * 70}")

    for i, query in enumerate(queries):
        # 完全一致キャッシュ
        exact_hit, _ = exact_cache.lookup(query)

        # セマンティックキャッシュ
        sem_hit, cached_response, similarity, matched_query = semantic_cache.lookup(query)

        # キャッシュミスの場合は Bedrock を呼び出してキャッシュに保存
        if not sem_hit:
            answer, usage = call_bedrock(query)
            exact_cache.store(query, answer)
            semantic_cache.store(query, answer)
            response_text = answer
        else:
            response_text = cached_response

        exact_status = "✅ HIT" if exact_hit else "❌ MISS"
        sem_status = "✅ HIT" if sem_hit else "❌ MISS"
        sim_display = f"{similarity:.3f}" if similarity > 0 else "N/A"

        print(f"  Q{i+1}: {query:<26} │ {exact_status:<10} │ {sem_status:<14} │ {sim_display}")

        if sem_hit:
            print(f"      → キャッシュ応答（元クエリ: 「{matched_query[:20]}...」）")

        time.sleep(1)

    print(f"{'─' * 70}")

    # 結果サマリー
    exact_hits = exact_cache.stats["hits"]
    exact_total = exact_cache.stats["hits"] + exact_cache.stats["misses"]
    sem_stats = semantic_cache.get_stats()

    print(f"\n  📊 結果比較:")
    print(f"     完全一致キャッシュ: ヒット率 {exact_hits}/{exact_total} ({exact_hits/exact_total*100:.0f}%)")
    print(f"     セマンティックキャッシュ: ヒット率 {sem_stats['hits']}/{sem_stats['total_requests']} ({sem_stats['hit_rate']:.0f}%)")
    print(f"\n  💡 セマンティックキャッシュは意味的に類似するクエリにもヒットするため、")
    print(f"     実運用ではヒット率が大幅に向上し、Bedrock API コールを削減できます。")


# ============================================================
# デモ 2: 類似度しきい値のチューニング
# ============================================================

def demo_threshold_tuning():
    """しきい値による精度とヒット率のトレードオフを実証"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: 類似度しきい値のチューニング")
    print("=" * 70)
    print("""
  しきい値を変えることで、精度とヒット率のバランスを調整できます。

  ┌────────────┬────────────────────┬──────────────────────────────┐
  │ しきい値   │ 特性               │ ユースケース                 │
  ├────────────┼────────────────────┼──────────────────────────────┤
  │ 0.95以上   │ 高精度・低ヒット率 │ 医療・金融（誤答リスク大）   │
  │ 0.85前後   │ バランス（推奨）   │ 一般的なカスタマーサポート   │
  │ 0.75以下   │ 低精度・高ヒット率 │ FAQ・定型応答                │
  └────────────┴────────────────────┴──────────────────────────────┘
""")

    # 基準クエリをキャッシュに登録
    base_query = "商品の返品手続きについて教えてください"
    print(f"  基準クエリ: 「{base_query}」")
    print()

    # テストクエリ（類似度が異なる）
    test_queries = [
        ("返品の方法を知りたいです", "ほぼ同じ意図"),
        ("購入した商品を返したいのですが", "同じ意図・異なる表現"),
        ("不良品だったので交換してほしい", "関連するが異なる意図"),
        ("おすすめの商品はありますか", "完全に異なる意図"),
    ]

    # 基準クエリの埋め込みを取得
    cache = SemanticCache(similarity_threshold=0.85)
    base_embedding = cache.get_embedding(base_query)

    print(f"{'─' * 70}")
    print(f"  {'テストクエリ':<30} │ {'類似度':<8} │ 0.95 │ 0.85 │ 0.75")
    print(f"{'─' * 70}")

    for query, description in test_queries:
        query_embedding = cache.get_embedding(query)
        similarity = cache.cosine_similarity(base_embedding, query_embedding)

        hit_95 = "✅" if similarity >= 0.95 else "❌"
        hit_85 = "✅" if similarity >= 0.85 else "❌"
        hit_75 = "✅" if similarity >= 0.75 else "❌"

        print(f"  {query:<30} │ {similarity:.4f} │  {hit_95}  │  {hit_85}  │  {hit_75}")
        print(f"  {'(' + description + ')':<30} │")

        time.sleep(0.5)

    print(f"{'─' * 70}")
    print(f"\n  📊 しきい値選択の指針:")
    print(f"     • 誤った応答のコスト > API呼び出しのコスト → 高しきい値（0.90+）")
    print(f"     • API呼び出しコスト削減が最優先 → 低しきい値（0.80-）")
    print(f"     • 推奨: 0.85 から開始し、誤ヒット率を監視しながら調整")


# ============================================================
# デモ 3: キャッシュ無効化戦略
# ============================================================

def demo_invalidation():
    """キャッシュ無効化の3つの戦略を紹介"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: キャッシュ無効化戦略")
    print("=" * 70)
    print("""
  キャッシュの鮮度を保つための3つの戦略をシミュレーションします。
""")

    # --- TTL ベース無効化 ---
    print(f"{'─' * 70}")
    print("  戦略 1: TTL（Time To Live）ベース無効化")
    print(f"{'─' * 70}")

    cache_short = SemanticCache(similarity_threshold=0.85, ttl_seconds=5)

    query = "今日のセール商品は何ですか？"
    answer, _ = call_bedrock(query)
    cache_short.store(query, answer)
    print(f"\n  クエリ「{query}」をキャッシュに保存（TTL: 5秒）")

    # 即時ルックアップ
    hit, _, sim, _ = cache_short.lookup(query)
    print(f"  即時ルックアップ: {'✅ HIT' if hit else '❌ MISS'}")

    # TTL 経過を待つ
    print(f"  ⏳ 6秒待機（TTL 超過）...")
    time.sleep(6)

    hit, _, sim, _ = cache_short.lookup(query)
    print(f"  TTL後ルックアップ: {'✅ HIT' if hit else '❌ MISS（期限切れ）'}")

    print(f"""
  💡 TTL の設計指針:
     • リアルタイム情報（在庫、価格）: 1-5分
     • 半静的情報（商品説明、FAQ）: 1-24時間
     • 静的情報（利用規約、ヘルプ）: 24時間-7日
""")

    # --- イベントベース無効化 ---
    print(f"{'─' * 70}")
    print("  戦略 2: イベントベース無効化")
    print(f"{'─' * 70}")
    print("""
  特定のイベント発生時に関連キャッシュを選択的に無効化します。

  実装パターン（擬似コード）:
  ┌─────────────────────────────────────────────────────────────────┐
  │ # SNS → Lambda → キャッシュ無効化                              │
  │                                                                 │
  │ def handle_product_update(event):                               │
  │     product_id = event['product_id']                            │
  │     # 該当商品に関連するキャッシュエントリを検索・削除          │
  │     invalidate_cache_by_metadata(                               │
  │         filter={"product_id": product_id}                       │
  │     )                                                           │
  │                                                                 │
  │ def handle_knowledge_base_update(event):                        │
  │     category = event['category']                                │
  │     # カテゴリに関連するキャッシュを全削除                      │
  │     invalidate_cache_by_metadata(                               │
  │         filter={"category": category}                           │
  │     )                                                           │
  └─────────────────────────────────────────────────────────────────┘

  適用例:
  • 商品情報更新 → 該当商品のキャッシュを無効化
  • ナレッジベース更新 → 関連カテゴリのキャッシュを無効化
  • 価格変更 → 価格関連クエリのキャッシュを無効化
""")

    # --- バージョンベース無効化 ---
    print(f"{'─' * 70}")
    print("  戦略 3: バージョンベース無効化")
    print(f"{'─' * 70}")
    print("""
  モデルやプロンプトのバージョン変更時に全キャッシュをクリアします。

  実装パターン:
  ┌─────────────────────────────────────────────────────────────────┐
  │ cache_key = f"{model_version}:{prompt_version}:{query_hash}"   │
  │                                                                 │
  │ # バージョンが変わると自動的に新しいキャッシュ空間になる        │
  │ # 旧バージョンのエントリはTTLで自然消滅                        │
  └─────────────────────────────────────────────────────────────────┘

  トリガー:
  • モデル更新（nova-pro-v1:0 → v2:0）
  • システムプロンプト変更
  • 応答フォーマット変更
""")


# ============================================================
# デモ 4: コスト削減効果のシミュレーション
# ============================================================

def demo_cost_simulation():
    """セマンティックキャッシュによるコスト削減をシミュレーション"""
    print("\n\n" + "=" * 70)
    print("  デモ 4: コスト削減効果シミュレーション")
    print("=" * 70)

    # 実際のクエリパターンをシミュレーション
    # ECサイトでは同じ質問の言い換えが多い
    query_groups = [
        # グループ1: 返品関連（全体の25%）
        [
            "返品したいです",
            "商品を返したい",
            "返品の手続き方法",
            "返品ポリシーを教えて",
            "購入した商品の返品について",
        ],
        # グループ2: 配送関連（全体の30%）
        [
            "配送状況を知りたい",
            "荷物はいつ届きますか",
            "配達予定日を教えて",
            "注文した商品の到着日は",
            "発送されましたか",
            "追跡番号を教えて",
        ],
        # グループ3: 支払い関連（全体の20%）
        [
            "支払い方法を変更したい",
            "クレジットカードの変更",
            "別の支払い方法に切り替えたい",
            "決済手段の変更方法",
        ],
        # グループ4: その他（全体の25%）
        [
            "おすすめ商品を教えて",
            "セール情報はありますか",
            "ポイントの使い方",
            "会員ランクについて",
            "店舗の営業時間",
        ],
    ]

    # コスト計算パラメータ
    bedrock_cost_per_call = 0.003  # 1リクエストあたりの平均コスト（USD）
    embedding_cost_per_call = 0.0001  # 埋め込み生成コスト
    monthly_requests = 100000

    # セマンティックキャッシュのシミュレーション
    # 各グループの最初のクエリはMISS、以降はHIT（類似度による）
    estimated_hit_rate = 0.65  # 65%のヒット率を想定

    cost_without_cache = monthly_requests * bedrock_cost_per_call
    cost_with_cache = (
        monthly_requests * (1 - estimated_hit_rate) * bedrock_cost_per_call  # ミス時
        + monthly_requests * embedding_cost_per_call  # 全リクエストで埋め込み生成
    )
    savings = cost_without_cache - cost_with_cache

    print(f"""
  📊 月間シミュレーション結果（{monthly_requests:,} リクエスト/月）

  ┌──────────────────────────┬────────────────┬────────────────┐
  │                          │ キャッシュなし │ セマンティック │
  ├──────────────────────────┼────────────────┼────────────────┤
  │ Bedrock API コール       │ {monthly_requests:>10,}   │ {int(monthly_requests * (1-estimated_hit_rate)):>10,}   │
  │ 埋め込み生成コール       │          0     │ {monthly_requests:>10,}   │
  │ キャッシュヒット率       │       0%       │      {estimated_hit_rate*100:.0f}%       │
  ├──────────────────────────┼────────────────┼────────────────┤
  │ Bedrock API コスト       │   ${cost_without_cache:>9,.2f}  │   ${monthly_requests * (1-estimated_hit_rate) * bedrock_cost_per_call:>9,.2f}  │
  │ 埋め込みコスト           │       $0.00    │      ${monthly_requests * embedding_cost_per_call:>6,.2f}  │
  │ 合計コスト               │   ${cost_without_cache:>9,.2f}  │   ${cost_with_cache:>9,.2f}  │
  ├──────────────────────────┼────────────────┼────────────────┤
  │ 月間削減額               │       -        │   ${savings:>9,.2f}  │
  │ 削減率                   │       -        │      {savings/cost_without_cache*100:.1f}%      │
  └──────────────────────────┴────────────────┴────────────────┘
""")

    # レイテンシー改善
    avg_bedrock_latency = 2.0  # 秒
    avg_cache_latency = 0.1  # 秒（埋め込み生成 + キャッシュ検索）

    avg_latency_without = avg_bedrock_latency
    avg_latency_with = (
        avg_bedrock_latency * (1 - estimated_hit_rate)
        + avg_cache_latency * estimated_hit_rate
    )

    print(f"  ⚡ レイテンシー改善:")
    print(f"     キャッシュなし平均: {avg_latency_without:.1f}秒")
    print(f"     キャッシュあり平均: {avg_latency_with:.2f}秒")
    print(f"     改善率: {(1 - avg_latency_with/avg_latency_without)*100:.0f}%")


# ============================================================
# アーキテクチャまとめ
# ============================================================

def print_architecture():
    """本番環境のセマンティックキャッシュアーキテクチャ"""
    print("\n\n" + "=" * 70)
    print("  本番環境アーキテクチャ")
    print("=" * 70)
    print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │                  セマンティックキャッシュ構成                    │
  └─────────────────────────────────────────────────────────────────┘

  ユーザークエリ
       │
       ▼
  ┌──────────────────┐     ┌────────────────────────────────────┐
  │ Bedrock Titan    │────▶│ Amazon OpenSearch Serverless        │
  │ Embeddings       │     │ (k-NN ベクトル検索)                 │
  │ (ベクトル化)     │     │                                     │
  └──────────────────┘     │ 類似度 >= しきい値?                 │
                           └──────────┬─────────────┬───────────┘
                                      │ YES         │ NO
                                      ▼             ▼
                           ┌──────────────┐  ┌──────────────────┐
                           │ ElastiCache  │  │ Amazon Bedrock    │
                           │ (Redis)      │  │ Converse API      │
                           │ 応答を返却   │  │ 新規推論          │
                           └──────────────┘  └────────┬─────────┘
                                                      │
                                                      ▼
                                             ┌──────────────────┐
                                             │ キャッシュ保存    │
                                             │ OpenSearch + Redis│
                                             └──────────────────┘

  AWS サービス構成:
  • Amazon Bedrock Titan Embeddings: クエリのベクトル化
  • Amazon OpenSearch Serverless: ベクトル類似度検索（k-NN）
  • Amazon ElastiCache (Redis): 応答本文のキャッシュ
  • Amazon SNS/EventBridge: キャッシュ無効化イベント
  • Amazon CloudWatch: ヒット率・レイテンシーモニタリング

  コスト内訳の目安（10万リクエスト/月）:
  • OpenSearch Serverless: ~$30/月
  • ElastiCache (cache.t3.small): ~$25/月
  • Titan Embeddings: ~$10/月
  • 合計インフラコスト: ~$65/月 → Bedrock API $190/月の削減
  • ROI: 約 2.9倍
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 7: セマンティックキャッシュによるコスト削減デモ")
    print("🔷" * 35)
    print("\n  意味的に類似するクエリをキャッシュヒットさせ、API コールを削減します。")
    print("  従来の完全一致キャッシュとの比較を通じて効果を実証します。")
    print()

    # デモ 1: 従来 vs セマンティック
    demo_comparison()
    time.sleep(1)

    # デモ 2: しきい値チューニング
    demo_threshold_tuning()
    time.sleep(1)

    # デモ 3: キャッシュ無効化
    demo_invalidation()

    # デモ 4: コスト削減シミュレーション
    demo_cost_simulation()

    # アーキテクチャまとめ
    print_architecture()
