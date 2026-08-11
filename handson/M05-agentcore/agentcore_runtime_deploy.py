"""
パート 2 ステップ 2.4: AgentCore Runtime デプロイ

bedrock-agentcore-starter-toolkit を使って Strands Agents で作った
エージェントを AgentCore Runtime にデプロイする。

前提:
  pip install bedrock-agentcore strands-agents strands-agents-tools
  pip install bedrock-agentcore-starter-toolkit
  AWS 認証情報が設定済み（us-east-1）
  Docker が起動中（コンテナビルドに必要）

実行:
  python3.12 agentcore_runtime_deploy.py

呼び出しテスト:
  python3.12 agentcore_runtime_deploy.py --invoke "沖縄旅行のプランを作って"

クリーンアップ:
  python3.12 agentcore_runtime_deploy.py --cleanup
"""

import sys
import os
import boto3

# ======================================================================
# エージェント定義ファイルの生成
# ======================================================================

AGENT_CODE = '''"""AgentCore Runtime にデプロイする旅行エージェント
- Gateway 経由でツールを呼び出し（MCPClient）
- Memory でセッション管理（AgentCoreMemorySessionManager）
"""
import os
import uuid
import logging
import boto3

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client

app = BedrockAgentCoreApp(debug=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "us-east-1")

# Gateway URL と Memory ID は環境変数から取得
GATEWAY_URL = os.environ.get("AGENTCORE_GATEWAY_URL", "")
MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID", "")

model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",
    region_name=REGION,
)


@app.entrypoint
def invoke(payload):
    """エージェントのエントリーポイント"""
    user_input = payload.get("prompt", "こんにちは")
    actor_id = payload.get("actor_id", "default-user")
    session_id = payload.get("session_id", str(uuid.uuid4()))

    logger.info(f"User: {user_input}, Actor: {actor_id}, Session: {session_id}")

    # --- Memory 統合 ---
    session_manager = None
    if MEMORY_ID:
        memory_config = AgentCoreMemoryConfig(
            memory_id=MEMORY_ID,
            session_id=session_id,
            actor_id=actor_id,
        )
        session_manager = AgentCoreMemorySessionManager(
            agentcore_memory_config=memory_config
        )
        logger.info(f"Memory connected: {MEMORY_ID}")

    # --- Gateway 統合 (MCPClient でツールを取得) ---
    if GATEWAY_URL:
        logger.info(f"Connecting to Gateway: {GATEWAY_URL}")
        mcp_client = MCPClient(
            lambda: streamablehttp_client(GATEWAY_URL)
        )
        with mcp_client:
            tools = mcp_client.list_tools_sync()
            logger.info(f"Gateway tools: {[t.tool_name for t in tools]}")

            agent = Agent(
                model=model,
                tools=tools,
                session_manager=session_manager,
                system_prompt="""あなたは旅行プランニングアシスタントです。
ユーザーの要件に基づき、利用可能なツールを使って情報を収集し、
最適な旅行プランを提案してください。""",
            )
            response = agent(user_input)
    else:
        # Gateway 未設定の場合はローカルツールを使用
        from strands import tool

        @tool
        def search_flights(origin: str, destination: str, date: str) -> str:
            """フライトを検索します。"""
            return str([
                {"airline": "ANA", "departure": "08:00", "price": 35000},
                {"airline": "JAL", "departure": "10:30", "price": 38000},
            ])

        @tool
        def search_hotels(city: str, checkin: str, checkout: str) -> str:
            """ホテルを検索します。"""
            return str([
                {"name": "オーシャンビューリゾート", "price": 25000, "rating": 4.5},
            ])

        @tool
        def get_weather(city: str, date: str) -> str:
            """天気予報を取得します。"""
            return "天気: 晴れ, 最高28℃, 最低22℃"

        agent = Agent(
            model=model,
            tools=[search_flights, search_hotels, get_weather],
            session_manager=session_manager,
            system_prompt="""あなたは旅行プランニングアシスタントです。
ユーザーの要件に基づき、フライト検索、ホテル検索、天気確認を
自律的に実行し、最適な旅行プランを提案してください。""",
        )
        response = agent(user_input)

    result = response.message["content"][0]["text"]
    logger.info(f"Agent result: {result[:100]}")
    return result


if __name__ == "__main__":
    app.run()
'''

