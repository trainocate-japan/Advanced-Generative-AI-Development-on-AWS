"""
モジュール 2: AWS Glue Data Quality デモ
- Glue Data Catalog テーブルの作成
- DQDL ルールセットの作成と評価
- 品質スコアの確認

前提条件:
  1. CloudFormation スタック 'glue-data-quality-demo' がデプロイ済み
     (infra/glue-data-quality-demo.yaml)
  2. サンプル CSV が S3 にアップロード済み（スタック作成時に自動実行）

使い方:
  python3.12 glue_data_quality_demo.py
"""

import boto3
import json
import time
import sys

# =============================================================================
# 設定
# =============================================================================
REGION = "us-east-1"
DATABASE_NAME = "glue_dq_demo_db"
TABLE_NAME = "customers"
RULESET_NAME = "customer_quality_rules"

glue = boto3.client('glue', region_name=REGION)


# =============================================================================
# スライドと同じ DQDL ルール定義
# =============================================================================
DQDL_RULESET = """
Rules = [
    ColumnCount = 6,
    IsComplete "customer_id",
    ColumnDataType "email" = "STRING",
    IsUnique "customer_id",
    ColumnValues "age" between 18 and 120
]
"""


def get_stack_outputs():
    """CloudFormation スタックの出力を取得"""
    cfn = boto3.client('cloudformation', region_name=REGION)
    try:
        response = cfn.describe_stacks(StackName='glue-data-quality-demo')
        outputs = {}
        for output in response['Stacks'][0].get('Outputs', []):
            outputs[output['OutputKey']] = output['OutputValue']
        return outputs
    except Exception as e:
        print(f"  ❌ スタック 'glue-data-quality-demo' が見つかりません: {e}")
        print(f"\n  先に CloudFormation スタックをデプロイしてください:")
        print(f"  aws cloudformation create-stack \\")
        print(f"    --stack-name glue-data-quality-demo \\")
        print(f"    --template-body file://glue-data-quality-demo.yaml \\")
        print(f"    --capabilities CAPABILITY_NAMED_IAM \\")
        print(f"    --region {REGION}")
        sys.exit(1)


def create_ruleset(role_arn):
    """DQDL ルールセットを作成する"""
    print(f"\n  ルールセット名: {RULESET_NAME}")
    print(f"  対象テーブル: {DATABASE_NAME}.{TABLE_NAME}")
    print(f"\n  DQDL ルール定義:")
    for line in DQDL_RULESET.strip().split('\n'):
        print(f"    {line}")

    # 既存のルールセットがあれば削除
    try:
        glue.delete_data_quality_ruleset(Name=RULESET_NAME)
        print(f"\n  (既存ルールセットを削除しました)")
    except glue.exceptions.EntityNotFoundException:
        pass

    # ルールセット作成
    glue.create_data_quality_ruleset(
        Name=RULESET_NAME,
        Description="顧客データの品質検証ルール（スライド p.8 のデモ）",
        Ruleset=DQDL_RULESET.strip(),
        TargetTable={
            'TableName': TABLE_NAME,
            'DatabaseName': DATABASE_NAME
        }
    )
    print(f"\n  ✅ ルールセット作成完了")


def start_evaluation(role_arn):
    """ルール評価を実行する"""
    print(f"\n  評価ジョブを開始中...")
    response = glue.start_data_quality_ruleset_evaluation_run(
        DataSource={
            'GlueTable': {
                'DatabaseName': DATABASE_NAME,
                'TableName': TABLE_NAME
            }
        },
        Role=role_arn,
        RulesetNames=[RULESET_NAME],
        NumberOfWorkers=2,
        Timeout=30
    )
    run_id = response['RunId']
    print(f"  Run ID: {run_id}")
    return run_id


def wait_for_completion(run_id):
    """評価完了を待機する"""
    print(f"\n  評価実行中（Glue ジョブが起動するため 2〜5 分かかります）...")
    
    while True:
        response = glue.get_data_quality_ruleset_evaluation_run(RunId=run_id)
        status = response['Status']
        
        if status in ('SUCCEEDED', 'FAILED', 'STOPPED', 'TIMEOUT'):
            print(f"  ステータス: {status}")
            return response
        
        elapsed = ""
        if 'StartedOn' in response:
            import datetime
            delta = datetime.datetime.now(datetime.timezone.utc) - response['StartedOn']
            elapsed = f" (経過: {int(delta.total_seconds())}秒)"
        
        print(f"    ... {status}{elapsed}", flush=True)
        time.sleep(30)


