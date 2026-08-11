"""
モジュール 2: Step Functions パイプラインデモ
- ステートマシンの実行と結果確認
- 並列処理パターンの可視化
- 各ステージのレイテンシー分析

前提条件:
  CloudFormation スタック 'stepfunctions-pipeline-demo' がデプロイ済み

使い方:
  python3.12 stepfunctions_demo.py
"""

import boto3
import json
import time
import sys
from datetime import datetime, timezone

# =============================================================================
# 設定
# =============================================================================
REGION = "us-east-1"
STACK_NAME = "stepfunctions-pipeline-demo"

sfn = boto3.client('stepfunctions', region_name=REGION)
cfn = boto3.client('cloudformation', region_name=REGION)
dynamodb = boto3.client('dynamodb', region_name=REGION)

# テストデータ
TEST_INPUT = {
    "records": [
        {
            "id": "rec-001",
            "timestamp": "2024-11-15T10:30:00Z",
            "content": "田中太郎です。電話番号は090-1234-5678です。先日の診察について質問があります。処方された薬の副作用が気になります。メールアドレスはtanaka@example.comです。",
            "category": "medical_inquiry",
            "language": "ja"
        },
        {
            "id": "rec-002",
            "timestamp": "2024-11-15T11:00:00Z",
            "content": "予約の変更をお願いします。次回は来週の火曜日に変更したいです。担当医の山田先生でお願いします。",
            "category": "appointment",
            "language": "ja"
        },
        {
            "id": "rec-003",
            "timestamp": "2024-11-15T14:00:00Z",
            "content": "私のマイナンバーは123456789012です。保険証番号は12345678で、住所は東京都渋谷区神宮前1-2-3です。検査結果を郵送してください。",
            "category": "personal_info",
            "language": "ja"
        },
        {
            "id": "rec-004",
            "timestamp": "",
            "content": "",
            "category": "general",
            "language": "ja"
        }
    ]
}


def get_state_machine_arn():
    """CloudFormation スタックからステートマシン ARN を取得"""
    try:
        response = cfn.describe_stacks(StackName=STACK_NAME)
        outputs = {o['OutputKey']: o['OutputValue'] for o in response['Stacks'][0].get('Outputs', [])}
        return outputs.get('StateMachineArn')
    except Exception as e:
        print(f"  ❌ スタック '{STACK_NAME}' が見つかりません: {e}")
        print(f"\n  先に CloudFormation スタックをデプロイしてください:")
        print(f"  aws cloudformation create-stack \\")
        print(f"    --stack-name {STACK_NAME} \\")
        print(f"    --template-body file://stepfunctions-pipeline-demo.yaml \\")
        print(f"    --capabilities CAPABILITY_NAMED_IAM \\")
        print(f"    --region {REGION}")
        sys.exit(1)


def start_execution(state_machine_arn, input_data):
    """ステートマシンを実行する"""
    response = sfn.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(input_data, ensure_ascii=False)
    )
    return response['executionArn']


def wait_for_execution(execution_arn):
    """実行完了を待機する"""
    while True:
        response = sfn.describe_execution(executionArn=execution_arn)
        status = response['status']

        if status in ('SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED'):
            return response

        elapsed = ""
        if 'startDate' in response:
            delta = datetime.now(timezone.utc) - response['startDate']
            elapsed = f" (経過: {int(delta.total_seconds())}秒)"

        print(f"    ... {status}{elapsed}", flush=True)
        time.sleep(5)


def get_execution_history(execution_arn):
    """実行履歴を取得してステージごとのレイテンシーを分析"""
    response = sfn.get_execution_history(
        executionArn=execution_arn,
        maxResults=100
    )
    return response['events']


def analyze_execution(execution_response):
    """実行結果を分析する"""
    start_time = execution_response['startDate']
    stop_time = execution_response.get('stopDate', datetime.now(timezone.utc))
    total_duration = (stop_time - start_time).total_seconds()

    output = None
    if execution_response['status'] == 'SUCCEEDED' and 'output' in execution_response:
        output = json.loads(execution_response['output'])

    return {
        "status": execution_response['status'],
        "duration": total_duration,
        "output": output
    }


