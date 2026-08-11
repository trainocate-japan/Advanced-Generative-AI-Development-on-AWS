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

# ======================================================================
# エージェント定義ファイルの生成
# ======================================================================

AGENT_CODE = '''"""AgentCore Runtime にデプロイする旅行エージェント"""
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool
from strands.models import BedrockModel
import logging

app = BedrockAgentCoreApp(debug=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """フライトを検索します。出発地、目的地、日付を指定。

    Args:
        origin: 出発地（例: 東京）
        destination: 目的地（例: 沖縄）
        date: 搭乗日（例: 2025-03-15）
    """
    flights = [
        {"airline": "ANA", "departure": "08:00", "price": 35000},
        {"airline": "JAL", "departure": "10:30", "price": 38000},
        {"airline": "Peach", "departure": "06:30", "price": 15000},
    ]
    return str(flights)


@tool
def search_hotels(city: str, checkin: str, checkout: str) -> str:
    """ホテルを検索します。都市、チェックイン日、チェックアウト日を指定。

    Args:
        city: 都市名（例: 沖縄）
        checkin: チェックイン日
        checkout: チェックアウト日
    """
    hotels = [
        {"name": "オーシャンビューリゾート", "price": 25000, "rating": 4.5},
        {"name": "シティホテル那覇", "price": 12000, "rating": 4.0},
    ]
    return str(hotels)


@tool
def get_weather(city: str, date: str) -> str:
    """天気予報を取得します。都市と日付を指定。

    Args:
        city: 都市名
        date: 日付
    """
    return "天気: 晴れ, 最高28℃, 最低22℃, 降水確率10%"


model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",
    region_name="us-east-1",
)

agent = Agent(
    model=model,
    tools=[search_flights, search_hotels, get_weather],
    system_prompt="""あなたは旅行プランニングアシスタントです。
ユーザーの要件に基づき、フライト検索、ホテル検索、天気確認を
自律的に実行し、最適な旅行プランを提案してください。""",
)


@app.entrypoint
def invoke(payload):
    """エージェントのエントリーポイント"""
    user_input = payload.get("prompt", "こんにちは")
    logger.info(f"User input: {user_input}")
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
    print(f"      ツール: search_flights, search_hotels, get_weather")
    print(f"      フレームワーク: Strands Agents")


def deploy():
    """starter-toolkit で AgentCore Runtime にデプロイ"""
    print("\n  [2] AgentCore Runtime へのデプロイ")
    print("  " + "-" * 55)

    from bedrock_agentcore_starter_toolkit import Runtime
    from boto3.session import Session

    boto_session = Session()
    region = boto_session.region_name or "us-east-1"

    runtime = Runtime()

    # Step 1: Configure
    print(f"\n    Configure...")
    config_response = runtime.configure(
        entrypoint=AGENT_FILE,
        auto_create_execution_role=True,
        auto_create_ecr=True,
        requirements_file=REQUIREMENTS_FILE,
        region=region,
        agent_name=AGENT_NAME,
    )
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

    runtime = Runtime()
    print(f"    プロンプト: {prompt}")
    print(f"    呼び出し中...")

    response = runtime.invoke({"prompt": prompt})
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
  1. configure() - エントリーポイント、IAMロール、ECR を設定
  2. launch()    - Docker ビルド → ECR プッシュ → Runtime デプロイ
  3. invoke()    - デプロイ済みエージェントを呼び出し

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
