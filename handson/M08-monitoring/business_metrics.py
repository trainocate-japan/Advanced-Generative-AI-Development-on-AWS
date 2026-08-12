"""
モジュール 8: ビジネス影響の測定
- ユーザーエンゲージメント: セッション数、対話ターン数、完了率
- タスク完了: 問題解決率、エスカレーション率、平均解決時間
- ROI 計算: コスト削減、効率改善、顧客満足度
- CloudWatch ダッシュボードへのビジネスメトリクス発行
"""

import boto3
import json
import time
import random
from datetime import datetime, timezone, timedelta
from collections import defaultdict

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

MODEL_ID = "amazon.nova-lite-v1:0"
NAMESPACE = "GenAI/Bedrock"


# ============================================================
# ビジネスメトリクス収集エンジン
# ============================================================

class BusinessMetricsEngine:
    """
    AI カスタマーサービスのビジネス影響を測定するエンジン

    3つの柱:
    1. ユーザーエンゲージメント
    2. タスク完了
    3. ROI（投資対効果）
    """

    def __init__(self):
        self.sessions = []
        self.metrics = defaultdict(list)

    def simulate_session(self, scenario):
        """カスタマーサービスセッションをシミュレーション"""
        session = {
            "session_id": f"sess_{random.randint(10000, 99999)}",
            "start_time": datetime.now(timezone.utc),
            "scenario": scenario["type"],
            "turns": [],
            "resolved": False,
            "escalated": False,
            "satisfaction_score": 0,
        }

        # 対話のシミュレーション
        messages = []
        for i, user_msg in enumerate(scenario["messages"]):
            messages.append({"role": "user", "content": [{"text": user_msg}]})

            start = time.time()
            try:
                response = bedrock.converse(
                    modelId=MODEL_ID,
                    messages=messages,
                    inferenceConfig={"temperature": 0.3, "maxTokens": 300}
                )
                latency = time.time() - start
                assistant_msg = response['output']['message']['content'][0]['text']
                usage = response['usage']

                messages.append({"role": "assistant", "content": [{"text": assistant_msg}]})

                session["turns"].append({
                    "turn": i + 1,
                    "user": user_msg[:50],
                    "assistant": assistant_msg[:80],
                    "latency": latency,
                    "tokens": usage.get('inputTokens', 0) + usage.get('outputTokens', 0),
                })

            except Exception as e:
                session["turns"].append({
                    "turn": i + 1,
                    "user": user_msg[:50],
                    "error": str(e),
                })
            time.sleep(1)

        # セッション結果の設定
        session["end_time"] = datetime.now(timezone.utc)
        session["total_turns"] = len(session["turns"])
        session["resolved"] = scenario.get("expected_resolution", True)
        session["escalated"] = scenario.get("expected_escalation", False)
        session["satisfaction_score"] = scenario.get("satisfaction", 4)
        session["duration_seconds"] = (session["end_time"] - session["start_time"]).total_seconds()

        self.sessions.append(session)
        return session

    def calculate_engagement_metrics(self):
        """ユーザーエンゲージメントメトリクスを計算"""
        if not self.sessions:
            return {}

        total_sessions = len(self.sessions)
        total_turns = sum(s["total_turns"] for s in self.sessions)
        avg_turns = total_turns / total_sessions
        completed = sum(1 for s in self.sessions if s["resolved"] and not s["escalated"])
        abandoned = sum(1 for s in self.sessions if not s["resolved"] and not s["escalated"])

        return {
            "total_sessions": total_sessions,
            "total_turns": total_turns,
            "avg_turns_per_session": avg_turns,
            "completion_rate": completed / total_sessions * 100,
            "abandonment_rate": abandoned / total_sessions * 100,
            "avg_duration_seconds": sum(s["duration_seconds"] for s in self.sessions) / total_sessions,
        }

    def calculate_task_metrics(self):
        """タスク完了メトリクスを計算"""
        if not self.sessions:
            return {}

        total = len(self.sessions)
        resolved = sum(1 for s in self.sessions if s["resolved"])
        escalated = sum(1 for s in self.sessions if s["escalated"])
        first_turn_resolved = sum(
            1 for s in self.sessions if s["resolved"] and s["total_turns"] <= 2
        )

        return {
            "resolution_rate": resolved / total * 100,
            "escalation_rate": escalated / total * 100,
            "first_contact_resolution": first_turn_resolved / total * 100,
            "avg_resolution_turns": sum(s["total_turns"] for s in self.sessions if s["resolved"]) / max(resolved, 1),
            "avg_satisfaction": sum(s["satisfaction_score"] for s in self.sessions) / total,
        }

    def calculate_roi(self, monthly_requests=10000):
        """ROI を計算"""
        if not self.sessions:
            return {}

        # コスト計算
        avg_tokens = sum(
            sum(t.get("tokens", 0) for t in s["turns"])
            for s in self.sessions
        ) / len(self.sessions)

        cost_per_session = (avg_tokens / 1000) * 0.00024  # Nova Lite 概算
        monthly_ai_cost = cost_per_session * monthly_requests

        # 人件費との比較
        human_cost_per_session = 500  # ¥500/件（人間のオペレーター）
        ai_resolution_rate = sum(1 for s in self.sessions if s["resolved"]) / len(self.sessions)
        human_handled = monthly_requests * (1 - ai_resolution_rate)
        ai_handled = monthly_requests * ai_resolution_rate

        monthly_human_cost = human_handled * human_cost_per_session
        monthly_human_only_cost = monthly_requests * human_cost_per_session

        # インフラコスト
        monthly_infra_cost = 50000  # ¥50,000/月（CloudWatch, S3, Lambda等）

        total_costs = (monthly_ai_cost * 150) + monthly_infra_cost  # USD→JPY概算
        total_benefits = monthly_human_only_cost - monthly_human_cost
        roi = ((total_benefits - total_costs) / total_costs) * 100 if total_costs > 0 else 0

        return {
            "monthly_requests": monthly_requests,
            "ai_resolution_rate": ai_resolution_rate * 100,
            "cost_per_session_usd": cost_per_session,
            "monthly_ai_cost_usd": monthly_ai_cost,
            "monthly_human_cost_jpy": monthly_human_cost,
            "monthly_human_only_cost_jpy": monthly_human_only_cost,
            "monthly_savings_jpy": total_benefits,
            "monthly_total_cost_jpy": total_costs,
            "roi_percent": roi,
        }

    def publish_metrics(self, engagement, task, roi):
        """ビジネスメトリクスを CloudWatch に発行"""
        metrics_data = []

        # エンゲージメントメトリクス
        if engagement:
            metrics_data.extend([
                self._metric("SessionCount", engagement["total_sessions"], "Count"),
                self._metric("AvgTurnsPerSession", engagement["avg_turns_per_session"], "Count"),
                self._metric("CompletionRate", engagement["completion_rate"], "Percent"),
                self._metric("AbandonmentRate", engagement["abandonment_rate"], "Percent"),
            ])

        # タスクメトリクス
        if task:
            metrics_data.extend([
                self._metric("TaskCompletionRate", task["resolution_rate"], "Percent"),
                self._metric("EscalationRate", task["escalation_rate"], "Percent"),
                self._metric("FirstContactResolution", task["first_contact_resolution"], "Percent"),
                self._metric("UserSatisfactionScore", task["avg_satisfaction"], "None"),
            ])

        # ROI メトリクス
        if roi:
            metrics_data.extend([
                self._metric("CostPerSession", roi["cost_per_session_usd"], "None"),
                self._metric("MonthlySavingsJPY", roi["monthly_savings_jpy"], "None"),
                self._metric("ROIPercent", roi["roi_percent"], "Percent"),
            ])

        if metrics_data:
            try:
                # 20件ずつバッチ送信
                for i in range(0, len(metrics_data), 20):
                    batch = metrics_data[i:i + 20]
                    cloudwatch.put_metric_data(
                        Namespace=NAMESPACE,
                        MetricData=batch
                    )
                return len(metrics_data)
            except Exception as e:
                print(f"  ⚠️  メトリクス送信エラー: {e}")
                return 0
        return 0

    def _metric(self, name, value, unit):
        """メトリクスデータポイントを生成"""
        return {
            'MetricName': name,
            'Value': float(value),
            'Unit': unit,
            'Timestamp': datetime.now(timezone.utc),
            'Dimensions': [
                {'Name': 'Service', 'Value': 'CustomerAssistant'},
                {'Name': 'Environment', 'Value': 'demo'},
            ]
        }


