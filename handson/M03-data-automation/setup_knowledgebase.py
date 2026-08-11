"""
モジュール 3: Bedrock ナレッジベースのセットアップスクリプト
- Amazon S3 Vectors（ベクトルバケット + ベクトルインデックス）の作成
- ナレッジベースの作成（S3 Vectors をベクトルストアとして使用）
- S3 データソースの設定と同期
"""

import boto3
import json
import time
import sys

# AWS クライアント
bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')
s3vectors = boto3.client('s3vectors', region_name='us-east-1')
sts = boto3.client('sts')
iam = boto3.client('iam')
s3 = boto3.client('s3')

# アカウント情報
ACCOUNT_ID = sts.get_caller_identity()['Account']
REGION = 'us-east-1'
BUCKET_NAME = f"legal-kb-demo-{ACCOUNT_ID}"
VECTOR_BUCKET_NAME = "legal-vectors-demo"
VECTOR_INDEX_NAME = "legal-docs-index"
KB_NAME = "legal-knowledge-base-demo"
KB_DESCRIPTION = "法律文書ナレッジベース（デモ用）- S3 Vectors 使用"
EMBEDDING_MODEL_ARN = f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024


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

    # S3 Vectors 用の IAM ポリシー（s3vectors: 名前空間を使用）
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
                "Sid": "S3VectorsAccess",
                "Effect": "Allow",
                "Action": [
                    "s3vectors:CreateIndex",
                    "s3vectors:PutVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:DeleteVectors",
                    "s3vectors:GetIndex",
                    "s3vectors:ListIndexes"
                ],
                "Resource": [
                    f"arn:aws:s3vectors:{REGION}:{ACCOUNT_ID}:vector-bucket/{VECTOR_BUCKET_NAME}",
                    f"arn:aws:s3vectors:{REGION}:{ACCOUNT_ID}:vector-bucket/{VECTOR_BUCKET_NAME}/*"
                ]
            }
        ]
    }

    try:
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for Bedrock Knowledge Base - Legal Demo (S3 Vectors)"
        )
        role_arn = response['Role']['Arn']

        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="BedrockKBPolicy-S3Vectors",
            PolicyDocument=json.dumps(policy)
        )

        print(f"  ✅ IAM ロール作成: {role_arn}")
        time.sleep(10)  # ロールの伝播を待つ
        return role_arn

    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{role_name}"
        print(f"  ℹ IAM ロール既存: {role_arn}")

        # ポリシーを更新（S3 Vectors 用に変更されている可能性があるため）
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="BedrockKBPolicy-S3Vectors",
            PolicyDocument=json.dumps(policy)
        )
        print(f"  ✅ IAM ポリシー更新済み")
        return role_arn


def create_vector_bucket():
    """S3 Vectors のベクトルバケットを作成"""
    print(f"\n  ▶ S3 ベクトルバケットを作成中...")

    try:
        response = s3vectors.create_vector_bucket(
            vectorBucketName=VECTOR_BUCKET_NAME
        )
        vector_bucket_arn = response['vectorBucket']['vectorBucketArn']
        print(f"  ✅ ベクトルバケット作成: {vector_bucket_arn}")
        return vector_bucket_arn

    except s3vectors.exceptions.ConflictException:
        # 既存のバケットを取得
        response = s3vectors.get_vector_bucket(
            vectorBucketName=VECTOR_BUCKET_NAME
        )
        vector_bucket_arn = response['vectorBucket']['vectorBucketArn']
        print(f"  ℹ ベクトルバケット既存: {vector_bucket_arn}")
        return vector_bucket_arn

    except Exception as e:
        print(f"  ❌ ベクトルバケット作成エラー: {e}")
        return None


def create_vector_index(vector_bucket_arn):
    """S3 Vectors のベクトルインデックスを作成"""
    print(f"\n  ▶ ベクトルインデックスを作成中...")
    print(f"    次元数: {EMBEDDING_DIMENSIONS}")
    print(f"    距離メトリック: cosine")
    print(f"    データ型: float32")

    try:
        response = s3vectors.create_index(
            vectorBucketName=VECTOR_BUCKET_NAME,
            indexName=VECTOR_INDEX_NAME,
            dimension=EMBEDDING_DIMENSIONS,
            distanceMetric="cosine",
            dataType="float32",
            metadataConfiguration={
                "nonFilterableMetadataKeys": [
                    "AMAZON_BEDROCK_TEXT_CHUNK",
                    "AMAZON_BEDROCK_METADATA"
                ]
            }
        )
        index_arn = response['index']['indexArn']
        print(f"  ✅ ベクトルインデックス作成: {index_arn}")
        return index_arn

    except s3vectors.exceptions.ConflictException:
        # 既存のインデックスを取得
        response = s3vectors.get_index(
            vectorBucketName=VECTOR_BUCKET_NAME,
            indexName=VECTOR_INDEX_NAME
        )
        index_arn = response['index']['indexArn']
        print(f"  ℹ ベクトルインデックス既存: {index_arn}")
        return index_arn

    except Exception as e:
        print(f"  ❌ ベクトルインデックス作成エラー: {e}")
        return None


