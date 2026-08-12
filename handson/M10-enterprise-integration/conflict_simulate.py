"""
セマンティック競合解決ハンズオン - Part 1: 競合の発生
=====================================================
DynamoDB テーブルを作成し、2つのシステムから同じ顧客レコードに
矛盾する更新を発生させて競合状態を作ります。

使い方:
  python conflict_simulate.py

実行後、DynamoDB 上で競合状態（unresolved）を確認してから
conflict_resolve.py を実行してください。
"""

import boto3
import json
import uuid
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# ============================================================
# 設定
# ============================================================
REGION = "us-east-1"
TABLE_NAME = "semantic-conflict-demo"

dynamodb = boto3.resource("dynamodb", region_name=REGION)


# ============================================================
# テーブル作成
# ============================================================
def setup_table():
    """DynamoDB テーブルを作成する"""
    print("=" * 60)
    print("ステップ 1: DynamoDB テーブルの作成")
    print("=" * 60)

    try:
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"  テーブル '{TABLE_NAME}' を作成中...")
        table.wait_until_exists()
        print(f"  テーブル作成完了\n")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  テーブル '{TABLE_NAME}' は既に存在します（スキップ）\n")
        else:
            raise

    return dynamodb.Table(TABLE_NAME)


# ============================================================
# 初期データ投入
# ============================================================
def seed_data(table):
    """初期顧客データを投入"""
    print("=" * 60)
    print("ステップ 2: 初期顧客データの投入")
    print("=" * 60)

    initial_record = {
        "PK": "CUSTOMER#C-1001",
        "SK": "PROFILE",
        "customer_id": "C-1001",
        "name": "田中太郎",
        "email": "tanaka@example.com",
        "phone": "03-1234-5678",
        "address": "東京都渋谷区",
        "contract_status": "active",
        "priority": 3,
        "notes": "2024年より利用開始。年間契約。",
        "version": 1,
        "last_updated_by": "system",
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
    }

    table.put_item(Item=initial_record)

    print(f"\n  顧客レコードを作成しました:")
    print(f"    顧客ID:  {initial_record['customer_id']}")
    print(f"    名前:    {initial_record['name']}")
    print(f"    メール:  {initial_record['email']}")
    print(f"    電話:    {initial_record['phone']}")
    print(f"    住所:    {initial_record['address']}")
    print(f"    契約:    {initial_record['contract_status']}")
    print(f"    優先度:  {initial_record['priority']}")
    print(f"    備考:    {initial_record['notes']}")
    print(f"    version: {initial_record['version']}")
    print()