# ============================================================
# デモ 1: ユーザーエンゲージメント測定
# ============================================================

def demo_engagement():
    """カスタマーサービスのエンゲージメントメトリクスを計測"""
    print("=" * 70)
    print("  デモ 1: ユーザーエンゲージメント測定")
    print("=" * 70)
    print("""
  AI カスタマーサービスアシスタントへの対話をシミュレーションし、
  エンゲージメントメトリクスをリアルタイムで計測します。

  測定指標:
  ┌────────────────────────┬────────────────────────────────────────┐
  │ セッション数           │ AI と対話を開始したユーザー数          │
  │ 対話ターン数           │ ユーザーとAIのやり取りの回数           │
  │ 会話完了率             │ 目的を達成して終了したセッションの割合 │
  │ 離脱率                 │ 途中で離脱したセッションの割合         │
  │ 平均セッション時間     │ 1セッションの平均所要時間             │
  └────────────────────────┴────────────────────────────────────────┘
""")

    engine = BusinessMetricsEngine()

    # シナリオ定義
    scenarios = [
        {
            "type": "FAQ",
            "messages": [
                "注文のキャンセル方法を教えてください。",
            ],
            "expected_resolution": True,
            "expected_escalation": False,
            "satisfaction": 5,
        },
        {
            "type": "問題解決",
            "messages": [
                "昨日注文した商品がまだ発送されていません。注文番号は ORD-12345 です。",
                "いつ届きますか？急いでいます。",
            ],
            "expected_resolution": True,
            "expected_escalation": False,
            "satisfaction": 4,
        },
        {
            "type": "複雑な問い合わせ",
            "messages": [
                "先月購入した商品が故障しました。保証期間内だと思いますが、修理と交換どちらが可能ですか？",
                "交換を希望します。在庫がない場合は返金でもいいです。",
                "返金の場合、いつ頃入金されますか？",
            ],
            "expected_resolution": True,
            "expected_escalation": False,
            "satisfaction": 3,
        },
        {
            "type": "エスカレーション",
            "messages": [
                "請求金額が間違っています。2重請求されています。すぐに修正してください。",
                "AIでは対応できないのですか？人間のオペレーターに繋いでください。",
            ],
            "expected_resolution": False,
            "expected_escalation": True,
            "satisfaction": 2,
        },
    ]

    print(f"  {len(scenarios)} 件のセッションをシミュレーション中...\n")

    for i, scenario in enumerate(scenarios, 1):
        print(f"{'─' * 70}")
        print(f"  セッション {i}: {scenario['type']}")
        print(f"{'─' * 70}")

        session = engine.simulate_session(scenario)

        # セッション結果表示
        status = "✅ 解決" if session["resolved"] else ("🔄 エスカレーション" if session["escalated"] else "❌ 未解決")
        print(f"    ターン数: {session['total_turns']}")
        print(f"    結果: {status}")
        print(f"    所要時間: {session['duration_seconds']:.1f}秒")
        print(f"    満足度: {'⭐' * session['satisfaction_score']}")

        if session["turns"]:
            last_turn = session["turns"][-1]
            if "assistant" in last_turn:
                print(f"    最終応答: {last_turn['assistant'][:60]}...")

        time.sleep(1)

    # エンゲージメントメトリクス集計
    engagement = engine.calculate_engagement_metrics()

    print(f"\n{'─' * 70}")
    print(f"  📊 エンゲージメントメトリクス:")
    print(f"  {'─' * 50}")
    print(f"  総セッション数:        {engagement['total_sessions']}")
    print(f"  総対話ターン数:        {engagement['total_turns']}")
    print(f"  平均ターン/セッション: {engagement['avg_turns_per_session']:.1f}")
    print(f"  会話完了率:            {engagement['completion_rate']:.1f}%")
    print(f"  離脱率:                {engagement['abandonment_rate']:.1f}%")
    print(f"  平均セッション時間:    {engagement['avg_duration_seconds']:.1f}秒")

    return engine


