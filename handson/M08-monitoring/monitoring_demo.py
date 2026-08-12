"""
モジュール 8: カスタムメトリクス発行とトークンモニタリングデモ
- Bedrock モデル呼び出しとトークン使用量の記録
- CloudWatch カスタムメトリクスへのリアルタイム発行
- レイテンシー（P50/P95/P99）の計測
- 推定コストの追跡とアラート連携
- 動的ベースラインによる異常検知
"""

import boto3
import json
import time
import random
from datetime import datetime, timezone
from collections import defaultdict

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

MODEL_ID = "amazon.nova-lite-v1:0"
NAMESPACE = "GenAI/Bedrock"

# Nova Lite の参考料金（1000トークンあたり、USD）
PRICING = {
    "input_per_1k": 0.00006,
    "output_per_1k": 0.00024,
}


# ============================================================
# メトリクス収集クラス
# ============================================================

class MetricsCollector:
    """
    Bedrock 呼び出しのメトリクスを収集し CloudWatch に発行するクラス

    追跡メトリクス:
    - InputTokensPerRequest: リクエストあたりの入力トークン数
    - OutputTokensPerRequest: リクエストあたりの出力トークン数
    - ModelLatency: モデル呼び出しレイテンシー（ms）
    - EstimatedCost: 推定コスト（USD）
    - ErrorRate: エラー発生率（%）
    - RequestCount: リクエスト数
    """

    def __init__(self, model_id, namespace=NAMESPACE):
        self.model_id = model_id
        self.namespace = namespace
        self.metrics_buffer = []
        self.latencies = []
        self.total_requests = 0
        self.total_errors = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0

    def record_invocation(self, usage, latency_ms, success=True):
        """単一のモデル呼び出し結果を記録"""
        self.total_requests += 1

        if not success:
            self.total_errors += 1
            self._add_metric("ErrorRate", 100.0, "Percent")
            self._add_metric("RequestCount", 1, "Count")
            return

        input_tokens = usage.get('inputTokens', 0)
        output_tokens = usage.get('outputTokens', 0)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.latencies.append(latency_ms)

        # コスト計算
        cost = (
            (input_tokens / 1000) * PRICING["input_per_1k"]
            + (output_tokens / 1000) * PRICING["output_per_1k"]
        )
        self.total_cost += cost

        # メトリクスをバッファに追加
        self._add_metric("InputTokensPerRequest", input_tokens, "Count")
        self._add_metric("OutputTokensPerRequest", output_tokens, "Count")
        self._add_metric("ModelLatency", latency_ms, "Milliseconds")
        self._add_metric("EstimatedCost", cost, "None")  # USD
        self._add_metric("ErrorRate", 0.0, "Percent")
        self._add_metric("RequestCount", 1, "Count")

    def _add_metric(self, name, value, unit):
        """メトリクスデータポイントをバッファに追加"""
        self.metrics_buffer.append({
            'MetricName': name,
            'Value': value,
            'Unit': unit,
            'Timestamp': datetime.now(timezone.utc),
            'Dimensions': [
                {'Name': 'ModelId', 'Value': self.model_id},
                {'Name': 'Environment', 'Value': 'demo'},
            ]
        })

    def flush_to_cloudwatch(self):
        """バッファのメトリクスを CloudWatch に一括送信"""
        if not self.metrics_buffer:
            return 0

        # CloudWatch は1回の API コールで最大 1000 メトリクスデータ
        batch_size = 20  # PutMetricData は 1 回最大 1000 だが、1リクエスト20件程度に
        sent = 0

        for i in range(0, len(self.metrics_buffer), batch_size):
            batch = self.metrics_buffer[i:i + batch_size]
            try:
                cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )
                sent += len(batch)
            except Exception as e:
                print(f"  ⚠️  メトリクス送信エラー: {e}")

        self.metrics_buffer = []
        return sent

    def get_percentile(self, p):
        """レイテンシーのパーセンタイル値を計算"""
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * p / 100)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]

    def get_summary(self):
        """収集したメトリクスのサマリーを返す"""
        error_rate = (self.total_errors / self.total_requests * 100) if self.total_requests > 0 else 0
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": error_rate,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "avg_input_tokens": self.total_input_tokens / max(self.total_requests - self.total_errors, 1),
            "avg_output_tokens": self.total_output_tokens / max(self.total_requests - self.total_errors, 1),
            "latency_p50": self.get_percentile(50),
            "latency_p95": self.get_percentile(95),
            "latency_p99": self.get_percentile(99),
            "total_cost": self.total_cost,
        }


