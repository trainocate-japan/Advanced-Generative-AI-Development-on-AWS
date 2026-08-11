"""
モジュール 5: エージェンティック AI - 旅行プランニングエージェント
- Bedrock Converse API の toolUse によるツール自律選択
- モデルが自ら必要なツールを判断し呼び出すエージェントループ
- メモリ管理とコンテキスト保持
"""

import boto3
import json
import time
from datetime import datetime, timedelta
import random

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "amazon.nova-pro-v1:0"


# ======================================================================
# ツール定義（シミュレーション）
# ======================================================================

def search_flights(origin, destination, date, max_budget=None):
    """フライト検索ツール（シミュレーション）"""
    flights = [
        {"airline": "ANA", "departure": "08:00", "arrival": "10:30", "price": 35000, "class": "普通席"},
        {"airline": "JAL", "departure": "10:30", "arrival": "13:00", "price": 38000, "class": "普通席"},
        {"airline": "Peach", "departure": "06:30", "arrival": "09:15", "price": 15000, "class": "LCC"},
        {"airline": "ANA", "departure": "14:00", "arrival": "16:30", "price": 55000, "class": "プレミアムクラス"},
    ]
    if max_budget:
        flights = [f for f in flights if f["price"] <= int(max_budget)]
    return {
        "tool": "search_flights",
        "params": {"origin": origin, "destination": destination, "date": date},
        "results": flights
    }


def search_hotels(city, checkin, checkout, max_budget_per_night=None):
    """ホテル検索ツール（シミュレーション）"""
    hotels = [
        {"name": "オーシャンビューリゾート", "price_per_night": 25000, "rating": 4.5, "type": "リゾート"},
        {"name": "シティホテル那覇", "price_per_night": 12000, "rating": 4.0, "type": "ビジネス"},
        {"name": "ビーチフロント ヴィラ", "price_per_night": 45000, "rating": 4.8, "type": "高級"},
        {"name": "ゲストハウス美ら海", "price_per_night": 5000, "rating": 3.8, "type": "ゲストハウス"},
    ]
    if max_budget_per_night:
        hotels = [h for h in hotels if h["price_per_night"] <= int(max_budget_per_night)]
    return {
        "tool": "search_hotels",
        "params": {"city": city, "checkin": checkin, "checkout": checkout},
        "results": hotels
    }


def get_weather(city, date):
    """天気予報ツール（シミュレーション）"""
    weathers = ["晴れ", "曇り", "晴れ時々曇り", "曇り時々雨"]
    return {
        "tool": "get_weather",
        "params": {"city": city, "date": date},
        "results": {
            "condition": random.choice(weathers),
            "high_temp": random.randint(25, 32),
            "low_temp": random.randint(20, 25),
            "rain_probability": random.randint(0, 40)
        }
    }


def calculate_budget(flights, hotel_per_night, nights, activities=0):
    """予算計算ツール"""
    flight_cost = int(flights) * 2  # 往復
    hotel_cost = int(hotel_per_night) * int(nights)
    activities = int(activities)
    total = flight_cost + hotel_cost + activities
    return {
        "tool": "calculate_budget",
        "results": {
            "flight_round_trip": flight_cost,
            "hotel_total": hotel_cost,
            "activities": activities,
            "total": total
        }
    }


# ツール名から関数へのマッピング
TOOL_FUNCTIONS = {
    "search_flights": search_flights,
    "search_hotels": search_hotels,
    "get_weather": get_weather,
    "calculate_budget": calculate_budget,
}


# ======================================================================
# ツールスキーマ（Converse API の toolConfig 形式）
# ======================================================================

