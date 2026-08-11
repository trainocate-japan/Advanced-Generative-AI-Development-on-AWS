"""
モジュール 5 パート 2: Amazon Bedrock AgentCore の各コンポーネント
- Gateway: ツール検索とルーティング
- Memory: コンテキスト保持（短期・長期・エピソード記憶）
- Identity: セキュアなアクセス制御
- Runtime: サーバーレスデプロイ
"""

import json
import time
import uuid
from datetime import datetime, timedelta


# ======================================================================
# ステップ 2.1: AgentCore Gateway - ツール検索とルーティング
# ======================================================================

class AgentCoreGateway:
    """
    AgentCore Gateway のシミュレーション

    Gateway の役割:
    - 利用可能なツールの自動検出とインデックス作成
    - セマンティック検索によるツール選択
    - MCP サーバー、Lambda、API の統一管理
    - ツール呼び出しのルーティング
    """

    def __init__(self):
        self.tool_registry = {}
        self.tool_index = []  # セマンティック検索用インデックス
        self.call_history = []

    def register_tool(self, name, description, tool_type, endpoint, parameters):
        """ツールを Gateway に登録"""
        tool = {
            "name": name,
            "description": description,
            "type": tool_type,  # "lambda", "mcp", "api"
            "endpoint": endpoint,
            "parameters": parameters,
            "registered_at": datetime.now().isoformat(),
            "call_count": 0,
            "avg_latency_ms": 0,
        }
        self.tool_registry[name] = tool
        # セマンティックインデックスにキーワードを追加
        keywords = description.lower().split()
        self.tool_index.append({"name": name, "keywords": keywords})
        return tool

    def search_tools(self, query):
        """セマンティック検索でツールを検索（簡易版）"""
        query_words = query.lower().split()
        scores = []
        for entry in self.tool_index:
            # キーワードマッチングによるスコアリング（本番では埋め込みベクトル）
            score = sum(1 for w in query_words if w in entry["keywords"])
            if score > 0:
                scores.append((entry["name"], score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [self.tool_registry[name] for name, _ in scores]

    def route_call(self, tool_name, parameters):
        """ツール呼び出しのルーティング"""
        if tool_name not in self.tool_registry:
            return {"error": f"ツール '{tool_name}' が見つかりません"}

        tool = self.tool_registry[tool_name]
        start_time = time.time()

        # ルーティング（ツールタイプに応じた呼び出し）
        result = {
            "tool": tool_name,
            "type": tool["type"],
            "endpoint": tool["endpoint"],
            "parameters": parameters,
            "status": "success",
            "response": f"[{tool['type']}] {tool_name} を実行しました",
        }

        latency = (time.time() - start_time) * 1000
        tool["call_count"] += 1
        tool["avg_latency_ms"] = (
            (tool["avg_latency_ms"] * (tool["call_count"] - 1) + latency)
            / tool["call_count"]
        )

        self.call_history.append({
            "tool": tool_name,
            "timestamp": datetime.now().isoformat(),
            "latency_ms": latency,
            "status": "success",
        })
        return result

    def get_stats(self):
        """Gateway の統計情報"""
        return {
            "registered_tools": len(self.tool_registry),
            "total_calls": len(self.call_history),
            "tools": {
                name: {"calls": t["call_count"], "avg_latency_ms": round(t["avg_latency_ms"], 2)}
                for name, t in self.tool_registry.items()
            },
        }


# ======================================================================
# ステップ 2.2: AgentCore Memory - コンテキスト保持
# ======================================================================

class AgentCoreMemory:
    """
    AgentCore Memory のシミュレーション

    Memory の種類:
    - 短期記憶 (Short-term): 現在のセッション内の会話
    - 長期記憶 (Long-term): ユーザー嗜好、過去の履歴
    - エピソード記憶 (Episodic): 過去の対話パターンと結果
    """

    def __init__(self, user_id):
        self.user_id = user_id
        self.short_term = []       # 現在セッションのメッセージ
        self.long_term = {}        # ユーザープロファイル・嗜好
        self.episodic = []         # 過去の対話エピソード
        self.session_id = str(uuid.uuid4())[:8]

    def add_message(self, role, content):
        """短期記憶にメッセージ追加"""
        self.short_term.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
        })

    def store_preference(self, key, value):
        """長期記憶にユーザー嗜好を保存"""
        self.long_term[key] = {
            "value": value,
            "updated_at": datetime.now().isoformat(),
        }

    def store_episode(self, episode):
        """エピソード記憶に過去の対話を保存"""
        self.episodic.append({
            **episode,
            "episode_id": str(uuid.uuid4())[:8],
            "stored_at": datetime.now().isoformat(),
        })

    def recall_preference(self, key):
        """長期記憶からユーザー嗜好を取得"""
        return self.long_term.get(key, {}).get("value")

    def recall_relevant_episodes(self, query):
        """エピソード記憶から関連する過去の対話を検索"""
        # 簡易キーワードマッチ（本番ではセマンティック検索）
        query_words = query.lower().split()
        relevant = []
        for ep in self.episodic:
            summary = ep.get("summary", "").lower()
            if any(w in summary for w in query_words):
                relevant.append(ep)
        return relevant

    def get_context_window(self, max_messages=10):
        """コンテキストウィンドウの構築"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "recent_messages": self.short_term[-max_messages:],
            "user_preferences": self.long_term,
            "relevant_episodes": len(self.episodic),
        }

    def clear_session(self):
        """セッション終了時に短期記憶をエピソードとして保存"""
        if self.short_term:
            self.store_episode({
                "summary": f"セッション {self.session_id} の会話 ({len(self.short_term)}メッセージ)",
                "messages_count": len(self.short_term),
                "session_id": self.session_id,
            })
            self.short_term = []
            self.session_id = str(uuid.uuid4())[:8]


# ======================================================================
# ステップ 2.3: AgentCore Identity - セキュアなアクセス
# ======================================================================

class AgentCoreIdentity:
    """
    AgentCore Identity のシミュレーション

    Identity の機能:
    - エージェント ID ディレクトリ（各エージェントに固有IDを付与）
    - 委任されたアクセス制御（ユーザー権限をエージェントに委任）
    - ツール呼び出し前のポリシーチェック
    - OAuth2 ベースの認証フロー
    """

    def __init__(self):
        self.agents = {}
        self.policies = {}
        self.audit_log = []

    def register_agent(self, agent_name, owner, allowed_tools, max_budget=None):
        """エージェントIDの登録"""
        agent_id = f"agent-{str(uuid.uuid4())[:8]}"
        self.agents[agent_id] = {
            "name": agent_name,
            "owner": owner,
            "agent_id": agent_id,
            "allowed_tools": allowed_tools,
            "max_budget": max_budget,
            "created_at": datetime.now().isoformat(),
            "status": "active",
        }
        return agent_id

    def create_policy(self, agent_id, policy_name, rules):
        """ポリシーの作成"""
        policy_id = f"policy-{str(uuid.uuid4())[:8]}"
        self.policies[policy_id] = {
            "policy_id": policy_id,
            "agent_id": agent_id,
            "name": policy_name,
            "rules": rules,
            "created_at": datetime.now().isoformat(),
        }
        return policy_id

    def check_permission(self, agent_id, tool_name, parameters=None):
        """ツール呼び出し前のポリシーチェック"""
        agent = self.agents.get(agent_id)
        if not agent:
            result = {"allowed": False, "reason": "エージェントが見つかりません"}
            self._log_audit(agent_id, tool_name, "DENIED", result["reason"])
            return result

        if agent["status"] != "active":
            result = {"allowed": False, "reason": f"エージェントは {agent['status']} 状態です"}
            self._log_audit(agent_id, tool_name, "DENIED", result["reason"])
            return result

        if tool_name not in agent["allowed_tools"]:
            result = {"allowed": False, "reason": f"ツール '{tool_name}' は許可されていません"}
            self._log_audit(agent_id, tool_name, "DENIED", result["reason"])
            return result

        # 予算チェック
        if agent["max_budget"] and parameters:
            cost = parameters.get("estimated_cost", 0)
            if cost > agent["max_budget"]:
                result = {"allowed": False, "reason": f"予算超過 (¥{cost:,} > ¥{agent['max_budget']:,})"}
                self._log_audit(agent_id, tool_name, "DENIED", result["reason"])
                return result

        result = {"allowed": True, "reason": "ポリシーチェック通過"}
        self._log_audit(agent_id, tool_name, "ALLOWED", result["reason"])
        return result

    def _log_audit(self, agent_id, tool_name, decision, reason):
        """監査ログの記録"""
        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "agent_id": agent_id,
            "tool": tool_name,
            "decision": decision,
            "reason": reason,
        })

    def get_audit_log(self, agent_id=None):
        """監査ログの取得"""
        if agent_id:
            return [log for log in self.audit_log if log["agent_id"] == agent_id]
        return self.audit_log


# ======================================================================
# ステップ 2.4: AgentCore Runtime - サーバーレスデプロイ
# ======================================================================

class AgentCoreRuntime:
    """
    AgentCore Runtime のシミュレーション

    Runtime の機能:
    - サーバーレスでエージェントを実行
    - オートスケーリング（0→N インスタンス）
    - フレームワーク非依存（Strands、LangGraph、CrewAI 対応）
    - 長時間実行ワークフローのサポート
    - ヘルスチェックとモニタリング
    """

    def __init__(self):
        self.deployments = {}
        self.invocations = []
        self.metrics = {
            "total_invocations": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_duration_ms": 0,
            "active_instances": 0,
        }

    def deploy_agent(self, agent_name, framework, config):
        """エージェントをランタイムにデプロイ"""
        deployment_id = f"deploy-{str(uuid.uuid4())[:8]}"
        self.deployments[deployment_id] = {
            "deployment_id": deployment_id,
            "agent_name": agent_name,
            "framework": framework,
            "config": config,
            "status": "deploying",
            "deployed_at": None,
            "endpoint": None,
        }

        # デプロイプロセスのシミュレーション
        time.sleep(0.5)
        self.deployments[deployment_id]["status"] = "active"
        self.deployments[deployment_id]["deployed_at"] = datetime.now().isoformat()
        self.deployments[deployment_id]["endpoint"] = (
            f"https://agentcore.{config.get('region', 'us-east-1')}"
            f".amazonaws.com/agents/{deployment_id}"
        )
        return self.deployments[deployment_id]

    def invoke_agent(self, deployment_id, input_data):
        """デプロイされたエージェントの呼び出し"""
        deployment = self.deployments.get(deployment_id)
        if not deployment:
            return {"error": "デプロイメントが見つかりません"}
        if deployment["status"] != "active":
            return {"error": f"エージェントは {deployment['status']} 状態です"}

        start_time = time.time()
        self.metrics["active_instances"] += 1
        self.metrics["total_invocations"] += 1

        # 呼び出しシミュレーション
        invocation = {
            "invocation_id": str(uuid.uuid4())[:8],
            "deployment_id": deployment_id,
            "input": input_data,
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }

        time.sleep(0.3)  # 処理時間のシミュレーション
        invocation["status"] = "completed"
        invocation["duration_ms"] = (time.time() - start_time) * 1000
        invocation["output"] = f"エージェント '{deployment['agent_name']}' が応答を生成しました"

        self.invocations.append(invocation)
        self.metrics["success_count"] += 1
        self.metrics["active_instances"] -= 1

        # 平均応答時間の更新
        total = self.metrics["total_invocations"]
        self.metrics["avg_duration_ms"] = (
            (self.metrics["avg_duration_ms"] * (total - 1) + invocation["duration_ms"]) / total
        )
        return invocation

    def get_metrics(self):
        """ランタイムメトリクスの取得"""
        return {
            **self.metrics,
            "deployments": len(self.deployments),
            "active_deployments": sum(
                1 for d in self.deployments.values() if d["status"] == "active"
            ),
        }

    def scale_info(self, deployment_id):
        """スケーリング情報"""
        return {
            "deployment_id": deployment_id,
            "min_instances": 0,
            "max_instances": 100,
            "current_instances": self.metrics["active_instances"],
            "scaling_policy": "リクエスト数に基づくオートスケーリング",
            "cold_start_ms": "~500ms",
        }


# ======================================================================
# デモ実行
# ======================================================================

def demo_gateway():
    """Gateway デモ"""
    print("=" * 70)
    print("  ステップ 2.1: AgentCore Gateway - ツール検索とルーティング")
    print("=" * 70)

    gateway = AgentCoreGateway()

    # ツールの登録
    print("\n  [1] ツールの登録")
    print("  " + "-" * 50)

    tools_to_register = [
        ("search_flights", "フライトを検索する 航空券 出発 到着 予約",
         "lambda", "arn:aws:lambda:us-east-1:123456:function:search-flights",
         {"origin": "str", "destination": "str", "date": "str"}),
        ("search_hotels", "ホテルを検索する 宿泊 予約 チェックイン",
         "lambda", "arn:aws:lambda:us-east-1:123456:function:search-hotels",
         {"city": "str", "checkin": "str", "checkout": "str"}),
        ("get_weather", "天気予報を取得する 気温 降水確率",
         "api", "https://api.weather.example.com/forecast",
         {"city": "str", "date": "str"}),
        ("book_restaurant", "レストランを予約する 食事 ディナー ランチ",
         "mcp", "mcp://restaurant-booking-server",
         {"restaurant_id": "str", "date": "str", "guests": "int"}),
        ("translate_text", "テキストを翻訳する 言語 英語 日本語",
         "lambda", "arn:aws:lambda:us-east-1:123456:function:translate",
         {"text": "str", "source_lang": "str", "target_lang": "str"}),
    ]

    for name, desc, tool_type, endpoint, params in tools_to_register:
        gateway.register_tool(name, desc, tool_type, endpoint, params)
        print(f"    ✓ {name} ({tool_type}) を登録")

    # セマンティック検索デモ
    print("\n  [2] セマンティック検索によるツール選択")
    print("  " + "-" * 50)

    queries = [
        "フライト 航空券 を 予約 したい",
        "明日の天気を教えて",
        "ホテルを探している チェックイン",
        "レストラン ディナー 予約",
    ]

    for query in queries:
        results = gateway.search_tools(query)
        if results:
            top = results[0]
            print(f"    クエリ: 「{query}」")
            print(f"    → 最適ツール: {top['name']} ({top['type']})")
            print()

    # ルーティングデモ
    print("  [3] ツール呼び出しのルーティング")
    print("  " + "-" * 50)

    calls = [
        ("search_flights", {"origin": "東京", "destination": "沖縄", "date": "2025-03-15"}),
        ("search_hotels", {"city": "沖縄", "checkin": "2025-03-15", "checkout": "2025-03-17"}),
        ("get_weather", {"city": "沖縄", "date": "2025-03-15"}),
    ]

    for tool_name, params in calls:
        result = gateway.route_call(tool_name, params)
        print(f"    {tool_name} → [{result['type']}] {result['status']}")

    # 存在しないツールの呼び出し
    result = gateway.route_call("non_existent_tool", {})
    print(f"    non_existent_tool → エラー: {result['error']}")

    # 統計
    print(f"\n  [4] Gateway 統計")
    print("  " + "-" * 50)
    stats = gateway.get_stats()
    print(f"    登録ツール数: {stats['registered_tools']}")
    print(f"    総呼び出し数: {stats['total_calls']}")
    for name, info in stats['tools'].items():
        if info['calls'] > 0:
            print(f"      • {name}: {info['calls']}回")

    return gateway


def demo_memory():
    """Memory デモ"""
    print(f"\n\n{'=' * 70}")
    print("  ステップ 2.2: AgentCore Memory - コンテキスト保持")
    print("=" * 70)

    memory = AgentCoreMemory(user_id="user-tanaka-001")

    # 長期記憶: ユーザー嗜好の登録
    print("\n  [1] 長期記憶: ユーザー嗜好の保存")
    print("  " + "-" * 50)

    preferences = [
        ("preferred_airline", "ANA"),
        ("hotel_type", "リゾート"),
        ("budget_range", "8万〜12万円"),
        ("travel_style", "のんびり観光"),
        ("food_preference", "海鮮料理"),
        ("last_destination", "沖縄・恩納村"),
    ]

    for key, value in preferences:
        memory.store_preference(key, value)
        print(f"    ✓ {key}: {value}")

    # エピソード記憶: 過去の旅行
    print("\n  [2] エピソード記憶: 過去の対話を保存")
    print("  " + "-" * 50)

    past_episodes = [
        {
            "summary": "沖縄 恩納村 リゾートホテル 3泊4日 予算12万",
            "destination": "沖縄",
            "hotel": "オーシャンビューリゾート恩納",
            "satisfaction": "高",
        },
        {
            "summary": "京都 紅葉 2泊3日 旅館 予算10万",
            "destination": "京都",
            "hotel": "嵐山温泉旅館",
            "satisfaction": "高",
        },
        {
            "summary": "北海道 スキー 4泊5日 ペンション 予算15万",
            "destination": "北海道",
            "hotel": "ニセコペンション",
            "satisfaction": "中",
        },
    ]

    for ep in past_episodes:
        memory.store_episode(ep)
        print(f"    ✓ エピソード保存: {ep['summary'][:30]}...")

    # 短期記憶: 現在のセッション
    print("\n  [3] 短期記憶: 現在のセッション")
    print("  " + "-" * 50)

    conversation = [
        ("user", "前回と同じホテルで沖縄旅行を計画したいです"),
        ("assistant", "前回は恩納村のオーシャンビューリゾートでしたね。同じホテルで手配しますか？"),
        ("user", "はい、今回は予算をもう少し上げて、アクティビティも追加したいです"),
        ("assistant", "承知しました。前回の予算12万円から上乗せして、シュノーケリングツアーなどを追加しますね。"),
    ]

    for role, content in conversation:
        memory.add_message(role, content)
        speaker = "ユーザー" if role == "user" else "エージェント"
        print(f"    [{speaker}] {content[:40]}...")

    # メモリの活用: 関連エピソードの検索
    print("\n  [4] メモリ活用: コンテキストの構築")
    print("  " + "-" * 50)

    query = "沖縄 ホテル"
    relevant = memory.recall_relevant_episodes(query)
    print(f"    検索クエリ: 「{query}」")
    print(f"    関連エピソード: {len(relevant)}件")
    for ep in relevant:
        print(f"      • {ep['summary'][:40]}")

    pref = memory.recall_preference("preferred_airline")
    print(f"\n    ユーザー嗜好:")
    print(f"      • 好みの航空会社: {pref}")
    print(f"      • ホテルタイプ: {memory.recall_preference('hotel_type')}")
    print(f"      • 前回の旅先: {memory.recall_preference('last_destination')}")

    context = memory.get_context_window()
    print(f"\n    コンテキストウィンドウ:")
    print(f"      • セッション: {context['session_id']}")
    print(f"      • 直近メッセージ: {len(context['recent_messages'])}件")
    print(f"      • 保存嗜好: {len(context['user_preferences'])}項目")
    print(f"      • エピソード: {context['relevant_episodes']}件")

    return memory


def demo_identity():
    """Identity デモ"""
    print(f"\n\n{'=' * 70}")
    print("  ステップ 2.3: AgentCore Identity - セキュアなアクセス")
    print("=" * 70)

    identity = AgentCoreIdentity()

    # エージェントの登録
    print("\n  [1] エージェント ID の登録")
    print("  " + "-" * 50)

    travel_agent_id = identity.register_agent(
        agent_name="旅行プランニングエージェント",
        owner="tanaka@example.com",
        allowed_tools=["search_flights", "search_hotels", "get_weather", "calculate_budget"],
        max_budget=200000,
    )
    print(f"    ✓ 旅行エージェント登録: {travel_agent_id}")
    print(f"      許可ツール: search_flights, search_hotels, get_weather, calculate_budget")
    print(f"      予算上限: ¥200,000")

    booking_agent_id = identity.register_agent(
        agent_name="予約実行エージェント",
        owner="tanaka@example.com",
        allowed_tools=["search_flights", "search_hotels", "book_flight", "book_hotel"],
        max_budget=500000,
    )
    print(f"\n    ✓ 予約エージェント登録: {booking_agent_id}")
    print(f"      許可ツール: search_flights, search_hotels, book_flight, book_hotel")
    print(f"      予算上限: ¥500,000")

    # ポリシーの作成
    print("\n  [2] ポリシーの設定")
    print("  " + "-" * 50)

    policy_id = identity.create_policy(
        travel_agent_id,
        "旅行検索ポリシー",
        rules=[
            "検索系ツールのみ許可（予約は不可）",
            "1回のリクエストでの予算上限: ¥200,000",
            "営業時間内（9:00-21:00）のみ実行可能",
        ]
    )
    print(f"    ✓ ポリシー作成: {policy_id}")
    for rule in identity.policies[policy_id]["rules"]:
        print(f"      • {rule}")

    # ポリシーチェックのデモ
    print("\n  [3] ポリシーチェック（ツール呼び出し前の認可）")
    print("  " + "-" * 50)

    checks = [
        (travel_agent_id, "search_flights", None, "フライト検索"),
        (travel_agent_id, "search_hotels", None, "ホテル検索"),
        (travel_agent_id, "book_flight", None, "フライト予約（権限なし）"),
        (travel_agent_id, "search_flights", {"estimated_cost": 300000}, "高額フライト検索"),
        ("invalid-agent-id", "search_flights", None, "無効なエージェント"),
    ]

    for agent_id, tool, params, description in checks:
        result = identity.check_permission(agent_id, tool, params)
        status = "✓ 許可" if result["allowed"] else "✗ 拒否"
        print(f"    {status} | {description}")
        print(f"          理由: {result['reason']}")

    # 監査ログ
    print("\n  [4] 監査ログ")
    print("  " + "-" * 50)

    audit = identity.get_audit_log(travel_agent_id)
    print(f"    エージェント {travel_agent_id} のログ: {len(audit)}件")
    for log in audit:
        icon = "✓" if log["decision"] == "ALLOWED" else "✗"
        print(f"      {icon} [{log['decision']}] {log['tool']} - {log['reason']}")

    return identity


def demo_runtime():
    """Runtime デモ"""
    print(f"\n\n{'=' * 70}")
    print("  ステップ 2.4: AgentCore Runtime - サーバーレスデプロイ")
    print("=" * 70)

    runtime = AgentCoreRuntime()

    # エージェントのデプロイ
    print("\n  [1] エージェントのデプロイ")
    print("  " + "-" * 50)

    deployment = runtime.deploy_agent(
        agent_name="旅行プランニングエージェント",
        framework="strands-agents",
        config={
            "region": "us-east-1",
            "model_id": "amazon.nova-pro-v1:0",
            "memory_type": "dynamodb",
            "timeout_seconds": 300,
            "max_concurrent": 50,
        }
    )
    print(f"    ✓ デプロイ完了")
    print(f"      デプロイメントID: {deployment['deployment_id']}")
    print(f"      フレームワーク: {deployment['framework']}")
    print(f"      ステータス: {deployment['status']}")
    print(f"      エンドポイント: {deployment['endpoint']}")

    # 複数フレームワークのデプロイ
    print("\n  [2] フレームワーク非依存のデプロイ")
    print("  " + "-" * 50)

    frameworks = [
        ("分析エージェント", "langgraph", {"region": "us-east-1"}),
        ("チームエージェント", "crewai", {"region": "us-west-2"}),
    ]

    for name, fw, config in frameworks:
        dep = runtime.deploy_agent(name, fw, config)
        print(f"    ✓ {name} ({fw}) → {dep['status']}")

    # エージェントの呼び出し
    print("\n  [3] エージェントの呼び出しとオートスケーリング")
    print("  " + "-" * 50)

    requests = [
        "東京から沖縄の旅行プランを作成",
        "大阪から北海道の週末旅行",
        "名古屋から福岡の出張手配",
    ]

    for req in requests:
        result = runtime.invoke_agent(deployment['deployment_id'], {"message": req})
        print(f"    呼び出し: 「{req}」")
        print(f"      → {result['status']} ({result['duration_ms']:.0f}ms)")

    # メトリクス
    print("\n  [4] ランタイムメトリクス")
    print("  " + "-" * 50)

    metrics = runtime.get_metrics()
    print(f"    デプロイ数: {metrics['deployments']} (アクティブ: {metrics['active_deployments']})")
    print(f"    総呼び出し数: {metrics['total_invocations']}")
    print(f"    成功率: {metrics['success_count']}/{metrics['total_invocations']} ({metrics['success_count']/max(1,metrics['total_invocations'])*100:.0f}%)")
    print(f"    平均応答時間: {metrics['avg_duration_ms']:.0f}ms")

    # スケーリング情報
    print("\n  [5] オートスケーリング設定")
    print("  " + "-" * 50)

    scale = runtime.scale_info(deployment['deployment_id'])
    print(f"    最小インスタンス: {scale['min_instances']} (0からスケール)")
    print(f"    最大インスタンス: {scale['max_instances']}")
    print(f"    スケーリングポリシー: {scale['scaling_policy']}")
    print(f"    コールドスタート: {scale['cold_start_ms']}")

    return runtime


def demo_integration():
    """全コンポーネントの統合デモ"""
    print(f"\n\n{'=' * 70}")
    print("  統合デモ: AgentCore コンポーネントの連携")
    print("=" * 70)

    print("""
  エージェント呼び出しの全体フロー:

  ┌─────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐
  │  User   │────▶│ Runtime  │────▶│ Identity │────▶│ Gateway │
  │ Request │     │ (実行)   │     │ (認証)   │     │(ツール) │
  └─────────┘     └──────────┘     └──────────┘     └─────────┘
                       │                                   │
                       ▼                                   ▼
                  ┌──────────┐                       ┌──────────┐
                  │  Memory  │                       │  Tools   │
                  │(コンテキスト)│                    │(Lambda等)│
                  └──────────┘                       └──────────┘

  1. ユーザーがリクエストを送信
  2. Runtime がリクエストを受信し、エージェントインスタンスを起動
  3. Memory から過去のコンテキストを取得
  4. エージェントがツール呼び出しを決定
  5. Identity がポリシーチェック（認可）
  6. Gateway が適切なツールにルーティング
  7. 結果を統合してユーザーに応答
  8. Memory に今回の対話を保存
