"""
パート 2 ステップ 2.2: AgentCore Memory デモ

実際に Memory リソースを作成し、会話イベントを登録、
長期記憶を検索する。

前提:
  pip install boto3
  AWS 認証情報が設定済み（us-east-1）

実行:
  python3.12 agentcore_memory_demo.py

クリーンアップ:
  python3.12 agentcore_memory_demo.py --cleanup
"""

import boto3
import json
import sys
import time
from datetime import datetime

REGION = "us-east-1"
MEMORY_NAME = "handson_travel_agent_memory"

control = boto3.client("bedrock-agentcore-control", region_name=REGION)
data = boto3.client("bedrock-agentcore", region_name=REGION)


# ======================================================================
# 1. Memory リソースの作成
# ======================================================================

def create_memory():
    """Memory リソースを作成"""
    print("\n  [1] Memory リソースの作成")
    print("  " + "-" * 55)

    # 既存チェック
    existing = find_existing_memory()
    if existing:
        memory_id = existing["id"]
        print(f"    → 既存の Memory を使用: {memory_id}")
        print(f"      Name: {existing.get('name')}")
        print(f"      Status: {existing.get('status')}")
        return existing

    # 既存チェック
    existing = find_existing_memory()
    if existing:
        memory_id = existing["id"]
        print(f"    → 既存の Memory を使用: {memory_id}")
        print(f"      Name: {existing.get('name')}")
        print(f"      Status: {existing.get('status')}")
        return existing

    print(f"    Memory 名: {MEMORY_NAME}")
    print(f"    戦略:")
    print(f"      • SessionSummarizer: 会話の要約を抽出")
    print(f"      • UserPreferenceExtractor: ユーザー嗜好を抽出")

    response = control.create_memory(
        name=MEMORY_NAME,
        description="旅行プランニングエージェント用メモリ",
        eventExpiryDuration=30,  # 30日 - デモ用
        memoryStrategies=[
            {
                "summaryMemoryStrategy": {
                    "name": "SessionSummarizer",
                    "namespaceTemplates": ["/summaries/{actorId}/{sessionId}/"],
                }
            },
            {
                "userPreferenceMemoryStrategy": {
                    "name": "UserPreferenceExtractor",
                    "namespaceTemplates": ["/users/{actorId}/preferences/"],
                }
            },
        ],
    )

    memory_id = response["memory"]["id"]
    print(f"\n    ✓ Memory 作成開始")
    print(f"      ID:  {memory_id}")
    print(f"      ARN: {response['memory']['arn']}")

    # ACTIVE まで待機
    print(f"\n    ACTIVE になるまで待機...")
    for _ in range(30):
        mem = control.get_memory(memoryId=memory_id)
        status = mem.get("memory", {}).get("status")
        if status == "ACTIVE":
            print(f"    ✓ Memory ACTIVE")
            return mem["memory"]
        if status == "FAILED":
            raise Exception(f"Memory FAILED: {mem['memory'].get('failureReason')}")
        print(f"      ステータス: {status} ... 待機中")
        time.sleep(10)

    raise TimeoutError("Memory タイムアウト")


def find_existing_memory():
    """既存 Memory を検索"""
    resp = control.list_memories()
    for mem in resp.get("memories", []):
        if mem.get("name") == MEMORY_NAME:
            return mem
    return None


# ======================================================================
# 2. 会話イベントの登録（短期記憶）
# ======================================================================

def ingest_conversation(memory_id):
    """会話イベントを Memory に登録"""
    print("\n  [2] 会話イベントの登録（短期記憶）")
    print("  " + "-" * 55)

    actor_id = "user-tanaka-001"
    session_id = "travel-session-001"

    conversation = [
        {
            "conversational": {
                "role": "USER",
                "content": {"text": "来月東京から沖縄に2泊3日で旅行したいです。予算は10万円以内で。"},
            }
        },
        {
            "conversational": {
                "role": "ASSISTANT",
                "content": {"text": "沖縄への2泊3日旅行ですね。ANAのフライトとオーシャンビューリゾートをお勧めします。往復フライト¥70,000＋ホテル2泊¥50,000で合計¥120,000ですが、LCCを使えば予算内に収まります。"},
            }
        },
        {
            "conversational": {
                "role": "USER",
                "content": {"text": "ANAが好きなので、ANAでお願いします。ホテルはリゾートタイプがいいです。"},
            }
        },
        {
            "conversational": {
                "role": "ASSISTANT",
                "content": {"text": "承知しました。ANA利用、リゾートホテルで手配します。オーシャンビューリゾート恩納村が評価4.5で人気です。"},
            }
        },
    ]

    print(f"    Actor: {actor_id}")
    print(f"    Session: {session_id}")
    print(f"    メッセージ数: {len(conversation)}")

    for msg in conversation:
        conv = msg["conversational"]
        role = conv["role"]
        text = conv["content"]["text"][:40]
        print(f"      [{role:9s}] {text}...")

    data.create_event(
        memoryId=memory_id,
        actorId=actor_id,
        sessionId=session_id,
        eventTimestamp=datetime.now(),
        payload=conversation,
    )

    print(f"\n    ✓ 会話イベント登録完了")
    return actor_id, session_id