# ============================================================
# デモ 2: タスク完了率とエスカレーション分析
# ============================================================

def demo_task_completion(engine):
    """タスク完了に関するメトリクスの分析"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: タスク完了率とエスカレーション分析")
    print("=" * 70)
    print("""
  AI アシスタントの問題解決能力を定量的に評価します。

  KPI:
  ┌──────────────────────────┬──────────────────────────────────────┐
  │ 問題解決率（FCR）        │ 最初のコンタクトで解決した割合       │
  │ エスカレーション率       │ 人間オペレーターに転送された割合     │
  │ 平均解決ターン数         │ 解決に要した平均対話ターン数         │
  │ 顧客満足度（CSAT）       │ 5段階評価の平均                      │
  └──────────────────────────┴──────────────────────────────────────┘
""")

    task = engine.calculate_task_metrics()

    print(f"  📊 タスク完了メトリクス:")
    print(f"  {'─' * 50}")
    print(f"  問題解決率:            {task['resolution_rate']:.1f}%")
    print(f"  エスカレーション率:    {task['escalation_rate']:.1f}%")
    print(f"  初回解決率（FCR）:     {task['first_contact_resolution']:.1f}%")
    print(f"  平均解決ターン数:      {task['avg_resolution_turns']:.1f}")
    print(f"  平均顧客満足度:        {task['avg_satisfaction']:.1f}/5.0")

    # 可視化
    resolution = task['resolution_rate']
    bar_len = 40
    filled = int(bar_len * resolution / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\n  問題解決率: [{bar}] {resolution:.1f}%")

    escalation = task['escalation_rate']
    filled_e = int(bar_len * escalation / 100)
    bar_e = "█" * filled_e + "░" * (bar_len - filled_e)
    print(f"  ｴｽｶﾚｰｼｮﾝ: [{bar_e}] {escalation:.1f}%")

    # シナリオ別分析
    print(f"\n  📋 シナリオ別パフォーマンス:")
    print(f"  ┌──────────────────┬──────┬────────┬──────────┐")
    print(f"  │ シナリオ         │ 結果 │ ターン │ 満足度   │")
    print(f"  ├──────────────────┼──────┼────────┼──────────┤")
    for s in engine.sessions:
        status = "解決" if s["resolved"] else ("転送" if s["escalated"] else "未解決")
        stars = "⭐" * s["satisfaction_score"]
        print(f"  │ {s['scenario']:<14} │ {status:<4} │ {s['total_turns']:<6} │ {stars:<8} │")
    print(f"  └──────────────────┴──────┴────────┴──────────┘")

    # 改善ポイント
    print(f"""
  💡 改善ポイント:
     • エスカレーション率 > 20% の場合:
       → エスカレーション理由を分析し、対応可能範囲を拡大
     • FCR < 50% の場合:
       → プロンプト改善、ナレッジベース拡充を検討
     • CSAT < 3.5 の場合:
       → ユーザーフィードバックを分析し、応答品質を改善
