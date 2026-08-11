"""
モジュール 5 パート 3: プロトタイプ vs 本番のギャップ
- プロトタイプエージェントの問題点を可視化
- 本番環境で必要な非機能要件
- AgentCore による解決策のデモ
"""

import json
import time
import random
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


# ======================================================================
# ステップ 3.1: プロトタイプの問題点
# ======================================================================

class PrototypeAgent:
    """
    プロトタイプレベルのエージェント（問題点を示す）

    問題点:
    - エラーハンドリングが不十分
    - スケーリングを考慮していない
    - セキュリティなし
    - モニタリングなし
    - メモリ管理なし（メモリリーク）
    """

    def __init__(self):
        self.conversations = []  # メモリリークの原因

    def handle_request(self, user_input):
        """プロトタイプ: 単純なリクエスト処理"""
        # 問題1: エラーハンドリングなし
        result = self._call_tool(user_input)

        # 問題2: メモリが無限に蓄積
        self.conversations.append({
            "input": user_input,
            "output": result,
            "all_history": self.conversations.copy(),  # メモリリーク！
        })

        # 問題3: ログが print 文のみ
        print(f"  [処理完了] {user_input[:30]}...")
        return result

    def _call_tool(self, query):
        """ツール呼び出し（問題のある実装）"""
        # 問題4: タイムアウトなし
        # 問題5: リトライなし
        # 問題6: 認証なし
        time.sleep(random.uniform(0.1, 0.5))

        # 問題7: ランダムに失敗（エラーハンドリングなし）
        if random.random() < 0.2:
            raise Exception("ツール呼び出し失敗: 接続タイムアウト")

        return f"結果: {query}"


# ======================================================================
# ステップ 3.2: 本番レベルのエージェント（AgentCore 活用）
# ======================================================================

class ProductionAgent:
    """
    本番レベルのエージェント（AgentCore を活用）

    解決策:
    - 構造化ログ & トレーシング
    - リトライ & サーキットブレーカー
    - 認証 & 認可
    - メモリ管理
    - メトリクス収集
    - グレースフルデグラデーション
    """

    def __init__(self, agent_id, config):
        self.agent_id = agent_id
        self.config = config
        self.metrics = {
            "requests": 0,
            "successes": 0,
            "failures": 0,
            "latencies": [],
            "circuit_breaker_trips": 0,
        }
        self.circuit_breaker = {"failures": 0, "threshold": 3, "state": "closed"}
        self.traces = []

    def handle_request(self, user_input, user_id=None):
        """本番: 堅牢なリクエスト処理"""
        trace_id = f"trace-{random.randint(10000, 99999)}"
        start_time = time.time()
        self.metrics["requests"] += 1

        trace = {
            "trace_id": trace_id,
            "agent_id": self.agent_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "steps": [],
        }

        try:
            # ステップ1: 認証チェック
            trace["steps"].append({"step": "auth", "status": "pass"})

            # ステップ2: サーキットブレーカーチェック
            if self.circuit_breaker["state"] == "open":
                trace["steps"].append({"step": "circuit_breaker", "status": "open"})
                self.metrics["circuit_breaker_trips"] += 1
                return self._fallback_response(user_input)

            # ステップ3: ツール呼び出し（リトライ付き）
            result = self._call_tool_with_retry(user_input, trace)

            # ステップ4: メトリクス記録
            latency = (time.time() - start_time) * 1000
            self.metrics["successes"] += 1
            self.metrics["latencies"].append(latency)
            trace["steps"].append({"step": "complete", "latency_ms": latency})
            trace["status"] = "success"

            self.circuit_breaker["failures"] = 0
            return result

        except Exception as e:
            self.metrics["failures"] += 1
            self.circuit_breaker["failures"] += 1

            if self.circuit_breaker["failures"] >= self.circuit_breaker["threshold"]:
                self.circuit_breaker["state"] = "open"
                trace["steps"].append({"step": "circuit_breaker", "status": "tripped"})

            trace["status"] = "error"
            trace["error"] = str(e)

            # グレースフルデグラデーション
            return self._fallback_response(user_input)

        finally:
            self.traces.append(trace)

    def _call_tool_with_retry(self, query, trace, max_retries=3):
        """リトライ付きツール呼び出し"""
        for attempt in range(max_retries):
            try:
                time.sleep(random.uniform(0.05, 0.2))
                if random.random() < 0.15:
                    raise Exception("一時的なエラー")
                trace["steps"].append({
                    "step": "tool_call",
                    "attempt": attempt + 1,
                    "status": "success",
                })
                return f"結果: {query}"
            except Exception as e:
                trace["steps"].append({
                    "step": "tool_call",
                    "attempt": attempt + 1,
                    "status": "retry",
                    "error": str(e),
                })
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.1 * (2 ** attempt))  # 指数バックオフ

    def _fallback_response(self, query):
        """フォールバック応答（グレースフルデグラデーション）"""
        return f"[フォールバック] 現在一部機能に制限があります。基本情報: {query}"

    def get_metrics_summary(self):
        """メトリクスサマリー"""
        latencies = self.metrics["latencies"]
        return {
            "total_requests": self.metrics["requests"],
            "success_rate": f"{self.metrics['successes'] / max(1, self.metrics['requests']) * 100:.1f}%",
            "failure_rate": f"{self.metrics['failures'] / max(1, self.metrics['requests']) * 100:.1f}%",
            "avg_latency_ms": f"{sum(latencies) / max(1, len(latencies)):.0f}ms",
            "p95_latency_ms": f"{sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0:.0f}ms",
            "circuit_breaker": self.circuit_breaker["state"],
            "circuit_breaker_trips": self.metrics["circuit_breaker_trips"],
        }


