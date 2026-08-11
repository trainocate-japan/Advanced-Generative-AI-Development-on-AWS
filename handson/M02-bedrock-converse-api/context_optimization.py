"""
モジュール 2: 入力最適化とコンテキスト管理
- プロンプト圧縮によるトークン効率化
- スライディングウィンドウによる会話コンテキスト管理
- 動的バッチサイジング
"""

import boto3
import json
import time

# AWS クライアント
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

MODEL_ID = "amazon.nova-lite-v1:0"


def count_approximate_tokens(text):
    """トークン数の近似計算（日本語: 文字数 * 1.5）"""
    return int(len(text) * 1.5)


def compress_prompt(original_prompt):
    """
    プロンプト圧縮: 冗長な表現を削減しトークン数を最適化
    """
    compressions = [
        # 冗長な丁寧表現の削除
        ("以下の内容について詳しく分析して、わかりやすく説明してください。", "以下を分析してください:"),
        ("についての詳細な情報を提供してください", "について説明"),
        ("可能であれば具体的な例を挙げて説明してください", "具体例を含めて"),
        ("以下の質問に対して回答をお願いします", "質問:"),
    ]
    
    compressed = original_prompt
    for original, replacement in compressions:
        compressed = compressed.replace(original, replacement)
    
    return compressed


class SlidingWindowManager:
    """
    スライディングウィンドウ方式の会話コンテキスト管理
    - 最近の N ターンを完全に保持
    - 古いターンは要約して保持
    - トークン予算内に収める
    """
    
    def __init__(self, max_recent_turns=5, max_total_tokens=4000):
        self.history = []
        self.summary = ""
        self.max_recent_turns = max_recent_turns
        self.max_total_tokens = max_total_tokens
    
    def add_turn(self, role, content):
        """会話ターンを追加"""
        self.history.append({"role": role, "content": content})
        
        # 最近のターンを超えた場合、古いターンを要約に統合
        if len(self.history) > self.max_recent_turns * 2:
            self._compress_history()
    
    def _compress_history(self):
        """古い会話履歴を Bedrock で要約に圧縮"""
        # 古いターン（最近5ターン以外）を要約
        old_turns = self.history[:-self.max_recent_turns * 2]
        
        if old_turns:
            # Bedrock Converse API を使って会話を要約
            conversation_text = "\n".join(
                f"{t['role']}: {t['content']}" for t in old_turns
            )
            self.summary = self._summarize_with_bedrock(conversation_text)
            self.history = self.history[-self.max_recent_turns * 2:]
    
    def _summarize_with_bedrock(self, conversation_text):
        """Bedrock Converse API で会話履歴を要約する"""
        prompt = (
            "以下の会話履歴を3文以内で簡潔に要約してください。"
            "重要な事実（数値、条件、決定事項）を優先的に残してください。\n\n"
            f"会話履歴:\n{conversation_text}"
        )
        
        try:
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [{"text": prompt}]
                }],
                inferenceConfig={"temperature": 0.2, "maxTokens": 200}
            )
            summary = response['output']['message']['content'][0]['text']
            print(f"    [要約生成] Bedrock で {len(conversation_text)} 文字 → {len(summary)} 文字に圧縮")
            return summary
        except Exception as e:
            # フォールバック: API エラー時は簡易要約
            print(f"    [要約生成] Bedrock エラー: {e}（簡易要約にフォールバック）")
            old_content = conversation_text[:200]
            return f"[過去の会話要約: {old_content}...]"
    
    def get_context(self):
        """現在のコンテキストを取得"""
        context_parts = []
        
        if self.summary:
            context_parts.append(self.summary)
        
        for turn in self.history:
            context_parts.append(f"{turn['role']}: {turn['content']}")
        
        return "\n".join(context_parts)
    
    def get_messages_for_api(self):
        """Converse API 用のメッセージ形式で取得"""
        messages = []
        
        # 要約をシステムコンテキストとして最初に配置
        if self.summary:
            messages.append({
                "role": "user",
                "content": [{"text": f"過去の会話コンテキスト: {self.summary}"}]
            })
            messages.append({
                "role": "assistant",
                "content": [{"text": "はい、過去の会話内容を理解しました。続けてください。"}]
            })
        
        # 最近のターンをそのまま追加
        for turn in self.history:
            messages.append({
                "role": turn["role"],
                "content": [{"text": turn["content"]}]
            })
        
        return messages
    
    def get_token_count(self):
        """現在のコンテキストの推定トークン数"""
        context = self.get_context()
        return count_approximate_tokens(context)