""")

    return task


# ============================================================
# デモ 3: ROI 計算フレームワーク
# ============================================================

def demo_roi_calculation(engine):
    """AI カスタマーサービスの ROI を計算"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: ROI 計算フレームワーク")
    print("=" * 70)
    print("""
  AI カスタマーサービス導入の投資対効果（ROI）を計算します。

  ROI = (Total Benefits - Total Costs) / Total Costs × 100%

  ┌─────────────────────────────────────────────────────────────────┐
  │ Benefits（効果）                                                │
  │   • 自動解決による人件費削減                                    │
  │   • 処理速度向上（24/7対応、即時応答）                         │
  │   • 処理件数のスケーラビリティ                                  │
  ├─────────────────────────────────────────────────────────────────┤
  │ Costs（コスト）                                                 │
  │   • Bedrock API コスト                                          │
  │   • インフラ運用コスト（CloudWatch, S3, Lambda等）              │
  │   • 開発・保守コスト                                            │
  └─────────────────────────────────────────────────────────────────┘
""")

    # 異なる規模での ROI 計算
    scales = [1000, 10000, 50000, 100000]

    print(f"  月間リクエスト数別 ROI 試算:")
    print(f"  {'─' * 65}")
    print(f"  {'月間件数':>10} {'AI解決率':>8} {'AI費用(USD)':>12} {'人件費削減(¥)':>14} {'ROI':>8}")
    print(f"  {'─' * 65}")

    for monthly in scales:
        roi = engine.calculate_roi(monthly_requests=monthly)
        print(f"  {monthly:>10,} {roi['ai_resolution_rate']:>7.1f}% "
              f"${roi['monthly_ai_cost_usd']:>10.2f} "
              f"¥{roi['monthly_savings_jpy']:>12,.0f} "
              f"{roi['roi_percent']:>7.1f}%")

    print(f"  {'─' * 65}")

    # 詳細な ROI レポート（10,000件/月のケース）
    roi_detail = engine.calculate_roi(monthly_requests=10000)

    print(f"""
  📊 詳細 ROI レポート（月間 10,000 件）:
  ┌─────────────────────────────────────────────────────────────────┐
  │ コスト                                                          │
  ├─────────────────────────────────────────────────────────────────┤
  │  Bedrock API:        ${roi_detail['monthly_ai_cost_usd']:>10.2f}/月                       │
  │  インフラ運用:       ¥50,000/月                                 │
  │  開発・保守（按分）: ¥100,000/月                                │
  ├─────────────────────────────────────────────────────────────────┤
  │ 効果                                                            │
  ├─────────────────────────────────────────────────────────────────┤
  │  AI自動解決率:       {roi_detail['ai_resolution_rate']:>5.1f}%                                │
  │  AI解決件数:         {int(10000 * roi_detail['ai_resolution_rate'] / 100):>5,} 件/月                              │
  │  人件費削減:         ¥{roi_detail['monthly_savings_jpy']:>10,.0f}/月                        │
  ├─────────────────────────────────────────────────────────────────┤
  │ ROI                                                             │
  ├─────────────────────────────────────────────────────────────────┤
  │  投資対効果:         {roi_detail['roi_percent']:>7.1f}%                                  │
  └─────────────────────────────────────────────────────────────────┘
""")

    # 損益分岐点分析
    print(f"  📈 損益分岐点分析:")
    breakeven_requests = 0
    for test_volume in range(100, 100000, 100):
        test_roi = engine.calculate_roi(monthly_requests=test_volume)
        if test_roi["roi_percent"] > 0:
            breakeven_requests = test_volume
            break

    if breakeven_requests > 0:
        print(f"     損益分岐点: 月間 {breakeven_requests:,} リクエスト以上で黒字化")
    else:
        print(f"     ※ 現在の解決率では損益分岐に達しない可能性があります")

    # 月次トレンドシミュレーション
    print(f"\n  📋 月次トレンド予測（改善シナリオ）:")
    print(f"  {'─' * 55}")
    print(f"  {'月':>4} {'解決率':>6} {'月間件数':>8} {'コスト(¥)':>10} {'削減額(¥)':>10}")
    print(f"  {'─' * 55}")

    base_resolution = roi_detail['ai_resolution_rate'] / 100
    for month in range(1, 7):
        # 月ごとに解決率が改善（学習効果）
        improved_rate = min(base_resolution + month * 0.03, 0.95)
        volume = 10000 + month * 2000  # 利用増加
        ai_cost_jpy = (volume * improved_rate * roi_detail['cost_per_session_usd'] * 150)
        savings = volume * improved_rate * 500  # 人件費削減
        print(f"  {month:>4} {improved_rate*100:>5.1f}% {volume:>8,} ¥{ai_cost_jpy:>9,.0f} ¥{savings:>9,.0f}")

    print(f"  {'─' * 55}")

    return roi_detail


