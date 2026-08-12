"""
モジュール 2: エンドツーエンド データ処理パイプラインデモ
- 検証ステージ → 処理ステージ → 最適化効果の測定
- 各ステージのレイテンシー、トークン使用量、コストを比較
"""

import boto3
import json
import time
import re
from datetime import datetime

# AWS クライアント
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

MODEL_ID = "amazon.nova-lite-v1:0"

# Nova Lite 料金（1000トークンあたり USD）
COST_INPUT_PER_1K = 0.00006
COST_OUTPUT_PER_1K = 0.00024


# =============================================================================
# サンプルデータ
# =============================================================================
SAMPLE_RECORDS = [
    {
        "id": "rec-001",
        "timestamp": "2024-11-15T10:30:00Z",
        "content": "田中太郎です。電話番号は090-1234-5678です。先日の診察について質問があります。処方された薬の副作用が気になります。メールアドレスはtanaka@example.comです。",
        "category": "medical_inquiry",
        "language": "ja"
    },
    {
        "id": "rec-002",
        "timestamp": "2024-11-15T11:00:00Z",
        "content": "予約の変更をお願いします。次回は来週の火曜日に変更したいです。担当医の山田先生でお願いします。",
        "category": "appointment",
        "language": "ja"
    },
    {
        "id": "rec-003",
        "timestamp": "2024-11-15T14:00:00Z",
        "content": "私のマイナンバーは123456789012です。保険証番号は12345678で、住所は東京都渋谷区神宮前1-2-3です。検査結果を郵送してください。",
        "category": "personal_info",
        "language": "ja"
    },
]


# =============================================================================
# ステージ 1: データ検証
# =============================================================================
def validate_record(record):
    """レコードの完全性と形式を検証する"""
    issues = []
    required = ["id", "timestamp", "content", "category", "language"]

    for field in required:
        if not record.get(field):
            issues.append(f"'{field}' が空または欠落")

    if record.get("timestamp"):
        try:
            datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            issues.append("タイムスタンプ形式不正")

    content = record.get("content", "")
    if len(content) > 10000:
        issues.append("コンテンツが長すぎます")

    is_valid = len(issues) == 0
    return {"valid": is_valid, "issues": issues}


# =============================================================================
# ステージ 2: PII 検出とマスキング（正規表現ベース）
# =============================================================================
PII_PATTERNS = {
    "PHONE": r'0\d{1,4}-\d{1,4}-\d{3,4}',
    "EMAIL": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "MY_NUMBER": r'\d{12}',
    "ADDRESS": r'(東京都|大阪府|北海道|.{2,3}県).{2,}[0-9\-]+',
}


def detect_and_mask_pii(text):
    """PII を検出しマスキングする"""
    entities = []
    for pii_type, pattern in PII_PATTERNS.items():
        for match in re.finditer(pattern, text):
            entities.append({
                "type": pii_type,
                "text": match.group(),
                "begin": match.start(),
                "end": match.end()
            })

    # マスキング（後ろから）
    masked = text
    for entity in sorted(entities, key=lambda x: x['begin'], reverse=True):
        masked = masked[:entity['begin']] + f"[{entity['type']}]" + masked[entity['end']:]

    return {"original": text, "masked": masked, "pii_count": len(entities), "entities": entities}


# =============================================================================
# ステージ 3: Bedrock Converse API 処理
# =============================================================================
def process_with_bedrock(text, system_prompt="", use_optimization=False):
    """Bedrock Converse API でテキストを処理する"""
    messages = [{"role": "user", "content": [{"text": text}]}]

    kwargs = {
        "modelId": MODEL_ID,
        "messages": messages,
        "inferenceConfig": {"temperature": 0.3, "maxTokens": 256}
    }
    if system_prompt:
        kwargs["system"] = [{"text": system_prompt}]

    start = time.time()
    response = bedrock.converse(**kwargs)
    latency = time.time() - start

    output = response['output']['message']['content'][0]['text']
    usage = response['usage']

    return {
        "response": output,
        "latency": latency,
        "input_tokens": usage['inputTokens'],
        "output_tokens": usage['outputTokens'],
        "cost": (usage['inputTokens'] / 1000 * COST_INPUT_PER_1K +
                 usage['outputTokens'] / 1000 * COST_OUTPUT_PER_1K)
    }


# =============================================================================
# パイプライン実行
# =============================================================================
def run_pipeline(records, use_optimization=False):
    """パイプライン全体を実行する"""
    label = "最適化あり" if use_optimization else "最適化なし"
    results = []
    total_latency = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0

    for record in records:
        stage_results = {"id": record["id"]}

        # ステージ 1: 検証
        t0 = time.time()
        validation = validate_record(record)
        stage_results["validation_latency"] = time.time() - t0
        stage_results["valid"] = validation["valid"]

        if not validation["valid"]:
            stage_results["skipped"] = True
            results.append(stage_results)
            continue

        # ステージ 2: PII マスキング
        t0 = time.time()
        pii_result = detect_and_mask_pii(record["content"])
        stage_results["pii_latency"] = time.time() - t0
        stage_results["pii_count"] = pii_result["pii_count"]

        # ステージ 3: Bedrock 処理（マスキング済みテキストを使用）
        if use_optimization:
            # 最適化版: 簡潔なプロンプト + JSON出力指示のみ
            query = f"分析対象:\n{pii_result['masked']}\n\nカテゴリと優先度(高/中/低)をJSON出力。"
            system = "フィードバック分析AI。JSON形式: {{\"category\":...,\"priority\":...,\"reason\":...}}"
        else:
            query = f"以下のフィードバックを分析し、カテゴリと対応優先度（高/中/低）を判定してください。\n\n{pii_result['masked']}"
            system = "あなたはヘルスケア企業のフィードバック分析アシスタントです。JSON形式で回答してください。"

        bedrock_result = process_with_bedrock(query, system_prompt=system)
        stage_results["bedrock_latency"] = bedrock_result["latency"]
        stage_results["input_tokens"] = bedrock_result["input_tokens"]
        stage_results["output_tokens"] = bedrock_result["output_tokens"]
        stage_results["cost"] = bedrock_result["cost"]

        total_latency += bedrock_result["latency"]
        total_input_tokens += bedrock_result["input_tokens"]
        total_output_tokens += bedrock_result["output_tokens"]
        total_cost += bedrock_result["cost"]

        results.append(stage_results)

    return {
        "label": label,
        "results": results,
        "total_latency": total_latency,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost": total_cost
    }


