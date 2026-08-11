"""
パート 4: フレームワーク比較 - LangGraph
- グラフベースのステートフル・ワークフロー
- 条件分岐、ループ、Human-in-the-Loop に強い
- 複雑な対話フローの設計に最適

インストール:
  pip install langgraph langchain-aws langchain-core boto3
"""

from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


# ======================================================================
# ステート定義（グラフ全体で共有される状態）
# ======================================================================

class TravelState(TypedDict):
    """旅行プランニングの状態"""
    messages: list          # 会話履歴
    origin: str             # 出発地
    destination: str        # 目的地
    date: str               # 日付
    budget: int             # 予算
    flights: list           # フライト検索結果
    hotels: list            # ホテル検索結果
    weather: dict           # 天気情報
    plan: str               # 最終プラン
    needs_approval: bool    # 承認が必要か


# ======================================================================
# ノード定義（グラフの各処理ステップ）
# ======================================================================

def parse_request(state: TravelState) -> TravelState:
    """ユーザーリクエストの解析ノード"""
    # 本番では LLM で解析
    state["origin"] = "東京"
    state["destination"] = "沖縄"
    state["date"] = "2025-03-15"
    state["budget"] = 100000
    state["messages"].append(
        AIMessage(content="リクエストを解析しました: 東京→沖縄, 予算10万円")
    )
    return state


def search_flights_node(state: TravelState) -> TravelState:
    """フライト検索ノード"""
    state["flights"] = [
        {"airline": "ANA", "departure": "08:00", "price": 35000},
        {"airline": "JAL", "departure": "10:30", "price": 38000},
        {"airline": "Peach", "departure": "06:30", "price": 15000},
    ]
    state["messages"].append(
        AIMessage(content=f"フライト検索完了: {len(state['flights'])}件")
    )
    return state


def search_hotels_node(state: TravelState) -> TravelState:
    """ホテル検索ノード"""
    state["hotels"] = [
        {"name": "オーシャンビューリゾート", "price": 25000, "rating": 4.5},
        {"name": "シティホテル那覇", "price": 12000, "rating": 4.0},
    ]
    state["messages"].append(
        AIMessage(content=f"ホテル検索完了: {len(state['hotels'])}件")
    )
    return state


def check_weather_node(state: TravelState) -> TravelState:
    """天気確認ノード"""
    state["weather"] = {"condition": "晴れ", "high": 28, "low": 22}
    state["messages"].append(
        AIMessage(content=f"天気確認: {state['weather']['condition']}")
    )
    return state


def check_budget(state: TravelState) -> TravelState:
    """予算チェックノード"""
    if state["flights"] and state["hotels"]:
        cheapest_flight = min(state["flights"], key=lambda x: x["price"])
        cheapest_hotel = min(state["hotels"], key=lambda x: x["price"])
        total = cheapest_flight["price"] * 2 + cheapest_hotel["price"] * 2
        state["needs_approval"] = total > state["budget"]
        state["messages"].append(
            AIMessage(content=f"予算チェック: 最安合計 ¥{total:,} / 予算 ¥{state['budget']:,}")
        )
    return state


def generate_plan(state: TravelState) -> TravelState:
    """プラン生成ノード"""
    llm = ChatBedrockConverse(
        model="amazon.nova-pro-v1:0",
        region_name="us-east-1",
    )

    context = f"""
以下の情報で旅行プランを作成してください:
- 行き先: {state['origin']}→{state['destination']}
- フライト: {state['flights']}
- ホテル: {state['hotels']}
- 天気: {state['weather']}
- 予算: ¥{state['budget']:,}
"""
    response = llm.invoke([
        SystemMessage(content="あなたは旅行プランナーです。簡潔に提案してください。"),
        HumanMessage(content=context),
    ])
    state["plan"] = response.content
    state["messages"].append(AIMessage(content="プラン生成完了"))
    return state


def human_approval(state: TravelState) -> TravelState:
    """Human-in-the-Loop: 承認ノード"""
    state["messages"].append(
        AIMessage(content="[Human-in-the-Loop] 予算超過のため承認を求めています...")
    )
    # 本番では実際に人間の承認を待つ
    state["needs_approval"] = False
    return state


