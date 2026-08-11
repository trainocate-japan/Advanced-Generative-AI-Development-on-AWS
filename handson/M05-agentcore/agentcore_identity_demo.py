"""
パート 2 ステップ 2.3: AgentCore Identity デモ

実際に Workload Identity（エージェント ID）を作成し、
エージェントに固有の認証情報を付与する。

前提:
  pip install boto3
  AWS 認証情報が設定済み（us-east-1）

実行:
  python3.12 agentcore_identity_demo.py

クリーンアップ:
  python3.12 agentcore_identity_demo.py --cleanup
"""

import boto3
import json
import sys
import time

REGION = "us-east-1"
IDENTITY_NAME = "handson-travel-agent"

control = boto3.client("bedrock-agentcore-control", region_name=REGION)


# ======================================================================
# 1. Workload Identity の作成
# ======================================================================

def create_workload_identity():
    """エージェント用 Workload Identity を作成"""
    print("\n  [1] Workload Identity の作成")
    print("  " + "-" * 55)

    # 既存チェック
    existing = find_existing_identity()
    if existing:
        print(f"    → 既存の Identity を使用")
        print(f"      Name: {existing.get('name')}")
        print(f"      ARN:  {existing.get('workloadIdentityArn')}")
        return existing

    print(f"    Identity 名: {IDENTITY_NAME}")

    response = control.create_workload_identity(
        name=IDENTITY_NAME,
    )

    identity_arn = response.get("workloadIdentityArn")
    print(f"\n    ✓ Workload Identity 作成完了")
    print(f"      Name: {IDENTITY_NAME}")
    print(f"      ARN:  {identity_arn}")

    return response


def find_existing_identity():
    """既存の Workload Identity を検索"""
    try:
        resp = control.list_workload_identities()
        for identity in resp.get("workloadIdentities", []):
            if identity.get("name") == IDENTITY_NAME:
                return identity
    except Exception:
        pass
    return None


# ======================================================================
# 2. Identity 情報の確認
# ======================================================================

def show_identity_info():
    """Identity ディレクトリの情報を表示"""
    print("\n  [2] Identity 情報の確認")
    print("  " + "-" * 55)

    resp = control.list_workload_identities()
    identities = resp.get("workloadIdentities", [])
    print(f"    登録済み Workload Identity: {len(identities)} 件")

    for identity in identities:
        print(f"\n      Name: {identity.get('name')}")
        print(f"      ARN:  {identity.get('workloadIdentityArn')}")


# ======================================================================
# 3. Identity の仕組み解説
# ======================================================================

def explain_identity():
    """Identity の役割を説明"""
    print("\n  [3] AgentCore Identity の役割")
    print("  " + "-" * 55)
    print("""
    Workload Identity は以下を実現します:

    ┌─────────────────────────────────────────────────────────┐
    │ AgentCore Identity                                       │
    │                                                         │
    │  • エージェントに固有の ID を付与                       │
    │    → IAM ロールとは別の「エージェント ID」              │
    │                                                         │
    │  • OAuth2 フローによる委任アクセス                      │
    │    → ユーザーがエージェントに権限を委任                 │
    │    → エージェントがユーザーの代わりにツールを呼び出し   │
    │                                                         │
    │  • Gateway との連携                                     │
    │    → Gateway が Identity でエージェントを認証           │
    │    → ツール呼び出し前にポリシーチェック                 │
    │                                                         │
    │  • 監査とトレーサビリティ                               │
    │    → どのエージェントが何をしたか追跡可能               │
    └─────────────────────────────────────────────────────────┘

    フロー:
    1. エージェントを Workload Identity として登録
    2. ユーザーが OAuth2 で権限を委任
    3. エージェントが Workload Access Token を取得
    4. Gateway がトークンを検証し、ツール呼び出しを許可
""")


# ======================================================================
# クリーンアップ
# ======================================================================

def cleanup():
    """Workload Identity を削除"""
    print("\n  [クリーンアップ] Workload Identity の削除")
    print("  " + "-" * 55)

    existing = find_existing_identity()
    if not existing:
        print(f"    Identity '{IDENTITY_NAME}' は存在しません。")
        return

    identity_name = existing["name"]
    print(f"    Identity 削除: {identity_name}")
    control.delete_workload_identity(name=identity_name)
    print(f"    ✓ 削除完了")


# ======================================================================
# メイン
# ======================================================================

def main():
    print("\n")
    print("=" * 65)
    print("  AgentCore Identity デモ - 実リソース操作")
    print("=" * 65)

    if "--cleanup" in sys.argv:
        cleanup()
        return

    # 1. Workload Identity 作成
    create_workload_identity()

    # 2. 情報確認
    show_identity_info()

    # 3. 解説
    explain_identity()

    print(f"""
  {'=' * 65}
  まとめ
  {'=' * 65}

  作成したリソース:
  • Workload Identity: {IDENTITY_NAME}

  Identity が解決する課題:
  • エージェントの身元確認（誰が呼び出したか）
  • 委任アクセス（ユーザーの権限をエージェントに付与）
  • ツール呼び出しの認可（ポリシーベースの制御）
  • 監査ログ（全アクションの追跡）

  クリーンアップ:
    python3.12 agentcore_identity_demo.py --cleanup
""")


if __name__ == "__main__":
    main()