# ============================================================
# デモ 1: 基本的なメトリクス収集と発行
# ============================================================

def demo_basic_metrics():
    """基本的なトークンメトリクスの収集と CloudWatch 発行"""
    print("=" * 70)
    print("  デモ 1: トークンモニタリングとメトリクス発行")
    print("=" * 70)
    print("""
  Bedrock API を複数回呼び出し、以下のメトリクスをリアルタイムで
  CloudWatch カスタムメトリクスに発行します。

  ┌──────────────────────────┬──────────────────────────────────────┐
  │ メトリクス               │ 説明                                 │
  ├──────────────────────────┼──────────────────────────────────────┤
  │ InputTokensPerRequest    │ リクエストあたりの入力トークン数     │
  │ OutputTokensPerRequest   │ リクエストあたりの出力トークン数     │
  │ ModelLatency             │ モデル呼び出しレイテンシー（ms）     │
  │ EstimatedCost            │ 推定コスト（USD）                    │
  │ ErrorRate                │ エラー発生率（%）                    │
  │ RequestCount             │ リクエスト数                         │
  └──────────────────────────┴──────────────────────────────────────┘
""")

    collector = MetricsCollector(MODEL_ID)

    # さまざまな長さのクエリでメトリクスを収集
    queries = [
        "AWSのS3とは何ですか？一文で説明してください。",
        "Lambda関数のコールドスタートを軽減するベストプラクティスを3つ挙げ、それぞれの効果を説明してください。",
        "DynamoDBのパーティションキーとソートキーの設計原則を、実際のユースケース（ECサイトの注文管理）を例に詳しく解説してください。テーブル設計のアンチパターンも含めてください。",
        "CloudFrontのキャッシュ戦略について教えてください。",
        "マイクロサービスアーキテクチャにおけるサービス間通信パターン（同期/非同期）のトレードオフを分析し、AWS上での推奨実装パターンを示してください。API Gateway、SQS、EventBridge、Step Functionsの使い分けを含めてください。",
    ]

    print(f"  {len(queries)} 件のクエリを実行中...\n")

    for i, query in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] クエリ: 「{query[:40]}{'...' if len(query) > 40 else ''}」")

        start = time.time()
        try:
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [{"text": query}]
                }],
                inferenceConfig={"temperature": 0.3, "maxTokens": 400}
            )
            latency_ms = (time.time() - start) * 1000

            usage = response['usage']
            collector.record_invocation(usage, latency_ms, success=True)

            input_tokens = usage.get('inputTokens', 0)
            output_tokens = usage.get('outputTokens', 0)
            cost = (input_tokens / 1000) * PRICING["input_per_1k"] + (output_tokens / 1000) * PRICING["output_per_1k"]

            print(f"         入力: {input_tokens:>5} tokens | "
                  f"出力: {output_tokens:>5} tokens | "
                  f"レイテンシー: {latency_ms:>7.0f}ms | "
                  f"コスト: ${cost:.6f}")

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            collector.record_invocation({}, latency_ms, success=False)
            print(f"         ❌ エラー: {e}")

        time.sleep(1)

    # CloudWatch にメトリクスを送信
    print(f"\n{'─' * 70}")
    print(f"  CloudWatch にメトリクスを送信中...")
    sent = collector.flush_to_cloudwatch()
    print(f"  ✅ {sent} 件のメトリクスデータポイントを送信完了")

    # サマリー表示
    summary = collector.get_summary()
    print(f"\n{'─' * 70}")
    print(f"  📊 メトリクスサマリー:")
    print(f"  {'─' * 50}")
    print(f"  総リクエスト数:        {summary['total_requests']}")
    print(f"  エラー数:              {summary['total_errors']}")
    print(f"  エラー率:              {summary['error_rate']:.1f}%")
    print(f"  平均入力トークン:      {summary['avg_input_tokens']:.0f}")
    print(f"  平均出力トークン:      {summary['avg_output_tokens']:.0f}")
    print(f"  レイテンシー P50:      {summary['latency_p50']:.0f}ms")
    print(f"  レイテンシー P95:      {summary['latency_p95']:.0f}ms")
    print(f"  レイテンシー P99:      {summary['latency_p99']:.0f}ms")
    print(f"  推定総コスト:          ${summary['total_cost']:.6f}")

    return collector


