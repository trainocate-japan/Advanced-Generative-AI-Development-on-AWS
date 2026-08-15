"""
パート 1 ステップ 1.1: Bedrock Guardrails の作成

医療系チャットボット向けに以下の保護機能を持つ Guardrail を作成:
- コンテンツフィルター（暴力的、性的、有害なコンテンツのブロック）
- 拒否トピック（医療診断、処方箋発行、法的助言）
- 単語フィルター（カスタムブロックワードリスト）
- PII 保護（氏名、電話番号、メールの自動マスキング）
- プロンプト攻撃フィルター（インジェクション試行の検出）

前提:
  pip install boto3
  AWS 認証情報が設定済み（us-east-1）

実行:
  python setup_guardrails.py

クリーンアップ:
  python cleanup_guardrails.py
"""

import boto3
import json
import sys
import time

REGION = "us-east-1"
GUARDRAIL_NAME = "health-chatbot-guardrail"

bedrock = boto3.client("bedrock", region_name=REGION)


# ======================================================================
# ヘルパー
# ======================================================================

def find_existing_guardrail(name):
    """既存の Guardrail を名前で検索"""
    resp = bedrock.list_guardrails()
    for g in resp.get("guardrails", []):
        if g.get("name") == name:
            return g
    return None


def wait_for_guardrail(guardrail_id, timeout=60):
    """Guardrail が READY になるまで待機"""
    for _ in range(timeout // 5):
        resp = bedrock.get_guardrail(guardrailIdentifier=guardrail_id)
        status = resp.get("status")
        if status == "READY":
            return resp
        if status == "FAILED":
            raise Exception(f"Guardrail FAILED: {resp.get('failureReasons')}")
        print(f"      ステータス: {status} ... 待機中")
        time.sleep(5)
    raise TimeoutError("Guardrail がタイムアウトしました")


# ======================================================================
# 1. Guardrail の作成
# ======================================================================

def create_guardrail():
    """Bedrock Guardrail を作成"""
    print("\n  [1] Guardrail の作成")
    print("  " + "-" * 55)

    # 既存チェック
    existing = find_existing_guardrail(GUARDRAIL_NAME)
    if existing:
        guardrail_id = existing["id"]
        print(f"    → 既存の Guardrail を使用: {guardrail_id}")
        detail = bedrock.get_guardrail(guardrailIdentifier=guardrail_id)
        print(f"      Status: {detail.get('status')}")
        return detail

    # ----- コンテンツフィルター設定（Standard ティア: 日本語対応） -----
    content_policy = {
        "filtersConfig": [
            {
                "type": "SEXUAL",
                "inputStrength": "HIGH",
                "outputStrength": "HIGH",
            },
            {
                "type": "VIOLENCE",
                "inputStrength": "HIGH",
                "outputStrength": "HIGH",
            },
            {
                "type": "HATE",
                "inputStrength": "HIGH",
                "outputStrength": "HIGH",
            },
            {
                "type": "INSULTS",
                "inputStrength": "HIGH",
                "outputStrength": "HIGH",
            },
            {
                "type": "MISCONDUCT",
                "inputStrength": "HIGH",
                "outputStrength": "HIGH",
            },
            {
                "type": "PROMPT_ATTACK",
                "inputStrength": "HIGH",
                "outputStrength": "NONE",
            },
        ],
        "tierConfig": {
            "tierName": "STANDARD",
        },
    }

    # ----- 拒否トピック設定（Standard ティア: 日本語対応） -----
    topic_policy = {
        "topicsConfig": [
            {
                "name": "medical-diagnosis",
                "definition": "ユーザーの症状に基づいて特定の病名を診断すること。"
                              "病気の確定診断、病名の特定、検査結果の解釈を含む。",
                "examples": [
                    "この症状から考えられる病名を教えてください",
                    "私は糖尿病でしょうか？",
                    "血液検査の結果、この数値は何を意味しますか",
                ],
                "type": "DENY",
            },
            {
                "name": "prescription",
                "definition": "特定の薬の処方や投与量の指示。"
                              "処方箋の発行、薬の推奨、投薬スケジュールの指示を含む。",
                "examples": [
                    "この症状にはどの薬を飲めばいいですか",
                    "抗生物質を処方してください",
                    "この薬の量を増やしてもいいですか",
                ],
                "type": "DENY",
            },
            {
                "name": "legal-advice",
                "definition": "法的助言の提供。医療訴訟、保険請求、"
                              "法的責任に関する具体的なアドバイスを含む。",
                "examples": [
                    "医療ミスで訴えることはできますか",
                    "保険会社を訴える方法を教えてください",
                    "この治療の法的リスクは何ですか",
                ],
                "type": "DENY",
            },
        ],
        "tierConfig": {
            "tierName": "STANDARD",
        },
    }

    # ----- 単語フィルター設定 -----
    word_policy = {
        "wordsConfig": [
            {"text": "自殺方法"},
            {"text": "違法薬物の入手"},
            {"text": "爆弾の作り方"},
        ],
        "managedWordListsConfig": [
            {"type": "PROFANITY"},
        ],
    }

    # ----- PII 保護設定 -----
    sensitive_info_policy = {
        "piiEntitiesConfig": [
            {"type": "NAME", "action": "ANONYMIZE"},
            {"type": "PHONE", "action": "ANONYMIZE"},
            {"type": "EMAIL", "action": "ANONYMIZE"},
            {"type": "US_SOCIAL_SECURITY_NUMBER", "action": "BLOCK"},
            {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
        ],
    }

    # Guardrail 作成（Standard ティア + クロスリージョン推論）
    response = bedrock.create_guardrail(
        name=GUARDRAIL_NAME,
        description="医療系チャットボット向け安全性ガードレール - "
                    "有害コンテンツ、PII、プロンプト攻撃からの保護",
        topicPolicyConfig=topic_policy,
        contentPolicyConfig=content_policy,
        wordPolicyConfig=word_policy,
        sensitiveInformationPolicyConfig=sensitive_info_policy,
        crossRegionConfig={
            "guardrailProfileIdentifier": "us.guardrail.v1:0",
        },
        blockedInputMessaging=(
            "申し訳ありませんが、このリクエストにはお応えできません。"
            "当システムは一般的な健康情報の提供のみを行っており、"
            "医療診断や処方は行いません。医師にご相談ください。"
        ),
        blockedOutputsMessaging=(
            "申し訳ありませんが、安全性の観点からこの応答は提供できません。"
            "別の質問をお試しください。"
        ),
    )

    guardrail_id = response["guardrailId"]
    print(f"    ✓ Guardrail 作成完了")
    print(f"      ID:      {guardrail_id}")
    print(f"      ARN:     {response['guardrailArn']}")
    print(f"      Version: {response['version']}")

    # READY まで待機
    print(f"\n    READY になるまで待機...")
    detail = wait_for_guardrail(guardrail_id)
    print(f"    ✓ Guardrail READY")

    return detail


# ======================================================================
# 2. 設定内容の確認
# ======================================================================

def show_guardrail_config(guardrail_id):
    """Guardrail の設定内容を表示"""
    print("\n  [2] Guardrail 設定内容の確認")
    print("  " + "-" * 55)

    detail = bedrock.get_guardrail(guardrailIdentifier=guardrail_id)

    print(f"    名前: {detail['name']}")
    print(f"    ID:   {detail['guardrailId']}")
    print(f"    説明: {detail.get('description', 'N/A')}")

    # コンテンツフィルター
    content = detail.get("contentPolicy", {})
    filters = content.get("filters", [])
    print(f"\n    コンテンツフィルター ({len(filters)} 件):")
    for f in filters:
        print(f"      • {f['type']}: 入力={f['inputStrength']}, "
              f"出力={f['outputStrength']}")

    # トピックポリシー
    topics = detail.get("topicPolicy", {}).get("topics", [])
    print(f"\n    拒否トピック ({len(topics)} 件):")
    for t in topics:
        print(f"      • {t['name']}: {t['definition'][:40]}...")

    # 単語フィルター
    word_policy = detail.get("wordPolicy", {})
    words = word_policy.get("words", [])
    managed = word_policy.get("managedWordLists", [])
    print(f"\n    単語フィルター:")
    print(f"      カスタム単語: {len(words)} 件")
    print(f"      マネージドリスト: {[m['type'] for m in managed]}")

    # PII 保護
    sensitive = detail.get("sensitiveInformationPolicy", {})
    pii = sensitive.get("piiEntities", [])
    print(f"\n    PII 保護 ({len(pii)} 件):")
    for p in pii:
        print(f"      • {p['type']}: {p['action']}")

    # ブロックメッセージ
    print(f"\n    入力ブロックメッセージ:")
    print(f"      {detail.get('blockedInputMessaging', 'N/A')[:60]}...")
    print(f"\n    出力ブロックメッセージ:")
    print(f"      {detail.get('blockedOutputsMessaging', 'N/A')[:60]}...")


# ======================================================================
# 3. Guardrail バージョンの作成
# ======================================================================

def create_version(guardrail_id):
    """Guardrail のバージョンを作成（本番使用向け）"""
    print("\n  [3] Guardrail バージョンの作成")
    print("  " + "-" * 55)

    response = bedrock.create_guardrail_version(
        guardrailIdentifier=guardrail_id,
        description="初回バージョン - 医療チャットボット用",
    )

    version = response["version"]
    print(f"    ✓ バージョン作成完了: v{version}")
    print(f"    → デモでは DRAFT を使用します")

    return version


# ======================================================================
# メイン
# ======================================================================

def main():
    print("\n")
    print("=" * 65)
    print("  Bedrock Guardrails セットアップ - 医療系チャットボット")
    print("=" * 65)

    # 1. Guardrail 作成
    detail = create_guardrail()
    guardrail_id = detail["guardrailId"]

    # 2. 設定内容の確認
    show_guardrail_config(guardrail_id)

    # 3. バージョン作成
    try:
        version = create_version(guardrail_id)
    except Exception as e:
        print(f"    ⚠ バージョン作成スキップ: {e}")
        version = "DRAFT"

    print(f"""
  {'=' * 65}
  セットアップ完了
  {'=' * 65}

  作成した Guardrail:
  • 名前:    {GUARDRAIL_NAME}
  • ID:      {guardrail_id}
  • Version: {version}

  保護機能:
  • コンテンツフィルター: 暴力/性的/憎悪/侮辱/不正行為 → HIGH
  • プロンプト攻撃:       入力検出 HIGH
  • 拒否トピック:         医療診断 / 処方箋 / 法的助言
  • 単語フィルター:       カスタム + Profanity
  • PII 保護:            氏名・電話・メール → マスキング
                          SSN・クレジットカード → ブロック

  次のステップ:
    python guardrails_demo.py

  クリーンアップ:
    python cleanup_guardrails.py
""")


if __name__ == "__main__":
    main()