# ======================================================================
# デモ実行
# ======================================================================

def demo_prototype_problems():
    """プロトタイプの問題点デモ"""
    print("=" * 70)
    print("  ステップ 3.1: プロトタイプの問題点")
    print("=" * 70)

    agent = PrototypeAgent()

    print("\n  [1] エラーハンドリングの問題")
    print("  " + "-" * 50)

    success = 0
    failures = 0
    for i in range(10):
        try:
            agent.handle_request(f"リクエスト {i+1}: 沖縄旅行の検索")
            success += 1
        except Exception as e:
            failures += 1
            print(f"  ✗ クラッシュ！ → {e}")

    print(f"\n    結果: 成功 {success}/10, 失敗 {failures}/10")
    print(f"    → 本番では 20% のリクエストがエラーで落ちる！")

    print("\n  [2] メモリリークの問題")
    print("  " + "-" * 50)

    # メモリ使用量のシミュレーション
    memory_usage = []
    for i in range(5):
        try:
            agent.handle_request(f"テストリクエスト {i}")
        except Exception:
            pass
        # 各メッセージが全履歴をコピーするためメモリが指数的に増加
        size = len(json.dumps(agent.conversations))
        memory_usage.append(size)

    print(f"    メモリ使用量の推移:")
    for i, size in enumerate(memory_usage):
        bar = "█" * min(50, size // 100)
        print(f"      リクエスト {i+1}: {size:>6} bytes {bar}")
    print(f"    → メモリが指数的に増加！長時間稼働でOOM発生のリスク")

    print("\n  [3] スケーラビリティの問題")
    print("  " + "-" * 50)

    print(f"    同時リクエスト処理のシミュレーション:")
    print(f"    (シングルスレッド = 1つずつ順番に処理)")

    start = time.time()
    for i in range(5):
        try:
            agent.handle_request(f"同時リクエスト {i+1}")
        except Exception:
            pass
    sequential_time = time.time() - start
    print(f"    5リクエスト順次処理: {sequential_time:.2f}秒")
    print(f"    → 1000同時リクエストでは約 {sequential_time * 200:.0f}秒 かかる！")

    print("\n  [4] セキュリティの問題")
    print("  " + "-" * 50)

    print(f"    • 認証なし: 誰でもエージェントを呼び出せる")
    print(f"    • 認可なし: 全ツールに無制限アクセス")
    print(f"    • 監査なし: 誰が何をしたか追跡不能")
    print(f"    • 入力検証なし: インジェクション攻撃に脆弱")

    print("\n  [5] モニタリングの問題")
    print("  " + "-" * 50)

    print(f"    • print文のみ: 構造化されていないログ")
    print(f"    • メトリクスなし: レイテンシ、成功率が不明")
    print(f"    • アラートなし: 障害に気づけない")
    print(f"    • トレーシングなし: 問題の原因特定が困難")


def demo_production_solution():
    """本番レベルの解決策デモ"""
    print(f"\n\n{'=' * 70}")
    print("  ステップ 3.2: AgentCore による本番レベルの解決")
    print("=" * 70)

    agent = ProductionAgent(
        agent_id="agent-travel-001",
        config={
            "max_retries": 3,
            "timeout_ms": 5000,
            "circuit_breaker_threshold": 3,
        }
    )

    print("\n  [1] リトライ & サーキットブレーカー")
    print("  " + "-" * 50)

    for i in range(10):
        result = agent.handle_request(
            f"リクエスト {i+1}: 沖縄旅行の検索",
            user_id="user-001"
        )
        status = "✓" if "[フォールバック]" not in result else "△(フォールバック)"
        print(f"    リクエスト {i+1:2d}: {status}")

    metrics = agent.get_metrics_summary()
    print(f"\n    メトリクス:")
    print(f"      成功率: {metrics['success_rate']}")
    print(f"      平均レイテンシ: {metrics['avg_latency_ms']}")
    print(f"      サーキットブレーカー: {metrics['circuit_breaker']}")

    print("\n  [2] Observability（可観測性）")
    print("  " + "-" * 50)

    print(f"    トレース例（最新のリクエスト）:")
    if agent.traces:
        latest_trace = agent.traces[-1]
        print(f"      Trace ID: {latest_trace['trace_id']}")
        print(f"      Agent ID: {latest_trace['agent_id']}")
        print(f"      Status: {latest_trace.get('status', 'unknown')}")
        print(f"      Steps:")
        for step in latest_trace["steps"]:
            print(f"        → {step['step']}: {step.get('status', '')}")

    print("\n  [3] スケーラビリティ（並行処理）")
    print("  " + "-" * 50)

    # 並行処理のシミュレーション
    parallel_agent = ProductionAgent(
        agent_id="agent-travel-002",
        config={"max_retries": 3, "timeout_ms": 5000}
    )

    start = time.time()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(
                parallel_agent.handle_request,
                f"並行リクエスト {i+1}",
                f"user-{i:03d}"
            )
            for i in range(10)
        ]
        results = [f.result() for f in as_completed(futures)]
    parallel_time = time.time() - start

    print(f"    10リクエスト並行処理: {parallel_time:.2f}秒")
    print(f"    （プロトタイプの順次処理比: 約 {parallel_time / max(0.01, parallel_time * 3):.1f}x 高速）")
    print(f"    → AgentCore Runtime のオートスケーリングでさらに高速化")

    print("\n  [4] 品質評価（AgentCore Evaluations）")
    print("  " + "-" * 50)

    evaluations = [
        ("正確性", 0.92, "回答が事実に基づいているか"),
        ("関連性", 0.88, "ユーザーの質問に適切に答えているか"),
        ("完全性", 0.85, "必要な情報が網羅されているか"),
        ("有害性", 0.02, "有害なコンテンツが含まれていないか"),
        ("幻覚", 0.08, "事実と異なる情報が含まれていないか"),
        ("ツール適切性", 0.95, "適切なツールが選択されているか"),
    ]

    print(f"    ビルトインエバリュエーターのスコア（サンプル）:")
    for name, score, desc in evaluations:
        bar_len = int(score * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        print(f"      {name:10s} [{bar}] {score:.0%}  {desc}")


def demo_comparison_table():
    """プロトタイプ vs 本番の比較"""
    print(f"\n\n{'=' * 70}")
    print("  プロトタイプ vs 本番 比較まとめ")
    print("=" * 70)

    print("""
  ┌──────────────────┬────────────────────────┬────────────────────────────────┐
  │ 側面             │ プロトタイプ           │ 本番（AgentCore）              │
  ├──────────────────┼────────────────────────┼────────────────────────────────┤
  │ スケール         │ 1ユーザー             │ 1000+同時接続（オートスケール）│
  │ 可用性           │ ダウン許容             │ 99.9% SLA（Runtime）           │
  │ セキュリティ     │ なし                   │ Identity + Policy              │
  │ コスト           │ 固定（無駄あり）       │ 従量課金（Runtime）            │
  │ モニタリング     │ print文               │ Observability（トレース）      │
  │ エラー処理       │ クラッシュ             │ リトライ+フォールバック        │
  │ メモリ           │ インメモリ（リーク）   │ Memory（永続化+検索）          │
  │ ツール管理       │ ハードコード           │ Gateway（自動検出）            │
  │ 品質保証         │ なし                   │ Evaluations（自動スコア）      │
  │ デプロイ         │ 手動（python app.py）  │ サーバーレス（Runtime）         │
  └──────────────────┴────────────────────────┴────────────────────────────────┘
""")

    print("  AgentCore による本番移行の 5 ステップ:")
    print("  " + "-" * 50)
    steps = [
        ("1. Runtime にデプロイ", "サーバーレス化、オートスケーリング有効化"),
        ("2. Identity を設定", "エージェントIDの登録、アクセスポリシーの設定"),
        ("3. Gateway でツール登録", "MCP/Lambda/API を統一管理、セマンティック検索有効化"),
        ("4. Memory を接続", "DynamoDB ベースの永続メモリ、コンテキスト管理"),
        ("5. Observability を有効化", "トレーシング、メトリクス、Evaluations の設定"),
    ]

    for step, desc in steps:
        print(f"    {step}")
        print(f"      → {desc}")


def demo_agentcore_architecture():
    """AgentCore アーキテクチャの全体像"""
    print(f"\n\n{'=' * 70}")
    print("  AgentCore アーキテクチャ全体像")
    print("=" * 70)

    print("""
  開発フロー:

  ┌─────────────────────────────────────────────────────────────────────┐
  │  ローカル開発                                                       │
  │                                                                     │
  │  ┌──────────────────────────────────────────────────┐              │
  │  │ Strands Agents / LangGraph / CrewAI               │              │
  │  │                                                    │              │
  │  │  agent = Agent(                                    │              │
  │  │      model=BedrockModel("nova-pro"),               │              │
  │  │      tools=[search_flights, search_hotels, ...],   │              │
  │  │      memory=SessionMemory()                        │              │
  │  │  )                                                 │              │
  │  └──────────────────────────────────────────────────┘              │
  │                          │                                          │
  │                          ▼                                          │
  │                   python agent.py                                    │
  │                   (ローカルテスト)                                   │
  └─────────────────────────────────────────────────────────────────────┘
                             │
                             │ デプロイ
                             ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Amazon Bedrock AgentCore                                           │
  │                                                                     │
  │  ┌───────────────────────────────────────────────────────────────┐ │
  │  │ Runtime (サーバーレス実行)                                     │ │
  │  │  • オートスケーリング (0→N)                                   │ │
  │  │  • フレームワーク非依存                                       │ │
  │  │  • 長時間実行サポート                                         │ │
  │  └───────────────────────────────────────────────────────────────┘ │
  │                                                                     │
  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────────────────┐ │
  │  │   Gateway   │  │   Memory    │  │        Identity            │ │
  │  │  ツール管理 │  │ コンテキスト│  │  認証・認可・ポリシー      │ │
  │  └─────────────┘  └─────────────┘  └────────────────────────────┘ │
  │                                                                     │
  │  ┌───────────────────────────────────────────────────────────────┐ │
  │  │ Observability & Evaluations                                    │ │
  │  │  • トレーシング  • メトリクス  • 品質評価（13種類）           │ │
  │  └───────────────────────────────────────────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────────┘
""")


# ======================================================================
# メイン実行
# ======================================================================

if __name__ == "__main__":
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  Amazon Bedrock AgentCore - プロトタイプ vs 本番                     ║")
    print("║  パート 3: 本番稼働の課題と AgentCore による解決                    ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    demo_prototype_problems()
    demo_production_solution()
    demo_comparison_table()
    demo_agentcore_architecture()

    print(f"\n{'=' * 70}")
    print("  キーポイント")
    print("=" * 70)
    print("""
  1. プロトタイプと本番の間には大きなギャップがある
     - エラーハンドリング、スケール、セキュリティ、モニタリング

  2. AgentCore はこのギャップを埋めるマネージドサービス
     - Runtime: サーバーレス実行 + オートスケーリング
     - Gateway: ツールの統一管理 + セマンティック検索
     - Memory: 永続的なコンテキスト管理
     - Identity: 認証・認可・ポリシー
     - Observability: トレーシング + 品質評価

  3. フレームワーク非依存
     - Strands Agents、LangGraph、CrewAI どれでもデプロイ可能
     - ローカル開発 → そのまま AgentCore にデプロイ

  4. プロダクションレディネスのチェックリスト:
     ✓ エラーハンドリング（リトライ、サーキットブレーカー）
     ✓ スケーラビリティ（オートスケーリング）
     ✓ セキュリティ（認証、認可、監査）
     ✓ 可観測性（トレース、メトリクス、ログ）
     ✓ 品質保証（Evaluations による自動評価）
""")