# ============================================================
# デモ 2: 負荷パターンシミュレーションと異常検知
# ============================================================

def demo_load_pattern():
    """さまざまな負荷パターンをシミュレーションし異常検知の効果を確認"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: 負荷パターンシミュレーションと動的ベースライン")
    print("=" * 70)
    print("""
  通常パターンと異常パターンのメトリクスを発行し、
  CloudWatch 異常検知がどのように反応するかを示します。

  シミュレーションパターン:
  ┌──────────┬───────────────────────────────────────────────────┐
  │ フェーズ │ パターン                                          │
  ├──────────┼───────────────────────────────────────────────────┤
  │ 正常     │ 入力100-300 tokens / 出力50-200 tokens           │
  │ 異常 1   │ 入力トークン急増（プロンプトインジェクション想定）│
  │ 異常 2   │ レイテンシー劣化（モデル過負荷想定）             │
  │ 正常復帰 │ 通常パターンに戻る                               │
  └──────────┴───────────────────────────────────────────────────┘
""")

    collector = MetricsCollector(MODEL_ID)

    # フェーズ 1: 正常パターン
    print(f"  フェーズ 1: 正常パターン（3リクエスト）")
    print(f"{'─' * 70}")

    normal_queries = [
        "S3のバージョニングを有効にする方法は？",
        "IAMロールとIAMユーザーの違いは？",
        "CloudWatchのログ保持期間のデフォルト値は？",
    ]

    for query in normal_queries:
        start = time.time()
        try:
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": query}]}],
                inferenceConfig={"temperature": 0.3, "maxTokens": 200}
            )
            latency_ms = (time.time() - start) * 1000
            usage = response['usage']
            collector.record_invocation(usage, latency_ms)
            print(f"  ✅ 正常: 入力={usage['inputTokens']:>4} / "
                  f"出力={usage['outputTokens']:>4} / "
                  f"レイテンシー={latency_ms:.0f}ms")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
        time.sleep(1)

    # フェーズ 2: 異常パターン - トークン急増
    print(f"\n  フェーズ 2: 異常パターン（入力トークン急増）")
    print(f"{'─' * 70}")
    print(f"  ⚠️  意図的に長文プロンプトを送信してトークン急増をシミュレーション")

    long_context = "以下のログを分析してください。\n" + "\n".join(
        [f"[{datetime.now().isoformat()}] ERROR: Connection timeout to service-{i} "
         f"after 30000ms. Retry attempt {random.randint(1,5)}/5. "
         f"Stack trace: java.net.SocketTimeoutException at com.example.service.Client.connect(Client.java:{random.randint(100,500)})"
         for i in range(30)]
    )

    start = time.time()
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": long_context}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 500}
        )
        latency_ms = (time.time() - start) * 1000
        usage = response['usage']
        collector.record_invocation(usage, latency_ms)
        print(f"  🔴 異常: 入力={usage['inputTokens']:>4} / "
              f"出力={usage['outputTokens']:>4} / "
              f"レイテンシー={latency_ms:.0f}ms")
        print(f"     → 入力トークンが通常の {usage['inputTokens'] / 30:.1f}倍!")
    except Exception as e:
        print(f"  ❌ エラー: {e}")

    time.sleep(1)

    # フェーズ 3: 正常復帰
    print(f"\n  フェーズ 3: 正常復帰")
    print(f"{'─' * 70}")

    start = time.time()
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": "VPCとは何ですか？"}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 150}
        )
        latency_ms = (time.time() - start) * 1000
        usage = response['usage']
        collector.record_invocation(usage, latency_ms)
        print(f"  ✅ 正常: 入力={usage['inputTokens']:>4} / "
              f"出力={usage['outputTokens']:>4} / "
              f"レイテンシー={latency_ms:.0f}ms")
    except Exception as e:
        print(f"  ❌ エラー: {e}")

    # メトリクス送信
    print(f"\n{'─' * 70}")
    sent = collector.flush_to_cloudwatch()
    print(f"  ✅ {sent} 件のメトリクスデータポイントを CloudWatch に送信")

    # 異常検知の仕組み説明
    print(f"""
  📊 CloudWatch 異常検知の動作:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 機械学習ベースの動的ベースライン                                    │
  │                                                                     │
  │ 1. 学習期間（2週間）で正常パターンを学習                           │
  │    - 時間帯別のトラフィックパターン                                 │
  │    - 曜日ごとの傾向                                                 │
  │    - 季節性の自動検出                                               │
  │                                                                     │
  │ 2. 異常スコアの計算                                                 │
  │    - 予測バンド（上限/下限）を動的に計算                           │
  │    - バンド外のデータポイント = 異常                                │
  │                                                                     │
  │ 3. アラーム発火条件                                                 │
  │    ANOMALY_DETECTION_BAND(m1, 2)                                    │
  │    → 2標準偏差を超えた場合にアラーム                                │
  └─────────────────────────────────────────────────────────────────────┘