# =============================================================================
# メイン
# =============================================================================
def main():
    print("=" * 70)
    print("  エンドツーエンド データ処理パイプライン デモ")
    print("=" * 70)
    print(f"\n  モデル: {MODEL_ID}")
    print(f"  レコード数: {len(SAMPLE_RECORDS)}")

    # --- パイプライン 1: 最適化なし ---
    print(f"\n\n{'─' * 70}")
    print("  パイプライン実行 [1/2]: 最適化なし")
    print(f"{'─' * 70}")

    run1 = run_pipeline(SAMPLE_RECORDS, use_optimization=False)

    for r in run1["results"]:
        status = "✅ 処理完了" if not r.get("skipped") else "⏭ スキップ"
        print(f"\n  {r['id']}: {status}")
        if not r.get("skipped"):
            print(f"    検証: {r['validation_latency']*1000:.1f}ms | PII: {r['pii_count']}件 ({r['pii_latency']*1000:.1f}ms)")
            print(f"    Bedrock: {r['bedrock_latency']:.2f}s | トークン: {r['input_tokens']}入力 + {r['output_tokens']}出力")
            print(f"    コスト: ${r['cost']:.6f}")

    # --- パイプライン 2: 最適化あり ---
    print(f"\n\n{'─' * 70}")
    print("  パイプライン実行 [2/2]: 最適化あり（プロンプト圧縮）")
    print(f"{'─' * 70}")

    run2 = run_pipeline(SAMPLE_RECORDS, use_optimization=True)

    for r in run2["results"]:
        status = "✅ 処理完了" if not r.get("skipped") else "⏭ スキップ"
        print(f"\n  {r['id']}: {status}")
        if not r.get("skipped"):
            print(f"    検証: {r['validation_latency']*1000:.1f}ms | PII: {r['pii_count']}件 ({r['pii_latency']*1000:.1f}ms)")
            print(f"    Bedrock: {r['bedrock_latency']:.2f}s | トークン: {r['input_tokens']}入力 + {r['output_tokens']}出力")
            print(f"    コスト: ${r['cost']:.6f}")

    # --- 比較サマリー ---
    print(f"\n\n{'=' * 70}")
    print("  最適化効果の比較")
    print(f"{'=' * 70}")

    print(f"\n  {'メトリクス':<20} {'最適化なし':<18} {'最適化あり':<18} {'削減率'}")
    print(f"  {'─' * 65}")

    # レイテンシー
    lat1, lat2 = run1["total_latency"], run2["total_latency"]
    lat_reduction = (1 - lat2 / lat1) * 100 if lat1 > 0 else 0
    print(f"  {'合計レイテンシー':<20} {lat1:<18.2f} {lat2:<18.2f} {lat_reduction:.1f}%")

    # 入力トークン
    tok1, tok2 = run1["total_input_tokens"], run2["total_input_tokens"]
    tok_reduction = (1 - tok2 / tok1) * 100 if tok1 > 0 else 0
    print(f"  {'入力トークン':<20} {tok1:<18} {tok2:<18} {tok_reduction:.1f}%")

    # コスト
    cost1, cost2 = run1["total_cost"], run2["total_cost"]
    cost_reduction = (1 - cost2 / cost1) * 100 if cost1 > 0 else 0
    print(f"  {'合計コスト (USD)':<20} ${cost1:<17.6f} ${cost2:<17.6f} {cost_reduction:.1f}%")

    # 月間試算
    daily_requests = 10000
    monthly_cost1 = cost1 / len(SAMPLE_RECORDS) * daily_requests * 30
    monthly_cost2 = cost2 / len(SAMPLE_RECORDS) * daily_requests * 30

    print(f"\n  月間コスト試算（{daily_requests:,}リクエスト/日）:")
    print(f"    最適化なし: ${monthly_cost1:.2f}/月")
    print(f"    最適化あり: ${monthly_cost2:.2f}/月")
    print(f"    月間削減額: ${monthly_cost1 - monthly_cost2:.2f}")

    print(f"\n{'=' * 70}")
    print("  パイプラインの処理フロー:")
    print("""
  ┌──────────┐    ┌───────────┐    ┌──────────────┐    ┌──────────┐
  │ データ   │───▶│  検証     │───▶│ PII マスク   │───▶│ Bedrock  │
  │ 入力     │    │ (形式等)  │    │ (Comprehend/ │    │ Converse │
  │          │    │           │    │  正規表現)   │    │ API      │
  └──────────┘    └───────────┘    └──────────────┘    └──────────┘
                        │                                     │
                   不合格 → 差戻し                       分析結果出力
""")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