def simulate_conversation(num_turns=20):
    """多数ターンの会話をシミュレーション"""
    conversations = [
        ("user", "この保険プランの補償内容を教えてください。"),
        ("assistant", "このプランでは、入院給付金として1日あたり10,000円、手術給付金として20万円が補償されます。また、通院給付金として1日5,000円が支給されます。"),
        ("user", "免責期間はありますか？"),
        ("assistant", "はい、契約開始から90日間の免責期間があります。この期間中に発症した疾病については給付対象外となります。"),
        ("user", "家族も加入できますか？"),
        ("assistant", "はい、配偶者とお子様（18歳未満）を被保険者として追加可能です。家族追加の場合、月額保険料に2,000円が加算されます。"),
        ("user", "既往症がある場合はどうなりますか？"),
        ("assistant", "既往症については告知義務があります。告知内容によっては、特定疾病不担保特約が付く場合や、保険料が割増になる場合があります。"),
        ("user", "解約するとどうなりますか？"),
        ("assistant", "解約時には解約返戻金が支払われます。ただし、契約から3年未満の場合は返戻率が低くなります。3年以上の場合は支払保険料の約70%が返戻されます。"),
        ("user", "保険金の請求手続きについて教えてください。"),
        ("assistant", "保険金請求には、診断書、領収書、請求書の提出が必要です。オンラインまたは郵送で申請可能で、審査期間は約2週間です。"),
        ("user", "月額保険料はいくらですか？"),
        ("assistant", "30歳男性の場合、月額3,500円からです。年齢、性別、健康状態により保険料が異なります。"),
        ("user", "保障の上限額はありますか？"),
        ("assistant", "入院給付金は1回の入院あたり60日、通算1,095日が上限です。手術給付金は1回の手術につき上限があります。"),
        ("user", "特約のオプションを教えてください。"),
        ("assistant", "先進医療特約（月額100円追加）、がん特約（月額500円追加）、三大疾病特約（月額800円追加）があります。"),
        ("user", "それでは、先進医療特約付きで加入したいのですが、最初に説明していた補償内容と合わせて確認させてください。"),
    ]
    
    return conversations[:num_turns]


def compare_approaches():
    """全履歴保持 vs スライディングウィンドウの比較"""
    print("=" * 70)
    print("  入力最適化: コンテキスト管理戦略の比較")
    print("=" * 70)
    
    conversations = simulate_conversation(20)
    
    # アプローチ 1: 全履歴保持
    print("\n" + "─" * 70)
    print("  アプローチ 1: 全履歴保持")
    print("─" * 70)
    
    full_context = "\n".join(
        f"{role}: {content}" for role, content in conversations
    )
    full_tokens = count_approximate_tokens(full_context)
    print(f"  トークン数: {full_tokens}")
    print(f"  推定コスト (Nova Lite): ${full_tokens * 0.00006 / 1000:.6f}")
    
    # アプローチ 2: スライディングウィンドウ
    print("\n" + "─" * 70)
    print("  アプローチ 2: スライディングウィンドウ（最近5ターン + 要約）")
    print("─" * 70)
    
    window = SlidingWindowManager(max_recent_turns=5, max_total_tokens=2000)
    
    for role, content in conversations:
        window.add_turn(role, content)
    
    window_tokens = window.get_token_count()
    print(f"  トークン数: {window_tokens}")
    print(f"  推定コスト (Nova Lite): ${window_tokens * 0.00006 / 1000:.6f}")
    
    if window.summary:
        print(f"  要約部分: {window.summary[:80]}...")
    print(f"  保持ターン数: {len(window.history)}")
    
    # 比較
    print("\n" + "─" * 70)
    print("  比較結果")
    print("─" * 70)
    
    reduction = (1 - window_tokens / full_tokens) * 100 if full_tokens > 0 else 0
    print(f"  全履歴: {full_tokens} トークン")
    print(f"  スライディングウィンドウ: {window_tokens} トークン")
    print(f"  削減率: {reduction:.1f}%")
    
    # 月間コスト比較（1日1000会話、各20ターン想定）
    daily_conversations = 1000
    monthly_cost_full = daily_conversations * 30 * (full_tokens / 1000) * 0.00006
    monthly_cost_window = daily_conversations * 30 * (window_tokens / 1000) * 0.00006
    
    print(f"\n  月間コスト試算（1000会話/日）:")
    print(f"    全履歴: ${monthly_cost_full:.2f}/月")
    print(f"    ウィンドウ: ${monthly_cost_window:.2f}/月")
    print(f"    月間削減額: ${monthly_cost_full - monthly_cost_window:.2f}")