# ============================================================
# メトリクス発行とダッシュボード連携
# ============================================================

def publish_all_metrics(engine, engagement, task, roi):
    """全メトリクスを CloudWatch に発行"""
    print("\n\n" + "=" * 70)
    print("  CloudWatch メトリクス発行")
    print("=" * 70)

    sent = engine.publish_metrics(engagement, task, roi)
    print(f"\n  ✅ {sent} 件のビジネスメトリクスを CloudWatch に送信完了")
    print(f"     名前空間: {NAMESPACE}")
    print(f"     ディメンション: Service=CustomerAssistant, Environment=demo")

    print(f"""
  📊 ダッシュボードで確認できるメトリクス:

  エンゲージメント:
    • SessionCount:          セッション数
    • AvgTurnsPerSession:    平均対話ターン数
    • CompletionRate:        会話完了率
    • AbandonmentRate:       離脱率

  タスク完了:
    • TaskCompletionRate:    タスク完了率
    • EscalationRate:        エスカレーション率
    • FirstContactResolution: 初回解決率
    • UserSatisfactionScore: ユーザー満足度

  コスト・ROI:
    • CostPerSession:        セッションあたりコスト
    • MonthlySavingsJPY:     月間コスト削減額
    • ROIPercent:            投資対効果

  確認方法:
    CloudWatch コンソール → ダッシュボード → Bedrock-GenAI-Monitoring
    URL: https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=Bedrock-GenAI-Monitoring
""")


