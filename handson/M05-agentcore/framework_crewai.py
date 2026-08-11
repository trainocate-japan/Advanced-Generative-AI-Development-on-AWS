"""
パート 4: フレームワーク比較 - CrewAI
- マルチエージェント協調フレームワーク
- 役割分担による複雑なタスクの分業
- エージェント間のコミュニケーションと委任

インストール:
  pip install crewai crewai-tools boto3
"""

from crewai import Agent, Task, Crew, Process
from crewai.tools import tool as crewai_tool
from crewai import LLM


# ======================================================================
# ツール定義（CrewAI の @tool デコレータ）
# ======================================================================

@crewai_tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """指定された出発地・目的地・日付でフライトを検索します。

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
    return f"検索結果: {flights}"


@crewai_tool
def search_hotels(city: str, checkin: str, checkout: str) -> str:
    """指定された都市・日付でホテルを検索します。

    Args:
        city: 都市名（例: 沖縄）
        checkin: チェックイン日
        checkout: チェックアウト日
    """
    hotels = [
        {"name": "オーシャンビューリゾート", "price": 25000, "rating": 4.5},
        {"name": "シティホテル那覇", "price": 12000, "rating": 4.0},
    ]
    return f"検索結果: {hotels}"


@crewai_tool
def get_weather(city: str, date: str) -> str:
    """指定された都市・日付の天気予報を取得します。

    Args:
        city: 都市名
        date: 日付
    """
    return "天気: 晴れ, 最高28℃, 最低22℃, 降水確率10%"


@crewai_tool
def calculate_budget(items: str) -> str:
    """旅行の合計費用を計算します。

    Args:
        items: 費用項目のリスト（JSON文字列）
    """
    return "合計予算: ¥85,000（フライト往復¥30,000 + ホテル2泊¥50,000 + その他¥5,000）"


# ======================================================================
# エージェント定義（役割ベース）
# ======================================================================

def create_crew():
    """旅行プランニングクルーの作成"""

    # LLM の設定（Amazon Bedrock）
    llm = LLM(
        model="bedrock/amazon.nova-pro-v1:0",
        region_name="us-east-1",
    )

    # エージェント 1: リサーチャー（情報収集担当）
    researcher = Agent(
        role="旅行リサーチャー",
        goal="最適なフライトとホテルの組み合わせを調査する",
        backstory="""あなたは経験豊富な旅行リサーチャーです。
最安値のフライトやコスパの良いホテルを見つけることが得意です。
複数の選択肢を比較し、ユーザーの予算と好みに合った候補を提示します。""",
        tools=[search_flights, search_hotels, get_weather],
        llm=llm,
        verbose=True,
    )

    # エージェント 2: プランナー（計画策定担当）
    planner = Agent(
        role="旅行プランナー",
        goal="収集した情報を基に最適な旅行プランを策定する",
        backstory="""あなたはプロの旅行プランナーです。
リサーチャーが収集した情報を統合し、日程、予算、天気を考慮した
具体的な旅行プランを作成します。代替案も含めて提案します。""",
        tools=[calculate_budget],
        llm=llm,
        verbose=True,
    )

    # エージェント 3: レビュアー（品質チェック担当）
    reviewer = Agent(
        role="旅行プランレビュアー",
        goal="提案されたプランの品質と実現可能性をチェックする",
        backstory="""あなたは旅行プランの品質管理担当です。
予算超過、スケジュールの無理、天候リスクなどを確認し、
必要に応じて改善提案を行います。""",
        llm=llm,
        verbose=True,
    )

    # タスク定義
    research_task = Task(
        description="""東京から沖縄への2泊3日旅行について以下を調査してください:
1. フライトの検索（出発地: 東京、目的地: 沖縄、日付: 2025-03-15）
2. ホテルの検索（都市: 沖縄、チェックイン: 2025-03-15、チェックアウト: 2025-03-17）
3. 天気の確認（都市: 沖縄、日付: 2025-03-15）
予算は10万円以内です。""",
        agent=researcher,
        expected_output="フライト候補、ホテル候補、天気情報のリスト",
    )

    planning_task = Task(
        description="""リサーチャーの調査結果を基に、以下を含む旅行プランを作成してください:
1. 推薦するフライト（往復）
2. 推薦するホテル
3. 予算の内訳
4. 日程表（1日目〜3日目）
予算10万円以内に収めてください。""",
        agent=planner,
        expected_output="具体的な日程表と予算内訳を含む旅行プラン",
    )

    review_task = Task(
        description="""プランナーが作成した旅行プランをレビューしてください:
1. 予算は10万円以内か
2. スケジュールに無理はないか
3. 天候リスクへの対策はあるか
4. 改善点があれば提案
最終的な推薦プランを出力してください。""",
        agent=reviewer,
        expected_output="レビュー結果と最終推薦プラン",
    )

    # クルーの作成（チームの組み立て）
    crew = Crew(
        agents=[researcher, planner, reviewer],
        tasks=[research_task, planning_task, review_task],
        process=Process.sequential,  # 順次実行（hierarchical も可能）
        verbose=True,
    )

    return crew


# ======================================================================
# メイン実行
# ======================================================================

def main():
    print("=" * 70)
    print("  フレームワーク比較: CrewAI")
    print("  特徴: マルチエージェント協調、役割分担、チーム型タスク処理")
    print("=" * 70)

    # クルー構造の表示
    print("""
  クルー構成:
  ┌─────────────────────────────────────────────────────────────────┐
  │                     旅行プランニング Crew                        │
  │                                                                 │
  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐  │
  │  │ リサーチャー │ → │ プランナー  │ → │    レビュアー       │  │
  │  │             │   │             │   │                     │  │
  │  │ • フライト  │   │ • 日程作成  │   │ • 予算チェック      │  │
  │  │ • ホテル    │   │ • 予算計算  │   │ • スケジュール確認  │  │
  │  │ • 天気      │   │ • 提案作成  │   │ • 改善提案          │  │
  │  └─────────────┘   └─────────────┘   └─────────────────────┘  │
  │                                                                 │
  │  Process: Sequential（順次実行）                                │
  └─────────────────────────────────────────────────────────────────┘
""")

    # クルーの実行
    print("  実行開始...")
    print("  " + "-" * 50)

    crew = create_crew()
    result = crew.kickoff()

    print("\n  " + "-" * 50)
    print("  最終結果:")
    print("  " + "-" * 50)
    print(f"    {result}")

    print(f"""
  CrewAI の特徴:
  ┌──────────────────────────────────────────────────────────────────┐
  │ • Agent に role / goal / backstory を設定（人格を持つ）          │
  │ • Task で各エージェントの具体的な仕事を定義                      │
  │ • Crew でチームを編成し、Process（順次/階層）を指定              │
  │ • エージェント間で結果を受け渡し（委任も可能）                   │
  │ • crew.kickoff() で全タスクを自動実行                            │
  └──────────────────────────────────────────────────────────────────┘

  最適なユースケース:
  • 複数の専門家が協力して解決するタスク
  • 調査→分析→レビューのようなパイプライン
  • 品質チェックや承認フローを含む業務
  • チーム型の自律的なタスク分担
""")


if __name__ == "__main__":
    main()
