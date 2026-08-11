"""
モジュール 5: エージェンティック AI - 旅行プランニングエージェント
- Strands Agents パターンでのエージェント構築
- ツール定義と自律的呼び出し
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
        flights = [f for f in flights if f["price"] <= max_budget]
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
        hotels = [h for h in hotels if h["price_per_night"] <= max_budget_per_night]
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
    flight_cost = flights * 2  # 往復
    hotel_cost = hotel_per_night * nights
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


# ======================================================================
# エージェント実装
# ======================================================================

TOOLS_SCHEMA = [
    {
        "name": "search_flights",
        "description": "フライトを検索します。出発地、目的地、日付を指定して利用可能なフライトを返します。",
        "parameters": {
            "origin": "出発空港（例: 東京）",
            "destination": "到着空港（例: 沖縄）",
            "date": "搭乗日（例: 2025-02-15）",
            "max_budget": "予算上限（オプション）"
        }
    },
    {
        "name": "search_hotels",
        "description": "ホテルを検索します。都市、日付、予算を指定して利用可能なホテルを返します。",
        "parameters": {
            "city": "都市名",
            "checkin": "チェックイン日",
            "checkout": "チェックアウト日",
            "max_budget_per_night": "1泊あたりの予算上限（オプション）"
        }
    },
    {
        "name": "get_weather",
        "description": "指定した都市と日付の天気予報を取得します。",
        "parameters": {
            "city": "都市名",
            "date": "日付"
        }
    },
    {
        "name": "calculate_budget",
        "description": "旅行の総予算を計算します。",
        "parameters": {
            "flights": "片道フライト料金",
            "hotel_per_night": "1泊あたりのホテル料金",
            "nights": "宿泊数",
            "activities": "アクティビティ費用"
        }
    }
]


class TravelPlanningAgent:
    """旅行プランニングエージェント"""

    def __init__(self):
        self.memory = []  # 会話履歴
        self.tool_calls = []  # ツール呼び出し履歴
        self.system_prompt = """あなたは経験豊富な旅行プランニングアシスタントです。

あなたの役割:
- ユーザーの旅行要件を理解する
- 利用可能なツールを使って情報を収集する
- 予算内で最適な旅行プランを提案する

利用可能なツール:
- search_flights: フライト検索
- search_hotels: ホテル検索
- get_weather: 天気予報
- calculate_budget: 予算計算

行動指針:
1. ユーザーの要件を確認する（目的地、日程、予算、人数）
2. フライトを検索する
3. ホテルを検索する
4. 天気を確認する
5. 予算を計算する
6. 最適なプランを提案する

回答形式:
- まず収集した情報を整理する
- 予算内の最適プランを提案する
- 代替案も提示する"""

    def plan_trip(self, user_request):
        """旅行プランの自律的な作成"""
        print(f"\n  ユーザー: {user_request}")
        print(f"\n  {'─' * 60}")
        print("  エージェント思考過程:")
        print(f"  {'─' * 60}")

        # 要件の解析（簡易版 - 本番ではLLMで解析）
        params = self._parse_request(user_request)

        # ツール呼び出し（自律的な実行）
        print(f"\n  [ステップ1] フライト検索...")
        flights = search_flights(
            params["origin"], params["destination"], params["date"],
            max_budget=params.get("flight_budget")
        )
        self.tool_calls.append(flights)
        print(f"    → {len(flights['results'])} 件のフライトが見つかりました")
        for f in flights['results'][:3]:
            print(f"      • {f['airline']} {f['departure']}発 ¥{f['price']:,} ({f['class']})")

        print(f"\n  [ステップ2] ホテル検索...")
        hotels = search_hotels(
            params["destination"],
            params["date"],
            params.get("checkout", params["date"]),
            max_budget_per_night=params.get("hotel_budget")
        )
        self.tool_calls.append(hotels)
        print(f"    → {len(hotels['results'])} 件のホテルが見つかりました")
        for h in hotels['results'][:3]:
            print(f"      • {h['name']} ¥{h['price_per_night']:,}/泊 (★{h['rating']})")

        print(f"\n  [ステップ3] 天気確認...")
        weather = get_weather(params["destination"], params["date"])
        self.tool_calls.append(weather)
        w = weather['results']
        print(f"    → {w['condition']} ({w['low_temp']}~{w['high_temp']}℃, 降水確率{w['rain_probability']}%)")

        print(f"\n  [ステップ4] 予算計算...")
        if flights['results'] and hotels['results']:
            best_flight = flights['results'][0]
            best_hotel = hotels['results'][0]
            budget = calculate_budget(
                best_flight['price'],
                best_hotel['price_per_night'],
                params.get("nights", 2),
                activities=10000
            )
            self.tool_calls.append(budget)
            b = budget['results']
            print(f"    → 総額: ¥{b['total']:,}")
            print(f"      (フライト往復: ¥{b['flight_round_trip']:,} + ホテル: ¥{b['hotel_total']:,} + アクティビティ: ¥{b['activities']:,})")

        # 最終プラン生成
        print(f"\n  {'─' * 60}")
        print("  最終提案:")
        print(f"  {'─' * 60}")

        self._generate_proposal(params, flights, hotels, weather, budget)

        # メモリに保存
        self.memory.append({
            "request": user_request,
            "params": params,
            "tool_calls": len(self.tool_calls),
            "timestamp": datetime.now().isoformat()
        })

    def _parse_request(self, request):
        """リクエストの解析（シンプル版）"""
        # 本番ではLLMで解析
        params = {
            "origin": "東京",
            "destination": "沖縄",
            "date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "nights": 2,
            "budget": 100000,
            "flight_budget": 40000,
            "hotel_budget": 25000,
        }
        params["checkout"] = (
            datetime.strptime(params["date"], "%Y-%m-%d") + timedelta(days=params["nights"])
        ).strftime("%Y-%m-%d")
        return params

    def _generate_proposal(self, params, flights, hotels, weather, budget):
        """提案の生成"""
        try:
            context = f"""
