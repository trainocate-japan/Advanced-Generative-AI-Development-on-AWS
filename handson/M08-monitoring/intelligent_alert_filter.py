"""
モジュール 8: インテリジェントアラートシステム - 知性フィルター
- コンテキストを読み取る知性フィルターの実装
- 営業時間・使用パターン・計画イベントに基づくアラート判定
- 3層エスカレーション（即時 / まとめ / 戦略的）
- 無駄なアラートの抑制とノイズ低減
"""

import boto3
import json
import time
from datetime import datetime, timezone, timedelta
from enum import Enum

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sns = boto3.client('sns', region_name='us-east-1')

NAMESPACE = "GenAI/Bedrock"
MODEL_ID = "amazon.nova-lite-v1:0"


# ============================================================
# アラート重要度の定義
# ============================================================

class Severity(Enum):
    """アラートの重要度レベル"""
    CRITICAL = "critical"      # 即時対応が必要
    WARNING = "warning"        # 注意が必要
    INFO = "info"              # 傾向レポートに含める
    SUPPRESSED = "suppressed"  # 抑制（無駄なアラート防止）


class EscalationTier(Enum):
    """エスカレーションピラミッドの3層"""
    IMMEDIATE = "immediate"    # 即時: 重大な問題 → PagerDuty/オンコール
    SUMMARY = "summary"        # まとめ: 傾向レポート → Slack/メール
    STRATEGIC = "strategic"    # 戦略的: 詳細な分析 → 経営レポート


# ============================================================
# コンテキスト認識エンジン
# ============================================================

class ContextEngine:
    """
    アラート判定に必要なコンテキスト情報を収集・管理する。
    
    コンテキストの種類:
    - 時間コンテキスト: 営業時間、曜日、祝日
    - パターンコンテキスト: 過去の使用パターン（ベースライン）
    - イベントコンテキスト: 計画済みイベント（リリース、キャンペーン等）
    - 運用コンテキスト: メンテナンスウィンドウ、既知の障害
    """

    # 営業時間の定義（JST）
    BUSINESS_HOURS_START = 9
    BUSINESS_HOURS_END = 18
    JST = timezone(timedelta(hours=9))

    # 計画イベントのサンプル（実運用では DynamoDB から取得）
    PLANNED_EVENTS = [
        {
            "name": "新機能リリース",
            "start": "2026-08-12T09:00:00+09:00",
            "end": "2026-08-12T18:00:00+09:00",
            "expected_spike_factor": 3.0,
            "description": "新しいAIチャット機能のリリースによりトークン増加が見込まれる"
        },
        {
            "name": "マーケティングキャンペーン",
            "start": "2026-08-15T00:00:00+09:00",
            "end": "2026-08-17T23:59:59+09:00",
            "expected_spike_factor": 2.5,
            "description": "週末キャンペーンによるアクセス増加"
        },
    ]

    # 曜日別の正常倍率（月〜日、1.0 が平均）
    DAY_OF_WEEK_FACTORS = {
        0: 1.0,   # 月曜
        1: 1.1,   # 火曜
        2: 1.2,   # 水曜（ピーク）
        3: 1.1,   # 木曜
        4: 0.9,   # 金曜
        5: 0.4,   # 土曜
        6: 0.3,   # 日曜
    }

    def get_time_context(self, timestamp=None):
        """時間に関するコンテキストを取得"""
        if timestamp is None:
            timestamp = datetime.now(self.JST)
        elif timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc).astimezone(self.JST)
        else:
            timestamp = timestamp.astimezone(self.JST)

        hour = timestamp.hour
        weekday = timestamp.weekday()

        return {
            "timestamp": timestamp.isoformat(),
            "hour": hour,
            "weekday": weekday,
            "is_business_hours": self.BUSINESS_HOURS_START <= hour < self.BUSINESS_HOURS_END,
            "is_weekend": weekday >= 5,
            "day_factor": self.DAY_OF_WEEK_FACTORS.get(weekday, 1.0),
            "is_late_night": 0 <= hour < 6,
        }

    def get_planned_events(self, timestamp=None):
        """現在時刻に該当する計画イベントを取得"""
        if timestamp is None:
            timestamp = datetime.now(self.JST)
        elif timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc).astimezone(self.JST)
        else:
            timestamp = timestamp.astimezone(self.JST)

        active_events = []
        for event in self.PLANNED_EVENTS:
            start = datetime.fromisoformat(event["start"])
            end = datetime.fromisoformat(event["end"])
            if start <= timestamp <= end:
                active_events.append(event)

        return active_events

    def get_baseline(self, metric_name, time_context):
        """
        動的ベースラインを計算する。
        
        実運用では CloudWatch Anomaly Detection の予測バンドを使用。
        ここではシンプルな統計ベースのベースラインをデモ。
        """
        # 基本ベースライン（過去2週間の平均を想定）
        baselines = {
            "InputTokensPerRequest": 150,
            "OutputTokensPerRequest": 100,
            "ModelLatency": 1500,         # ms
            "ErrorRate": 2.0,             # %
            "HourlyRequests": 200,
            "HourlyCost": 0.05,           # USD
            "TokensPerMinute": 5000,
        }

        base_value = baselines.get(metric_name, 100)

        # 時間帯による調整
        if time_context["is_business_hours"]:
            base_value *= 1.5  # 営業時間は50%増が正常
        elif time_context["is_late_night"]:
            base_value *= 0.1  # 深夜はほぼゼロが正常

        # 曜日による調整
        base_value *= time_context["day_factor"]

        return base_value


