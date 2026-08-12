"""
セマンティック競合解決ハンズオン - Part 2: AI による競合解決
============================================================
DynamoDB に保存された未解決の競合を Amazon Bedrock で解決します。

前提:
  conflict_simulate.py を先に実行し、競合状態が存在すること。

使い方:
  python conflict_resolve.py
"""

import boto3
import json
import re
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# ============================================================
# 設定
# ============================================================
REGION = "us-east-1"
TABLE_NAME = "semantic-conflict-demo"
MODEL_ID = "amazon.nova-lite-v1:0"

# ビジネスルール（Bedrock に渡すコンテキスト）
BUSINESS_RULES = """
以下のビジネスルールに基づいて競合を解決してください：

1. 連絡先情報（電話番号、メールアドレス）: 顧客本人が直接提供した情報を優先する
2. 住所情報: より詳細（番地、建物名まで含む）な方を優先する
3. 契約ステータス: カスタマーサポートシステムの情報を優先する（顧客対応の最新状態を反映）
4. 顧客メモ/備考: 両方の内容をマージして保持する（情報の欠落を防ぐ）
5. 優先度/ランク: より高い優先度（数値が大きい方）を採用する
6. 更新日時が24時間以上離れている場合: 新しい方を優先する（古い情報は陳腐化の可能性）
"""

dynamodb = boto3.resource("dynamodb", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)


# ============================================================
# 競合解決
# ============================================================
def resolve_conflicts():
    """未解決の競合を Bedrock で解決する"""
    table = dynamodb.Table(TABLE_NAME)

    # 未解決の競合を取得
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq("CUSTOMER#C-1001")
        & boto3.dynamodb.conditions.Key("SK").begins_with("CONFLICT#"),
        FilterExpression=boto3.dynamodb.conditions.Attr("status").eq("unresolved"),
    )

    conflicts = response.get("Items", [])
    if not conflicts:
        print("\n  未解決の競合はありません。")
        print("  先に conflict_simulate.py を実行してください。\n")
        return

    print(f"\n  未解決の競合: {len(conflicts)} 件")
    print(f"  Bedrock ({MODEL_ID}) で解決します...\n")

    for conflict in conflicts:
        resolve_single_conflict(table, conflict)

    # 解決後の最終状態を表示
    show_final_state(table)


