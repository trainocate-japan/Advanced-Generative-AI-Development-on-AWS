"""
モジュール 3: 会話型ナレッジアシスタント
- セッション管理による会話コンテキストの保持
- マルチターン会話（前の質問を踏まえた追加質問）
- 引用付き回答の生成
- ガードレール統合による回答品質制御
"""

import boto3
import json
import time
import uuid
import os

# AWS クライアント
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# 設定読み込み
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "kb_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

config = load_config()
KNOWLEDGE_BASE_ID = config.get("knowledge_base_id", "YOUR_KB_ID")
MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"


# ═══════════════════════════════════════════════════════════════════════
#  ナレッジアシスタント クラス
# ═══════════════════════════════════════════════════════════════════════

class KnowledgeAssistant:
    """
    会話型ナレッジアシスタント

    機能:
    - セッション管理によるマルチターン会話
    - RetrieveAndGenerate API を使用した引用付き回答
    - 会話履歴に基づくコンテキスト理解
    - 回答品質の制御（検索パラメータ調整）
    """

    def __init__(self, kb_id=None, model_arn=None):
        self.kb_id = kb_id or KNOWLEDGE_BASE_ID
        self.model_arn = model_arn or MODEL_ARN
        self.session_id = None
        self.conversation_history = []
        self.turn_count = 0

    def start_session(self):
        """新しい会話セッションを開始"""
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
        self.turn_count = 0
        return self.session_id

    def ask(self, question, num_results=5, temperature=0.2):
        """
        ナレッジベースに質問し、引用付きの回答を取得

        Parameters:
            question: ユーザーの質問
            num_results: 検索するチャンク数
            temperature: 生成の温度パラメータ

        Returns:
            回答テキスト、引用情報、メタデータ
        """
        self.turn_count += 1

        try:
            # RetrieveAndGenerate API 呼び出し
            params = {
                "input": {"text": question},
                "retrieveAndGenerateConfiguration": {
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": self.kb_id,
                        "modelArn": self.model_arn,
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": num_results,
                                "overrideSearchType": "SEMANTIC"
                            }
                        },
                        "generationConfiguration": {
                            "inferenceConfig": {
                                "textInferenceConfig": {
                                    "temperature": temperature,
                                    "maxTokens": 1024
                                }
                            }
                        }
                    }
                }
            }

            # セッション ID があればマルチターン会話として処理
            if self.session_id and self.turn_count > 1:
                params["sessionId"] = self.session_id

            response = bedrock_agent_runtime.retrieve_and_generate(**params)

            # セッション ID を更新
            self.session_id = response.get('sessionId', self.session_id)

            # 回答の抽出
            answer = response['output']['text']
            citations = response.get('citations', [])

            # 引用情報の整理
            citation_details = []
            for citation in citations:
                for ref in citation.get('retrievedReferences', []):
                    location = ref.get('location', {})
                    s3_loc = location.get('s3Location', {})
                    citation_details.append({
                        "source": s3_loc.get('uri', 'N/A'),
                        "text_snippet": ref.get('content', {}).get('text', '')[:100]
                    })

            # 会話履歴に保存
            self.conversation_history.append({
                "turn": self.turn_count,
                "question": question,
                "answer": answer,
                "citations": len(citation_details)
            })

            return {
                "success": True,
                "answer": answer,
                "citations": citation_details,
                "turn": self.turn_count,
                "session_id": self.session_id
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_history(self):
        """会話履歴を取得"""
        return self.conversation_history


# ═══════════════════════════════════════════════════════════════════════
#  アクセス制御付きアシスタント
# ═══════════════════════════════════════════════════════════════════════

class AccessControlledAssistant(KnowledgeAssistant):
    """
    アクセス制御付きナレッジアシスタント

    ユーザーのロールに基づいてアクセス可能なドキュメントカテゴリを制限
    """

    # ロール別アクセス制御マトリックス
    ACCESS_MATRIX = {
        "partner": ["contract", "employment_law", "privacy", "ip", "confidential"],
        "associate": ["contract", "employment_law", "privacy", "ip"],
        "paralegal": ["contract", "employment_law"],
        "intern": ["contract"],
    }

    def __init__(self, user_role="associate", **kwargs):
        super().__init__(**kwargs)
        self.user_role = user_role
        self.allowed_categories = self.ACCESS_MATRIX.get(user_role, [])

    def ask(self, question, **kwargs):
        """アクセス制御を適用した質問"""

        # スコープ外の質問を検出
        if self._is_out_of_scope(question):
            return {
                "success": True,
                "answer": "申し訳ありませんが、その質問は現在のナレッジベースの範囲外です。"
                          "法律文書に関する質問をお願いします。",
                "citations": [],
                "access_denied": False,
                "out_of_scope": True
            }

        result = super().ask(question, **kwargs)

        # アクセス制御のチェック（引用元がアクセス可能か確認）
        if result.get("success") and result.get("citations"):
            filtered_citations = []
            for citation in result["citations"]:
                source = citation.get("source", "")
                if self._is_accessible(source):
                    filtered_citations.append(citation)

            if not filtered_citations and result["citations"]:
                return {
                    "success": True,
                    "answer": "この情報へのアクセス権限がありません。"
                              f"現在のロール（{self.user_role}）では、"
                              f"以下のカテゴリのみ閲覧可能です: {', '.join(self.allowed_categories)}",
                    "citations": [],
                    "access_denied": True
                }

            result["citations"] = filtered_citations

        return result

    def _is_accessible(self, source_uri):
        """ソースがアクセス可能か判定"""
        for category in self.allowed_categories:
            if category in source_uri.lower():
                return True
        return True  # メタデータがない場合はデフォルト許可

    def _is_out_of_scope(self, question):
        """質問がスコープ外かを判定"""
        out_of_scope_keywords = ["天気", "料理", "スポーツ", "ゲーム", "映画"]
        return any(kw in question for kw in out_of_scope_keywords)


# ═══════════════════════════════════════════════════════════════════════
#  デモ関数
# ═══════════════════════════════════════════════════════════════════════

def demo_multiturn_conversation():
    """マルチターン会話のデモ"""
    print("=" * 70)
    print("  デモ 1: マルチターン会話型アシスタント")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_multiturn()
        return

    assistant = KnowledgeAssistant()
    assistant.start_session()

    # 会話シナリオ
    conversation = [
        "契約書の解除条件について教えてください",
        "その場合の損害賠償はどうなりますか",
        "解除の通知期間は何日前ですか",
        "これらの条件は雇用契約にも適用されますか",
    ]

    print(f"\n  セッション ID: {assistant.session_id[:8]}...")
    print(f"  シナリオ: 契約解除に関する段階的な質問\n")

    for question in conversation:
        print(f"  ┌─ ターン {assistant.turn_count + 1} ─────────────────────────────")
        print(f"  │ 👤 {question}")

        start = time.time()
        result = assistant.ask(question)
        elapsed = time.time() - start

        if result["success"]:
            # 回答を整形表示
            answer_lines = result["answer"][:200].split('\n')
            for line in answer_lines:
                print(f"  │ 🤖 {line}")
            if len(result["answer"]) > 200:
                print(f"  │    ...")

            print(f"  │")
            print(f"  │ 📎 引用: {len(result['citations'])}件 | ⏱ {elapsed:.2f}秒")
            if result["citations"]:
                for cit in result["citations"][:2]:
                    source_name = cit['source'].split('/')[-1] if cit['source'] != 'N/A' else 'N/A'
                    print(f"  │    └─ {source_name}")
        else:
            print(f"  │ ❌ エラー: {result['error']}")

        print(f"  └{'─' * 60}\n")

    # 会話履歴のサマリー
    print(f"\n  ── 会話サマリー ──")
    for entry in assistant.get_history():
        print(f"  Turn {entry['turn']}: {entry['question'][:40]}... ({entry['citations']}引用)")


def demo_access_control():
    """アクセス制御のデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: アクセス制御付きアシスタント")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_access_control()
        return

    question = "機密保持契約の詳細と知的財産権の帰属について教えてください"

    roles = ["partner", "associate", "paralegal", "intern"]

    for role in roles:
        print(f"\n  ── ロール: {role} ──")
        assistant = AccessControlledAssistant(user_role=role)
        assistant.start_session()

        result = assistant.ask(question)
        if result.get("access_denied"):
            print(f"    🚫 {result['answer']}")
        elif result.get("success"):
            print(f"    ✅ 回答: {result['answer'][:100]}...")
            print(f"    引用数: {len(result.get('citations', []))}")


def demo_quality_control():
    """回答品質制御のデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: 回答品質の制御")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        demo_simulated_quality_control()
        return

    question = "従業員の残業時間の上限について詳しく教えてください"

    configs = [
        {"num_results": 3, "temperature": 0.1, "label": "精密モード（少ない検索、低温度）"},
        {"num_results": 5, "temperature": 0.3, "label": "バランスモード（標準）"},
        {"num_results": 10, "temperature": 0.7, "label": "創造モード（多い検索、高温度）"},
    ]

    for cfg in configs:
        print(f"\n  ── {cfg['label']} ──")
        assistant = KnowledgeAssistant()
        assistant.start_session()

        result = assistant.ask(question, num_results=cfg["num_results"], temperature=cfg["temperature"])
        if result["success"]:
            print(f"    回答長: {len(result['answer'])}文字 | 引用: {len(result['citations'])}件")
            print(f"    回答: {result['answer'][:150]}...")


# ═══════════════════════════════════════════════════════════════════════
#  シミュレーションモード
# ═══════════════════════════════════════════════════════════════════════

def demo_simulated_multiturn():
    """シミュレーション: マルチターン会話"""
    print(f"\n  📋 シミュレーション: マルチターン会話")
    print(f"{'─' * 70}")

    print(f"""
  セッション ID: a1b2c3d4...
  シナリオ: 契約解除に関する段階的な質問

  ┌─ ターン 1 ─────────────────────────────────────────────
  │ 👤 契約書の解除条件について教えてください
  │ 🤖 契約の解除条件は主に以下の場合に認められます：
  │    1. 相手方の重大な契約違反（催告後30日以内に是正されない場合）
  │    2. 相手方の破産手続開始の決定
  │    3. 相手方の信用不安が生じた場合
  │    なお、解除は将来に向かってのみ効力を生じます（第7条）。
  │
  │ 📎 引用: 2件 | ⏱ 1.82秒
  │    └─ contract_template.txt
  │    └─ contract_template.txt
  └──────────────────────────────────────────────────────────

  ┌─ ターン 2 ─────────────────────────────────────────────
  │ 👤 その場合の損害賠償はどうなりますか
  │ 🤖 契約解除に伴う損害賠償については第8条に規定されています：
  │    - 契約違反により解除された場合、違反当事者は相手方に
  │      生じた損害（逸失利益を含む）を賠償する責任を負います
  │    - 損害賠償額の上限は契約金額の100%と定められています
  │    - 不可抗力による解除の場合は損害賠償義務は生じません
  │
  │ 📎 引用: 2件 | ⏱ 1.56秒
  │    └─ contract_template.txt
  └──────────────────────────────────────────────────────────

  ┌─ ターン 3 ─────────────────────────────────────────────
  │ 👤 解除の通知期間は何日前ですか
  │ 🤖 契約解除の通知期間は以下の通りです：
  │    - 相手方への書面通知：30日前（催告期間）
  │    - 催告後の是正期間経過後に解除可能
  │    - 即時解除が認められる場合：破産、差押え、重大な違反
  │
  │ 📎 引用: 1件 | ⏱ 1.23秒
  │    └─ contract_template.txt
  └──────────────────────────────────────────────────────────

  ┌─ ターン 4 ─────────────────────────────────────────────
  │ 👤 これらの条件は雇用契約にも適用されますか
  │ 🤖 雇用契約（労働契約）の解除は、一般的な契約とは異なる
  │    規制が適用されます：
  │    - 労働基準法により、解雇には「客観的に合理的な理由」と
  │      「社会的相当性」が必要（解雇権濫用法理）
  │    - 解雇予告は少なくとも30日前（または30日分の平均賃金支払い）
  │    - 上記の一般契約の解除条件は、業務委託契約等には適用可能
  │
  │ 📎 引用: 3件 | ⏱ 2.11秒
  │    └─ contract_template.txt
  │    └─ employment_law.txt
  └──────────────────────────────────────────────────────────

  ポイント:
    - ターン2「その場合」→ ターン1の「契約解除」を文脈から理解
    - ターン4「これら」→ ターン1-3の条件を参照し、労働法との比較を提示
    - セッション ID により Bedrock が会話コンテキストを自動管理
    """)


def demo_simulated_access_control():
    """シミュレーション: アクセス制御"""
    print(f"\n  📋 シミュレーション: アクセス制御")
    print(f"{'─' * 70}")

    print(f"""
  質問: 「機密保持契約の詳細と知的財産権の帰属について」

  ── ロール: partner ──
    ✅ アクセス可能カテゴリ: contract, employment_law, privacy, ip, confidential
    回答: NDA（秘密保持契約）の主要条項は以下の通りです...
         知的財産権の帰属については、職務発明規定により...
    引用数: 4件

  ── ロール: associate ──
    ✅ アクセス可能カテゴリ: contract, employment_law, privacy, ip
    回答: NDA の基本条項について説明します...
         知的財産権の帰属については...
    引用数: 3件

  ── ロール: paralegal ──
    ✅ アクセス可能カテゴリ: contract, employment_law
    回答: 秘密保持契約の基本的な構成について説明します...
    引用数: 1件（IP関連の引用は除外）

  ── ロール: intern ──
    🚫 この情報へのアクセス権限がありません。
       現在のロール（intern）では、以下のカテゴリのみ閲覧可能です:
       contract

  ┌──────────────────────────────────────────────────────────────────┐
  │  アクセス制御の実装パターン                                       │
  │                                                                   │
  │  1. メタデータフィルタリング（推奨）                              │
  │     - ドキュメントにカテゴリ/機密レベルのメタデータを付与         │
  │     - Retrieve API のフィルタで検索時に制限                       │
  │     - 最も効率的（不要なチャンクを検索しない）                   │
  │                                                                   │
  │  2. ポストフィルタリング                                          │
  │     - 検索後に引用元をチェックしてフィルタ                       │
  │     - 柔軟だが、検索コストは変わらない                           │
  │                                                                   │
  │  3. ナレッジベース分割                                            │
  │     - カテゴリごとに別のナレッジベースを作成                     │
  │     - 完全な分離が可能だが、管理コスト増                         │
  └──────────────────────────────────────────────────────────────────┘
    """)


def demo_simulated_quality_control():
    """シミュレーション: 品質制御"""
    print(f"\n  📋 シミュレーション: 回答品質制御パラメータ")
    print(f"{'─' * 70}")

    print(f"""
  質問: 「従業員の残業時間の上限について詳しく教えてください」

  ── 精密モード（numberOfResults=3, temperature=0.1）──
    回答長: 180文字 | 引用: 2件
    回答: 労働基準法により、時間外労働の上限は原則として月45時間・
         年360時間です。36協定の特別条項により延長は可能ですが、
         年720時間を超えることはできません。
    特徴: 簡潔、事実に忠実、ハルシネーション最小

  ── バランスモード（numberOfResults=5, temperature=0.3）──
    回答長: 350文字 | 引用: 3件
    回答: 残業時間の上限規制について以下に説明します。
         原則: 月45時間・年360時間（36協定の範囲内）
         特別条項: 年720時間以内、単月100時間未満、
         2-6ヶ月平均80時間以内。
         違反した場合は6ヶ月以下の懲役または30万円以下の罰金。
         なお、建設業、自動車運転者等は適用猶予があります。
    特徴: 適度な詳細さ、バランスの取れた回答

  ── 創造モード（numberOfResults=10, temperature=0.7）──
    回答長: 580文字 | 引用: 5件
    回答: 従業員の残業時間上限について包括的に説明いたします。
         [法的根拠] 労働基準法第36条に基づく...
         [具体的な上限] ...
         [例外規定] ...
         [罰則] ...
         [実務上のアドバイス] 36協定の届出を確実に行い...
    特徴: 詳細だが冗長、一部推測が混じる可能性

  ┌──────────────────────────────────────────────────────────────────┐
  │  パラメータ選択の指針                                             │
  │                                                                   │
  │  用途              numberOfResults  temperature  searchType       │
  │  ─────────────────────────────────────────────────────────────   │
  │  正確な法令確認        3             0.1         SEMANTIC        │
  │  一般的な法律相談      5             0.3         SEMANTIC        │
  │  探索的リサーチ        10            0.5         SEMANTIC        │
  │  要約・概要作成        7             0.4         SEMANTIC        │
  └──────────────────────────────────────────────────────────────────┘
    """)


# ═══════════════════════════════════════════════════════════════════════
#  対話モード（インタラクティブ）
# ═══════════════════════════════════════════════════════════════════════

def interactive_mode():
    """対話モードで実行"""
    print("\n" + "=" * 70)
    print("  ナレッジアシスタント - 対話モード")
    print("=" * 70)

    if KNOWLEDGE_BASE_ID == "YOUR_KB_ID":
        print("\n  ⚠ ナレッジベース ID が設定されていません。")
        print("  デモモードで実行します。\n")
        demo_simulated_multiturn()
        return

    assistant = KnowledgeAssistant()
    assistant.start_session()

    print(f"\n  セッション開始 (ID: {assistant.session_id[:8]}...)")
    print("  質問を入力してください（'quit' で終了）\n")

    while True:
        question = input("  👤 > ").strip()
        if question.lower() in ['quit', 'exit', 'q', '終了']:
            break
        if not question:
            continue

        result = assistant.ask(question)
        if result["success"]:
            print(f"\n  🤖 {result['answer']}")
            if result["citations"]:
                print(f"\n  📎 引用元:")
                for cit in result["citations"][:3]:
                    source_name = cit['source'].split('/')[-1]
                    print(f"     └─ {source_name}")
            print()
        else:
            print(f"\n  ❌ エラー: {result['error']}\n")

    print(f"\n  セッション終了（{assistant.turn_count} ターン）")


# ═══════════════════════════════════════════════════════════════════════
#  メイン実行
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if "--interactive" in sys.argv or "-i" in sys.argv:
        interactive_mode()
    else:
        demo_multiturn_conversation()
        demo_access_control()
        demo_quality_control()