""")

    return collector


# ============================================================
# デモ 3: コスト追跡とアラート
# ============================================================

def demo_cost_tracking():
    """コストの追跡と予算管理メトリクスの発行"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: コスト追跡と予算アラート")
    print("=" * 70)
    print("""
  リアルタイムのコスト追跡メトリクスを発行し、
  予算超過時のアラート設計パターンを示します。
""")

    # シミュレーション: 1時間分のコストを集約して発行
    hourly_cost_simulation = [
        {"hour": "09:00", "requests": 150, "input_tokens": 45000, "output_tokens": 30000},
        {"hour": "10:00", "requests": 280, "input_tokens": 84000, "output_tokens": 56000},
        {"hour": "11:00", "requests": 350, "input_tokens": 105000, "output_tokens": 70000},
        {"hour": "12:00", "requests": 120, "input_tokens": 36000, "output_tokens": 24000},
        {"hour": "13:00", "requests": 200, "input_tokens": 60000, "output_tokens": 40000},
        {"hour": "14:00", "requests": 420, "input_tokens": 126000, "output_tokens": 84000},  # ピーク
        {"hour": "15:00", "requests": 300, "input_tokens": 90000, "output_tokens": 60000},
        {"hour": "16:00", "requests": 180, "input_tokens": 54000, "output_tokens": 36000},
    ]

    print(f"  時間帯別コストシミュレーション:")
    print(f"  {'─' * 60}")
    print(f"  {'時間':<8} {'リクエスト数':>10} {'入力トークン':>12} {'出力トークン':>12} {'コスト':>10}")
    print(f"  {'─' * 60}")

    total_daily_cost = 0
    metrics_data = []

    for slot in hourly_cost_simulation:
        cost = (
            (slot["input_tokens"] / 1000) * PRICING["input_per_1k"]
            + (slot["output_tokens"] / 1000) * PRICING["output_per_1k"]
        )
        total_daily_cost += cost

        # コストバー表示
        bar_length = int(cost / 0.005)  # スケール調整
        bar = "█" * min(bar_length, 30)

        print(f"  {slot['hour']:<8} {slot['requests']:>10,} {slot['input_tokens']:>12,} "
              f"{slot['output_tokens']:>12,} ${cost:>8.4f} {bar}")

        # CloudWatch メトリクスとして発行
        metrics_data.append({
            'MetricName': 'HourlyCost',
            'Value': cost,
            'Unit': 'None',
            'Timestamp': datetime.now(timezone.utc),
            'Dimensions': [
                {'Name': 'ModelId', 'Value': MODEL_ID},
                {'Name': 'Environment', 'Value': 'demo'},
            ]
        })
        metrics_data.append({
            'MetricName': 'HourlyRequests',
            'Value': slot["requests"],
            'Unit': 'Count',
            'Timestamp': datetime.now(timezone.utc),
            'Dimensions': [
                {'Name': 'ModelId', 'Value': MODEL_ID},
                {'Name': 'Environment', 'Value': 'demo'},
            ]
        })

    print(f"  {'─' * 60}")
    print(f"  {'合計':<8} {'':>10} {'':>12} {'':>12} ${total_daily_cost:>8.4f}")

    # メトリクス発行
    try:
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=metrics_data
        )
        print(f"\n  ✅ コストメトリクスを CloudWatch に送信完了")
    except Exception as e:
        print(f"\n  ⚠️  メトリクス送信エラー: {e}")

    # 月間コスト予測
    monthly_estimate = total_daily_cost * 30
    budget = 50.0  # USD
    usage_pct = (monthly_estimate / budget) * 100

    print(f"\n  💰 月間コスト予測:")
    print(f"     日次コスト:     ${total_daily_cost:.4f}")
    print(f"     月間予測:       ${monthly_estimate:.2f}")
    print(f"     月間予算:       ${budget:.2f}")
    print(f"     予算使用率:     {usage_pct:.1f}%")

    bar_length = 40
    filled = int(bar_length * min(usage_pct, 100) / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    color_indicator = "✅" if usage_pct < 80 else ("⚠️" if usage_pct < 95 else "🛑")
    print(f"     [{bar}] {color_indicator}")

    # アラート設計
    print(f"""
  📋 コストアラート設計:
  ┌──────────────┬──────────────────────────────────────────────────┐
  │ しきい値     │ アクション                                       │
  ├──────────────┼──────────────────────────────────────────────────┤
  │ 日次 > $2    │ 管理者にメール通知                               │
  │ 週次 > $10   │ レートリミット強化検討                           │
  │ 月次 > 80%   │ コスト最適化レビュー開始                         │
  │ 月次 > 95%   │ 低コストモデルへの自動切り替え                   │
  │ 急増 > 3x    │ 即座にアラート + 原因調査                        │
  └──────────────┴──────────────────────────────────────────────────┘
""")


# ============================================================
# ベストプラクティスまとめ
# ============================================================

def print_best_practices():
    """モニタリングのベストプラクティスを表示"""
    print("\n" + "=" * 70)
    print("  トークンモニタリング ベストプラクティス")
    print("=" * 70)
    print("""
  1. メトリクスのディメンション設計:
     ┌──────────────────────────────────────────────────────────────┐
     │ 必須ディメンション:                                         │
     │   • ModelId: 使用モデルの識別                                │
     │   • Environment: dev / staging / production                  │
     │   • UseCase: チャット / RAG / コード生成 等                  │
     │                                                              │
     │ オプション:                                                  │
     │   • CustomerId: テナント別コスト配分                         │
     │   • RequestType: streaming / batch / sync                    │
     └──────────────────────────────────────────────────────────────┘

  2. アラーム設計の原則:
     • 静的しきい値: 絶対値での上限設定（SLA 準拠）
     • 異常検知: パターン変化の自動検出（ベースラインからの逸脱）
     • 複合アラーム: 複数メトリクスの組み合わせ判定
       例: エラー率 > 5% AND レイテンシー P95 > 10秒 → 緊急

  3. ダッシュボードの階層:
     Level 1（概要）: ビジネスKPI、全体ヘルス
     Level 2（技術）: トークン、レイテンシー、エラー率
     Level 3（詳細）: モデル別、テナント別、リクエストタイプ別

  4. コスト最適化の指標:
     • Cost per Successful Request: 成功リクエストあたりコスト
     • Token Efficiency: 有効トークン率（無駄なトークンの割合）
     • Cache Hit Rate: キャッシュ利用率（プロンプトキャッシング）
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 8: カスタムメトリクス発行とトークンモニタリング")
    print("🔷" * 35)
    print("\n  Bedrock モデル呼び出しのメトリクスをリアルタイムで")
    print("  CloudWatch に発行し、モニタリングダッシュボードを活用します。")
    print()

    # デモ 1: 基本メトリクス収集
    demo_basic_metrics()
    time.sleep(2)

    # デモ 2: 負荷パターンと異常検知
    demo_load_pattern()
    time.sleep(1)

    # デモ 3: コスト追跡
    demo_cost_tracking()

    # ベストプラクティス
    print_best_practices()
