"""
モジュール 8: モニタリング環境のセットアップ
- Bedrock モデル呼び出しログの有効化（S3 + CloudWatch Logs）
- CloudWatch ダッシュボードの作成
- CloudWatch アラームの設定（異常検知含む）
- SNS トピックによるアラート通知
"""

import boto3
import json
import time
from datetime import datetime

# クライアント初期化
bedrock = boto3.client('bedrock', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')
logs = boto3.client('logs', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
sns = boto3.client('sns', region_name='us-east-1')
iam = boto3.client('iam', region_name='us-east-1')
sts = boto3.client('sts', region_name='us-east-1')

# リソース命名
ACCOUNT_ID = sts.get_caller_identity()['Account']
TIMESTAMP = datetime.now().strftime('%Y%m%d')
S3_BUCKET = f"bedrock-monitoring-logs-{ACCOUNT_ID}-{TIMESTAMP}"
LOG_GROUP = "/aws/bedrock/model-invocations"
DASHBOARD_NAME = "Bedrock-GenAI-Monitoring"
SNS_TOPIC_NAME = "bedrock-monitoring-alerts"
NAMESPACE = "GenAI/Bedrock"


# ============================================================
# ステップ 1: S3 バケットの作成（ログ保存用）
# ============================================================

def setup_s3_bucket():
    """モデル呼び出しログ保存用の S3 バケットを作成"""
    print("\n" + "─" * 70)
    print("  ステップ 1: S3 バケットの作成（ログ保存用）")
    print("─" * 70)

    try:
        s3.create_bucket(
            Bucket=S3_BUCKET,
            CreateBucketConfiguration={'LocationConstraint': 'us-east-1'}
        )
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"  ℹ️  バケット既存: {S3_BUCKET}")
    except Exception as e:
        # us-east-1 では LocationConstraint 不要な場合がある
        if "IllegalLocationConstraintException" in str(e):
            try:
                s3.create_bucket(Bucket=S3_BUCKET)
            except s3.exceptions.BucketAlreadyOwnedByYou:
                pass
        else:
            raise

    # ライフサイクルルール設定（コスト管理）
    s3.put_bucket_lifecycle_configuration(
        Bucket=S3_BUCKET,
        LifecycleConfiguration={
            'Rules': [
                {
                    'ID': 'TransitionToIA',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': 'bedrock-logs/'},
                    'Transitions': [
                        {'Days': 30, 'StorageClass': 'STANDARD_IA'},
                        {'Days': 90, 'StorageClass': 'GLACIER'},
                    ],
                    'Expiration': {'Days': 365},
                }
            ]
        }
    )

    print(f"  ✅ S3 バケット作成完了: {S3_BUCKET}")
    print(f"     ライフサイクル: 30日→IA / 90日→Glacier / 365日→削除")
    return S3_BUCKET


# ============================================================
# ステップ 2: CloudWatch Logs ロググループの作成
# ============================================================

def setup_cloudwatch_logs():
    """モデル呼び出しログ用の CloudWatch Logs ロググループを作成"""
    print("\n" + "─" * 70)
    print("  ステップ 2: CloudWatch Logs ロググループの作成")
    print("─" * 70)

    try:
        logs.create_log_group(logGroupName=LOG_GROUP)
        print(f"  ✅ ロググループ作成: {LOG_GROUP}")
    except logs.exceptions.ResourceAlreadyExistsException:
        print(f"  ℹ️  ロググループ既存: {LOG_GROUP}")

    # 保持期間の設定（90日）
    logs.put_retention_policy(
        logGroupName=LOG_GROUP,
        retentionInDays=90
    )
    print(f"     保持期間: 90日")

    return LOG_GROUP


# ============================================================
# ステップ 3: Bedrock モデル呼び出しログの有効化
# ============================================================

def setup_model_invocation_logging():
    """Bedrock モデル呼び出しログを S3 と CloudWatch Logs の両方に出力"""
    print("\n" + "─" * 70)
    print("  ステップ 3: Bedrock モデル呼び出しログの有効化")
    print("─" * 70)

    logging_config = {
        "textDataDeliveryEnabled": True,
        "imageDataDeliveryEnabled": False,
        "embeddingDataDeliveryEnabled": True,
        "s3Config": {
            "bucketName": S3_BUCKET,
            "keyPrefix": "bedrock-logs/"
        },
        "cloudWatchConfig": {
            "logGroupName": LOG_GROUP,
            "roleArn": f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockLoggingRole",
            "largeDataDeliveryS3Config": {
                "bucketName": S3_BUCKET,
                "keyPrefix": "bedrock-logs/large-data/"
            }
        }
    }

    print(f"\n  設定内容:")
    print(f"    テキストデータ配信: 有効")
    print(f"    画像データ配信: 無効")
    print(f"    埋め込みデータ配信: 有効")
    print(f"    S3 出力先: s3://{S3_BUCKET}/bedrock-logs/")
    print(f"    CloudWatch Logs: {LOG_GROUP}")

    try:
        bedrock.put_model_invocation_logging_configuration(
            loggingConfig=logging_config
        )
        print(f"\n  ✅ モデル呼び出しログ有効化完了")
    except Exception as e:
        print(f"\n  ⚠️  ログ設定エラー: {e}")
        print(f"     IAM ロール 'BedrockLoggingRole' が必要です。")
        print(f"     手動で設定する場合: Bedrock コンソール → Settings → Model invocation logging")

    # 設定確認
    try:
        config = bedrock.get_model_invocation_logging_configuration()
        current = config.get('loggingConfig', {})
        print(f"\n  現在の設定:")
        print(f"    テキスト配信: {current.get('textDataDeliveryEnabled', 'N/A')}")
        print(f"    S3 バケット: {current.get('s3Config', {}).get('bucketName', 'N/A')}")
        print(f"    CloudWatch: {current.get('cloudWatchConfig', {}).get('logGroupName', 'N/A')}")
    except Exception as e:
        print(f"  ℹ️  設定確認スキップ: {e}")


# ============================================================
# ステップ 4: SNS トピックの作成（アラート通知用）
# ============================================================

def setup_sns_topic():
    """アラート通知用の SNS トピックを作成"""
    print("\n" + "─" * 70)
    print("  ステップ 4: SNS トピック作成（アラート通知用）")
    print("─" * 70)

    response = sns.create_topic(
        Name=SNS_TOPIC_NAME,
        Tags=[
            {'Key': 'Project', 'Value': 'GenAI-Monitoring'},
            {'Key': 'Module', 'Value': 'M08'},
        ]
    )
    topic_arn = response['TopicArn']
    print(f"  ✅ SNS トピック作成: {topic_arn}")
    print(f"     ※ サブスクリプション（メール等）は手動で追加してください")

    return topic_arn


# ============================================================
# ステップ 5: CloudWatch アラームの設定
# ============================================================

def setup_cloudwatch_alarms(topic_arn):
    """モニタリング用の CloudWatch アラームを設定"""
    print("\n" + "─" * 70)
    print("  ステップ 5: CloudWatch アラームの設定")
    print("─" * 70)

    alarms = [
        {
            "name": "Bedrock-HighLatency-P95",
            "description": "モデル呼び出しレイテンシー P95 が 10秒を超過",
            "metric": "ModelLatency",
            "threshold": 10000,  # ミリ秒
            "comparison": "GreaterThanThreshold",
            "period": 300,
            "evaluation_periods": 3,
            "statistic": "p95",
        },
        {
            "name": "Bedrock-HighErrorRate",
            "description": "エラー率が 1% を超過",
            "metric": "ErrorRate",
            "threshold": 1.0,
            "comparison": "GreaterThanThreshold",
            "period": 300,
            "evaluation_periods": 2,
            "statistic": "Average",
        },
        {
            "name": "Bedrock-HighHallucinationRate",
            "description": "ハルシネーション率が 5% を超過",
            "metric": "HallucinationRate",
            "threshold": 5.0,
            "comparison": "GreaterThanThreshold",
            "period": 600,
            "evaluation_periods": 2,
            "statistic": "Average",
        },
        {
            "name": "Bedrock-CostSpike",
            "description": "推定コストが閾値を超過（異常なコスト増加）",
            "metric": "EstimatedCost",
            "threshold": 10.0,  # USD/時間
            "comparison": "GreaterThanThreshold",
            "period": 3600,
            "evaluation_periods": 1,
            "statistic": "Sum",
        },
    ]

    for alarm in alarms:
        try:
            # 拡張統計（p95 等）の場合
            if alarm["statistic"].startswith("p"):
                cloudwatch.put_metric_alarm(
                    AlarmName=alarm["name"],
                    AlarmDescription=alarm["description"],
                    Namespace=NAMESPACE,
                    MetricName=alarm["metric"],
                    ExtendedStatistic=alarm["statistic"],
                    Period=alarm["period"],
                    EvaluationPeriods=alarm["evaluation_periods"],
                    Threshold=alarm["threshold"],
                    ComparisonOperator=alarm["comparison"],
                    AlarmActions=[topic_arn],
                    Tags=[
                        {'Key': 'Project', 'Value': 'GenAI-Monitoring'},
                    ]
                )
            else:
                cloudwatch.put_metric_alarm(
                    AlarmName=alarm["name"],
                    AlarmDescription=alarm["description"],
                    Namespace=NAMESPACE,
                    MetricName=alarm["metric"],
                    Statistic=alarm["statistic"],
                    Period=alarm["period"],
                    EvaluationPeriods=alarm["evaluation_periods"],
                    Threshold=alarm["threshold"],
                    ComparisonOperator=alarm["comparison"],
                    AlarmActions=[topic_arn],
                    Tags=[
                        {'Key': 'Project', 'Value': 'GenAI-Monitoring'},
                    ]
                )

            print(f"  ✅ アラーム作成: {alarm['name']}")
            print(f"     条件: {alarm['metric']} {alarm['statistic']} > {alarm['threshold']}")

        except Exception as e:
            print(f"  ⚠️  アラーム作成エラー ({alarm['name']}): {e}")

    # 異常検知アラーム
    print(f"\n  異常検知アラームの設定:")
    try:
        cloudwatch.put_anomaly_detector(
            Namespace=NAMESPACE,
            MetricName="InputTokensPerRequest",
            Stat="Average",
        )
        print(f"  ✅ 異常検知: InputTokensPerRequest（トークン消費量の急増検知）")
    except Exception as e:
        print(f"  ⚠️  異常検知設定エラー: {e}")

    try:
        cloudwatch.put_anomaly_detector(
            Namespace=NAMESPACE,
            MetricName="ModelLatency",
            Stat="Average",
        )
        print(f"  ✅ 異常検知: ModelLatency（レイテンシー劣化の検知）")
    except Exception as e:
        print(f"  ⚠️  異常検知設定エラー: {e}")


# ============================================================
# ステップ 6: CloudWatch ダッシュボードの作成
# ============================================================

def setup_dashboard():
    """モニタリングダッシュボードを作成"""
    print("\n" + "─" * 70)
    print("  ステップ 6: CloudWatch ダッシュボード作成")
    print("─" * 70)

    dashboard_body = {
        "widgets": [
            # トークン使用量
            {
                "type": "metric",
                "x": 0, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "トークン使用量",
                    "region": "us-east-1",
                    "metrics": [
                        [NAMESPACE, "InputTokensPerRequest", {"stat": "Average", "label": "入力トークン（平均）"}],
                        [NAMESPACE, "OutputTokensPerRequest", {"stat": "Average", "label": "出力トークン（平均）"}],
                        [NAMESPACE, "InputTokensPerRequest", {"stat": "Sum", "label": "入力トークン（合計）", "yAxis": "right"}],
                    ],
                    "period": 300,
                    "view": "timeSeries",
                }
            },
            # レイテンシー
            {
                "type": "metric",
                "x": 12, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "モデルレイテンシー (ms)",
                    "region": "us-east-1",
                    "metrics": [
                        [NAMESPACE, "ModelLatency", {"stat": "p50", "label": "P50"}],
                        [NAMESPACE, "ModelLatency", {"stat": "p95", "label": "P95"}],
                        [NAMESPACE, "ModelLatency", {"stat": "p99", "label": "P99"}],
                    ],
                    "period": 300,
                    "view": "timeSeries",
                    "annotations": {
                        "horizontal": [
                            {"value": 10000, "label": "SLA: 10秒", "color": "#ff0000"}
                        ]
                    }
                }
            },
            # コスト推移
            {
                "type": "metric",
                "x": 0, "y": 6, "width": 12, "height": 6,
                "properties": {
                    "title": "推定コスト (USD)",
                    "region": "us-east-1",
                    "metrics": [
                        [NAMESPACE, "EstimatedCost", {"stat": "Sum", "label": "推定コスト", "period": 3600}],
                    ],
                    "period": 3600,
                    "view": "timeSeries",
                }
            },
            # 品質メトリクス
            {
                "type": "metric",
                "x": 12, "y": 6, "width": 12, "height": 6,
                "properties": {
                    "title": "応答品質メトリクス",
                    "region": "us-east-1",
                    "metrics": [
                        [NAMESPACE, "HallucinationRate", {"stat": "Average", "label": "ハルシネーション率 (%)"}],
                        [NAMESPACE, "FaithfulnessScore", {"stat": "Average", "label": "忠実性スコア"}],
                        [NAMESPACE, "AnswerRelevancy", {"stat": "Average", "label": "回答関連性"}],
                    ],
                    "period": 600,
                    "view": "timeSeries",
                    "annotations": {
                        "horizontal": [
                            {"value": 5, "label": "警告: 5%", "color": "#ff9900"},
                            {"value": 10, "label": "緊急: 10%", "color": "#ff0000"},
                        ]
                    }
                }
            },
            # エラー率
            {
                "type": "metric",
                "x": 0, "y": 12, "width": 12, "height": 6,
                "properties": {
                    "title": "エラー率 & リクエスト数",
                    "region": "us-east-1",
                    "metrics": [
                        [NAMESPACE, "ErrorRate", {"stat": "Average", "label": "エラー率 (%)"}],
                        [NAMESPACE, "RequestCount", {"stat": "Sum", "label": "リクエスト数", "yAxis": "right"}],
                    ],
                    "period": 300,
                    "view": "timeSeries",
                }
            },
            # ビジネスメトリクス
            {
                "type": "metric",
                "x": 12, "y": 12, "width": 12, "height": 6,
                "properties": {
                    "title": "ビジネスメトリクス",
                    "region": "us-east-1",
                    "metrics": [
                        [NAMESPACE, "TaskCompletionRate", {"stat": "Average", "label": "タスク完了率 (%)"}],
                        [NAMESPACE, "UserSatisfactionScore", {"stat": "Average", "label": "ユーザー満足度"}],
                        [NAMESPACE, "EscalationRate", {"stat": "Average", "label": "エスカレーション率 (%)"}],
                    ],
                    "period": 3600,
                    "view": "timeSeries",
                }
            },
        ]
    }

    try:
        cloudwatch.put_dashboard(
            DashboardName=DASHBOARD_NAME,
            DashboardBody=json.dumps(dashboard_body)
        )
        print(f"  ✅ ダッシュボード作成完了: {DASHBOARD_NAME}")
        print(f"     URL: https://us-east-1.console.aws.amazon.com/cloudwatch/home"
              f"?region=us-east-1#dashboards:name={DASHBOARD_NAME}")
        print(f"\n  ウィジェット一覧:")
        print(f"    📊 トークン使用量（入力/出力、平均/合計）")
        print(f"    ⏱️  モデルレイテンシー（P50/P95/P99）")
        print(f"    💰 推定コスト（時間別）")
        print(f"    🎯 応答品質メトリクス（ハルシネーション率、忠実性、関連性）")
        print(f"    ❌ エラー率 & リクエスト数")
        print(f"    📈 ビジネスメトリクス（タスク完了率、満足度、エスカレーション）")
    except Exception as e:
        print(f"  ⚠️  ダッシュボード作成エラー: {e}")


