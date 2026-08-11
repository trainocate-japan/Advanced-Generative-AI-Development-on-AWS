"""
モジュール 4: Bedrock プロンプト管理ハンズオン
- マネージドプロンプトの作成（CreatePrompt）
- バージョン管理（CreatePromptVersion）
- 複数バージョンの実行比較（Converse API + promptVariables）
- プロンプトの更新とバージョン間比較
- クリーンアップ
"""

import boto3
import json
import time

bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

MODEL_ID = "amazon.nova-pro-v1:0"
PROMPT_NAME = f"CustomerSupport-{int(time.time())}"


# ============================================================
# ステップ 1: マネージドプロンプトの作成
# ============================================================

def create_managed_prompt():
    """Bedrock プロンプト管理でプロンプトを作成する"""
    print("=" * 70)
    print("  ステップ 1: マネージドプロンプトの作成")
    print("=" * 70)

    # バリアント1: カスタマーサポート用（簡潔版）
    response = bedrock_agent.create_prompt(
        name=PROMPT_NAME,
        description="カスタマーサポート向け応答生成プロンプト（バージョン管理デモ）",
        defaultVariant="support-v1",
        variants=[
            {
                "name": "support-v1",
                "modelId": MODEL_ID,
                "templateType": "TEXT",
                "inferenceConfiguration": {
                    "text": {
                        "temperature": 0.3,
                        "maxTokens": 500
                    }
                },
                "templateConfiguration": {
                    "text": {
                        "text": (
                            "あなたはカスタマーサポート担当です。\n"
                            "お客様の問い合わせに回答してください。\n\n"
                            "お客様の問い合わせ: {{query}}"
                        ),
                        "inputVariables": [{"name": "query"}]
                    }
                }
            }
        ]
    )

    prompt_id = response["id"]
    prompt_arn = response["arn"]

    print(f"\n  ✅ プロンプト作成完了")
    print(f"     名前: {PROMPT_NAME}")
    print(f"     ID:   {prompt_id}")
    print(f"     ARN:  {prompt_arn}")
    print(f"     状態: DRAFT（ドラフト）")

    return prompt_id, prompt_arn


# ============================================================
# ステップ 2: バージョン 1 の作成
# ============================================================

def create_version_1(prompt_id):
    """ドラフトからバージョン 1 を作成"""
    print(f"\n{'─' * 70}")
    print("  ステップ 2: バージョン 1 の作成（スナップショット）")
    print(f"{'─' * 70}")

    response = bedrock_agent.create_prompt_version(
        promptIdentifier=prompt_id,
        description="v1: シンプルなカスタマーサポートプロンプト"
    )

    version = response["version"]
    version_arn = response["arn"]

    print(f"\n  ✅ バージョン 1 作成完了")
    print(f"     バージョン番号: {version}")
    print(f"     ARN: {version_arn}")
    print(f"     説明: v1: シンプルなカスタマーサポートプロンプト")

    return version, version_arn


# ============================================================
# ステップ 3: プロンプトを改善してバージョン 2 を作成
# ============================================================

def update_and_create_version_2(prompt_id):
    """プロンプトを改善してバージョン 2 を作成"""
    print(f"\n{'─' * 70}")
    print("  ステップ 3: プロンプトを改善 → バージョン 2 作成")
    print(f"{'─' * 70}")

    # ドラフトを更新（改善版プロンプト）
    bedrock_agent.update_prompt(
        promptIdentifier=prompt_id,
        name=PROMPT_NAME,
        description="カスタマーサポート向け応答生成プロンプト（改善版）",
        defaultVariant="support-v2",
        variants=[
            {
                "name": "support-v2",
                "modelId": MODEL_ID,
                "templateType": "TEXT",
                "inferenceConfiguration": {
                    "text": {
                        "temperature": 0.3,
                        "maxTokens": 600
                    }
                },
                "templateConfiguration": {
                    "text": {
                        "text": (
                            "あなたは経験豊富なカスタマーサポートの専門家です。\n\n"
                            "応答ガイドライン:\n"
                            "1. まずお客様の状況に共感を示す\n"
                            "2. 問題を簡潔に要約する\n"
                            "3. 解決策をステップバイステップで提示する\n"
                            "4. 追加の質問がないか確認する\n\n"
                            "トーン: 温かく、プロフェッショナルで、簡潔に\n"
                            "制約: 200文字以内で回答する\n\n"
                            "お客様の問い合わせ: {{query}}"
                        ),
                        "inputVariables": [{"name": "query"}]
                    }
                }
            }
        ]
    )

    print("  📝 ドラフトを改善版に更新完了")
    print("     変更点:")
    print("       • ロール定義を具体化（「経験豊富な専門家」）")
    print("       • 応答ガイドライン（4ステップ）を追加")
    print("       • トーンと制約を明示")

    # バージョン 2 を作成
    response = bedrock_agent.create_prompt_version(
        promptIdentifier=prompt_id,
        description="v2: 構造化ガイドライン付きプロンプト"
    )

    version = response["version"]
    version_arn = response["arn"]

    print(f"\n  ✅ バージョン 2 作成完了")
    print(f"     バージョン番号: {version}")
    print(f"     ARN: {version_arn}")

    return version, version_arn