# ============================================================
# ビジネスメトリクス ベストプラクティス
# ============================================================

def print_best_practices():
    """ビジネスメトリクス設計のベストプラクティス"""
    print("\n" + "=" * 70)
    print("  ビジネスメトリクス設計のベストプラクティス")
    print("=" * 70)
    print("""
  1. 測定フレームワーク（HEART Framework 応用）:
     ┌─────────────┬───────────────────────────────────────────────┐
     │ Happiness   │ CSAT, NPS, フィードバックスコア              │
     │ Engagement  │ セッション数, ターン数, 利用頻度             │
     │ Adoption    │ 新規ユーザー率, 機能利用率                   │
     │ Retention   │ リピート率, 継続利用率                       │
     │ Task        │ 完了率, エスカレーション率, 解決時間         │
     └─────────────┴───────────────────────────────────────────────┘

  2. メトリクスの階層設計:
     ┌─────────────────────────────────────────────────────────────┐
     │ Level 1: ビジネスKPI（経営層向け）                          │
     │   ROI, コスト削減額, 顧客満足度                            │
     ├─────────────────────────────────────────────────────────────┤
     │ Level 2: サービスKPI（マネージャー向け）                    │
     │   解決率, エスカレーション率, 応答品質                      │
     ├─────────────────────────────────────────────────────────────┤
     │ Level 3: オペレーション（開発者向け）                       │
     │   トークン数, レイテンシー, エラー率, ハルシネーション率    │
     └─────────────────────────────────────────────────────────────┘

  3. 定期レビューサイクル:
     • 日次: オペレーションメトリクス確認（異常検知対応）
     • 週次: サービスKPIレビュー（品質改善アクション）
     • 月次: ビジネスKPIレビュー（ROI報告、予算管理）
     • 四半期: 戦略レビュー（モデル選定、機能拡張判断）

  4. 自動レポート生成:
     • CloudWatch → Lambda → S3 → QuickSight（BI ダッシュボード）
     • 週次サマリーを SNS + SES でステークホルダーにメール配信
     • 異常検知時のインシデントレポート自動生成
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 8: ビジネス影響の測定")
    print("🔷" * 35)
    print("\n  AI カスタマーサービスのビジネス影響を3つの柱で測定し、")
    print("  ROI を定量的に示します。")
    print()

    # デモ 1: エンゲージメント測定
    engine = demo_engagement()
    time.sleep(2)

    # デモ 2: タスク完了分析
    engagement = engine.calculate_engagement_metrics()
    task = demo_task_completion(engine)
    time.sleep(1)

    # デモ 3: ROI 計算
    roi = demo_roi_calculation(engine)

    # メトリクス発行
    publish_all_metrics(engine, engagement, task, roi)

    # ベストプラクティス
    print_best_practices()