# ============================================================
# 知性フィルター（メインロジック）
# ============================================================

class IntelligentAlertFilter:
    """
    コンテキストを読み取る知性フィルター。
    
    目的: 
    - 対応すべき問題と通常の運用上のばらつきを区別する
    - 無駄なアラートを抑制し、オペレーターの疲弊を防ぐ
    - 本当に重要なアラートを確実にエスカレーションする
    
    判定フロー:
    1. メトリクスイベントを受信
    2. コンテキスト情報を収集（時間帯、計画イベント、ベースライン）
    3. 偏差度を計算（実測値 / ベースライン）
    4. コンテキストに基づいて重要度を判定
    5. エスカレーション先を決定
    """

    # 偏差度のしきい値
    THRESHOLDS = {
        "critical": 5.0,    # ベースラインの5倍以上 → 即時
        "warning": 3.0,     # ベースラインの3倍以上 → 警告
        "info": 2.0,        # ベースラインの2倍以上 → 情報
    }

    # 連続異常回数のしきい値（単発の外れ値を無視）
    CONSECUTIVE_THRESHOLD = 3

    def __init__(self):
        self.context_engine = ContextEngine()
        self.alert_history = []       # 過去のアラート履歴
        self.consecutive_count = {}   # メトリクス別の連続異常カウント

    def evaluate(self, event):
        """
        メトリクスイベントを評価し、アラート判定を行う。
        
        Parameters:
            event (dict): メトリクスイベント
                - metric_name: メトリクス名
                - value: 実測値
                - timestamp: タイムスタンプ（ISO形式）
                - dimensions: ディメンション（ModelId等）
                
        Returns:
            dict: 判定結果
                - alert: アラートを発するか (bool)
                - severity: 重要度
                - tier: エスカレーション層
                - reason: 判定理由
                - context: 使用したコンテキスト情報
                - recommendation: 推奨アクション
        """
        metric_name = event["metric_name"]
        value = event["value"]
        timestamp = datetime.fromisoformat(event.get("timestamp", datetime.now(timezone.utc).isoformat()))

        # Step 1: コンテキスト収集
        time_context = self.context_engine.get_time_context(timestamp)
        planned_events = self.context_engine.get_planned_events(timestamp)
        baseline = self.context_engine.get_baseline(metric_name, time_context)

        # Step 2: 偏差度の計算
        deviation = value / baseline if baseline > 0 else float('inf')

        # Step 3: 計画イベントによる調整
        adjusted_deviation = deviation
        suppression_reason = None

        if planned_events:
            max_expected_spike = max(e["expected_spike_factor"] for e in planned_events)
            if deviation <= max_expected_spike:
                adjusted_deviation = deviation / max_expected_spike
                suppression_reason = (
                    f"計画イベント「{planned_events[0]['name']}」により "
                    f"最大{max_expected_spike}倍のスパイクが想定内"
                )

        # Step 4: 連続異常カウントの更新
        if adjusted_deviation >= self.THRESHOLDS["info"]:
            self.consecutive_count[metric_name] = self.consecutive_count.get(metric_name, 0) + 1
        else:
            self.consecutive_count[metric_name] = 0

        consecutive = self.consecutive_count.get(metric_name, 0)

        # Step 5: 重要度の判定
        severity, tier, reason = self._determine_severity(
            metric_name, value, adjusted_deviation, 
            time_context, consecutive, suppression_reason
        )

        # Step 6: 判定結果の構築
        result = {
            "alert": severity != Severity.SUPPRESSED,
            "severity": severity.value,
            "tier": tier.value if tier else None,
            "metric_name": metric_name,
            "value": value,
            "baseline": round(baseline, 2),
            "deviation": round(deviation, 2),
            "adjusted_deviation": round(adjusted_deviation, 2),
            "consecutive_anomalies": consecutive,
            "reason": reason,
            "context": {
                "time": time_context,
                "planned_events": [e["name"] for e in planned_events],
            },
            "recommendation": self._get_recommendation(severity, metric_name, deviation),
        }

        # 履歴に追加
        self.alert_history.append(result)

        return result

    def _determine_severity(self, metric_name, value, deviation, 
                            time_context, consecutive, suppression_reason):
        """コンテキストに基づいて重要度を決定する"""

        # ケース 1: 計画イベントで説明できるスパイク
        if suppression_reason and deviation < self.THRESHOLDS["warning"]:
            return (
                Severity.SUPPRESSED,
                None,
                f"抑制: {suppression_reason}"
            )

        # ケース 2: 深夜の異常（少量でも重大）
        if time_context["is_late_night"] and deviation >= self.THRESHOLDS["info"]:
            return (
                Severity.CRITICAL,
                EscalationTier.IMMEDIATE,
                f"深夜帯({time_context['hour']}時)に異常な使用量を検出。"
                f"ベースライン比 {deviation:.1f}倍。不正アクセスの可能性。"
            )

        # ケース 3: クリティカル（ベースラインの5倍以上）
        if deviation >= self.THRESHOLDS["critical"]:
            return (
                Severity.CRITICAL,
                EscalationTier.IMMEDIATE,
                f"{metric_name} がベースラインの {deviation:.1f}倍に到達。即時対応が必要。"
            )

        # ケース 4: 警告（3倍以上、かつ連続3回以上）
        if deviation >= self.THRESHOLDS["warning"] and consecutive >= self.CONSECUTIVE_THRESHOLD:
            return (
                Severity.WARNING,
                EscalationTier.SUMMARY,
                f"{metric_name} が連続 {consecutive} 回ベースラインの "
                f"{deviation:.1f}倍を超過。傾向レポートに追加。"
            )

        # ケース 5: 警告だが単発（抑制）
        if deviation >= self.THRESHOLDS["warning"] and consecutive < self.CONSECUTIVE_THRESHOLD:
            return (
                Severity.SUPPRESSED,
                None,
                f"単発の外れ値（連続{consecutive}回目、閾値{self.CONSECUTIVE_THRESHOLD}回）。"
                f"一時的なスパイクの可能性が高いため抑制。"
            )

        # ケース 6: 情報レベル
        if deviation >= self.THRESHOLDS["info"]:
            return (
                Severity.INFO,
                EscalationTier.STRATEGIC,
                f"{metric_name} がベースラインの {deviation:.1f}倍。"
                f"戦略レポートに記録。"
            )

        # ケース 7: 正常範囲
        return (
            Severity.SUPPRESSED,
            None,
            f"正常範囲内（ベースライン比 {deviation:.1f}倍）"
        )

    def _get_recommendation(self, severity, metric_name, deviation):
        """重要度に応じた推奨アクションを返す"""
        if severity == Severity.CRITICAL:
            recommendations = {
                "InputTokensPerRequest": "入力制限の即時適用を検討。プロンプトインジェクションの可能性を調査。",
                "ErrorRate": "モデルの可用性確認。フォールバックモデルへの切り替えを検討。",
                "ModelLatency": "レート制限への到達を確認。リクエストキューイングを検討。",
                "HourlyCost": "コスト上限に到達。低コストモデルへの自動切り替えを発動。",
            }
            return recommendations.get(metric_name, "即時調査を開始してください。")

        elif severity == Severity.WARNING:
            return "次回のレビューミーティングで議題に追加。傾向を引き続き監視。"

        elif severity == Severity.INFO:
            return "月次レポートに含める。アクション不要。"

        return "アクション不要。"

    def get_suppression_stats(self):
        """抑制されたアラートの統計を返す"""
        total = len(self.alert_history)
        suppressed = sum(1 for a in self.alert_history if a["severity"] == "suppressed")
        alerted = total - suppressed
        suppression_rate = (suppressed / total * 100) if total > 0 else 0

        return {
            "total_events": total,
            "alerted": alerted,
            "suppressed": suppressed,
            "suppression_rate": f"{suppression_rate:.1f}%",
        }