# ============================================================
# ステップ 4: バージョン一覧の確認
# ============================================================

def list_versions(prompt_id):
    """プロンプトのバージョン一覧を確認"""
    print(f"\n{'─' * 70}")
    print("  ステップ 4: バージョン一覧の確認")
    print(f"{'─' * 70}")

    response = bedrock_agent.list_prompts(promptIdentifier=prompt_id)

    print(f"\n  プロンプト: {PROMPT_NAME}")
    print(f"  {'─' * 50}")
    print(f"  {'バージョン':<12} {'状態':<10} {'作成日時':<24} {'説明'}")
    print(f"  {'─' * 50}")

    for prompt in response.get("promptSummaries", []):
        version = prompt.get("version", "DRAFT")
        status = "DRAFT" if version == "DRAFT" else "PUBLISHED"
        created = prompt.get("createdAt", "")
        if created:
            created = created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created, 'strftime') else str(created)[:19]
        desc = prompt.get("description", "")[:30]
        print(f"  {version:<12} {status:<10} {created:<24} {desc}")

    print(f"  {'─' * 50}")


# ============================================================
# ステップ 5: 複数バージョンの実行と比較
# ============================================================

def invoke_prompt_version(prompt_arn, version, query):
    """特定バージョンのプロンプトを Converse API で実行"""
    # バージョン付き ARN を構築
    versioned_arn = f"{prompt_arn}:{version}"

    response = bedrock_runtime.converse(
        modelId=versioned_arn,
        promptVariables={
            "query": {"text": query}
        }
    )

    return response["output"]["message"]["content"][0]["text"]


def compare_versions(prompt_arn, v1, v2):
    """2つのバージョンの応答を比較"""
    print(f"\n{'─' * 70}")
    print("  ステップ 5: 複数バージョンの実行と比較")
    print(f"{'─' * 70}")

    test_queries = [
        "注文した商品が届かないのですが、どうすればいいですか？",
        "プランの変更方法がわかりません。",
    ]

    for query in test_queries:
        print(f"\n  📩 問い合わせ: {query}")
        print(f"  {'─' * 60}")

        # バージョン 1 で実行
        print(f"\n  【バージョン {v1}（シンプル版）】")
        try:
            response_v1 = invoke_prompt_version(prompt_arn, v1, query)
            print(f"  {response_v1[:300]}")
        except Exception as e:
            print(f"  エラー: {e}")

        time.sleep(1)

        # バージョン 2 で実行
        print(f"\n  【バージョン {v2}（改善版）】")
        try:
            response_v2 = invoke_prompt_version(prompt_arn, v2, query)
            print(f"  {response_v2[:300]}")
        except Exception as e:
            print(f"  エラー: {e}")

        print(f"\n  {'─' * 60}")
        time.sleep(1)

    print(f"""
  📊 バージョン比較のポイント:
  ┌─────────────────────────────────────────────────────────────┐
  │ v1（シンプル版）          │ v2（改善版）                    │
  ├─────────────────────────────────────────────────────────────┤
  │ • 基本的な回答            │ • 共感 → 要約 → 手順 → 確認    │
  │ • トーン指定なし          │ • 温かくプロフェッショナル      │
  │ • 長さ制約なし            │ • 200文字以内で簡潔             │
  └─────────────────────────────────────────────────────────────┘
""")


# ============================================================
# ステップ 6: 特定バージョンの詳細確認
# ============================================================