REQUIREMENTS = """bedrock-agentcore
strands-agents
strands-agents-tools
mcp
boto3
"""


# ======================================================================
# デプロイ処理
# ======================================================================

AGENT_NAME = "handson-travel-agent"
AGENT_FILE = "runtime_agent.py"
REQUIREMENTS_FILE = "runtime_requirements.txt"


def setup_files():
    """エージェントファイルと requirements を生成"""
    print("\n  [1] エージェントファイルの準備")
    print("  " + "-" * 55)

    with open(AGENT_FILE, "w") as f:
        f.write(AGENT_CODE)
    print(f"    ✓ {AGENT_FILE} を生成")

    with open(REQUIREMENTS_FILE, "w") as f:
        f.write(REQUIREMENTS)
    print(f"    ✓ {REQUIREMENTS_FILE} を生成")

    print(f"\n    エージェント構成:")
    print(f"      モデル: us.amazon.nova-pro-v1:0")
    print(f"      Gateway: 環境変数 AGENTCORE_GATEWAY_URL で指定")
    print(f"      Memory:  環境変数 AGENTCORE_MEMORY_ID で指定")
    print(f"      フレームワーク: Strands Agents + MCPClient")


def get_gateway_url():
    """既存 Gateway の URL を取得"""
    try:
        ctrl = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
        gateways = ctrl.list_gateways()
        for gw in gateways.get("items", []):
            if gw.get("name") == "handson-travel-gateway":
                detail = ctrl.get_gateway(gatewayIdentifier=gw["gatewayId"])
                return detail.get("gatewayUrl", "")
    except Exception:
        pass
    return ""


def get_memory_id():
    """既存 Memory の ID を取得"""
    try:
        ctrl = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
        memories = ctrl.list_memories()
        for mem in memories.get("memories", []):
            if mem.get("name") == "handson_travel_agent_memory":
                return mem["id"]
    except Exception:
        pass
    return ""


def deploy():
    """starter-toolkit で AgentCore Runtime にデプロイ"""
    print("\n  [2] AgentCore Runtime へのデプロイ")
    print("  " + "-" * 55)

    from bedrock_agentcore_starter_toolkit import Runtime
    from boto3.session import Session

    boto_session = Session()
    region = boto_session.region_name or "us-east-1"

    # 前ステップで作成した Gateway / Memory を検出
    gateway_url = get_gateway_url()
    memory_id = get_memory_id()

    if gateway_url:
        print(f"    Gateway URL: {gateway_url}")
    else:
        print(f"    ⚠ Gateway 未検出 → ローカルツールで動作します")

    if memory_id:
        print(f"    Memory ID:   {memory_id}")
    else:
        print(f"    ⚠ Memory 未検出 → メモリなしで動作します")

    runtime = Runtime()

    # Step 1: Configure
    print(f"\n    Configure...")
    env_vars = {}
    if gateway_url:
        env_vars["AGENTCORE_GATEWAY_URL"] = gateway_url
    if memory_id:
        env_vars["AGENTCORE_MEMORY_ID"] = memory_id

    config_kwargs = dict(
        entrypoint=AGENT_FILE,
        auto_create_execution_role=True,
        auto_create_ecr=True,
        requirements_file=REQUIREMENTS_FILE,
        region=region,
        agent_name=AGENT_NAME,
    )
    if env_vars:
        config_kwargs["environment_variables"] = env_vars

    config_response = runtime.configure(**config_kwargs)
    print(f"    ✓ 設定完了")
    print(f"      {config_response}")

    # Step 2: Launch (ビルド＆デプロイ)
    print(f"\n    Launch (ビルド & デプロイ)...")
    print(f"    ※ Docker イメージのビルドとプッシュが行われます")
    print(f"    ※ 数分かかります...")
    launch_result = runtime.launch()
    print(f"    ✓ デプロイ完了!")
    print(f"      Agent ARN: {launch_result.get('agent_arn', 'N/A')}")

    return runtime


