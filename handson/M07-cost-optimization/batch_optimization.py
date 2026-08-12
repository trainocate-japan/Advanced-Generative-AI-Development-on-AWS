"""
モジュール 7: 動的バッチ処理とスケーリングによるコスト最適化デモ
- キュー深度に応じた動的バッチサイジング
- レイテンシー優先 / バランス / スループット優先モードの自動切り替え
- 予算ベースの自動コスト管理（アラート・モデル切り替え・キューイング）
- バッチ処理のスループットとコスト効率の測定
"""

import boto3
import json
import time
import asyncio
import random
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

# モデル定義（コスト順）
MODELS = {
    "high": {
        "id": "amazon.nova-pro-v1:0",
        "name": "Nova Pro",
        "cost_per_1k_input": 0.0008,
        "cost_per_1k_output": 0.0032,
    },
    "medium": {
        "id": "amazon.nova-lite-v1:0",
        "name": "Nova Lite",
        "cost_per_1k_input": 0.00006,
        "cost_per_1k_output": 0.00024,
    },
    "low": {
        "id": "amazon.nova-micro-v1:0",
        "name": "Nova Micro",
        "cost_per_1k_input": 0.000035,
        "cost_per_1k_output": 0.00014,
    },
}


# ============================================================
# 動的バッチサイジング エンジン
# ============================================================