def get_results(run_id):
    """評価結果を取得する"""
    response = glue.get_data_quality_ruleset_evaluation_run(RunId=run_id)
    
    if response['Status'] != 'SUCCEEDED':
        print(f"  ❌ 評価失敗: {response.get('ErrorString', 'Unknown error')}")
        return None
    
    # 結果を取得
    result_ids = response.get('ResultIds', [])
    if not result_ids:
        print("  結果が見つかりません")
        return None
    
    results = []
    for result_id in result_ids:
        result = glue.get_data_quality_result(ResultId=result_id)
        results.append(result)
    
    return results


def display_results(results):
    """結果を表示する"""
    print(f"\n{'─' * 70}")
    print("  評価結果")
    print(f"{'─' * 70}")
    
    for result in results:
        score = result.get('Score', 0)
        rule_results = result.get('RuleResults', [])
        
        print(f"\n  総合スコア: {score:.0%}")
        print(f"  ルール数: {len(rule_results)}")
        
        print(f"\n  {'ルール':<45} {'結果':<10} {'評価メトリクス'}")
        print(f"  {'─' * 70}")
        
        passed = 0
        failed = 0
        for rule in rule_results:
            name = rule.get('Name', 'Unknown')
            result_status = rule.get('Result', 'UNKNOWN')
            desc = rule.get('Description', '')
            metric = rule.get('EvaluatedMetrics', {})
            
            icon = "✅" if result_status == 'PASS' else "❌"
            metric_str = json.dumps(metric) if metric else ""
            
            print(f"  {icon} {name:<43} {result_status:<10} {metric_str[:40]}")
            
            if result_status == 'PASS':
                passed += 1
            else:
                failed += 1
        
        print(f"\n  合格: {passed} / 不合格: {failed} / 合計: {passed + failed}")


def explain_rules():
    """ルールの意味を解説する"""
    print(f"""
  ┌────────────────────────────────────────────────────────────────┐
  │  DQDL ルール解説                                               │
  ├────────────────────────────────────────────────────────────────┤
  │  ColumnCount = 6          → カラム数が6であること               │
  │  IsComplete "customer_id" → customer_id に NULL がないこと      │
  │  ColumnDataType "email" = "STRING" → email が文字列型          │
  │  IsUnique "customer_id"   → customer_id に重複がないこと        │
  │  ColumnValues "age" between 18 and 120 → 年齢が18-120の範囲    │
  └────────────────────────────────────────────────────────────────┘

  サンプルデータには意図的に以下の品質問題を含めています:
  • C005: email が空（IsComplete ルールは customer_id 対象なので通過）
  • C008: age = 150（ColumnValues "age" between 18 and 120 に違反）
  • C009: name が空（ルール対象外のため通過）
  • C011: membership_type = "gold"（ルール対象外のため通過）
""")


def main():
    print("=" * 70)
    print("  AWS Glue Data Quality デモ")
    print("=" * 70)

    # スタック出力を取得
    print("\n[1/5] CloudFormation スタック確認...")
    outputs = get_stack_outputs()
    role_arn = outputs.get('GlueRoleArn', '')
    bucket_name = outputs.get('DataBucketName', '')
    print(f"  ✅ スタック確認OK")
    print(f"  IAM ロール: {role_arn.split('/')[-1]}")
    print(f"  S3 バケット: {bucket_name}")

    # ルール解説
    print(f"\n{'─' * 70}")
    print("[2/5] DQDL ルールセット作成")
    print(f"{'─' * 70}")
    create_ruleset(role_arn)
    explain_rules()

    # 評価実行
    print(f"{'─' * 70}")
    print("[3/5] ルール評価の実行")
    print(f"{'─' * 70}")
    run_id = start_evaluation(role_arn)

    # 完了待ち
    print(f"\n{'─' * 70}")
    print("[4/5] 評価完了待機")
    print(f"{'─' * 70}")
    run_result = wait_for_completion(run_id)

    # 結果取得
    print(f"\n{'─' * 70}")
    print("[5/5] 結果確認")
    print(f"{'─' * 70}")
    
    if run_result['Status'] == 'SUCCEEDED':
        results = get_results(run_id)
        if results:
            display_results(results)
    else:
        print(f"  ❌ 評価が正常に完了しませんでした: {run_result['Status']}")
        if 'ErrorString' in run_result:
            print(f"  エラー: {run_result['ErrorString']}")

    # まとめ
    print(f"\n\n{'=' * 70}")
    print("  まとめ")
    print(f"{'=' * 70}")
    print("""
  AWS Glue Data Quality のポイント:

  1. DQDL (Data Quality Definition Language) でルールを宣言的に定義
  2. Glue ETL パイプラインに組み込んで自動実行可能
  3. ルール違反時にアラート → 品質問題を早期検出
  4. 品質スコアの傾向をモニタリングしプロアクティブに対処

  クリーンアップ:
    aws cloudformation delete-stack --stack-name glue-data-quality-demo
""")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