# ============================================================
# デモ: 知性フィルターの動作確認
# ============================================================

def demo_intelligent_filter():
    """さまざまなシナリオで知性フィルターの判定をデモ"""
    print("=" * 70)
    print("  インテリジェントアラートシステム - 知性フィルター デモ")
    print("=" * 70)
    print("""
  コンテキスト（営業時間・使用パターン・計画イベント）に基づいて
  アラートを発すべきか判定するフィルターの動作を確認します。

  ┌────────────────────────────────────────────────────────────────┐
  │ 知性フィルターの判定フロー                                     │
  │                                                                │
  │ メトリクス → コンテキスト収集 → 偏差度計算 → 重要度判定       │
  │                  ↑                              ↓              │
  │         営業時間/イベント/パターン       エスカレーション       │
  │                                                                │
  │ 目標: 無駄なアラートを抑制し、本当に重要な問題だけを通す      │
  └────────────────────────────────────────────────────────────────┘
""")

    alert_filter = IntelligentAlertFilter()

    # テストシナリオ
    scenarios = [
        {
            "title": "シナリオ 1: 営業時間内の正常なトラフィック",
            "event": {
                "metric_name": "HourlyRequests",
                "value": 250,
                "timestamp": "2026-08-12T14:00:00+09:00",
            },
            "expected": "抑制（正常範囲内）"
        },
        {
            "title": "シナリオ 2: 計画イベント中のトークン増加",
            "event": {
                "metric_name": "TokensPerMinute",
                "value": 12000,
                "timestamp": "2026-08-12T11:00:00+09:00",
            },
            "expected": "抑制（新機能リリースの想定範囲内）"
        },
        {
            "title": "シナリオ 3: 深夜の異常なリクエスト",
            "event": {
                "metric_name": "HourlyRequests",
                "value": 150,
                "timestamp": "2026-08-12T03:00:00+09:00",
            },
            "expected": "CRITICAL（深夜の異常使用 → 不正アクセスの疑い）"
        },
        {
            "title": "シナリオ 4: 入力トークンの急増（単発）",
            "event": {
                "metric_name": "InputTokensPerRequest",
                "value": 800,
                "timestamp": "2026-08-13T10:00:00+09:00",
            },
            "expected": "抑制（単発の外れ値）"
        },
        {
            "title": "シナリオ 5: 入力トークンの急増（連続2回目）",
            "event": {
                "metric_name": "InputTokensPerRequest",
                "value": 900,
                "timestamp": "2026-08-13T10:05:00+09:00",
            },
            "expected": "抑制（連続だが閾値未達）"
        },
        {
            "title": "シナリオ 6: 入力トークンの急増（連続3回目 → 警告）",
            "event": {
                "metric_name": "InputTokensPerRequest",
                "value": 850,
                "timestamp": "2026-08-13T10:10:00+09:00",
            },
            "expected": "WARNING（連続3回で閾値到達 → 傾向レポート）"
        },
        {
            "title": "シナリオ 7: エラー率の急騰",
            "event": {
                "metric_name": "ErrorRate",
                "value": 25.0,
                "timestamp": "2026-08-12T15:00:00+09:00",
            },
            "expected": "CRITICAL（ベースラインの5倍超）"
        },
        {
            "title": "シナリオ 8: 週末の低トラフィック",
            "event": {
                "metric_name": "HourlyRequests",
                "value": 30,
                "timestamp": "2026-08-16T14:00:00+09:00",
            },
            "expected": "抑制（週末は低トラフィックが正常）"
        },
    ]

    print(f"  {len(scenarios)} 件のシナリオを評価中...\n")

    for scenario in scenarios:
        print(f"  {'─' * 66}")
        print(f"  📋 {scenario['title']}")
        print(f"     期待: {scenario['expected']}")
        print(f"     入力: {scenario['event']['metric_name']} = {scenario['event']['value']}")
        print(f"     時刻: {scenario['event']['timestamp']}")

        result = alert_filter.evaluate(scenario["event"])

        # アラート判定結果の表示
        icon = {
            "critical": "🚨",
            "warning": "⚠️ ",
            "info": "ℹ️ ",
            "suppressed": "🔇",
        }.get(result["severity"], "❓")

        print(f"\n     {icon} 判定: {result['severity'].upper()}")
        print(f"     理由: {result['reason']}")
        print(f"     ベースライン: {result['baseline']} → 実測: {result['value']} "
              f"（{result['deviation']}倍）")

        if result["alert"]:
            print(f"     エスカレーション: {result['tier']}")
            print(f"     推奨: {result['recommendation']}")

        if result["context"]["planned_events"]:
            print(f"     計画イベント: {', '.join(result['context']['planned_events'])}")

        print()

    # 抑制統計
    stats = alert_filter.get_suppression_stats()
    print(f"{'═' * 70}")
    print(f"  📊 知性フィルター効果レポート:")
    print(f"  {'─' * 50}")
    print(f"  総イベント数:      {stats['total_events']}")
    print(f"  アラート発火:      {stats['alerted']}")
    print(f"  抑制（ノイズ除去）: {stats['suppressed']}")
    print(f"  抑制率:            {stats['suppression_rate']}")
    print(f"""
  ┌────────────────────────────────────────────────────────────────┐
  │ 💡 知性フィルターのポイント                                    │
  │                                                                │
  │ • 同じ値でも時間帯が違えば判定が変わる（深夜 vs 営業時間）   │
  │ • 計画イベント中のスパイクは自動的に抑制                       │
  │ • 単発の外れ値は無視し、連続異常のみエスカレーション           │
  │ • 曜日パターンを加味してベースラインを動的に調整               │
  │                                                                │
  │ → オペレーターのアラート疲れを防ぎ、意思決定を強化する        │
  └────────────────────────────────────────────────────────────────┘
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 8: インテリジェントアラートシステム")
    print("🔷" * 35)
    print()

    demo_intelligent_filter()