def resolve_single_conflict(table, conflict):
    """1件の競合を Bedrock で解決"""
    conflict_id = conflict["conflict_id"]
    base_record = json.loads(conflict["base_record"])
    version_a = json.loads(conflict["version_a"])
    version_b = json.loads(conflict["version_b"])

    print(f"  {'─'*56}")
    print(f"  競合 ID: {conflict_id}")
    print(f"  更新 A: {version_a['source_system']} - {version_a['update_reason']}")
    print(f"  更新 B: {version_b['source_system']} - {version_b['update_reason']}")
    print(f"  {'─'*56}")
    print(f"\n  Bedrock に問い合わせ中...")

    # Bedrock に送るプロンプトを構築
    prompt = f"""あなたはデータ整合性を管理するAIシステムです。
以下の顧客レコードに対して2つのシステムから同時に更新が発生し、競合しています。
ビジネスルールに基づいて、最適な解決策を決定してください。

## ビジネスルール
{BUSINESS_RULES}

## 現在のレコード（ベース）
{json.dumps(base_record, ensure_ascii=False, indent=2)}

## 更新 A（{version_a['source_system']}）
更新理由: {version_a['update_reason']}
変更内容:
{json.dumps(version_a['changes'], ensure_ascii=False, indent=2)}

## 更新 B（{version_b['source_system']}）
更新理由: {version_b['update_reason']}
変更内容:
{json.dumps(version_b['changes'], ensure_ascii=False, indent=2)}

## 出力形式
以下の JSON 形式で回答してください。他のテキストは含めないでください。

```json
{{
  "resolved_record": {{
    "email": "選択したメールアドレス",
    "phone": "選択した電話番号",
    "address": "選択した住所",
    "contract_status": "選択した契約ステータス",
    "priority": 選択した優先度（数値）,
    "notes": "マージした備考"
  }},
  "decisions": [
    {{
      "field": "フィールド名",
      "chosen_source": "A または B またはマージ",
      "reason": "選択理由"
    }}
  ]
}}
```"""

    # Bedrock 呼び出し
    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2048, "temperature": 0.0},
    )

    result_text = response["output"]["message"]["content"][0]["text"]

    # JSON 部分を抽出
    resolution = extract_json(result_text)

    if resolution is None:
        print(f"    エラー: Bedrock の応答を解析できませんでした")
        print(f"    応答: {result_text[:300]}")
        return

    # 解決結果を表示
    resolved = resolution["resolved_record"]
    print(f"\n  ┌─────────────────────────────────────────────────────┐")
    print(f"  │ AI の判断結果                                       │")
    print(f"  ├─────────────────────────────────────────────────────┤")

    for decision in resolution.get("decisions", []):
        field = decision["field"]
        source = decision["chosen_source"]
        reason = decision["reason"]
        print(f"  │  {field}:")
        print(f"  │    採用: {source}")
        print(f"  │    理由: {reason}")
        print(f"  │")

    print(f"  └─────────────────────────────────────────────────────┘")

    print(f"\n  解決後の値:")
    for field, value in resolved.items():
        print(f"    {field}: {value}")

    # メインレコードを更新
    update_expr_parts = []
    expr_values = {}
    expr_names = {}

    for i, (field, value) in enumerate(resolved.items()):
        placeholder_name = f"#f{i}"
        placeholder_value = f":v{i}"
        update_expr_parts.append(f"{placeholder_name} = {placeholder_value}")
        expr_names[placeholder_name] = field
        expr_values[placeholder_value] = value

    # version とメタデータも更新
    update_expr_parts.append("#ver = :newver")
    update_expr_parts.append("#lub = :lub")
    update_expr_parts.append("#lua = :lua")
    expr_names["#ver"] = "version"
    expr_names["#lub"] = "last_updated_by"
    expr_names["#lua"] = "last_updated_at"
    expr_values[":newver"] = int(conflict["base_version"]) + 1
    expr_values[":lub"] = "semantic-resolution-ai"
    expr_values[":lua"] = datetime.now(timezone.utc).isoformat()

    table.update_item(
        Key={"PK": "CUSTOMER#C-1001", "SK": "PROFILE"},
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )

    # 競合レコードのステータスを更新（監査ログとして保持）
    table.update_item(
        Key={"PK": "CUSTOMER#C-1001", "SK": conflict_id},
        UpdateExpression="SET #st = :st, resolved_at = :ra, resolution = :res",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={
            ":st": "resolved",
            ":ra": datetime.now(timezone.utc).isoformat(),
            ":res": json.dumps(resolution, ensure_ascii=False),
        },
    )

    print(f"\n  メインレコードを更新しました。")
    print(f"  監査ログ: 競合 '{conflict_id}' → status: resolved")
    print()


def show_final_state(table):
    """解決後の最終状態を表示"""
    print("=" * 60)
    print("  解決後の最終レコード")
    print("=" * 60)

    response = table.get_item(Key={"PK": "CUSTOMER#C-1001", "SK": "PROFILE"})
    current = response["Item"]

    print(f"\n    顧客ID:    {current['customer_id']}")
    print(f"    名前:      {current['name']}")
    print(f"    メール:    {current['email']}")
    print(f"    電話:      {current['phone']}")
    print(f"    住所:      {current['address']}")
    print(f"    契約:      {current['contract_status']}")
    print(f"    優先度:    {current['priority']}")
    print(f"    備考:      {current['notes']}")
    print(f"    version:   {current['version']}")
    print(f"    最終更新:  {current['last_updated_by']}")
    print(f"    更新日時:  {current['last_updated_at']}")
    print()

    # 監査ログの確認方法を案内
    print("=" * 60)
    print("  監査ログの確認")
    print("=" * 60)
    print()
    print("  DynamoDB に判断根拠が記録されています。以下で確認:")
    print()
    print("  aws dynamodb query \\")
    print(f"    --table-name {TABLE_NAME} \\")
    print('    --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \\')
    print("    --expression-attribute-values '{\":pk\": {\"S\": \"CUSTOMER#C-1001\"}, \":sk\": {\"S\": \"CONFLICT#\"}}' \\")
    print("    --output json | python3 -m json.tool")
    print()


def extract_json(text):
    """テキストから JSON ブロックを抽出"""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


# ============================================================
# メイン
# ============================================================
def main():
    print("\n" + "=" * 60)
    print("  セマンティック競合解決 - Part 2: AI による解決")
    print("  Amazon Bedrock がビジネスルールに基づいて判断します")
    print("=" * 60)

    resolve_conflicts()

    print("=" * 60)
    print("  クリーンアップ")
    print("=" * 60)
    print()
    print("  終了後、テーブルを削除する場合:")
    print(f"    aws dynamodb delete-table --table-name {TABLE_NAME}")
    print()


if __name__ == "__main__":
    main()