def get_version_details(prompt_id, version):
    """特定バージョンの設定内容を確認"""
    print(f"\n{'─' * 70}")
    print(f"  ステップ 6: バージョン {version} の詳細確認")
    print(f"{'─' * 70}")

    response = bedrock_agent.get_prompt(
        promptIdentifier=prompt_id,
        promptVersion=str(version)
    )

    print(f"\n  名前: {response['name']}")
    print(f"  バージョン: {response.get('version', 'DRAFT')}")
    print(f"  説明: {response.get('description', 'なし')}")
    print(f"  デフォルトバリアント: {response.get('defaultVariant', 'なし')}")

    for variant in response.get("variants", []):
        print(f"\n  バリアント: {variant['name']}")
        print(f"    モデル: {variant.get('modelId', 'N/A')}")
        print(f"    テンプレートタイプ: {variant.get('templateType', 'N/A')}")
        config = variant.get("templateConfiguration", {}).get("text", {})
        template_text = config.get("text", "")
        print(f"    テンプレート（先頭100文字）:")
        print(f"      {template_text[:100]}...")
        inf_config = variant.get("inferenceConfiguration", {}).get("text", {})
        print(f"    推論設定: temperature={inf_config.get('temperature')}, maxTokens={inf_config.get('maxTokens')}")


# ============================================================
# メイン実行
# ============================================================

def main():
    print("\n" + "=" * 70)
    print("  Bedrock プロンプト管理: バージョン管理と複数バージョン実行デモ")
    print("=" * 70)
    print(f"""
  このデモでは以下を実行します:
  1. マネージドプロンプトの作成
  2. バージョン 1 の作成（スナップショット）
  3. プロンプトを改善してバージョン 2 を作成
  4. バージョン一覧の確認
  5. 2つのバージョンを Converse API で実行・比較
  6. バージョン詳細の確認

  ※ 作成したプロンプトはコンソールで確認・削除できます
  ※ Bedrock → プロンプト管理 → "{PROMPT_NAME}" を参照
""")

    prompt_id = None
    versions = []

    try:
        # ステップ 1: プロンプト作成
        prompt_id, prompt_arn = create_managed_prompt()
        time.sleep(2)

        # ステップ 2: バージョン 1 作成
        v1, v1_arn = create_version_1(prompt_id)
        versions.append(v1)
        time.sleep(2)

        # ステップ 3: 改善してバージョン 2 作成
        v2, v2_arn = update_and_create_version_2(prompt_id)
        versions.append(v2)
        time.sleep(2)

        # ステップ 4: バージョン一覧
        list_versions(prompt_id)

        # ステップ 5: 複数バージョンの実行比較
        compare_versions(prompt_arn, v1, v2)

        # ステップ 6: バージョン詳細確認
        get_version_details(prompt_id, v2)

    except Exception as e:
        print(f"\n  ❌ エラー発生: {e}")
        import traceback
        traceback.print_exc()

    print(f"""
{'=' * 70}
  まとめ: Bedrock プロンプト管理の利点
{'=' * 70}

  ┌──────────────────────────────────────────────────────────────────┐
  │ 機能               │ メリット                                   │
  ├──────────────────────────────────────────────────────────────────┤
  │ バージョン管理     │ 変更履歴の追跡、いつでもロールバック可能   │
  │ Converse API 連携  │ プロンプトARNで直接実行、コード変更不要     │
  │ 変数テンプレート   │ 動的な値の埋め込み、再利用性の向上          │
  │ A/B テスト         │ バージョン間の品質比較が容易                │
  │ ガバナンス         │ 本番デプロイ前のレビューと承認              │
  └──────────────────────────────────────────────────────────────────┘

  運用パターン:
  • 開発: DRAFT で試行錯誤
  • テスト: バージョン作成 → staging エイリアスで検証
  • 本番: production エイリアスを更新 → 問題あればロールバック

  クリーンアップ:
  • AWS コンソール → Bedrock → プロンプト管理 → プロンプトを選択して削除
  • または: aws bedrock-agent delete-prompt --prompt-identifier <PROMPT_ID>
""")

    # プロンプトIDを表示（手動クリーンアップ用）
    if prompt_id:
        print(f"  作成されたプロンプト ID: {prompt_id}")
        print(f"  削除コマンド: aws bedrock-agent delete-prompt --prompt-identifier {prompt_id} --region us-east-1")
        print()


if __name__ == "__main__":
    main()
