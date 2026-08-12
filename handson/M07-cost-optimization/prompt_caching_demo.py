"""
モジュール 7: プロンプトキャッシングによるコスト削減デモ
- キャッシュなしのベースラインリクエスト
- cachePoint マーカーを使用したキャッシュ書き込み
- キャッシュヒットによるコスト削減の効果測定
- 最適なキャッシュポイント設計パターン
"""

import boto3
import json
import time

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "amazon.nova-pro-v1:0"


# ============================================================
# ECサイト商品推薦チャットボットのシステムコンテキスト（長文）
# キャッシュ効果を最大化するため、固定部分を大きくする
# ============================================================

PRODUCT_CATALOG_CONTEXT = """あなたはECサイト「TechMart」の商品推薦AIアシスタントです。

【企業情報】
- 企業名: TechMart株式会社
- 設立: 2015年
- 従業員数: 500名
- 年間取扱高: 200億円
- 取扱カテゴリ: 家電、PC周辺機器、スマートホーム、オフィス用品

【商品カタログ（抜粋）】

カテゴリ: ノートPC
- TM-NPC-001: UltraBook Pro 14" (¥198,000) - Core i7, 16GB RAM, 512GB SSD, 重量1.2kg
- TM-NPC-002: WorkStation 16" (¥298,000) - Core i9, 32GB RAM, 1TB SSD, RTX 4060
- TM-NPC-003: Budget Note 15" (¥79,800) - Core i5, 8GB RAM, 256GB SSD
- TM-NPC-004: Creator Pro 15" (¥258,000) - Core i7, 32GB RAM, 1TB SSD, RTX 4070
- TM-NPC-005: Student Edition 13" (¥59,800) - Ryzen 5, 8GB RAM, 256GB SSD

カテゴリ: モニター
- TM-MON-001: 4K Professional 27" (¥89,800) - IPS, sRGB 100%, USB-C
- TM-MON-002: Gaming 240Hz 27" (¥69,800) - IPS, 1ms応答, FreeSync
- TM-MON-003: Ultrawide 34" (¥128,000) - UWQHD, USB-C PD 90W
- TM-MON-004: Budget 24" FHD (¥29,800) - IPS, 75Hz, VESA対応
- TM-MON-005: Portable 15.6" (¥39,800) - FHD, USB-C, 重量680g

カテゴリ: スマートホーム
- TM-SH-001: スマートスピーカー Pro (¥15,800) - Alexa対応, 360度音響
- TM-SH-002: スマートライト 4個セット (¥9,800) - RGB, 音声操作対応
- TM-SH-003: スマートロック (¥29,800) - 指紋+暗証番号+アプリ対応
- TM-SH-004: ロボット掃除機 (¥59,800) - マッピング機能, 自動充電
- TM-SH-005: スマートカメラ 屋外用 (¥12,800) - 防水IP65, 暗視対応

カテゴリ: オフィス用品
- TM-OF-001: エルゴノミクスチェア (¥89,800) - メッシュ, ランバーサポート
- TM-OF-002: 電動昇降デスク (¥69,800) - 幅140cm, メモリ機能付き
- TM-OF-003: ワイヤレスキーボード (¥12,800) - メカニカル, BT5.0
- TM-OF-004: ドッキングステーション (¥19,800) - USB-C, デュアル4K対応
- TM-OF-005: ノイズキャンセリングヘッドセット (¥34,800) - BT, 30時間駆動

【推薦ルール】
1. ユーザーの予算を最優先で考慮する
2. 用途に合った性能要件を満たす商品を推薦する
3. 最大3つまでの候補を提示し、それぞれの理由を説明する
4. クロスセル機会があれば関連商品も提案する
5. 在庫切れ商品（末尾が偶数のSKU）は推薦しない
6. セット割引対象（同カテゴリ2点以上）の場合は割引情報を付記する

【応答フォーマット】
- 挨拶は不要、直接推薦に入る
- 各推薦に「おすすめ度」を★1-5で付与する
- 価格は税込表示（10%加算）
- 比較表を含める場合はMarkdown形式で"""

# 各質問のバリエーション（同じコンテキストで異なる質問を行う）
USER_QUESTIONS = [
    "予算15万円以内でリモートワーク用のノートPCを探しています。Web会議が多いです。",
    "プログラミングと動画編集を両方やりたいのですが、おすすめのPCとモニターの組み合わせは？",
    "新居に引っ越すので、スマートホーム化したいです。予算5万円でおすすめを教えてください。",
]


