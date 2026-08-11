"""
パート 2 ステップ 2.1: AgentCore Gateway デモ

実際に Gateway を作成し、Lambda ツールをターゲットとして登録し、
ツール一覧を確認する。

前提:
  pip install boto3
  AWS 認証情報が設定済み（us-east-1）

  Lambda 関数のデプロイ（先に実行）:
    cd ~/handson/M05-agentcore
    aws cloudformation deploy \
      --template-file lambda-cfn.yaml \
      --stack-name agentcore-travel-tools \
      --capabilities CAPABILITY_NAMED_IAM \
      --region us-east-1

実行:
  python3.12 agentcore_gateway_demo.py

クリーンアップ:
  python3.12 agentcore_gateway_demo.py --cleanup
  aws cloudformation delete-stack --stack-name agentcore-travel-tools --region us-east-1
"""

import boto3
import json
import sys
import time

REGION = "us-east-1"
GATEWAY_NAME = "handson-travel-gateway"

control = boto3.client("bedrock-agentcore-control", region_name=REGION)


# ======================================================================
# ヘルパー
# ======================================================================

def wait_for_gateway(gateway_id, target_status="READY", timeout=180):
    """Gateway が指定ステータスになるまで待機"""
    for _ in range(timeout // 10):
        resp = control.get_gateway(gatewayIdentifier=gateway_id)
        status = resp.get("status")
        if status in (target_status, "ACTIVE", "READY"):
            return resp
        if status == "FAILED":
            raise Exception(f"Gateway FAILED: {resp.get('failureReason')}")
        print(f"      ステータス: {status} ... 待機中")
        time.sleep(10)
    raise TimeoutError("Gateway がタイムアウトしました")


def wait_for_target(gateway_id, target_id, timeout=120):
    """Gateway Target が ACTIVE/READY になるまで待機"""
    for _ in range(timeout // 10):
        resp = control.get_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id,
        )
        status = resp.get("status")
        if status in ("ACTIVE", "READY"):
            return resp
        if status == "FAILED":
            raise Exception(f"Target FAILED: {resp.get('failureReason')}")
        print(f"      ターゲットステータス: {status} ... 待機中")
        time.sleep(10)
    raise TimeoutError("Target がタイムアウトしました")


def find_existing_gateway(name):
    """既存の Gateway を名前で検索"""
    resp = control.list_gateways()
    for gw in resp.get("items", []):
        if gw.get("name") == name:
            return gw
    return None


def get_gateway_role_arn():
    """CFn スタックから Gateway サービスロール ARN を取得"""
    cfn = boto3.client("cloudformation", region_name=REGION)
    try:
        resp = cfn.describe_stacks(StackName="agentcore-travel-tools")
        outputs = resp["Stacks"][0].get("Outputs", [])
        for out in outputs:
            if out["OutputKey"] == "GatewayServiceRoleArn":
                return out["OutputValue"]
    except Exception:
        pass

    # フォールバック: IAM から直接取得
    iam = boto3.client("iam")
    try:
        role = iam.get_role(RoleName="agentcore-gateway-service-role")
        return role["Role"]["Arn"]
    except Exception:
        pass

    raise RuntimeError(
        "Gateway サービスロールが見つかりません。先に Lambda スタックをデプロイしてください:\n"
        "  aws cloudformation deploy --template-file lambda-cfn.yaml "
        "--stack-name agentcore-travel-tools --capabilities CAPABILITY_NAMED_IAM"
    )


# ======================================================================
# 1. Gateway の作成
# ======================================================================

def create_gateway():
    """Gateway を作成（NONE 認可 = デモ用）"""
    print("\n  [1] Gateway の作成")
    print("  " + "-" * 55)

    # 既存チェック
    existing = find_existing_gateway(GATEWAY_NAME)
    if existing:
        gw_id = existing["gatewayId"]
        print(f"    → 既存の Gateway を使用: {gw_id}")
        detail = control.get_gateway(gatewayIdentifier=gw_id)
        print(f"      URL: {detail.get('gatewayUrl', 'N/A')}")
        print(f"      Status: {detail.get('status')}")
        return detail

    # Gateway サービスロール ARN を CFn スタックから取得
    role_arn = get_gateway_role_arn()

    response = control.create_gateway(
        name=GATEWAY_NAME,
        protocolType="MCP",
        authorizerType="NONE",
        roleArn=role_arn,
        description="ハンズオン旅行エージェント用 Gateway",
    )

    gateway_id = response["gatewayId"]
    print(f"    ✓ Gateway 作成開始")
    print(f"      ID:   {gateway_id}")
    print(f"      ARN:  {response['gatewayArn']}")
    print(f"      Auth: NONE (デモ用)")
    print(f"      Role: {role_arn}")

    # ACTIVE まで待機
    print(f"\n    ACTIVE になるまで待機...")
    detail = wait_for_gateway(gateway_id)
    print(f"    ✓ Gateway ACTIVE")
    print(f"      URL: {detail.get('gatewayUrl')}")
    return detail


# ======================================================================
# 2. Gateway Target の登録（Lambda ツール）
# ======================================================================

def create_gateway_target(gateway_id):
    """Lambda 関数をツールとして Gateway Target に登録"""
    print("\n  [2] Gateway Target の登録（Lambda ツール）")
    print("  " + "-" * 55)

    # 既存ターゲットの確認
    existing_targets = control.list_gateway_targets(gatewayIdentifier=gateway_id)
    for t in existing_targets.get("items", []):
        if t.get("name") == "travel-tools":
            print(f"    → 既存ターゲットを使用: {t['targetId']}")
            return control.get_gateway_target(
                gatewayIdentifier=gateway_id,
                targetId=t["targetId"],
            )

    # ツールスキーマ定義（Lambda に紐づくツール）
    tool_schema = [
        {
            "name": "search_flights",
            "description": "フライトを検索します。出発地、目的地、日付を指定。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "出発地"},
                    "destination": {"type": "string", "description": "目的地"},
                    "date": {"type": "string", "description": "搭乗日"},
                },
                "required": ["origin", "destination", "date"],
            },
        },
        {
            "name": "search_hotels",
            "description": "ホテルを検索します。都市、チェックイン日、チェックアウト日を指定。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "都市名"},
                    "checkin": {"type": "string", "description": "チェックイン日"},
                    "checkout": {"type": "string", "description": "チェックアウト日"},
                },
                "required": ["city", "checkin", "checkout"],
            },
        },
        {
            "name": "get_weather",
            "description": "天気予報を取得します。都市と日付を指定。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "都市名"},
                    "date": {"type": "string", "description": "日付"},
                },
                "required": ["city", "date"],
            },
        },
    ]

    # Lambda ARN を取得（CFn スタック agentcore-travel-tools でデプロイ済み）
    lambda_client = boto3.client("lambda", region_name=REGION)
    try:
        fn = lambda_client.get_function(FunctionName="travel-tools")
        lambda_arn = fn["Configuration"]["FunctionArn"]
    except Exception:
        account_id = boto3.client("sts").get_caller_identity()["Account"]
        lambda_arn = f"arn:aws:lambda:{REGION}:{account_id}:function:travel-tools"
        print(f"    ⚠ Lambda 関数が見つかりません。先にデプロイしてください:")
        print(f"      aws cloudformation deploy \\")
        print(f"        --template-file lambda-cfn.yaml \\")
        print(f"        --stack-name agentcore-travel-tools \\")
        print(f"        --capabilities CAPABILITY_NAMED_IAM --region {REGION}")

    print(f"    Lambda ARN: {lambda_arn}")
    print(f"    登録ツール数: {len(tool_schema)}")
    for ts in tool_schema:
        print(f"      • {ts['name']}: {ts['description'][:30]}...")

    response = control.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name="travel-tools",
        description="旅行プランニング用ツール群",
        targetConfiguration={
            "mcp": {
                "lambda": {
                    "lambdaArn": lambda_arn,
                    "toolSchema": {
                        "inlinePayload": tool_schema,
                    },
                }
            }
        },
        credentialProviderConfigurations=[
            {
                "credentialProviderType": "GATEWAY_IAM_ROLE",
            }
        ],
    )

    target_id = response["targetId"]
    print(f"\n    ✓ Target 作成開始: {target_id}")

    # ACTIVE まで待機
    print(f"    ACTIVE になるまで待機...")
    detail = wait_for_target(gateway_id, target_id)
    print(f"    ✓ Target ACTIVE")
    return detail


