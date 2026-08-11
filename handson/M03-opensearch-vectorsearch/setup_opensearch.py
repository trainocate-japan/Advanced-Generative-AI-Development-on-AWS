"""
モジュール 3 補足: Amazon OpenSearch Serverless コレクションのセットアップ
- 暗号化ポリシーの作成
- ネットワークポリシーの作成
- データアクセスポリシーの作成
- ベクトル検索コレクションの作成
- コレクションが ACTIVE になるまで待機
"""

import boto3
import json
import time
import sys

# AWS クライアント
aoss = boto3.client('opensearchserverless', region_name='us-east-1')
sts = boto3.client('sts')

# 設定
COLLECTION_NAME = "legal-vector-search-demo"
REGION = 'us-east-1'

# アカウント情報
caller_identity = sts.get_caller_identity()
ACCOUNT_ID = caller_identity['Account']
PRINCIPAL_ARN = caller_identity['Arn']


def create_encryption_policy():
    """暗号化ポリシーの作成"""
    policy_name = f"{COLLECTION_NAME}-enc"
    policy = {
        "Rules": [
            {
                "ResourceType": "collection",
                "Resource": [f"collection/{COLLECTION_NAME}"]
            }
        ],
        "AWSOwnedKey": True
    }

    try:
        response = aoss.create_security_policy(
            name=policy_name,
            type='encryption',
            policy=json.dumps(policy),
            description="Encryption policy for vector search demo collection"
        )
        print(f"  ✅ 暗号化ポリシー作成: {policy_name}")
        return response
    except aoss.exceptions.ConflictException:
        print(f"  ℹ️  暗号化ポリシー既存: {policy_name}")
        return None


def create_network_policy():
    """ネットワークポリシーの作成（パブリックアクセス）"""
    policy_name = f"{COLLECTION_NAME}-net"
    policy = [
        {
            "Rules": [
                {
                    "ResourceType": "collection",
                    "Resource": [f"collection/{COLLECTION_NAME}"]
                },
                {
                    "ResourceType": "dashboard",
                    "Resource": [f"collection/{COLLECTION_NAME}"]
                }
            ],
            "AllowFromPublic": True
        }
    ]

    try:
        response = aoss.create_security_policy(
            name=policy_name,
            type='network',
            policy=json.dumps(policy),
            description="Network policy for vector search demo collection (public access)"
        )
        print(f"  ✅ ネットワークポリシー作成: {policy_name}")
        return response
    except aoss.exceptions.ConflictException:
        print(f"  ℹ️  ネットワークポリシー既存: {policy_name}")
        return None


def create_data_access_policy():
    """データアクセスポリシーの作成"""
    policy_name = f"{COLLECTION_NAME}-access"
    policy = [
        {
            "Rules": [
                {
                    "ResourceType": "collection",
                    "Resource": [f"collection/{COLLECTION_NAME}"],
                    "Permission": [
                        "aoss:CreateCollectionItems",
                        "aoss:UpdateCollectionItems",
                        "aoss:DescribeCollectionItems"
                    ]
                },
                {
                    "ResourceType": "index",
                    "Resource": [f"index/{COLLECTION_NAME}/*"],
                    "Permission": [
                        "aoss:CreateIndex",
                        "aoss:DeleteIndex",
                        "aoss:UpdateIndex",
                        "aoss:DescribeIndex",
                        "aoss:ReadDocument",
                        "aoss:WriteDocument"
                    ]
                }
            ],
            "Principal": [PRINCIPAL_ARN],
            "Description": "Data access policy for vector search demo"
        }
    ]

    try:
        response = aoss.create_access_policy(
            name=policy_name,
            type='data',
            policy=json.dumps(policy),
            description="Data access policy for vector search demo collection"
        )
        print(f"  ✅ データアクセスポリシー作成: {policy_name}")
        print(f"     Principal: {PRINCIPAL_ARN}")
        return response
    except aoss.exceptions.ConflictException:
        print(f"  ℹ️  データアクセスポリシー既存: {policy_name}")
        return None