class DynamicBatchEngine:
    """
    キュー深度に応じてバッチサイズと処理戦略を動的に変更するエンジン

    スケーリングルール:
    - レイテンシー優先モード（<50 pending）: バッチ5、即時処理
    - バランスモード（50-500 pending）: バッチ25、5秒バッファ
    - スループットモード（>500 pending）: バッチ50、10秒バッファ
    """

    SCALING_RULES = {
        "latency": {
            "threshold": 50,
            "batch_size": 5,
            "buffer_seconds": 0,
            "description": "レイテンシー優先",
            "icon": "⚡",
        },
        "balanced": {
            "threshold": 500,
            "batch_size": 25,
            "buffer_seconds": 5,
            "description": "バランス",
            "icon": "⚖️",
        },
        "throughput": {
            "threshold": float('inf'),
            "batch_size": 50,
            "buffer_seconds": 10,
            "description": "スループット優先",
            "icon": "🚀",
        },
    }

    def __init__(self):
        self.queue = deque()
        self.processed = 0
        self.total_latency = 0
        self.mode_history = []
        self.batch_history = []

    def determine_mode(self, queue_depth):
        """キュー深度に基づいて処理モードを決定"""
        if queue_depth < self.SCALING_RULES["latency"]["threshold"]:
            return "latency"
        elif queue_depth < self.SCALING_RULES["balanced"]["threshold"]:
            return "balanced"
        else:
            return "throughput"

    def get_batch_config(self, queue_depth):
        """現在のキュー深度に対する最適なバッチ設定を返す"""
        mode = self.determine_mode(queue_depth)
        rule = self.SCALING_RULES[mode]
        return {
            "mode": mode,
            "batch_size": rule["batch_size"],
            "buffer_seconds": rule["buffer_seconds"],
            "description": rule["description"],
            "icon": rule["icon"],
        }

    def enqueue(self, requests):
        """リクエストをキューに追加"""
        for req in requests:
            self.queue.append(req)

    def process_batch(self, model_tier="high"):
        """キューからバッチを取得して処理"""
        queue_depth = len(self.queue)
        if queue_depth == 0:
            return None

        config = self.get_batch_config(queue_depth)
        batch_size = min(config["batch_size"], queue_depth)

        # バッチ取得
        batch = []
        for _ in range(batch_size):
            if self.queue:
                batch.append(self.queue.popleft())

        # バッチ処理実行
        start = time.time()
        results = self._execute_batch(batch, model_tier)
        elapsed = time.time() - start

        self.processed += len(batch)
        self.total_latency += elapsed

        batch_info = {
            "mode": config["description"],
            "icon": config["icon"],
            "batch_size": len(batch),
            "latency": elapsed,
            "remaining": len(self.queue),
            "model": MODELS[model_tier]["name"],
        }
        self.batch_history.append(batch_info)
        self.mode_history.append(config["mode"])

        return batch_info

    def _execute_batch(self, batch, model_tier):
        """バッチ内のリクエストを並列実行"""
        model_id = MODELS[model_tier]["id"]
        results = []

        # ThreadPoolExecutor で並列実行（Bedrock は同期 API）
        with ThreadPoolExecutor(max_workers=min(len(batch), 5)) as executor:
            futures = []
            for request in batch:
                future = executor.submit(self._call_bedrock, request, model_id)
                futures.append(future)

            for future in futures:
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e)})

        return results

    def _call_bedrock(self, request, model_id):
        """単一リクエストの Bedrock 呼び出し"""
        try:
            response = bedrock.converse(
                modelId=model_id,
                messages=[{
                    "role": "user",
                    "content": [{"text": request}]
                }],
                inferenceConfig={"temperature": 0.3, "maxTokens": 200}
            )
            return {
                "status": "success",
                "usage": response['usage'],
                "response": response['output']['message']['content'][0]['text'][:50],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ============================================================
# コスト自動管理エンジン
# ============================================================

class CostManager:
    """
    予算ベースの自動コスト管理

    しきい値アクション:
    - 警告（80%）: アラート送信
    - 制限（95%）: 高コストモデルから低コストモデルへ切り替え
    - 上限（100%）: 新規リクエストをキューイング
    """

    def __init__(self, monthly_budget_usd=100.0):
        self.monthly_budget = monthly_budget_usd
        self.current_spend = 0.0
        self.model_tier = "high"
        self.actions_taken = []
        self.queued_requests = 0

    @property
    def budget_usage_pct(self):
        return (self.current_spend / self.monthly_budget) * 100

    def add_cost(self, input_tokens, output_tokens):
        """コストを加算し、しきい値チェックを実行"""
        model = MODELS[self.model_tier]
        cost = (
            (input_tokens / 1000) * model["cost_per_1k_input"]
            + (output_tokens / 1000) * model["cost_per_1k_output"]
        )
        self.current_spend += cost
        self._check_thresholds()
        return cost

    def _check_thresholds(self):
        """予算しきい値のチェックとアクション実行"""
        pct = self.budget_usage_pct

        if pct >= 100 and "cap" not in [a["type"] for a in self.actions_taken]:
            self.actions_taken.append({
                "type": "cap",
                "timestamp": datetime.now().isoformat(),
                "message": "🛑 上限到達: 新規リクエストをキューイング",
                "budget_pct": pct,
            })

        elif pct >= 95 and self.model_tier != "low":
            old_tier = self.model_tier
            self.model_tier = "low"
            self.actions_taken.append({
                "type": "downgrade",
                "timestamp": datetime.now().isoformat(),
                "message": f"⚠️ 制限しきい値: {MODELS[old_tier]['name']} → {MODELS['low']['name']} に切り替え",
                "budget_pct": pct,
            })

        elif pct >= 80 and "warning" not in [a["type"] for a in self.actions_taken]:
            self.actions_taken.append({
                "type": "warning",
                "timestamp": datetime.now().isoformat(),
                "message": "⚡ 警告: 月間予算の80%に到達",
                "budget_pct": pct,
            })

    def can_process(self):
        """リクエスト処理可否を判定"""
        if self.budget_usage_pct >= 100:
            self.queued_requests += 1
            return False
        return True

    def get_status(self):
        """現在のコスト管理状態を返す"""
        return {
            "budget": self.monthly_budget,
            "current_spend": self.current_spend,
            "usage_pct": self.budget_usage_pct,
            "model_tier": self.model_tier,
            "model_name": MODELS[self.model_tier]["name"],
            "actions_taken": len(self.actions_taken),
            "queued_requests": self.queued_requests,
        }


# ============================================================
# デモ 1: 動的バッチサイジングの動作
# ============================================================

def demo_dynamic_batching():
    """キュー深度に応じたバッチサイズの動的変更をデモ"""
    print("=" * 70)
    print("  デモ 1: キュー深度に応じた動的バッチサイジング")
    print("=" * 70)
    print("""
  キューに溜まったリクエスト数に応じて、自動的に処理戦略を切り替えます。

  ┌──────────────────┬────────────┬──────────────┬──────────────────┐
  │ モード           │ キュー深度 │ バッチサイズ │ バッファ時間     │
  ├──────────────────┼────────────┼──────────────┼──────────────────┤
  │ ⚡ レイテンシー  │ < 50       │ 5            │ 即時処理         │
  │ ⚖️ バランス     │ 50-500     │ 25           │ 5秒バッファ      │
  │ 🚀 スループット │ > 500      │ 50           │ 10秒バッファ     │
  └──────────────────┴────────────┴──────────────┴──────────────────┘
""")

    engine = DynamicBatchEngine()

    # シミュレーション用クエリ
    sample_queries = [
        "この商品の配送日数は？",
        "返品ポリシーを教えて",
        "おすすめの周辺機器は？",
        "セール情報はありますか",
        "ギフトラッピングは可能？",
        "在庫状況を確認したい",
        "支払い方法の種類は？",
        "保証期間はどのくらい？",
    ]

    # フェーズ1: 少量リクエスト（レイテンシー優先モード）
    print(f"{'─' * 70}")
    print("  フェーズ 1: 少量リクエスト投入（10件）→ レイテンシー優先モード")
    print(f"{'─' * 70}")

    phase1_queries = [random.choice(sample_queries) for _ in range(10)]
    engine.enqueue(phase1_queries)

    config = engine.get_batch_config(len(engine.queue))
    print(f"\n  キュー深度: {len(engine.queue)} → {config['icon']} {config['description']}モード")
    print(f"  バッチサイズ: {config['batch_size']}, バッファ: {config['buffer_seconds']}秒")

    # 1バッチ処理
    result = engine.process_batch()
    if result:
        print(f"\n  処理結果:")
        print(f"    バッチサイズ: {result['batch_size']}件")
        print(f"    処理時間: {result['latency']:.2f}秒")
        print(f"    使用モデル: {result['model']}")
        print(f"    残キュー: {result['remaining']}件")

    time.sleep(1)

    # フェーズ2: 中量リクエスト（バランスモード）
    print(f"\n{'─' * 70}")
    print("  フェーズ 2: 追加リクエスト投入（+100件）→ バランスモード")
    print(f"{'─' * 70}")

    phase2_queries = [random.choice(sample_queries) for _ in range(100)]
    engine.enqueue(phase2_queries)

    config = engine.get_batch_config(len(engine.queue))
    print(f"\n  キュー深度: {len(engine.queue)} → {config['icon']} {config['description']}モード")
    print(f"  バッチサイズ: {config['batch_size']}, バッファ: {config['buffer_seconds']}秒")

    # 1バッチ処理
    result = engine.process_batch()
    if result:
        print(f"\n  処理結果:")
        print(f"    バッチサイズ: {result['batch_size']}件")
        print(f"    処理時間: {result['latency']:.2f}秒")
        print(f"    使用モデル: {result['model']}")
        print(f"    残キュー: {result['remaining']}件")

    time.sleep(1)

    # フェーズ3: 大量リクエスト（スループットモード）
    print(f"\n{'─' * 70}")
    print("  フェーズ 3: 大量リクエスト投入（+500件）→ スループットモード")
    print(f"{'─' * 70}")

    phase3_queries = [random.choice(sample_queries) for _ in range(500)]
    engine.enqueue(phase3_queries)

    config = engine.get_batch_config(len(engine.queue))
    print(f"\n  キュー深度: {len(engine.queue)} → {config['icon']} {config['description']}モード")
    print(f"  バッチサイズ: {config['batch_size']}, バッファ: {config['buffer_seconds']}秒")

    # 1バッチ処理
    result = engine.process_batch()
    if result:
        print(f"\n  処理結果:")
        print(f"    バッチサイズ: {result['batch_size']}件")
        print(f"    処理時間: {result['latency']:.2f}秒")
        print(f"    使用モデル: {result['model']}")
        print(f"    残キュー: {result['remaining']}件")

    # サマリー
    print(f"\n{'─' * 70}")
    print(f"  📊 動的バッチサイジング サマリー:")
    print(f"     総処理件数: {engine.processed}")
    print(f"     モード遷移: ", end="")
    for info in engine.batch_history:
        print(f"{info['icon']}", end=" ")
    print()
    print(f"     スループット優先モードでは1バッチあたりの処理件数が10倍に")
    print(f"     → バッファリングにより API 呼び出し回数を大幅削減")


# ============================================================
# デモ 2: コスト自動管理
# ============================================================

def demo_cost_management():
    """予算しきい値に応じた自動アクションをデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: 予算ベースの自動コスト管理")
    print("=" * 70)
    print("""
  月間予算に対する使用率に応じて、自動的にコスト制御アクションを実行します。

  ┌──────────────┬──────────────────────────────────────────────────┐
  │ しきい値     │ 自動アクション                                   │
  ├──────────────┼──────────────────────────────────────────────────┤
  │ 80%（警告）  │ CloudWatch アラート送信、管理者通知               │
  │ 95%（制限）  │ 高コストモデル → 低コストモデルへ自動切り替え     │
  │ 100%（上限） │ 新規リクエストをキューイング（翌月まで待機）      │
  └──────────────┴──────────────────────────────────────────────────┘
""")

    # 月間予算 $0.50 でシミュレーション（デモ用に小さく設定）
    budget = 0.50
    manager = CostManager(monthly_budget_usd=budget)
    print(f"  シミュレーション設定: 月間予算 ${budget:.2f}")
    print(f"{'─' * 70}")

    # リクエストを送信して予算消費をシミュレーション
    queries = [
        "この商品のレビューを要約して",
        "類似商品との比較表を作って",
        "購入者へのおすすめを3つ教えて",
        "この商品の特徴を箇条書きで",
        "競合製品との違いは何ですか",
    ]

    request_count = 0
    for i, query in enumerate(queries):
        if not manager.can_process():
            print(f"\n  🛑 リクエスト {i+1}: キューイング（予算上限到達）")
            continue

        request_count += 1
        model_id = MODELS[manager.model_tier]["id"]

        try:
            response = bedrock.converse(
                modelId=model_id,
                messages=[{
                    "role": "user",
                    "content": [{"text": query}]
                }],
                inferenceConfig={"temperature": 0.3, "maxTokens": 300}
            )

            usage = response['usage']
            cost = manager.add_cost(
                usage.get('inputTokens', 0),
                usage.get('outputTokens', 0)
            )

            status = manager.get_status()
            bar_length = 40
            filled = int(bar_length * min(status['usage_pct'], 100) / 100)
            bar = "█" * filled + "░" * (bar_length - filled)

            print(f"\n  リクエスト {i+1}: 「{query[:20]}...」")
            print(f"    モデル: {status['model_name']}")
            print(f"    コスト: ${cost:.6f}")
            print(f"    累計: ${status['current_spend']:.4f} / ${status['budget']:.2f}")
            print(f"    [{bar}] {status['usage_pct']:.1f}%")

            # アクションが発生した場合は表示
            for action in manager.actions_taken:
                if action not in getattr(demo_cost_management, '_shown_actions', []):
                    print(f"\n    → {action['message']}")
            demo_cost_management._shown_actions = manager.actions_taken.copy()

        except Exception as e:
            print(f"\n  リクエスト {i+1}: エラー - {e}")

        time.sleep(1)

    # 最終状態
    status = manager.get_status()
    print(f"\n{'─' * 70}")
    print(f"  📊 コスト管理 最終レポート:")
    print(f"     処理リクエスト数: {request_count}")
    print(f"     累計コスト: ${status['current_spend']:.4f}")
    print(f"     予算使用率: {status['usage_pct']:.1f}%")
    print(f"     最終モデル: {status['model_name']}")
    print(f"     発動アクション数: {status['actions_taken']}")
    print(f"     キューイング件数: {status['queued_requests']}")

    if manager.actions_taken:
        print(f"\n  📋 アクション履歴:")
        for action in manager.actions_taken:
            print(f"     {action['message']} (予算使用率: {action['budget_pct']:.1f}%)")


# リセット用
demo_cost_management._shown_actions = []


# ============================================================
# デモ 3: モデルルーティング戦略
# ============================================================

def demo_model_routing():
    """リクエスト特性に基づくモデルルーティング"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: インテリジェント モデルルーティング")
    print("=" * 70)
    print("""
  リクエストの複雑さに応じて、最適なモデルを自動選択します。
  シンプルな質問に高性能モデルを使うのはコストの無駄です。

  ルーティングロジック:
  ┌─────────────────────────┬──────────────┬──────────────────┐
  │ リクエスト特性          │ 選択モデル   │ コスト比         │
  ├─────────────────────────┼──────────────┼──────────────────┤
  │ 定型応答（FAQ等）       │ Nova Micro   │ 1x（ベースライン）│
  │ 一般的な質問            │ Nova Lite    │ 約 1.7x          │
  │ 複雑な分析・推論        │ Nova Pro     │ 約 23x           │
  └─────────────────────────┴──────────────┴──────────────────┘
""")

    # リクエストの複雑さを判定する簡易分類器
    def classify_complexity(query):
        """クエリの複雑さを簡易判定"""
        # 複雑さの指標
        complex_keywords = ["比較", "分析", "理由", "なぜ", "メリットとデメリット", "推薦", "戦略"]
        simple_keywords = ["営業時間", "住所", "電話番号", "はい", "いいえ", "いくら"]

        query_len = len(query)

        for kw in complex_keywords:
            if kw in query:
                return "high", "Nova Pro"
        for kw in simple_keywords:
            if kw in query:
                return "low", "Nova Micro"
        if query_len > 100:
            return "high", "Nova Pro"
        return "medium", "Nova Lite"

    # テストクエリ
    test_queries = [
        ("営業時間を教えてください", "定型FAQ"),
        ("この商品の在庫はありますか", "シンプルな質問"),
        ("予算10万円でゲーミングPCとモニターの最適な組み合わせを、性能バランスと将来のアップグレード性を考慮して提案してください", "複雑な分析"),
        ("返品できますか", "シンプルな質問"),
        ("競合3社の製品と比較して、当社製品のポジショニングを分析し、差別化戦略を提案してください", "複雑な分析"),
    ]

    print(f"{'─' * 70}")
    total_actual_cost = 0
    total_naive_cost = 0

    for query, expected_type in test_queries:
        complexity, selected_model = classify_complexity(query)
        model_config = MODELS[complexity]

        print(f"\n  クエリ: 「{query[:40]}{'...' if len(query) > 40 else ''}」")
        print(f"  分類: {expected_type} → {model_config['name']}（{complexity}）")

        try:
            response = bedrock.converse(
                modelId=model_config["id"],
                messages=[{
                    "role": "user",
                    "content": [{"text": query}]
                }],
                inferenceConfig={"temperature": 0.3, "maxTokens": 200}
            )

            usage = response['usage']
            input_tokens = usage.get('inputTokens', 0)
            output_tokens = usage.get('outputTokens', 0)

            # 実際のコスト（ルーティングあり）
            actual_cost = (
                (input_tokens / 1000) * model_config["cost_per_1k_input"]
                + (output_tokens / 1000) * model_config["cost_per_1k_output"]
            )

            # 全部 Pro で処理した場合のコスト
            naive_cost = (
                (input_tokens / 1000) * MODELS["high"]["cost_per_1k_input"]
                + (output_tokens / 1000) * MODELS["high"]["cost_per_1k_output"]
            )

            total_actual_cost += actual_cost
            total_naive_cost += naive_cost

            savings_pct = ((naive_cost - actual_cost) / naive_cost * 100) if naive_cost > 0 else 0

            print(f"  コスト: ${actual_cost:.6f}（Pro固定なら ${naive_cost:.6f}、{savings_pct:.0f}%削減）")

        except Exception as e:
            print(f"  エラー: {e}")

        time.sleep(1)

    print(f"\n{'─' * 70}")
    overall_savings = ((total_naive_cost - total_actual_cost) / total_naive_cost * 100) if total_naive_cost > 0 else 0
    print(f"  📊 モデルルーティング効果:")
    print(f"     ルーティングあり合計: ${total_actual_cost:.6f}")
    print(f"     全部Pro固定の合計:    ${total_naive_cost:.6f}")
    print(f"     コスト削減率:          {overall_savings:.1f}%")
    print(f"\n  💡 シンプルな質問には低コストモデルを自動選択することで、")
    print(f"     品質を大きく損なわずにコストを大幅削減できます。")