# ======================================================================
# 条件分岐（ルーティング関数）
# ======================================================================

def route_after_budget_check(state: TravelState) -> Literal["human_approval", "generate_plan"]:
    """予算チェック後のルーティング"""
    if state.get("needs_approval"):
        return "human_approval"
    return "generate_plan"


# ======================================================================
# グラフ構築（ノードとエッジの定義）
# ======================================================================

def build_travel_graph():
    """旅行プランニンググラフの構築"""
    graph = StateGraph(TravelState)

    # ノードの追加
    graph.add_node("parse_request", parse_request)
    graph.add_node("search_flights", search_flights_node)
    graph.add_node("search_hotels", search_hotels_node)
    graph.add_node("check_weather", check_weather_node)
    graph.add_node("check_budget", check_budget)
    graph.add_node("human_approval", human_approval)
    graph.add_node("generate_plan", generate_plan)

    # エッジの定義（フロー）
    graph.set_entry_point("parse_request")
    graph.add_edge("parse_request", "search_flights")
    graph.add_edge("search_flights", "search_hotels")
    graph.add_edge("search_hotels", "check_weather")
    graph.add_edge("check_weather", "check_budget")

    # 条件分岐: 予算超過なら承認フローへ
    graph.add_conditional_edges(
        "check_budget",
        route_after_budget_check,
        {"human_approval": "human_approval", "generate_plan": "generate_plan"},
    )
    graph.add_edge("human_approval", "generate_plan")
    graph.add_edge("generate_plan", END)

    return graph.compile()


# ======================================================================
# メイン実行
# ======================================================================

def main():
    print("=" * 70)
    print("  フレームワーク比較: LangGraph")
    print("  特徴: グラフベース、条件分岐、Human-in-the-Loop")
    print("=" * 70)

    # グラフの構築
    app = build_travel_graph()

    # グラフの可視化（テキスト形式）
    print("\n  グラフ構造:")
    print("  " + "-" * 50)
    print("""
    [parse_request] → [search_flights] → [search_hotels]
                                              ↓
    [generate_plan] ← [check_budget] ← [check_weather]
         ↓                 ↓ (予算超過)
        END          [human_approval]
                           ↓
                     [generate_plan]
""")

    # グラフの実行
    print("  実行:")
    print("  " + "-" * 50)

    initial_state: TravelState = {
        "messages": [HumanMessage(content="東京から沖縄に2泊3日、予算10万円で旅行したい")],
        "origin": "",
        "destination": "",
        "date": "",
        "budget": 0,
        "flights": [],
        "hotels": [],
        "weather": {},
        "plan": "",
        "needs_approval": False,
    }

    # ステップごとの実行を表示
    for step_output in app.stream(initial_state):
        for node_name, node_state in step_output.items():
            latest_msg = node_state.get("messages", [])
            if latest_msg:
                last = latest_msg[-1] if isinstance(latest_msg[-1], AIMessage) else None
                if last:
                    print(f"    [{node_name}] {last.content}")

    print("\n  最終プラン:")
    print("  " + "-" * 50)
    # 最終状態を取得
    final_state = app.invoke(initial_state)
    if final_state.get("plan"):
        plan_lines = final_state["plan"].split("\n")[:10]
        for line in plan_lines:
            print(f"    {line}")

    print(f"""
  LangGraph の特徴:
  ┌──────────────────────────────────────────────────────────────────┐
  │ • StateGraph でノードとエッジを定義（DAG/サイクル対応）          │
  │ • TypedDict でステートを型安全に管理                             │
  │ • add_conditional_edges で条件分岐を実現                         │
  │ • Human-in-the-Loop をグラフに組み込み可能                       │
  │ • stream() でステップごとの実行を可視化                          │
  └──────────────────────────────────────────────────────────────────┘

  最適なユースケース:
  • 複雑な条件分岐がある対話フロー
  • ループや再試行が必要なワークフロー
  • Human-in-the-Loop（人間の承認）が必要な業務
  • ステートの遷移を可視化・デバッグしたい場合
""")


if __name__ == "__main__":
    main()
