"""
モジュール 3: Bedrock ナレッジベースのセットアップスクリプト
- S3 データソースの設定
- ナレッジベースの作成
- データソースの同期
"""

import boto3
import json
import time
import sys

# AWS クライアント
bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')
sts = boto3.client('sts')
iam = boto3.client('iam')
s3 = boto3.client('s3')

# アカウント情報
ACCOUNT_ID = sts.get_caller_identity()['Account']
REGION = 'us-east-1'
BUCKET_NAME = f"legal-kb-demo-{ACCOUNT_ID}"
KB_NAME = "legal-knowledge-base-demo"
KB_DESCRIPTION = "法律文書ナレッジベース（デモ用）"
EMBEDDING_MODEL_ARN = f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"


def create_kb_role():
    """ナレッジベース用の IAM ロールを作成"""
    role_name = "AmazonBedrockKBRole-LegalDemo"

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": ACCOUNT_ID}
                }
            }
        ]
    }

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": [EMBEDDING_MODEL_ARN]
            },
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::{BUCKET_NAME}",
                    f"arn:aws:s3:::{BUCKET_NAME}/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "aoss:APIAccessAll"
                ],
                "Resource": ["*"]
            }
        ]
    }

    try:
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for Bedrock Knowledge Base - Legal Demo"
        )
        role_arn = response['Role']['Arn']

        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="BedrockKBPolicy",
            PolicyDocument=json.dumps(policy)
        )

        print(f"  ✅ IAM ロール作成: {role_arn}")
        time.sleep(10)  # ロールの伝播を待つ
        return role_arn

    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{role_name}"
        print(f"  ℹ IAM ロール既存: {role_arn}")
        return role_arn


def create_knowledge_base(role_arn):
    """ナレッジベースを作成"""
    print(f"\n  ▶ ナレッジベースを作成中...")

    try:
        response = bedrock_agent.create_knowledge_base(
            name=KB_NAME,
            description=KB_DESCRIPTION,
            roleArn=role_arn,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": EMBEDDING_MODEL_ARN,
                    "embeddingModelConfiguration": {
                        "bedrockEmbeddingModelConfiguration": {
                            "dimensions": 1024
                        }
                    }
                }
            },
            storageConfiguration={
                "type": "OPENSEARCH_SERVERLESS",
                "opensearchServerlessConfiguration": {
                    "collectionArn": "auto",  # 自動プロビジョニング
                    "vectorIndexName": "legal-docs-index",
                    "fieldMapping": {
                        "vectorField": "embedding",
                        "textField": "text",
                        "metadataField": "metadata"
                    }
                }
            }
        )

        kb_id = response['knowledgeBase']['knowledgeBaseId']
        print(f"  ✅ ナレッジベース作成: {kb_id}")
        return kb_id

    except Exception as e:
        if "already exists" in str(e).lower():
            # 既存の KB を検索
            kbs = bedrock_agent.list_knowledge_bases()
            for kb in kbs.get('knowledgeBaseSummaries', []):
                if kb['name'] == KB_NAME:
                    print(f"  ℹ ナレッジベース既存: {kb['knowledgeBaseId']}")
                    return kb['knowledgeBaseId']
        print(f"  ❌ エラー: {e}")
        return None


def create_data_source(kb_id):
    """データソースを作成"""
    print(f"\n  ▶ データソースを作成中...")

    try:
        response = bedrock_agent.create_data_source(
            knowledgeBaseId=kb_id,
            name="legal-documents",
            description="法律文書コレクション",
            dataSourceConfiguration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{BUCKET_NAME}",
                    "inclusionPrefixes": ["documents/"]
                }
            },
            vectorIngestionConfiguration={
                "chunkingConfiguration": {
                    "chunkingStrategy": "HIERARCHICAL",
                    "hierarchicalChunkingConfiguration": {
                        "levelConfigurations": [
                            {"maxTokens": 1500},  # 親チャンク
                            {"maxTokens": 300}    # 子チャンク
                        ],
                        "overlapTokens": 60
                    }
                }
            }
        )

        ds_id = response['dataSource']['dataSourceId']
        print(f"  ✅ データソース作成: {ds_id}")
        return ds_id

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        return None


def sync_data_source(kb_id, ds_id):
    """データソースを同期"""
    print(f"\n  ▶ データソースを同期中...")

    try:
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id
        )

        job_id = response['ingestionJob']['ingestionJobId']
        print(f"  同期ジョブ開始: {job_id}")

        # 同期完了を待機
        while True:
            status_response = bedrock_agent.get_ingestion_job(
                knowledgeBaseId=kb_id,
                dataSourceId=ds_id,
                ingestionJobId=job_id
            )
            status = status_response['ingestionJob']['status']
            print(f"    ステータス: {status}", end="\r")

            if status in ['COMPLETE', 'FAILED']:
                break
            time.sleep(5)

        if status == 'COMPLETE':
            stats = status_response['ingestionJob'].get('statistics', {})
            print(f"\n  ✅ 同期完了!")
            print(f"    処理ドキュメント数: {stats.get('numberOfDocumentsScanned', 'N/A')}")
            print(f"    インデックス済み: {stats.get('numberOfNewDocumentsIndexed', 'N/A')}")
        else:
            print(f"\n  ❌ 同期失敗: {status}")
            failure = status_response['ingestionJob'].get('failureReasons', [])
            for reason in failure:
                print(f"    理由: {reason}")

    except Exception as e:
        print(f"  ❌ エラー: {e}")


def main():
    """メイン実行"""
    print("=" * 70)
    print("  Bedrock ナレッジベース セットアップ")
    print("=" * 70)
    print(f"\n  アカウント: {ACCOUNT_ID}")
    print(f"  リージョン: {REGION}")
    print(f"  バケット: {BUCKET_NAME}")

    # S3 バケットの確認
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"  ✅ S3 バケット確認済み")
    except Exception:
        print(f"\n  ❌ S3 バケット '{BUCKET_NAME}' が見つかりません。")
        print(f"  先に以下を実行してください:")
        print(f"    aws s3 mb s3://{BUCKET_NAME}")
        print(f"    aws s3 cp sample-docs/ s3://{BUCKET_NAME}/documents/ --recursive")
        sys.exit(1)

    # 1. IAM ロール作成
    print(f"\n{'─' * 70}")
    print("  Step 1: IAM ロール作成")
    role_arn = create_kb_role()

    # 2. ナレッジベース作成
    print(f"\n{'─' * 70}")
    print("  Step 2: ナレッジベース作成")
    kb_id = create_knowledge_base(role_arn)
    if not kb_id:
        print("  ナレッジベースの作成に失敗しました。")
        sys.exit(1)

    # 3. データソース作成
    print(f"\n{'─' * 70}")
    print("  Step 3: データソース作成")
    ds_id = create_data_source(kb_id)
    if not ds_id:
        print("  データソースの作成に失敗しました。")
        sys.exit(1)

    # 4. 同期
    print(f"\n{'─' * 70}")
    print("  Step 4: データ同期")
    sync_data_source(kb_id, ds_id)

    # 結果の表示
    print(f"\n\n{'=' * 70}")
    print("  セットアップ完了!")
    print(f"{'=' * 70}")
    print(f"\n  ナレッジベース ID: {kb_id}")
    print(f"  データソース ID: {ds_id}")
    print(f"\n  次のステップ:")
    print(f"  1. rag_basic.py の KNOWLEDGE_BASE_ID を '{kb_id}' に更新")
    print(f"  2. python rag_basic.py を実行して動作確認")


if __name__ == "__main__":
    main()
