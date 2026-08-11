"""
パート 4: フレームワーク比較 - Strands Agents
- AWS ネイティブのエージェントフレームワーク
- シンプルな API でエージェントを構築
- Amazon Bedrock との統合が容易

インストール:
  pip install strands-agents strands-agents-tools boto3
"""

from strands import Agent, tool
from strands.models.bedrock import BedrockModel


# ======================================================================
# ツール定義（@tool デコレータでシンプルに定義）
# ======================================================================

@tool
def search_flights(origin: str, destination: str, date: str) -> dict:
    """指定された出発地・目的地・日付でフライトを検索します。

    Args:
        origin: 出発地（例: 東京）
        destination: 目的地（例: 沖縄）
        date: 搭乗日（例: 2025-03-15）
    """
    # 本番では実際の航空会社 API を呼び出す
    return {
        "flights": [
            {"airline": "ANA", "departure": "08:00", "price": 35000},
            {"airline": "JAL", "departure": "10:30", "price": 38000},
            {"airline": "Peach", "departure": "06:30", "price": 15000},
        ]
    }


@tool
def search_hotels(city: str, checkin: str, checkout: str) -> dict:
    """指定された都市・日付でホテルを検索します。

    Args:
        city: 都市名（例: 沖縄）
        checkin: チェックイン日
        checkout: チェックアウト日
    """
    return {
        "hotels": [
            {"name": "オーシャンビューリゾート", "price": 25000, "rating": 4.5},
            {"name": "シティホテル那覇", "price": 12000, "rating": 4.0},
        ]
    }


@tool
def get_weather(city: str, date: str) -> dict:
    """指定された都市・日付の天気予報を取得します。

    Args:
        city: 都市名
        date: 日付
    """
    return {"condition": "晴れ", "high": 28, "low": 22, "rain_prob": 10}


# ======================================================================
# エージェント構築（Strands Agents のシンプルさ）
# ======================================================================

def main():
    print("=" * 70)
    print("  フレームワーク比較: Strands Agents")
    print("  特徴: AWS ネイティブ、シンプル、Bedrock 統合")
    print("=" * 70)

    # モデルの設定
    model = BedrockModel(
        model_id="amazon.nova-pro-v1:0",
        region_name="us-east-1",
    )

    # エージェントの作成（たった数行で完成）
    agent = Agent(
        model=model,
        tools=[search_flights, search_hotels, get_weather],
        system_prompt="""あなたは旅行プランニングアシスタントです。
ユーザーの旅行要件を理解し、フライト検索、ホテル検索、天気確認を
自律的に実行して最適な旅行プランを提案してください。
予算内で最もコストパフォーマンスの良い組み合わせを推薦します。""",
    )

    # エージェントの実行
    print("\n  ユーザー: 来月東京から沖縄に2泊3日、予算10万円で旅行したい\n")
    print("-" * 70)

    response = agent("来月東京から沖縄に2泊3日で旅行したいです。予算は10万円以内で。")
    print(response)

    print("\n" + "-" * 70)
    print("""
  Strands Agents の特徴:
  ┌──────────────────────────────────────────────────────────────────┐
  │ • @tool デコレータでツールを定義（型ヒント + docstring で自動推論）│
  │ • Agent() に model と tools を渡すだけ                           │
  │ • agent("メッセージ") で対話（ツール呼び出しは自動）             │
  │ • Amazon Bedrock とネイティブ統合                                 │
  │ • AgentCore Runtime にそのままデプロイ可能                        │
  └──────────────────────────────────────────────────────────────────┘

  最適なユースケース:
  • AWS 環境での標準的なエージェント構築
  • シンプルなツール呼び出しパターン
  • プロトタイプから本番へ素早く移行したい場合
""")


if __name__ == "__main__":
    main()