# ============================================================
# コスト計算ユーティリティ
# ============================================================

# Nova Pro の参考料金（1000トークンあたり、USD）
PRICING = {
    "input_per_1k": 0.0008,
    "output_per_1k": 0.0032,
    "cache_write_per_1k": 0.00096,  # 書き込みプレミアム: 入力の1.2倍
    "cache_read_per_1k": 0.0002,    # キャッシュ読み取り: 入力の0.25倍
}


def calculate_cost(usage):
    """トークン使用量からコストを計算"""
    input_tokens = usage.get('inputTokens', 0)
    output_tokens = usage.get('outputTokens', 0)
    cache_read = usage.get('cacheReadInputTokens', 0)
    cache_write = usage.get('cacheWriteInputTokens', 0)

    # キャッシュ分は入力トークンから差し引いて計算
    regular_input = input_tokens - cache_read - cache_write

    cost = (
        (regular_input / 1000) * PRICING["input_per_1k"]
        + (output_tokens / 1000) * PRICING["output_per_1k"]
        + (cache_write / 1000) * PRICING["cache_write_per_1k"]
        + (cache_read / 1000) * PRICING["cache_read_per_1k"]
    )
    return cost


def print_usage(usage, label, elapsed_time):
    """トークン使用量とコストを整形表示"""
    input_tokens = usage.get('inputTokens', 0)
    output_tokens = usage.get('outputTokens', 0)
    cache_read = usage.get('cacheReadInputTokens', 0)
    cache_write = usage.get('cacheWriteInputTokens', 0)
    cost = calculate_cost(usage)

    print(f"\n  📊 {label}")
    print(f"  {'─' * 50}")
    print(f"  入力トークン:         {input_tokens:>8,}")
    print(f"  出力トークン:         {output_tokens:>8,}")
    print(f"  キャッシュ書き込み:   {cache_write:>8,}")
    print(f"  キャッシュ読み取り:   {cache_read:>8,}")
    print(f"  推定コスト:           ${cost:.6f}")
    print(f"  レイテンシー:         {elapsed_time:.2f}秒")


# ============================================================
# デモ 1: ベースライン（キャッシュなし）
# ============================================================

def demo_baseline():
    """キャッシュを使用しない通常リクエスト"""
    print("=" * 70)
    print("  パート 1: ベースライン（プロンプトキャッシングなし）")
    print("=" * 70)
    print("\n  長文のシステムコンテキスト + ユーザー質問を毎回フルで送信します。")
    print(f"  コンテキスト文字数: 約 {len(PRODUCT_CATALOG_CONTEXT):,} 文字")

    question = USER_QUESTIONS[0]
    print(f"\n  質問: {question}")
    print(f"\n{'─' * 70}")

    full_prompt = f"{PRODUCT_CATALOG_CONTEXT}\n\n---\nユーザーの質問: {question}"

    start = time.time()
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{
                "role": "user",
                "content": [{"text": full_prompt}]
            }],
            inferenceConfig={"temperature": 0.3, "maxTokens": 600}
        )
        elapsed = time.time() - start

        # レスポンス表示
        answer = response['output']['message']['content'][0]['text']
        print(f"\n  💬 応答:\n")
        for line in answer.split('\n'):
            print(f"    {line}")

        # 使用量表示
        usage = response['usage']
        print_usage(usage, "ベースライン使用量", elapsed)

        return usage, elapsed

    except Exception as e:
        print(f"\n  ❌ エラー: {e}")
        return None, 0


# ============================================================
# デモ 2: キャッシュ書き込み（cachePoint 付きリクエスト）
# ============================================================