TOOLS_SCHEMA = [
    {
        "name": "search_flights",
        "description": "フライトを検索します。出発地、目的地、日付を指定して利用可能なフライトを返します。",
        "parameters": {
            "origin": {"type": "string", "description": "出発空港（例: 東京）"},
            "destination": {"type": "string", "description": "到着空港（例: 沖縄）"},
            "date": {"type": "string", "description": "搭乗日（例: 2025-02-15）"},
            "max_budget": {"type": "string", "description": "予算上限（オプション）"},
        },
        "required": ["origin", "destination", "date"],
    },
    {
        "name": "search_hotels",
        "description": "ホテルを検索します。都市、日付、予算を指定して利用可能なホテルを返します。",
        "parameters": {
            "city": {"type": "string", "description": "都市名"},
            "checkin": {"type": "string", "description": "チェックイン日"},
            "checkout": {"type": "string", "description": "チェックアウト日"},
            "max_budget_per_night": {"type": "string", "description": "1泊あたりの予算上限（オプション）"},
        },
        "required": ["city", "checkin", "checkout"],
    },
    {
        "name": "get_weather",
        "description": "指定した都市と日付の天気予報を取得します。",
        "parameters": {
            "city": {"type": "string", "description": "都市名"},
            "date": {"type": "string", "description": "日付"},
        },
        "required": ["city", "date"],
    },
    {
        "name": "calculate_budget",
        "description": "旅行の総予算を計算します。フライト片道料金、ホテル1泊料金、宿泊数、アクティビティ費用を指定します。",
        "parameters": {
            "flights": {"type": "string", "description": "片道フライト料金（数値）"},
            "hotel_per_night": {"type": "string", "description": "1泊あたりのホテル料金（数値）"},
            "nights": {"type": "string", "description": "宿泊数（数値）"},
            "activities": {"type": "string", "description": "アクティビティ費用（数値、デフォルト0）"},
        },
        "required": ["flights", "hotel_per_night", "nights"],
    },
]


def build_tool_config():
    """TOOLS_SCHEMA から Converse API の toolConfig を構築"""
    tools = []
    for schema in TOOLS_SCHEMA:
        tool_spec = {
            "toolSpec": {
                "name": schema["name"],
                "description": schema["description"],
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": schema["parameters"],
                        "required": schema.get("required", []),
                    }
                },
            }
        }
        tools.append(tool_spec)
    return {"tools": tools}


# ======================================================================
# エージェント実装（Converse API + ツール自律選択ループ）
# ======================================================================

SYSTEM_PROMPT = """あなたは経験豊富な旅行プランニングアシスタントです。

あなたの役割:
- ユーザーの旅行要件を理解する
- 利用可能なツールを使って情報を収集する
- 予算内で最適な旅行プランを提案する

行動指針:
1. まずフライトを検索する
2. 次にホテルを検索する
3. 天気を確認する
4. 予算を計算する
5. 全情報を統合して最適なプランを提案する

回答形式:
- 予算内の最適プランを日本語で提案する
- フライト、ホテル、天気、予算の内訳を含める
- 代替案も提示する"""