# ============================================================
# 競合シミュレーション
# ============================================================
def simulate_conflict(table):
    """2つのシステムから同時に矛盾する更新を発生させる"""
    print("=" * 60)
    print("ステップ 3: 並行書き込みによる競合の発生")
    print("=" * 60)

    # 現在のレコードを取得
    response = table.get_item(Key={"PK": "CUSTOMER#C-1001", "SK": "PROFILE"})
    current = response["Item"]
    current_version = int(current["version"])

    # --- CRM システムからの更新 ---
    crm_update = {
        "source_system": "CRM",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changes": {
            "email": "t.tanaka@newcompany.co.jp",
            "phone": "03-9999-0000",
            "address": "東京都渋谷区神南1-2-3",
            "priority": 5,
            "notes": "2024年より利用開始。年間契約。2025年に法人契約へ移行。",
        },
        "update_reason": "顧客が営業担当に直接連絡先変更を依頼",
    }

    # --- カスタマーサポートからの更新 ---
    support_update = {
        "source_system": "CustomerSupport",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changes": {
            "email": "tanaka.personal@gmail.com",
            "phone": "090-1111-2222",
            "address": "東京都港区",
            "contract_status": "premium",
            "priority": 4,
            "notes": "2024年より利用開始。年間契約。サポート対応中に住所変更の申し出あり。",
        },
        "update_reason": "顧客がサポート窓口に連絡、住所変更とプラン変更を依頼",
    }

    print(f"\n  同じ顧客レコード (version={current_version}) に対して")
    print(f"  2つのシステムが同時に異なる更新を試みます...\n")

    print(f"  ┌─────────────────────────────────────────────────────┐")
    print(f"  │ 更新 A: CRM システム                                │")
    print(f"  │   理由: {crm_update['update_reason']}")
    print(f"  │   メール:  tanaka@example.com → {crm_update['changes']['email']}")
    print(f"  │   電話:    03-1234-5678 → {crm_update['changes']['phone']}")
    print(f"  │   住所:    東京都渋谷区 → {crm_update['changes']['address']}")
    print(f"  │   優先度:  3 → {crm_update['changes']['priority']}")
    print(f"  └─────────────────────────────────────────────────────┘")
    print()
    print(f"  ┌─────────────────────────────────────────────────────┐")
    print(f"  │ 更新 B: カスタマーサポート                          │")
    print(f"  │   理由: {support_update['update_reason']}")
    print(f"  │   メール:  tanaka@example.com → {support_update['changes']['email']}")
    print(f"  │   電話:    03-1234-5678 → {support_update['changes']['phone']}")
    print(f"  │   住所:    東京都渋谷区 → {support_update['changes']['address']}")
    print(f"  │   契約:    active → {support_update['changes']['contract_status']}")
    print(f"  │   優先度:  3 → {support_update['changes']['priority']}")
    print(f"  └─────────────────────────────────────────────────────┘")

    # 競合バージョンとして DynamoDB に保存（両方のバージョンを保持）
    conflict_id = f"CONFLICT#{uuid.uuid4().hex[:8]}"

    # Decimal を JSON にシリアライズ
    import decimal

    def convert(obj):
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj == int(obj) else float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    base_record_json = json.dumps(dict(current), default=convert, ensure_ascii=False)

    table.put_item(
        Item={
            "PK": "CUSTOMER#C-1001",
            "SK": conflict_id,
            "conflict_id": conflict_id,
            "status": "unresolved",
            "base_version": current_version,
            "base_record": base_record_json,
            "version_a": json.dumps(crm_update, ensure_ascii=False),
            "version_b": json.dumps(support_update, ensure_ascii=False),
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    print(f"\n  {'!'*50}")
    print(f"  競合を検出しました!")
    print(f"  {'!'*50}")
    print(f"\n  競合 ID: {conflict_id}")
    print(f"  ステータス: unresolved（未解決）")
    print(f"  両バージョンを DynamoDB に保存しました。")
    print()

    return conflict_id


# ============================================================
# 競合状態の確認
# ============================================================
def show_conflict_status(table):
    """現在の競合状態を表示"""
    print("=" * 60)
    print("現在の競合状態")
    print("=" * 60)

    # メインレコード
    response = table.get_item(Key={"PK": "CUSTOMER#C-1001", "SK": "PROFILE"})
    current = response["Item"]
    print(f"\n  [メインレコード] (変更されていない = ベースバージョンのまま)")
    print(f"    メール: {current['email']}")
    print(f"    電話:   {current['phone']}")
    print(f"    住所:   {current['address']}")
    print(f"    契約:   {current['contract_status']}")
    print(f"    version: {current['version']}")

    # 競合レコード
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq("CUSTOMER#C-1001")
        & boto3.dynamodb.conditions.Key("SK").begins_with("CONFLICT#"),
    )

    conflicts = response.get("Items", [])
    print(f"\n  [競合レコード] {len(conflicts)} 件")

    for c in conflicts:
        version_a = json.loads(c["version_a"])
        version_b = json.loads(c["version_b"])
        print(f"\n    競合 ID: {c['conflict_id']}")
        print(f"    ステータス: {c['status']}")
        print(f"    検出日時: {c['detected_at']}")
        print(f"    更新 A ({version_a['source_system']}): {version_a['update_reason']}")
        print(f"    更新 B ({version_b['source_system']}): {version_b['update_reason']}")

        if c["status"] == "resolved" and "resolution" in c:
            resolution = json.loads(c["resolution"])
            print(f"    解決日時: {c.get('resolved_at', 'N/A')}")
            print(f"    判断:")
            for d in resolution.get("decisions", []):
                print(f"      [{d['field']}] {d['chosen_source']} → {d['reason']}")

    print()


# ============================================================
# メイン
# ============================================================
def main():
    print("\n" + "=" * 60)
    print("  セマンティック競合解決 - Part 1: 競合の発生")
    print("  DynamoDB に競合状態を作成します")
    print("=" * 60 + "\n")

    # 1. テーブル作成
    table = setup_table()

    # 2. 初期データ投入
    seed_data(table)

    # 3. 競合シミュレーション
    conflict_id = simulate_conflict(table)

    # 4. 競合状態の確認
    show_conflict_status(table)

    print("=" * 60)
    print("  次のステップ")
    print("=" * 60)
    print()
    print("  競合状態を DynamoDB コンソールや CLI で確認してみましょう:")
    print()
    print("  aws dynamodb query \\")
    print(f"    --table-name {TABLE_NAME} \\")
    print('    --key-condition-expression "PK = :pk" \\')
    print("    --expression-attribute-values '{\":pk\": {\"S\": \"CUSTOMER#C-1001\"}}' \\")
    print("    --output json | python3 -m json.tool")
    print()
    print("  確認できたら、Bedrock で競合を解決します:")
    print("    python conflict_resolve.py")
    print()


if __name__ == "__main__":
    main()