def display_results(analysis):
    """結果を表示する"""
    output = analysis.get("output", [])
    if not output:
        print("  結果が取得できませんでした")
        return

    print(f"\n  処理結果（{len(output)} レコード）:")
    print(f"  {'─' * 60}")

    for i, record_result in enumerate(output):
        if isinstance(record_result, dict):
            status = record_result.get("status", "")
            record_id = record_result.get("record_id", f"rec-{i+1:03d}")

            if status == "skipped":
                print(f"  ⏭ {record_id}: スキップ（検証失敗）")
            elif status == "error":
                print(f"  ❌ {record_id}: エラー")
            elif status == "saved":
                print(f"  ✅ {record_id}: 処理完了 → DynamoDB 保存済み")
            else:
                print(f"  ℹ {record_id}: {json.dumps(record_result, ensure_ascii=False)[:80]}")


def display_dynamodb_results():
    """DynamoDB から処理結果を取得して表示"""
    try:
        response = dynamodb.scan(
            TableName='sfn-pipeline-results',
            Limit=10
        )
        items = response.get('Items', [])
        if not items:
            print("\n  DynamoDB にまだ結果がありません")
            return

        print(f"\n  DynamoDB 保存結果 ({len(items)} 件):")
        print(f"  {'─' * 60}")
        for item in items:
            record_id = item.get('record_id', {}).get('S', '')
            pii_count = item.get('pii_count', {}).get('N', '0')
            tokens = int(item.get('input_tokens', {}).get('N', '0')) + int(item.get('output_tokens', {}).get('N', '0'))
            print(f"  • {record_id}: PII {pii_count}件検出 | トークン: {tokens}")
    except Exception as e:
        print(f"\n  DynamoDB 結果取得エラー: {e}")


def main():
    print("=" * 70)
    print("  Step Functions パイプラインデモ")
    print("=" * 70)

    # ステートマシン ARN 取得
    print("\n[1/4] ステートマシン確認...")
    state_machine_arn = get_state_machine_arn()
    print(f"  ✅ {state_machine_arn.split(':')[-1]}")

    # パイプライン構造の表示
    print(f"\n  パイプライン構造:")
    print("""
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Validate │───▶│ PII Mask │───▶│ Bedrock  │───▶│  Save    │
  │          │    │          │    │ Analyze  │    │ (DynDB)  │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
       │
       │ 検証失敗
       ▼
  ┌──────────┐
  │ Skipped  │
  └──────────┘

  ※ Map ステートにより複数レコードを並列処理（MaxConcurrency=3）
""")

    # テストデータ表示
    print(f"[2/4] テストデータ ({len(TEST_INPUT['records'])} レコード):")
    for rec in TEST_INPUT['records']:
        content_preview = rec['content'][:40] + "..." if len(rec['content']) > 40 else rec['content']
        valid_mark = "✓" if rec['content'] and rec['timestamp'] else "✗"
        print(f"  {valid_mark} {rec['id']}: {content_preview}")

    # 実行
    print(f"\n[3/4] ステートマシン実行中...")
    execution_arn = start_execution(state_machine_arn, TEST_INPUT)
    print(f"  Execution ARN: ...{execution_arn[-40:]}")

    # 完了待ち
    execution_response = wait_for_execution(execution_arn)
    analysis = analyze_execution(execution_response)

    print(f"\n  ステータス: {analysis['status']}")
    print(f"  所要時間: {analysis['duration']:.1f} 秒")

    # 結果表示
    print(f"\n[4/4] 結果確認")
    print(f"{'─' * 70}")
    display_results(analysis)
    display_dynamodb_results()

    # まとめ
    print(f"\n\n{'=' * 70}")
    print("  まとめ")
    print(f"{'=' * 70}")
    print(f"""
  Step Functions パイプラインのメリット:

  1. 可視化: コンソールで各ステージの実行状態がリアルタイムに見える
  2. エラー処理: Retry + Catch で宣言的にエラーハンドリング
  3. 並列処理: Map ステートで複数レコードを同時処理（MaxConcurrency で制御）
  4. 疎結合: 各 Lambda が独立しており、個別にテスト・更新可能

  コンソールで実行フローを確認:
  https://{REGION}.console.aws.amazon.com/states/home#/statemachines/view/{state_machine_arn}

  クリーンアップ:
    aws cloudformation delete-stack --stack-name {STACK_NAME}
""")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
