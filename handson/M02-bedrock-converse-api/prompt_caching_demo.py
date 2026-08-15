"""
モジュール 2: プロンプトキャッシュデモ
- cachePoint を使ったプロンプトキャッシュの動作確認
- キャッシュ有無でのコストとレイテンシーの比較
- cache write / cache read のトークン数を出力

対応モデル: Amazon Nova Micro, Nova Lite, Nova Pro

使い方:
  python prompt_caching_demo.py
"""

import boto3
import json
import time

# =============================================================================
# 設定
# =============================================================================
REGION = "us-east-1"
MODEL_ID = "amazon.nova-lite-v1:0"

# Nova Lite の料金（USD / 1000トークン）
COST_INPUT = 0.00006        # 通常入力
COST_CACHE_WRITE = 0.00006  # キャッシュ書き込み（Nova は通常入力と同額）
COST_CACHE_READ = 0.000006  # キャッシュ読み込み（90%割引）
COST_OUTPUT = 0.00024       # 出力

bedrock = boto3.client('bedrock-runtime', region_name=REGION)


# =============================================================================
# 長いシステムプロンプト（キャッシュ対象）
# =============================================================================
INSURANCE_GUIDELINES = """
あなたは保険会社「サクラ生命」のカスタマーサポート AI アシスタントです。
以下の保険約款および社内規定に基づいて、正確かつ丁寧に回答してください。

■ 保険約款（抜粋）

第1条（目的）
本保険契約は、被保険者の生命または身体に関する保険事故が発生した場合に、
保険金を支払うことを目的とする。

第2条（保険期間）
保険期間は、契約日から起算して保険証券に記載された満了日までとする。
ただし、更新の意思表示がない場合は自動更新とする。

第3条（保険料）
保険料は、被保険者の年齢、性別、健康状態に基づき算定する。
月払い：口座振替日は毎月27日。年払い：契約応当日に一括引落し。
保険料未納が3ヶ月継続した場合、契約は失効する。

第4条（免責期間）
契約開始日から90日間を免責期間とする。
免責期間中に発症した疾病については、給付金の支払い対象外とする。
ただし、不慮の事故による入院は免責期間中も保障する。

第5条（入院給付金）
被保険者が治療を目的として入院した場合、1日あたり10,000円を支給する。
1回の入院につき支払限度日数は60日、通算限度日数は1,095日とする。
日帰り入院も対象とする。

第6条（手術給付金）
被保険者が所定の手術を受けた場合、手術の種類に応じて以下を支給する。
- 入院中の手術：入院給付金日額の20倍（200,000円）
- 外来手術：入院給付金日額の5倍（50,000円）

第7条（通院給付金）
入院給付金の支払い対象となる入院の退院後、180日以内の通院について、
1日あたり5,000円を支給する。通院限度日数は30日とする。

第8条（死亡・高度障害保険金）
被保険者が死亡または高度障害状態に該当した場合、
保険金額の全額（500万円〜3,000万円、契約内容による）を支給する。

第9条（解約返戻金）
契約から3年未満：支払保険料累計の30%
契約から3年以上5年未満：支払保険料累計の50%
契約から5年以上10年未満：支払保険料累計の70%
契約から10年以上：支払保険料累計の85%

第10条（告知義務）
契約時に以下の事項を正確に告知する義務を負う。
- 現在の健康状態、過去5年以内の入院・手術歴
- 現在治療中の疾病、定期的に服用している薬
告知義務違反が判明した場合、契約を解除し保険金を支払わない場合がある。

■ 社内規定

対応原則：
- 常に丁寧語を使用し、顧客に安心感を与える
- 不明確な場合は「確認いたします」と伝え、推測で回答しない
- 個人情報（マイナンバー、口座番号等）は復唱しない
- クレーム対応時は傾聴し、事実確認の上で対応策を提示する

エスカレーション基準：
- 法的判断が必要な場合 → 法務部門
- 保険金額100万円以上の請求 → 査定部門長
- 顧客の感情的な不満が解消されない場合 → スーパーバイザー
"""