class TravelPlanningAgent:
    """
    旅行プランニングエージェント

    Bedrock Converse API の toolUse 機能を使い、
    モデルが自律的にどのツールを呼ぶか判断するエージェントループを実装。
    """

    def __init__(self):
        self.messages = []
        self.tool_call_count = 0
        self.tool_config = build_tool_config()

    def run(self, user_request, max_iterations=10):
        """エージェントループの実行"""
        print(f"\n{'=' * 70}")
        print("  旅行プランニングエージェント（自律ツール選択）")
        print(f"{'=' * 70}")
        print(f"\n  ユーザー: {user_request}")
        print(f"\n  {'─' * 60}")
        print("  エージェント実行ログ:")
        print(f"  {'─' * 60}")

        # ユーザーメッセージをセット
        self.messages = [
            {"role": "user", "content": [{"text": user_request}]}
        ]

        # エージェントループ: モデルが end_turn を返すまで繰り返す
        for iteration in range(max_iterations):
            # Converse API 呼び出し
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=self.messages,
                system=[{"text": SYSTEM_PROMPT}],
                toolConfig=self.tool_config,
                inferenceConfig={"temperature": 0.3, "maxTokens": 2000},
            )

            stop_reason = response["stopReason"]
            assistant_message = response["output"]["message"]
            self.messages.append(assistant_message)

            # レスポンスの処理
            if stop_reason == "tool_use":
                # モデルがツール呼び出しを要求
                tool_results = self._handle_tool_use(assistant_message)
                # ツール結果をメッセージに追加して次のイテレーションへ
                self.messages.append({"role": "user", "content": tool_results})

            elif stop_reason == "end_turn":
                # モデルが最終回答を生成
                self._print_final_response(assistant_message)
                break

            else:
                print(f"\n  [予期しない停止理由: {stop_reason}]")
                break

        print(f"\n  {'─' * 60}")
        print(f"  ツール呼び出し回数: {self.tool_call_count}")
        print(f"  {'─' * 60}")

    def _handle_tool_use(self, assistant_message):
        """モデルが要求したツール呼び出しを実行"""
        tool_results = []

        for content_block in assistant_message["content"]:
            if "toolUse" in content_block:
                tool_use = content_block["toolUse"]
                tool_name = tool_use["name"]
                tool_input = tool_use["input"]
                tool_use_id = tool_use["toolUseId"]

                self.tool_call_count += 1
                print(f"\n  [ツール呼び出し #{self.tool_call_count}] {tool_name}")
                print(f"    パラメータ: {json.dumps(tool_input, ensure_ascii=False)}")

                # ツール関数を実行
                try:
                    func = TOOL_FUNCTIONS[tool_name]
                    result = func(**tool_input)
                    result_json = json.dumps(result, ensure_ascii=False)
                    print(f"    結果: {result_json[:100]}{'...' if len(result_json) > 100 else ''}")

                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"json": result}],
                        }
                    })
                except Exception as e:
                    print(f"    エラー: {e}")
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"text": f"エラー: {str(e)}"}],
                            "status": "error",
                        }
                    })

            elif "text" in content_block:
                # モデルの思考過程（ツール呼び出し前のテキスト）
                thought = content_block["text"]
                if thought.strip():
                    print(f"\n  [思考] {thought[:80]}{'...' if len(thought) > 80 else ''}")

        return tool_results

    def _print_final_response(self, assistant_message):
        """最終回答の表示"""
        print(f"\n  {'─' * 60}")
        print("  最終提案:")
        print(f"  {'─' * 60}")
        for content_block in assistant_message["content"]:
            if "text" in content_block:
                print(f"\n{content_block['text']}")


# ======================================================================
# メイン実行
# ======================================================================

def demo_agent():
    """エージェントのデモ実行"""
    agent = TravelPlanningAgent()
    agent.run("来月東京から沖縄に2泊3日で旅行したいです。予算は10万円以内で。")

    # AgentCore の説明
    print(f"\n\n{'=' * 70}")
    print("  Amazon Bedrock AgentCore のコンポーネント")
    print(f"{'=' * 70}")
    print("""
  上のデモでは、モデルが自律的にツールを選択・実行しました。
  これが「エージェンティック AI」の基本パターンです。

  ┌─────────────────────────────────────────────────────────────────┐
  │ エージェントループ（今回実装したもの）                           │
  │                                                                 │
  │  ユーザー入力 → モデル推論 → ツール選択 → ツール実行            │
  │                     ↑                         │                 │
  │                     └─────── 結果を返す ──────┘                 │
  │                                                                 │
  │  stopReason == "tool_use" → ループ継続                          │
  │  stopReason == "end_turn" → 最終回答を出力                      │
  └─────────────────────────────────────────────────────────────────┘

  AgentCore はこのパターンを本番で運用するためのコンポーネント群:

  • Gateway:  ツールの登録・検索・ルーティング
  • Memory:   会話コンテキストの永続化
  • Identity: エージェントの認証・認可
  • Runtime:  サーバーレス実行・オートスケーリング
  • Observability: トレーシング・品質評価
""")


if __name__ == "__main__":
    demo_agent()