""")

    # シミュレーション
    print("  実行シミュレーション:")
    print("  " + "-" * 50)

    steps = [
        ("Runtime", "リクエスト受信 → エージェント起動"),
        ("Memory", "ユーザー嗜好を取得: ANA優先、リゾートホテル希望"),
        ("Agent", "search_flights ツールの呼び出しを決定"),
        ("Identity", "ポリシーチェック → 許可"),
        ("Gateway", "search_flights → Lambda にルーティング"),
        ("Agent", "search_hotels ツールの呼び出しを決定"),
        ("Identity", "ポリシーチェック → 許可"),
        ("Gateway", "search_hotels → Lambda にルーティング"),
        ("Agent", "結果を統合して旅行プランを生成"),
        ("Memory", "今回のセッションを保存"),
        ("Runtime", "レスポンスをユーザーに返却"),
    ]

    for i, (component, action) in enumerate(steps, 1):
        time.sleep(0.1)
        print(f"    {i:2d}. [{component:8s}] {action}")

    print(f"\n  ✓ 全コンポーネントが連携してリクエストを処理しました")


# ======================================================================
# メイン実行
# ======================================================================

if __name__ == "__main__":
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  Amazon Bedrock AgentCore - 各コンポーネントデモ                    ║")
    print("║  パート 2: Gateway / Memory / Identity / Runtime                    ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    demo_gateway()
    demo_memory()
    demo_identity()
    demo_runtime()
    demo_integration()

    print(f"\n\n{'=' * 70}")
    print("  まとめ: AgentCore が解決する課題")
    print("=" * 70)
    print("""
  ┌────────────────┬──────────────────────────────────────────────────┐
  │ コンポーネント │ 解決する課題                                     │
  ├────────────────┼──────────────────────────────────────────────────┤
  │ Gateway        │ ツールの発見・選択・ルーティングの統一管理       │
  │ Memory         │ 会話コンテキストの永続化と効率的な検索           │
  │ Identity       │ エージェントの認証・認可とポリシー管理           │
  │ Runtime        │ サーバーレス実行、スケーリング、可用性           │
  │ Observability  │ トレーシング、メトリクス、品質評価               │
  └────────────────┴──────────────────────────────────────────────────┘

  → 次のパート 3 で、プロトタイプから本番への移行課題を詳しく見ていきます。
""")