def demo_cache_write():
    """cachePoint を使用してキャッシュを書き込む"""
    print("\n\n" + "=" * 70)
    print("  パート 2: キャッシュ書き込み（cachePoint マーカー使用）")
    print("=" * 70)
    print("""
  cachePoint の配置戦略:
  ┌────────────────────────────────────────┐
  │ 固定コンテキスト（商品カタログ等）     │ ← キャッシュ対象
  │ ...長文のシステム指示...               │
  ├──── cachePoint ────────────────────────┤ ← キャッシュ境界
  │ 可変部分（ユーザーの質問）             │ ← 毎回異なる
  └────────────────────────────────────────┘
""")

    question = USER_QUESTIONS[0]
    print(f"  質問: {question}")
    print(f"\n{'─' * 70}")

    start = time.time()
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{
                "role": "user",
                "content": [
                    {"text": PRODUCT_CATALOG_CONTEXT},
                    {"cachePoint": {"type": "default"}},
                    {"text": f"\n---\nユーザーの質問: {question}"}
                ]
            }],
            inferenceConfig={"temperature": 0.3, "maxTokens": 600}
        )
        elapsed = time.time() - start

        answer = response['output']['message']['content'][0]['text']
        print(f"\n  💬 応答:\n")
        for line in answer.split('\n'):
            print(f"    {line}")

        usage = response['usage']
        print_usage(usage, "キャッシュ書き込み使用量", elapsed)

        # 書き込みプレミアムの説明
        cache_write = usage.get('cacheWriteInputTokens', 0)
        if cache_write > 0:
            print(f"\n  💡 キャッシュ書き込み発生: {cache_write:,} トークンがキャッシュされました")
            print("     初回は書き込みプレミアム（入力の1.2倍）が加算されます")
            print("     次回以降のリクエストでコストが大幅削減されます")

        return usage, elapsed

    except Exception as e:
        print(f"\n  ❌ エラー: {e}")
        return None, 0


# ============================================================
# デモ 3: キャッシュヒット（同じプレフィックスで別の質問）
# ============================================================

def demo_cache_hit():
    """キャッシュヒットによるコスト削減を実証"""
    print("\n\n" + "=" * 70)
    print("  パート 3: キャッシュヒット（同じプレフィックスで別の質問）")
    print("=" * 70)
    print("\n  同じ商品カタログコンテキストで異なる質問を送信します。")
    print("  キャッシュされたプレフィックスが再利用され、コストが大幅削減されます。")

    results = []

    for i, question in enumerate(USER_QUESTIONS[1:], start=2):
        print(f"\n{'─' * 70}")
        print(f"  質問 {i}: {question}")
        print(f"{'─' * 70}")

        start = time.time()
        try:
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [
                        {"text": PRODUCT_CATALOG_CONTEXT},
                        {"cachePoint": {"type": "default"}},
                        {"text": f"\n---\nユーザーの質問: {question}"}
                    ]
                }],
                inferenceConfig={"temperature": 0.3, "maxTokens": 600}
            )
            elapsed = time.time() - start

            answer = response['output']['message']['content'][0]['text']
            print(f"\n  💬 応答:\n")
            for line in answer.split('\n'):
                print(f"    {line}")

            usage = response['usage']
            print_usage(usage, f"キャッシュヒット使用量（質問{i}）", elapsed)
            results.append((usage, elapsed))

            cache_read = usage.get('cacheReadInputTokens', 0)
            if cache_read > 0:
                print(f"\n  ✅ キャッシュヒット! {cache_read:,} トークンをキャッシュから読み取り")
                print(f"     キャッシュ読み取り料金は通常入力の 25% → 75%コスト削減")

        except Exception as e:
            print(f"\n  ❌ エラー: {e}")
            results.append((None, 0))

        time.sleep(1)

    return results


# ============================================================
# 効果測定サマリー
# ============================================================