# ======================================================================
# 3. 短期記憶の取得（イベント一覧）
# ======================================================================

def retrieve_short_term(memory_id, actor_id, session_id):
    """短期記憶（会話履歴）を取得"""
    print("\n  [3] 短期記憶の取得（会話履歴）")
    print("  " + "-" * 55)

    response = data.list_events(
        memoryId=memory_id,
        actorId=actor_id,
        sessionId=session_id,
        maxResults=10,
    )

    events = response.get("events", [])
    print(f"    取得イベント数: {len(events)}")

    for event in reversed(events):
        event_id = event.get("eventId", "N/A")
        timestamp = event.get("eventTimestamp", "N/A")
        print(f"      Event: {event_id} ({timestamp})")

    return events


# ======================================================================
# 4. 長期記憶の検索
# ======================================================================

def retrieve_long_term(memory_id, actor_id):
    """長期記憶（嗜好・要約）をセマンティック検索"""
    print("\n  [4] 長期記憶の検索（セマンティック検索）")
    print("  " + "-" * 55)

    # ユーザー嗜好の検索
    print(f"    検索クエリ: 「好みの航空会社は？」")
    print(f"    Namespace: /users/{actor_id}/preferences/")

    try:
        pref_response = data.retrieve_memory_records(
            memoryId=memory_id,
            namespace=f"/users/{actor_id}/preferences/",
            searchCriteria={"searchQuery": "好みの航空会社は？"},
        )

        records = pref_response.get("memoryRecordSummaries", [])
        print(f"    結果: {len(records)} 件")
        for record in records:
            print(f"      • {record}")

    except Exception as e:
        print(f"    ⚠ 長期記憶は非同期抽出のため、まだ利用不可の場合があります")
        print(f"      ({e})")
        print(f"      → 60秒程度待つと抽出が完了し、検索可能になります")

    # 要約の検索
    print(f"\n    検索クエリ: 「旅行の計画内容は？」")
    print(f"    Namespace: /summaries/{actor_id}/")

    try:
        summary_response = data.retrieve_memory_records(
            memoryId=memory_id,
            namespacePath=f"/summaries/{actor_id}/",
            searchCriteria={"searchQuery": "旅行の計画内容は？"},
        )

        records = summary_response.get("memoryRecordSummaries", [])
        print(f"    結果: {len(records)} 件")
        for record in records:
            print(f"      • {record}")

    except Exception as e:
        print(f"    ⚠ 要約は非同期生成のため、まだ利用不可の場合があります")
        print(f"      ({e})")


# ======================================================================
# クリーンアップ
# ======================================================================

def cleanup():
    """Memory リソースを削除"""
    print("\n  [クリーンアップ] Memory の削除")
    print("  " + "-" * 55)

    existing = find_existing_memory()
    if not existing:
        print(f"    Memory '{MEMORY_NAME}' は存在しません。")
        return

    memory_id = existing["id"]
    print(f"    Memory 削除: {memory_id}")
    control.delete_memory(memoryId=memory_id)
    print(f"    ✓ 削除リクエスト送信（削除完了まで数分かかります）")


# ======================================================================
# メイン
# ======================================================================

def main():
    print("\n")
    print("=" * 65)
    print("  AgentCore Memory デモ - 実リソース操作")
    print("=" * 65)

    if "--cleanup" in sys.argv:
        cleanup()
        return

    # 1. Memory 作成
    mem = create_memory()
    memory_id = mem["id"]

    # 2. 会話イベント登録
    actor_id, session_id = ingest_conversation(memory_id)

    # 3. 短期記憶取得
    retrieve_short_term(memory_id, actor_id, session_id)

    # 4. 長期記憶検索
    retrieve_long_term(memory_id, actor_id)

    print(f"""
  {'=' * 65}
  まとめ
  {'=' * 65}

  Memory の機能:
  • 短期記憶: 現在セッションの会話履歴を保持
  • 長期記憶: ユーザー嗜好・要約を自動抽出（非同期）
  • セマンティック検索: 過去の記憶を自然言語で検索

  Memory 戦略:
  • summaryMemoryStrategy: 会話を要約して保存
  • userPreferenceMemoryStrategy: ユーザー嗜好を抽出

  作成したリソース:
  • Memory: {MEMORY_NAME} ({memory_id})

  クリーンアップ:
    python3.12 agentcore_memory_demo.py --cleanup
""")


if __name__ == "__main__":
    main()