def create_collection():
    """ベクトル検索コレクションの作成"""
    try:
        response = aoss.create_collection(
            name=COLLECTION_NAME,
            type='VECTORSEARCH',
            description="Vector search demo collection for M03 hands-on lab"
        )
        collection_id = response['createCollectionDetail']['id']
        print(f"  ✅ コレクション作成開始: {COLLECTION_NAME} (ID: {collection_id})")
        return collection_id
    except aoss.exceptions.ConflictException:
        # 既存コレクションの ID を取得
        collections = aoss.list_collections(
            collectionFilters={'name': COLLECTION_NAME}
        )
        if collections['collectionSummaries']:
            collection_id = collections['collectionSummaries'][0]['id']
            print(f"  ℹ️  コレクション既存: {COLLECTION_NAME} (ID: {collection_id})")
            return collection_id
        raise


def wait_for_collection(collection_id):
    """コレクションが ACTIVE になるまで待機"""
    print("\n  ⏳ コレクションが ACTIVE になるまで待機中...")
    print("     （通常 1〜3 分かかります）")

    max_wait = 300  # 最大5分
    elapsed = 0
    interval = 10

    while elapsed < max_wait:
        response = aoss.batch_get_collection(ids=[collection_id])
        if response['collectionDetails']:
            status = response['collectionDetails'][0]['status']
            if status == 'ACTIVE':
                endpoint = response['collectionDetails'][0]['collectionEndpoint']
                print(f"\n  ✅ コレクション ACTIVE!")
                print(f"     エンドポイント: {endpoint}")
                return endpoint
            elif status == 'FAILED':
                print(f"\n  ❌ コレクション作成失敗")
                sys.exit(1)
            else:
                print(f"     状態: {status} ({elapsed}秒経過)")

        time.sleep(interval)
        elapsed += interval

    print(f"\n  ❌ タイムアウト: {max_wait}秒以内に ACTIVE になりませんでした")
    sys.exit(1)


def save_config(collection_id, endpoint):
    """設定情報をファイルに保存"""
    config = {
        "collection_name": COLLECTION_NAME,
        "collection_id": collection_id,
        "endpoint": endpoint,
        "region": REGION,
        "account_id": ACCOUNT_ID,
        "principal_arn": PRINCIPAL_ARN
    }

    config_path = "opensearch_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"\n  💾 設定保存: {config_path}")
    return config


def main():
    print("=" * 60)
    print(" Amazon OpenSearch Serverless - ベクトル検索コレクション構築")
    print("=" * 60)
    print(f"\n  リージョン: {REGION}")
    print(f"  アカウント: {ACCOUNT_ID}")
    print(f"  プリンシパル: {PRINCIPAL_ARN}")
    print(f"  コレクション名: {COLLECTION_NAME}")

    # Step 1: 暗号化ポリシー
    print("\n📋 Step 1: 暗号化ポリシーの作成")
    create_encryption_policy()

    # Step 2: ネットワークポリシー
    print("\n📋 Step 2: ネットワークポリシーの作成")
    create_network_policy()

    # Step 3: データアクセスポリシー
    print("\n📋 Step 3: データアクセスポリシーの作成")
    create_data_access_policy()

    # Step 4: コレクション作成
    print("\n📋 Step 4: ベクトル検索コレクションの作成")
    collection_id = create_collection()

    # Step 5: ACTIVE 待ち
    print("\n📋 Step 5: コレクションの起動待ち")
    endpoint = wait_for_collection(collection_id)

    # Step 6: 設定保存
    print("\n📋 Step 6: 設定情報の保存")
    config = save_config(collection_id, endpoint)

    print("\n" + "=" * 60)
    print(" ✅ セットアップ完了!")
    print("=" * 60)
    print("\n  次のステップ:")
    print("    python3.12 vector_search.py --setup")
    print("    python3.12 vector_search.py --search \"契約の解除条件\"")
    print()


if __name__ == "__main__":
    main()