def print_cost_summary(baseline, cache_write, cache_hits):
    """3パターンのコスト比較サマリーを表示"""
    print("\n\n" + "=" * 70)
    print("  コスト削減効果サマリー")
    print("=" * 70)

    baseline_usage, baseline_time = baseline
    write_usage, write_time = cache_write

    if not baseline_usage or not write_usage:
        print("\n  ⚠️ 一部のリクエストが失敗したため、完全な比較ができません")
        return

    baseline_cost = calculate_cost(baseline_usage)
    write_cost = calculate_cost(write_usage)

    print(f"""
  ┌─────────────────────┬──────────────┬──────────────┬────────────────┐
  │ リクエスト          │ 推定コスト   │ レイテンシー │ キャッシュ状態 │
  ├─────────────────────┼──────────────┼──────────────┼────────────────┤
  │ ベースライン        │ ${baseline_cost:.6f} │ {baseline_time:>6.2f}秒     │ なし           │
  │ キャッシュ書き込み  │ ${write_cost:.6f} │ {write_time:>6.2f}秒     │ WRITE          │""")

    total_hit_cost = 0
    for i, (usage, elapsed) in enumerate(cache_hits):
        if usage:
            hit_cost = calculate_cost(usage)
            total_hit_cost += hit_cost
            print(f"  │ キャッシュヒット {i+1}   │ ${hit_cost:.6f} │ {elapsed:>6.2f}秒     │ READ ✅        │")

    print(f"  └─────────────────────┴──────────────┴──────────────┴────────────────┘")

    # コスト削減率の計算
    if cache_hits and cache_hits[0][0]:
        hit_cost = calculate_cost(cache_hits[0][0])
        savings_pct = ((baseline_cost - hit_cost) / baseline_cost) * 100
        print(f"\n  📈 キャッシュヒット時のコスト削減率: {savings_pct:.1f}%")

        latency_improvement = ((baseline_time - cache_hits[0][1]) / baseline_time) * 100
        if latency_improvement > 0:
            print(f"  ⚡ レイテンシー改善率: {latency_improvement:.1f}%")

    # 月間コスト試算
    monthly_requests = 100000
    hit_rate = 0.7  # 想定キャッシュヒット率 70%
    print(f"\n  💰 月間試算（{monthly_requests:,} リクエスト、ヒット率 {hit_rate*100:.0f}%）:")
    monthly_baseline = baseline_cost * monthly_requests
    if cache_hits and cache_hits[0][0]:
        hit_cost = calculate_cost(cache_hits[0][0])
        monthly_optimized = (
            baseline_cost * monthly_requests * (1 - hit_rate)
            + hit_cost * monthly_requests * hit_rate
        )
        monthly_savings = monthly_baseline - monthly_optimized
        print(f"     最適化前: ${monthly_baseline:,.2f}/月")
        print(f"     最適化後: ${monthly_optimized:,.2f}/月")
        print(f"     削減額:   ${monthly_savings:,.2f}/月 ({monthly_savings/monthly_baseline*100:.1f}%削減)")


# ============================================================
# キャッシュポイント設計のベストプラクティス
# ============================================================

def print_best_practices():
    """キャッシュ設計のベストプラクティスを表示"""
    print("\n\n" + "=" * 70)
    print("  プロンプトキャッシング設計のベストプラクティス")
    print("=" * 70)
    print("""
  1. キャッシュポイントの配置原則:
     ┌──────────────────────────────────────────────────────────┐
     │ ✅ 効果的な配置                                         │
     │   • 固定のシステム指示（変更頻度: 月1回以下）           │
     │   • 商品カタログ、FAQ、ルール集                         │
     │   • RAG で取得した共通ドキュメント                      │
     ├──────────────────────────────────────────────────────────┤
     │ ❌ 非効果的な配置                                       │
     │   • ユーザーごとに異なるパーソナライズ情報              │
     │   • リアルタイム在庫情報（頻繁に変化）                  │
     │   • セッション固有の会話履歴                             │
     └──────────────────────────────────────────────────────────┘

  2. キャッシュ TTL 戦略:
     • デフォルト TTL: 5分（Bedrock のキャッシュ保持時間）
     • 利用パターンに合わせたリクエスト間隔設計
     • ウォームアップリクエストで事前キャッシュ構築

  3. コスト最適化の公式:
     損益分岐点 = 書き込みプレミアム / (通常料金 - 読み取り料金)
     例: 0.2倍プレミアム / (1.0 - 0.25) = 0.27回
     → 1回書き込み後、1回以上ヒットすれば元が取れる

  4. マルチターン会話でのキャッシュ活用:
     messages = [
         {"role": "user", "content": [
             {"text": system_context},        # 固定
             {"cachePoint": {"type": "default"}},
             {"text": conversation_history},   # 蓄積される
             {"cachePoint": {"type": "default"}},  # 2つ目のキャッシュポイント
             {"text": latest_question}         # 最新の質問のみ変化
         ]}
     ]
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 7: プロンプトキャッシングによるコスト削減デモ")
    print("🔷" * 35)
    print("\n  Bedrock プロンプトキャッシングの効果を3段階で実証します:")
    print("  1️⃣  ベースライン: キャッシュなし")
    print("  2️⃣  キャッシュ書き込み: cachePoint 配置")
    print("  3️⃣  キャッシュヒット: コスト大幅削減")
    print()

    # Step 1: ベースライン
    baseline = demo_baseline()
    time.sleep(2)

    # Step 2: キャッシュ書き込み
    cache_write_result = demo_cache_write()
    time.sleep(3)  # キャッシュが反映されるまで少し待つ

    # Step 3: キャッシュヒット
    cache_hits = demo_cache_hit()

    # サマリー
    print_cost_summary(baseline, cache_write_result, cache_hits)
    print_best_practices()