# ============================================================
# セットアップサマリー
# ============================================================

def print_summary():
    """セットアップ完了サマリーを表示"""
    print("\n\n" + "=" * 70)
    print("  セットアップ完了サマリー")
    print("=" * 70)
    print(f"""
  ┌─────────────────────────────────────────────────────────────────────┐
  │ リソース                │ 設定値                                    │
  ├─────────────────────────┼───────────────────────────────────────────┤
  │ S3 バケット             │ {S3_BUCKET:<41} │
  │ CloudWatch ロググループ │ {LOG_GROUP:<41} │
  │ ダッシュボード          │ {DASHBOARD_NAME:<41} │
  │ SNS トピック            │ {SNS_TOPIC_NAME:<41} │
  │ カスタム名前空間        │ {NAMESPACE:<41} │
  └─────────────────────────┴───────────────────────────────────────────┘

  次のステップ:
  1. monitoring_demo.py を実行してカスタムメトリクスを発行
  2. CloudWatch ダッシュボードでリアルタイム監視を確認
  3. hallucination_detection.py で品質モニタリングを体験

  アーキテクチャ概要:
  ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
  │ Bedrock API  │────▶│ Invocation Logs  │────▶│ S3 + CW Logs │
  └──────────────┘     └──────────────────┘     └──────────────┘
         │                                              │
         ▼                                              ▼
  ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
  │ Custom       │────▶│ CloudWatch       │────▶│ Dashboard    │
  │ Metrics      │     │ Alarms           │     │ + Alerts     │
  └──────────────┘     └──────────────────┘     └──────────────┘
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 8: モニタリング環境セットアップ")
    print("🔷" * 35)
    print("\n  Bedrock モデル呼び出しログとモニタリング基盤を構築します。")
    print()

    # Step 1: S3 バケット
    setup_s3_bucket()

    # Step 2: CloudWatch Logs
    setup_cloudwatch_logs()

    # Step 3: Bedrock ログ有効化
    setup_model_invocation_logging()

    # Step 4: SNS トピック
    topic_arn = setup_sns_topic()

    # Step 5: アラーム設定
    setup_cloudwatch_alarms(topic_arn)

    # Step 6: ダッシュボード
    setup_dashboard()

    # サマリー
    print_summary()