# ======================================================================
# 3. Gateway の確認
# ======================================================================

def show_gateway_info(gateway_id):
    """Gateway とターゲットの情報を表示"""
    print("\n  [3] Gateway 情報の確認")
    print("  " + "-" * 55)

    gw = control.get_gateway(gatewayIdentifier=gateway_id)
    print(f"    Gateway: {gw['name']}")
    print(f"      ID:       {gw['gatewayId']}")
    print(f"      URL:      {gw.get('gatewayUrl', 'N/A')}")
    print(f"      Protocol: {gw.get('protocolType')}")
    print(f"      Auth:     {gw.get('authorizerType')}")
    print(f"      Status:   {gw.get('status')}")

    targets = control.list_gateway_targets(gatewayIdentifier=gateway_id)
    print(f"\n    登録ターゲット: {len(targets.get('items', []))} 件")
    for t in targets.get("items", []):
        print(f"      • {t['name']} (ID: {t['targetId']}, Status: {t.get('status')})")


# ======================================================================
# 4. クリーンアップ
# ======================================================================

def cleanup():
    """Gateway とターゲットを削除"""
    print("\n  [クリーンアップ] Gateway の削除")
    print("  " + "-" * 55)

    existing = find_existing_gateway(GATEWAY_NAME)
    if not existing:
        print(f"    Gateway '{GATEWAY_NAME}' は存在しません。")
        return

    gateway_id = existing["gatewayId"]

    # ターゲットを先に削除
    targets = control.list_gateway_targets(gatewayIdentifier=gateway_id)
    for t in targets.get("items", []):
        print(f"    ターゲット削除: {t['name']} ({t['targetId']})")
        control.delete_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=t["targetId"],
        )
        time.sleep(5)

    # Gateway 削除
    print(f"    Gateway 削除: {gateway_id}")
    control.delete_gateway(gatewayIdentifier=gateway_id)
    print(f"    ✓ 削除完了")