def create_knowledge_base(role_arn, vector_bucket_arn, index_arn):
    """S3 Vectors をベクトルストアとしてナレッジベースを作成"""
    print(f"\n  ▶ ナレッジベースを作成中...")
    print(f"    ベクトルストア: S3 Vectors")
    print(f"    埋め込みモデル: Titan Embeddings V2 (1024次元)")

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
                            "dimensions": EMBEDDING_DIMENSIONS
                        }
                    }
                }
            },
            storageConfiguration={
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": {
                    "vectorBucketArn": vector_bucket_arn,
                    "indexArn": index_arn,
                    "indexName": VECTOR_INDEX_NAME
                }
            }
        )

        kb_id = response['knowledgeBase']['knowledgeBaseId']
        print(f"  ✅ ナレッジベース作成: {kb_id}")
        return kb_id

    except Exception as e:
        if "already exists" in str(e).lower() or "conflict" in str(e).lower():
            # 既存の KB を検索
            kbs = bedrock_agent.list_knowledge_bases()
            for kb in kbs.get('knowledgeBaseSummaries', []):
                if kb['name'] == KB_NAME:
                    print(f"  ℹ ナレッジベース既存: {kb['knowledgeBaseId']}")
                    return kb['knowledgeBaseId']
        print(f"  ❌ エラー: {e}")
        return None


def create_data_source(kb_id):
    """データソース（S3）を作成"""
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
    """データソースを同期（インジェスション）"""
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
    print("  Bedrock ナレッジベース セットアップ（S3 Vectors）")
    print("=" * 70)
    print(f"\n  アカウント: {ACCOUNT_ID}")
    print(f"  リージョン: {REGION}")
    print(f"  ドキュメント用 S3 バケット: {BUCKET_NAME}")
    print(f"  ベクトルバケット名: {VECTOR_BUCKET_NAME}")
    print(f"  ベクトルインデックス名: {VECTOR_INDEX_NAME}")

    print(f"""
  ┌──────────────────────────────────────────────────────────────────┐
  │  Amazon S3 Vectors について                                      │
  │                                                                   │
  │  - OpenSearch Serverless 比で最大 90% のコスト削減               │
  │  - 20 億ベクトルまでスケール可能                                 │
  │  - Bedrock ナレッジベースとシームレスに統合                      │
  │  - サーバーレス（インフラ管理不要）                              │
  │  - コールドクエリでもサブ秒レイテンシー                          │
  └──────────────────────────────────────────────────────────────────┘
    """)

    # S3 バケット（ドキュメント用）の確認
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"  ✅ ドキュメント用 S3 バケット確認済み")
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

    # 2. S3 ベクトルバケット作成
    print(f"\n{'─' * 70}")
    print("  Step 2: S3 ベクトルバケット作成")
    vector_bucket_arn = create_vector_bucket()
    if not vector_bucket_arn:
        print("  ベクトルバケットの作成に失敗しました。")
        sys.exit(1)

    # 3. ベクトルインデックス作成
    print(f"\n{'─' * 70}")
    print("  Step 3: ベクトルインデックス作成")
    index_arn = create_vector_index(vector_bucket_arn)
    if not index_arn:
        print("  ベクトルインデックスの作成に失敗しました。")
        sys.exit(1)

    # 4. ナレッジベース作成
    print(f"\n{'─' * 70}")
    print("  Step 4: ナレッジベース作成（S3 Vectors 連携）")
    kb_id = create_knowledge_base(role_arn, vector_bucket_arn, index_arn)
    if not kb_id:
        print("  ナレッジベースの作成に失敗しました。")
        sys.exit(1)

    # 5. データソース作成
    print(f"\n{'─' * 70}")
    print("  Step 5: データソース作成（階層型チャンキング）")
    ds_id = create_data_source(kb_id)
    if not ds_id:
        print("  データソースの作成に失敗しました。")
        sys.exit(1)

    # 6. データ同期
    print(f"\n{'─' * 70}")
    print("  Step 6: データ同期（インジェスション）")
    sync_data_source(kb_id, ds_id)

    # 完了サマリー
    print(f"\n{'═' * 70}")
    print("  セットアップ完了!")
    print(f"{'═' * 70}")
    print(f"\n  ナレッジベース ID: {kb_id}")
    print(f"  ベクトルストア: S3 Vectors ({VECTOR_BUCKET_NAME}/{VECTOR_INDEX_NAME})")
    print(f"\n  次のステップ:")
    print(f"    1. rag_basic.py の KNOWLEDGE_BASE_ID を '{kb_id}' に設定")
    print(f"    2. python3.12 rag_basic.py を実行")
    print(f"    3. python3.12 rag_retrieve.py で検索結果の詳細を確認")

    # 設定ファイルに KB ID を保存
    config = {
        "knowledge_base_id": kb_id,
        "vector_bucket_name": VECTOR_BUCKET_NAME,
        "vector_index_name": VECTOR_INDEX_NAME,
        "vector_bucket_arn": vector_bucket_arn,
        "index_arn": index_arn,
        "region": REGION,
        "document_bucket": BUCKET_NAME
    }
    with open("kb_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n  設定を kb_config.json に保存しました。")


if __name__ == "__main__":
    main()