以下の情報を基に、旅行プランを提案してください:

目的地: {params['destination']}
日程: {params['date']} から {params['nights']}泊
予算: ¥{params['budget']:,}

フライト候補: {json.dumps(flights['results'][:3], ensure_ascii=False)}
ホテル候補: {json.dumps(hotels['results'][:3], ensure_ascii=False)}
天気: {json.dumps(weather['results'], ensure_ascii=False)}
予算計算: {json.dumps(budget['results'], ensure_ascii=False)}

予算内で最適なプランを提案してください。"""

            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": context}]}],
                inferenceConfig={"temperature": 0.3, "maxTokens": 800}
            )
            proposal = response['output']['message']['content'][0]['text']
            print(f"\n{proposal}")
        except Exception as e:
            print(f"\n  プラン概要:")
            print(f"  • フライト: {flights['results'][0]['airline']} ¥{flights['results'][0]['price']:,}")
            print(f"  • ホテル: {hotels['results'][0]['name']} ¥{hotels['results'][0]['price_per_night']:,}/泊")
            print(f"  • 天気: {weather['results']['condition']}")
            print(f"  • 総額: ¥{budget['results']['total']:,}")


def demo_agent():
    """エージェントのデモ実行"""
    print("=" * 70)
    print("  旅行プランニングエージェント（Strands Agents パターン）")
    print("=" * 70)

    agent = TravelPlanningAgent()
    agent.plan_trip("来月東京から沖縄に2泊3日で旅行したいです。予算は10万円以内で。")

    # AgentCore の説明
    print(f"\n\n{'=' * 70}")
    print("  Amazon Bedrock AgentCore のコンポーネント")
    print(f"{'=' * 70}")
    print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │ AgentCore Gateway                                                │
  │  • ツールの自動検出とインデックス作成                            │
  │  • セマンティック検索で最適なツールを選択                        │
  │  • MCP サーバー、Lambda、API を統一的に管理                     │
  └─────────────────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────────────────┐
  │ AgentCore Memory                                                 │
  │  • 短期記憶: 現在のセッション                                   │
  │  • 長期記憶: ユーザー嗜好、過去の対話                          │
  │  • セマンティック記憶: 知識の構造化                             │
  └─────────────────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────────────────┐
  │ AgentCore Runtime                                                │
  │  • サーバーレスでエージェントを実行                              │
  │  • オートスケーリング                                           │
  │  • 長時間実行ワークフローのサポート                             │
  └─────────────────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────────────────┐
  │ AgentCore Identity & Policy                                      │
  │  • エージェントに固有のIDを付与                                 │
  │  • ツール呼び出し前にポリシーチェック                           │
  │  • 委任されたアクセス制御（ユーザーの権限をエージェントに委任） │
  └─────────────────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────────────────┐
  │ AgentCore Observability & Evaluations                             │
  │  • エージェントの全行動をトレース                               │
  │  • 13種類のビルトインエバリュエーターで品質評価                 │
  │  • ライブインタラクションのサンプリングとスコア付け             │
  └─────────────────────────────────────────────────────────────────┘

  プロトタイプ→本番の移行:
  1. ローカルで Strands Agents を使って開発・テスト
  2. AgentCore Runtime にデプロイ（フレームワーク非依存）
  3. Gateway でツールを登録・管理
  4. Identity/Policy でセキュリティを設定
  5. Observability で本番モニタリング
""")


if __name__ == "__main__":
    demo_agent()