# ユーザーからの質問（毎回変わる部分）
USER_QUESTIONS = [
    "免責期間中に事故で入院した場合は保障されますか？",
    "月々の保険料を3ヶ月滞納したらどうなりますか？",
    "手術給付金は外来手術でも支払われますか？金額は？",
    "5年加入して解約した場合、返戻金はいくらですか？",
]


# =============================================================================
# キャッシュなしの呼び出し
# =============================================================================
def call_without_cache(question):
    """キャッシュを使わない通常の呼び出し"""
    start = time.time()
    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": INSURANCE_GUIDELINES}],
        messages=[{
            "role": "user",
            "content": [{"text": question}]
        }],
        inferenceConfig={"temperature": 0.3, "maxTokens": 256}
    )
    latency = time.time() - start
    usage = response['usage']

    return {
        "response": response['output']['message']['content'][0]['text'],
        "latency": latency,
        "input_tokens": usage['inputTokens'],
        "output_tokens": usage['outputTokens'],
        "cache_read": usage.get('cacheReadInputTokens', 0),
        "cache_write": usage.get('cacheWriteInputTokens', 0),
    }


# =============================================================================
# キャッシュありの呼び出し
# =============================================================================
def call_with_cache(question):
    """cachePoint を使ったキャッシュ有効の呼び出し"""
    start = time.time()
    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[
            {"text": INSURANCE_GUIDELINES},
            {"cachePoint": {"type": "default"}}  # ← ここまでをキャッシュ
        ],
        messages=[{
            "role": "user",
            "content": [{"text": question}]
        }],
        inferenceConfig={"temperature": 0.3, "maxTokens": 256}
    )
    latency = time.time() - start
    usage = response['usage']

    return {
        "response": response['output']['message']['content'][0]['text'],
        "latency": latency,
        "input_tokens": usage['inputTokens'],
        "output_tokens": usage['outputTokens'],
        "cache_read": usage.get('cacheReadInputTokens', 0),
        "cache_write": usage.get('cacheWriteInputTokens', 0),
    }


# =============================================================================
# コスト計算
# =============================================================================
def calculate_cost(result):
    """トークン使用量からコストを計算"""
    cost = (
        result['input_tokens'] / 1000 * COST_INPUT +
        result['output_tokens'] / 1000 * COST_OUTPUT +
        result['cache_write'] / 1000 * COST_CACHE_WRITE +
        result['cache_read'] / 1000 * COST_CACHE_READ
    )
    return cost


