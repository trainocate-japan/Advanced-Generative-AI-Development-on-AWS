"""
モジュール 3 補足: クリーンアップスクリプト
- OpenSearch Serverless コレクションの削除
- 暗号化ポリシーの削除
- ネットワークポリシーの削除
- データアクセスポリシーの削除
- ローカル設定ファイルの削除
"""

import boto3
import json
import os
import time
import sys

# AWS クライアント
aoss = boto3.client('opensearchserverless', region_name='us-east-1')

# 設定
COLLECTION_NAME = "legal-vector-search-demo"


def load_config():
    """設定ファイルを読み込む"""
    config_path = os.path.join(os.path.dirname(__file__), "opensearch_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return None


def delete_collection(collection_id):
    """コレクションを削除"""
    try:
        aoss.delete_collection(id=collection_id)
        print(f"  ✅ コレクション削除開始: {COLLECTION_NAME} (ID: {collection_id})")
        return True
    except aoss.exceptions.ResourceNotFoundException:
        print(f"  ℹ️  コレクションが見つかりません（既に削除済み）")
        return False
    except Exception as e:
        print(f"  ❌ コレクション削除エラー: {e}")
        return False


def delete_encryption_policy():
    """暗号化ポリシーを削除"""
    policy_name = f"{COLLECTION_NAME}-enc"
    try:
        aoss.delete_security_policy(name=policy_name, type='encryption')
        print(f"  ✅ 暗号化ポリシー削除: {policy_name}")
    except aoss.exceptions.ResourceNotFoundException:
        print(f"  ℹ️  暗号化ポリシーが見つかりません: {policy_name}")
    except Exception as e:
        print(f"  ⚠️  暗号化ポリシー削除エラー: {e}")


def delete_network_policy():
    """ネットワークポリシーを削除"""
    policy_name = f"{COLLECTION_NAME}-net"
    try:
        aoss.delete_security_policy(name=policy_name, type='network')
        print(f"  ✅ ネットワークポリシー削除: {policy_name}")
    except aoss.exceptions.ResourceNotFoundException:
        print(f"  ℹ️  ネットワークポリシーが見つかりません: {policy_name}")
    except Exception as e:
        print(f"  ⚠️  ネットワークポリシー削除エラー: {e}")


def delete_data_access_policy():
    """データアクセスポリシーを削除"""
    policy_name = f"{COLLECTION_NAME}-access"
    try:
        aoss.delete_access_policy(name=policy_name, type='data')
        print(f"  ✅ データアクセスポリシー削除: {policy_name}")
    except aoss.exceptions.ResourceNotFoundException:
        print(f"  ℹ️  データアクセスポリシーが見つかりません: {policy_name}")
    except Exception as e:
        print(f"  ⚠️  データアクセスポリシー削除エラー: {e}")


def delete_local_config():
    """ローカル設定ファイルを削除"""
    config_path = os.path.join(os.path.dirname(__file__), "opensearch_config.json")
    if os.path.exists(config_path):
        os.remove(config_path)
        print(f"  ✅ ローカル設定ファイル削除: opensearch_config.json")
    else:
        print(f"  ℹ️  設定ファイルが見つかりません")


def wait_for_deletion(collection_id, timeout=120):
    """コレクション削除の完了を待機"""
    print(f"\n  ⏳ コレクション削除の完了を待機中...")
    elapsed = 0
    interval = 10

    while elapsed < timeout:
        try:
            response = aoss.batch_get_collection(ids=[collection_id])
            if response['collectionDetails']:
                status = response['collectionDetails'][0]['status']
                print(f"     状態: {status} ({elapsed}秒経過)")
                if status == 'DELETING':
                    time.sleep(interval)
                    elapsed += interval
                    continue
            else:
                print(f"  ✅ コレクション削除完了")
                return True
        except Exception:
            print(f"  ✅ コレクション削除完了")
            return True

        time.sleep(interval)
        elapsed += interval

    print(f"  ⚠️  タイムアウト: 削除はバックグラウンドで継続中")
    return False


def main():
    print("=" * 60)
    print(" クリーンアップ: OpenSearch Serverless リソースの削除")
    print("=" * 60)

    # 確認プロンプト
    print(f"\n  以下のリソースを削除します:")
    print(f"    • コレクション: {COLLECTION_NAME}")
    print(f"    • 暗号化ポリシー: {COLLECTION_NAME}-enc")
    print(f"    • ネットワークポリシー: {COLLECTION_NAME}-net")
    print(f"    • データアクセスポリシー: {COLLECTION_NAME}-access")
    print(f"    • ローカル設定ファイル: opensearch_config.json")

    if "--force" not in sys.argv:
        confirm = input("\n  続行しますか？ (y/N): ").strip().lower()
        if confirm != 'y':
            print("  キャンセルしました。")
            return

    # 設定ファイルからコレクション ID を取得
    config = load_config()
    collection_id = None
    if config:
        collection_id = config.get('collection_id')

    # コレクション ID がない場合は名前で検索
    if not collection_id:
        try:
            collections = aoss.list_collections(
                collectionFilters={'name': COLLECTION_NAME}
            )
            if collections['collectionSummaries']:
                collection_id = collections['collectionSummaries'][0]['id']
        except Exception:
            pass

    # Step 1: コレクション削除
    print("\n📋 Step 1: コレクションの削除")
    if collection_id:
        deleted = delete_collection(collection_id)
        if deleted:
            wait_for_deletion(collection_id)
    else:
        print(f"  ℹ️  コレクションが見つかりません")

    # Step 2: ポリシー削除（コレクション削除後に実行）
    print("\n📋 Step 2: セキュリティポリシーの削除")
    delete_encryption_policy()
    delete_network_policy()

    print("\n📋 Step 3: データアクセスポリシーの削除")
    delete_data_access_policy()

    # Step 4: ローカルファイル削除
    print("\n📋 Step 4: ローカル設定ファイルの削除")
    delete_local_config()

    print("\n" + "=" * 60)
    print(" ✅ クリーンアップ完了!")
    print("=" * 60)
    print("\n  すべてのリソースが削除されました。")
    print("  ※ コレクション削除がバックグラウンドで進行中の場合があります。")
    print("     AWS コンソールで確認してください:")
    print("     OpenSearch → Serverless → Collections")
    print()


if __name__ == "__main__":
    main()