# ======================================================================
# メイン
# ======================================================================

def main():
    print("\n")
    print("=" * 65)
    print("  AgentCore Gateway デモ - 実リソース操作")
    print("=" * 65)

    if "--cleanup" in sys.argv:
        cleanup()
        return

    # 1. Gateway 作成
    gw = create_gateway()
    gateway_id = gw["gatewayId"]

    # 2. Target 登録
    try:
        create_gateway_target(gateway_id)
    except Exception as e:
        print(f"\n    ⚠ Target 登録エラー: {e}")
        print(f"    （Lambda 関数が存在しない場合はこのエラーが出ます）")
        print(f"    → Gateway 自体は作成済みです。")

    # 3. 情報確認
    show_gateway_info(gateway_id)

    print(f"""
  {'=' * 65}
  まとめ
  {'=' * 65}

  Gateway の役割:
  • API / Lambda / MCP サーバーを MCP 互換ツールに変換
  • エージェントに統一的なツールアクセスを提供
  • セマンティック検索でツールを自動選択
  • 認証・認可を一元管理

  作成したリソース:
  • Gateway: {GATEWAY_NAME} ({gateway_id})

  クリーンアップ:
    python3.12 agentcore_gateway_demo.py --cleanup
""")


if __name__ == "__main__":
    main()