# =============================================================================
# メイン
# =============================================================================
def main():
    print("=" * 70)
    print("  プロンプトキャッシュ デモ")
    print("=" * 70)
    print(f"\n  モデル: {MODEL_ID}")
    print(f"  システムプロンプト: {len(INSURANCE_GUIDELINES)} 文字（保険約款+社内規定）")
    print(f"  質問数: {len(USER_QUESTIONS)}")

    # ─── キャッシュなし ───
    print(f"\n\n{'─' * 70}")
    print("  [1/2] キャッシュなし（通常呼び出し）")
    print(f"{'─' * 70}")

    no_cache_results = []
    for i, q in enumerate(USER_QUESTIONS, 1):
        print(f"\n  質問{i}: {q}")
        result = call_without_cache(q)
        no_cache_results.append(result)
        cost = calculate_cost(result)
        print(f"    レイテンシー: {result['latency']:.2f}s")
        print(f"    入力トークン: {result['input_tokens']} | 出力: {result['output_tokens']}")
        print(f"    キャッシュ読込: {result['cache_read']} | キャッシュ書込: {result['cache_write']}")
        print(f"    コスト: ${cost:.6f}")
        print(f"    回答: {result['response'][:80]}...")

    # ─── キャッシュあり ───
    print(f"\n\n{'─' * 70}")
    print("  [2/2] キャッシュあり（cachePoint 使用）")
    print(f"{'─' * 70}")
    print(f"\n  ※ 1回目はキャッシュ書き込み（cache write）、2回目以降はキャッシュ読込（cache read）")

    cache_results = []
    for i, q in enumerate(USER_QUESTIONS, 1):
        print(f"\n  質問{i}: {q}")
        result = call_with_cache(q)
        cache_results.append(result)
        cost = calculate_cost(result)

        # キャッシュ状態の判定
        if result['cache_write'] > 0:
            cache_status = "📝 CACHE WRITE（初回書き込み）"
        elif result['cache_read'] > 0:
            cache_status = "⚡ CACHE READ（キャッシュヒット!）"
        else:
            cache_status = "─ キャッシュ未使用"

        print(f"    レイテンシー: {result['latency']:.2f}s")
        print(f"    入力トークン: {result['input_tokens']} | 出力: {result['output_tokens']}")
        print(f"    キャッシュ読込: {result['cache_read']} | キャッシュ書込: {result['cache_write']}")
        print(f"    ステータス: {cache_status}")
        print(f"    コスト: ${cost:.6f}")
        print(f"    回答: {result['response'][:80]}...")

    # ─── 比較サマリー ───
    print(f"\n\n{'=' * 70}")
    print("  比較サマリー")
    print(f"{'=' * 70}")

    total_latency_no_cache = sum(r['latency'] for r in no_cache_results)
    total_latency_cache = sum(r['latency'] for r in cache_results)
    total_cost_no_cache = sum(calculate_cost(r) for r in no_cache_results)
    total_cost_cache = sum(calculate_cost(r) for r in cache_results)
    total_input_no_cache = sum(r['input_tokens'] for r in no_cache_results)
    total_cache_read = sum(r['cache_read'] for r in cache_results)

    print(f"\n  {'メトリクス':<20} {'キャッシュなし':<18} {'キャッシュあり':<18} {'効果'}")
    print(f"  {'─' * 70}")

    latency_diff = (1 - total_latency_cache / total_latency_no_cache) * 100 if total_latency_no_cache > 0 else 0
    print(f"  {'合計レイテンシー':<20} {total_latency_no_cache:<18.2f} {total_latency_cache:<18.2f} {latency_diff:+.1f}%")

    cost_diff = (1 - total_cost_cache / total_cost_no_cache) * 100 if total_cost_no_cache > 0 else 0
    print(f"  {'合計コスト (USD)':<20} ${total_cost_no_cache:<17.6f} ${total_cost_cache:<17.6f} {cost_diff:+.1f}%")

    print(f"  {'合計入力トークン':<20} {total_input_no_cache:<18} {sum(r['input_tokens'] for r in cache_results):<18}")
    print(f"  {'キャッシュ読込':<20} {'0':<18} {total_cache_read:<18}")

    # 月間試算
    daily_calls = 10000
    monthly_no_cache = total_cost_no_cache / len(USER_QUESTIONS) * daily_calls * 30
    monthly_cache = total_cost_cache / len(USER_QUESTIONS) * daily_calls * 30

    print(f"\n  月間コスト試算（{daily_calls:,} リクエスト/日、同一システムプロンプト想定）:")
    print(f"    キャッシュなし: ${monthly_no_cache:.2f}/月")
    print(f"    キャッシュあり: ${monthly_cache:.2f}/月")
    print(f"    月間削減額:     ${monthly_no_cache - monthly_cache:.2f}")

    print(f"""
{'=' * 70}
  プロンプトキャッシュのポイント:

  1. cachePoint を system プロンプトの後に配置
     → 長い約款・規定テキストをキャッシュ対象にする
  2. 1回目は cache write（書き込みコスト発生）
     2回目以降は cache read（読込コスト = 通常の 1/10）
  3. キャッシュ TTL は 5分（Nova）
     → 5分以内に次のリクエストが来ればキャッシュヒット
  4. 対応モデル: Nova Micro, Nova Lite, Nova Pro,
     Claude 3.5 Haiku, Claude 3.7/4 Sonnet, Claude 4 Opus
{'=' * 70}
""")


if __name__ == "__main__":
    main()