# ============================================================
# 本番環境アーキテクチャ
# ============================================================

def print_architecture():
    """本番環境での動的バッチ処理アーキテクチャ"""
    print("\n\n" + "=" * 70)
    print("  本番環境アーキテクチャ: 動的バッチ処理 + コスト管理")
    print("=" * 70)
    print("""
  ┌─────────────────────────────────────────────────────────────────────┐
  │                    動的バッチ処理アーキテクチャ                      │
  └─────────────────────────────────────────────────────────────────────┘

  リクエスト
       │
       ▼
  ┌──────────────────┐     ┌────────────────────────────────────────┐
  │ API Gateway      │────▶│ Lambda: リクエスト分類                  │
  │ (レート制限)     │     │ • 複雑さ判定 → モデル選択               │
  └──────────────────┘     │ • 優先度付与                            │
                           └────────────┬───────────────────────────┘
                                        │
                                        ▼
                           ┌────────────────────────────────────────┐
                           │ SQS キュー（優先度別）                  │
                           │ ┌──────┐ ┌──────┐ ┌──────┐            │
                           │ │ 高   │ │ 中   │ │ 低   │            │
                           │ └──┬───┘ └──┬───┘ └──┬───┘            │
                           └────┼────────┼────────┼────────────────┘
                                │        │        │
                                ▼        ▼        ▼
                           ┌────────────────────────────────────────┐
                           │ Lambda: バッチプロセッサ                │
                           │ • キュー深度監視 → バッチサイズ決定     │
                           │ • 並列実行制御                          │
                           │ • リトライ + DLQ                        │
                           └────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
           ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
           │ Nova Pro     │   │ Nova Lite    │   │ Nova Micro   │
           │ (複雑)       │   │ (一般)       │   │ (定型)       │
           └──────────────┘   └──────────────┘   └──────────────┘

  コスト管理レイヤー:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ CloudWatch Metrics → Alarm → SNS → Lambda (コスト制御)             │
  │                                                                     │
  │ • CostExplorer API で日次コスト取得                                 │
  │ • 予算アラーム: 80% / 95% / 100%                                   │
  │ • 自動アクション: モデルダウングレード、レート制限強化              │
  └─────────────────────────────────────────────────────────────────────┘

  SQS バッチ設定の目安:
  • BatchSize: 10（Lambda イベントソースマッピング）
  • MaximumBatchingWindowInSeconds: 5-30（キュー深度に応じて動的変更）
  • MaximumConcurrency: 10-50（モデルのスロットリング制限に合わせる）
  • VisibilityTimeout: 300秒（Bedrock の応答時間 + マージン）
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 7: 動的バッチ処理とスケーリングによるコスト最適化")
    print("🔷" * 35)
    print("\n  システム負荷に応じた処理戦略の自動切り替えと、")
    print("  予算ベースのコスト制御メカニズムを実装します。")
    print()

    # デモ 1: 動的バッチサイジング
    demo_dynamic_batching()
    time.sleep(1)

    # デモ 2: コスト自動管理
    demo_cost_management()
    time.sleep(1)

    # デモ 3: モデルルーティング
    demo_model_routing()

    # アーキテクチャまとめ
    print_architecture()