def invoke_agent(prompt):
    """デプロイ済みエージェントを呼び出す"""
    print("\n  [3] エージェントの呼び出し")
    print("  " + "-" * 55)

    from bedrock_agentcore_starter_toolkit import Runtime
    import uuid

    runtime = Runtime()
    print(f"    プロンプト: {prompt}")
    print(f"    呼び出し中...")

    response = runtime.invoke({
        "prompt": prompt,
        "actor_id": "demo-user-001",
        "session_id": str(uuid.uuid4())[:8],
    })
    print(f"\n    エージェント応答:")
    print(f"    {response}")

    return response


def cleanup_files():
    """生成したファイルを削除"""
    for f in [AGENT_FILE, REQUIREMENTS_FILE]:
        if os.path.exists(f):
            os.remove(f)
            print(f"    ✓ {f} 削除")


# ======================================================================
# メイン
# ======================================================================

def main():
    print("\n")
    print("=" * 65)
    print("  AgentCore Runtime デプロイ - starter-toolkit")
    print("=" * 65)

    if "--cleanup" in sys.argv:
        print("\n  [クリーンアップ]")
        print("  " + "-" * 55)
        print("    Runtime のエージェント削除は AWS コンソールまたは CLI で行います:")
        print(f"    aws bedrock-agentcore-control delete-agent --agent-name {AGENT_NAME}")
        cleanup_files()
        return

    if "--invoke" in sys.argv:
        idx = sys.argv.index("--invoke")
        prompt = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "沖縄旅行のプランを作って"
        invoke_agent(prompt)
        return

    # 1. ファイル準備
    setup_files()

    # 2. デプロイ
    try:
        deploy()
    except ImportError:
        print(f"\n    ⚠ bedrock-agentcore-starter-toolkit が未インストールです")
        print(f"    以下を実行してください:")
        print(f"      pip install bedrock-agentcore-starter-toolkit")
        print(f"\n    手動デプロイ手順:")
        print(f"      1. pip install bedrock-agentcore strands-agents")
        print(f"      2. pip install bedrock-agentcore-starter-toolkit")
        print(f"      3. python3.12 agentcore_runtime_deploy.py")
    except Exception as e:
        print(f"\n    ⚠ デプロイエラー: {e}")
        print(f"    Docker が起動中か確認してください。")

    print(f"""
  {'=' * 65}
  まとめ
  {'=' * 65}

  Runtime デプロイの 3 ステップ:
  1. configure() - エントリーポイント、IAMロール、ECR、環境変数を設定
  2. launch()    - Docker ビルド → ECR プッシュ → Runtime デプロイ
  3. invoke()    - デプロイ済みエージェントを呼び出し

  統合コンポーネント:
  • Gateway: MCPClient で Gateway 経由のツール呼び出し
  • Memory:  AgentCoreMemorySessionManager でセッション管理

  Runtime の機能:
  • サーバーレス実行（0→N オートスケーリング）
  • フレームワーク非依存（Strands / LangGraph / CrewAI）
  • 長時間実行ワークフローのサポート
  • ヘルスチェック（/ping エンドポイント）

  デプロイ後の呼び出し:
    python3.12 agentcore_runtime_deploy.py --invoke "東京から沖縄の旅行プラン"

  クリーンアップ:
    python3.12 agentcore_runtime_deploy.py --cleanup
""")


if __name__ == "__main__":
    main()