def demo_prompt_compression():
    """プロンプト圧縮のデモ"""
    print("\n\n" + "=" * 70)
    print("  入力最適化: プロンプト圧縮テクニック")
    print("=" * 70)
    
    examples = [
        {
            "original": "以下の内容について詳しく分析して、わかりやすく説明してください。この保険プランの月額保険料の計算方法についての詳細な情報を提供してください。可能であれば具体的な例を挙げて説明してください。",
            "category": "冗長な丁寧表現"
        },
        {
            "original": """以下の質問に対して回答をお願いします。
当社のシステムで発生しているパフォーマンス問題について、
以下の観点から詳しく分析して、わかりやすく説明してください。
1. レイテンシーが増加している原因
2. スループットが低下している理由
3. 改善するための具体的な対策""",
            "category": "構造化による最適化"
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{'─' * 70}")
        print(f"  例 {i}: {example['category']}")
        print(f"{'─' * 70}")
        
        original = example["original"]
        compressed = compress_prompt(original)
        
        orig_tokens = count_approximate_tokens(original)
        comp_tokens = count_approximate_tokens(compressed)
        reduction = (1 - comp_tokens / orig_tokens) * 100 if orig_tokens > 0 else 0
        
        print(f"\n  圧縮前 ({orig_tokens} トークン):")
        print(f"    {original[:100]}...")
        print(f"\n  圧縮後 ({comp_tokens} トークン):")
        print(f"    {compressed[:100]}...")
        print(f"\n  削減率: {reduction:.1f}%")


def demo_dynamic_batch_sizing():
    """動的バッチサイジングのデモ"""
    print("\n\n" + "=" * 70)
    print("  入力最適化: 動的バッチサイジング")
    print("=" * 70)
    
    scenarios = [
        {"queue_depth": 20, "label": "低負荷"},
        {"queue_depth": 200, "label": "中負荷"},
        {"queue_depth": 1500, "label": "高負荷"},
    ]
    
    print(f"\n  {'シナリオ':<12} {'キュー深度':<12} {'バッチサイズ':<12} {'並列度':<10} {'戦略'}")
    print(f"  {'─' * 60}")
    
    for scenario in scenarios:
        depth = scenario["queue_depth"]
        
        # 動的バッチサイズの計算
        if depth < 50:
            batch_size = 5
            concurrency = 2
            strategy = "低レイテンシー優先"
        elif depth < 500:
            batch_size = 25
            concurrency = 5
            strategy = "バランス"
        else:
            batch_size = 50
            concurrency = 10
            strategy = "スループット優先"
        
        est_time = depth / (batch_size * concurrency) * 2  # 各バッチ2秒想定
        
        print(f"  {scenario['label']:<12} {depth:<12} {batch_size:<12} {concurrency:<10} {strategy}")
    
    print(f"""
  動的バッチサイジングのルール:
  ┌─────────────────────────────────────────────────────────┐
  │ キュー深度 < 50   → バッチ5,  並列2  (レイテンシー優先) │
  │ キュー深度 50-500 → バッチ25, 並列5  (バランス)         │
  │ キュー深度 > 500  → バッチ50, 並列10 (スループット優先) │
  └─────────────────────────────────────────────────────────┘
  
  メリット:
  • 低負荷時: ユーザーの待ち時間を最小化
  • 高負荷時: リソース効率を最大化、コスト削減
  • CloudWatch メトリクスを使って自動調整可能
""")


if __name__ == "__main__":
    compare_approaches()
    demo_prompt_compression()
    demo_dynamic_batch_sizing()
