"""
モジュール 8: 推論経路分析とデバッグ
- AIロジックの透明性フロー（ブラックボックス → 思考の連鎖 → 透明な推論 → 信頼度）
- 体系的な論理エラーの検出（循環論法、誤った前提、一貫性の欠如）
- 推論ステップの構造化と検証
- LLM-as-a-Judge による論理的整合性チェック
"""

import boto3
import json
import time
import re
from datetime import datetime, timezone

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

MODEL_ID = "amazon.nova-lite-v1:0"
EVALUATOR_MODEL_ID = "amazon.nova-pro-v1:0"
NAMESPACE = "GenAI/Bedrock"


# ============================================================
# 推論経路の抽出と構造化
# ============================================================

class ReasoningExtractor:
    """
    AIの推論経路を構造化して抽出するクラス。

    透明性のレベル:
    Level 1: ブラックボックス（通常の回答、推論過程なし）
    Level 2: 思考の連鎖（CoT で推論ステップを表示）
    Level 3: 構造化推論（JSON で検証可能な形式に）
    Level 4: 説明可能な回答（ユーザー向けに信頼度付きで提示）
    """

    def invoke_blackbox(self, question):
        """Level 1: ブラックボックス - 通常の回答"""
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": question}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 300}
        )
        return {
            "level": 1,
            "answer": response['output']['message']['content'][0]['text'],
            "reasoning_visible": False,
            "verifiable": False,
        }

    def invoke_chain_of_thought(self, question):
        """Level 2: 思考の連鎖 - 推論過程を含む回答"""
        cot_prompt = f"""以下の質問にステップバイステップで回答してください。
各推論ステップを【ステップN】として明示してください。
最後に【結論】をまとめてください。

質問: {question}"""

        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": cot_prompt}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 600}
        )
        answer = response['output']['message']['content'][0]['text']

        # ステップの抽出
        steps = re.findall(r'【ステップ\d+】(.+?)(?=【|$)', answer, re.DOTALL)
        conclusion_match = re.search(r'【結論】(.+?)$', answer, re.DOTALL)
        conclusion = conclusion_match.group(1).strip() if conclusion_match else ""

        return {
            "level": 2,
            "answer": answer,
            "steps": [s.strip() for s in steps],
            "conclusion": conclusion,
            "step_count": len(steps),
            "reasoning_visible": True,
            "verifiable": False,
        }

    def invoke_structured_reasoning(self, question):
        """Level 3: 構造化推論 - JSON形式で検証可能"""
        structured_prompt = f"""以下の質問に回答してください。
推論過程を以下のJSON形式で構造化して出力してください。

質問: {question}

出力形式:
{{
  "reasoning_steps": [
    {{"step": 1, "type": "情報確認|ルール適用|推論|計算", "claim": "主張", "basis": "根拠", "confidence": 0.0-1.0}},
    {{"step": 2, "type": "...", "claim": "...", "basis": "...", "confidence": 0.0-1.0}}
  ],
  "conclusion": "最終回答",
  "overall_confidence": 0.0-1.0,
  "assumptions": ["前提1", "前提2"],
  "limitations": ["制限事項1"]
}}"""

        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": structured_prompt}]}],
            inferenceConfig={"temperature": 0.2, "maxTokens": 800}
        )
        answer = response['output']['message']['content'][0]['text']

        # JSON の抽出
        try:
            start = answer.index('{')
            brace_count = 0
            end = start
            for i, c in enumerate(answer[start:], start):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i
                        break
            parsed = json.loads(answer[start:end + 1])
        except (ValueError, json.JSONDecodeError):
            parsed = {
                "reasoning_steps": [],
                "conclusion": answer[:200],
                "overall_confidence": 0.5,
                "assumptions": [],
                "limitations": ["JSON解析失敗"],
            }

        parsed["level"] = 3
        parsed["reasoning_visible"] = True
        parsed["verifiable"] = True
        return parsed

    def invoke_explainable(self, question):
        """Level 4: 説明可能な回答 - ユーザー向け信頼度付き"""
        # まず構造化推論を取得
        structured = self.invoke_structured_reasoning(question)

        # ユーザー向けの説明を生成
        explanation_prompt = f"""以下の推論結果を、専門知識がないユーザーにも分かりやすく説明してください。
判断の根拠、確信度、注意点を含めてください。

推論結果:
{json.dumps(structured, ensure_ascii=False, indent=2)}

出力形式（自然な日本語で）:
1. 回答（結論）
2. なぜそう判断したか（簡潔に）
3. この回答の確信度（高/中/低 + 理由）
4. 注意点（この回答が間違っている可能性があるケース）"""

        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": explanation_prompt}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 400}
        )
        explanation = response['output']['message']['content'][0]['text']

        return {
            "level": 4,
            "structured_reasoning": structured,
            "user_explanation": explanation,
            "reasoning_visible": True,
            "verifiable": True,
            "explainable": True,
        }


# ============================================================
# 論理エラー検出エンジン
# ============================================================

class LogicalErrorDetector:
    """
    推論の連鎖から体系的な論理エラーを検出するクラス。

    検出する論理エラー:
    1. 循環論法: 結論を使って前提を正当化している
    2. 誤った前提: 初期前提が事実と異なる
    3. 一貫性の欠如: 推論ステップ間で矛盾がある
    4. 非論理的飛躍: ステップ間に論理的つながりがない
    5. 過度の一般化: 限定的な根拠から広い結論を導いている
    """

    # 論理エラーのパターン定義
    ERROR_PATTERNS = {
        "circular_reasoning": {
            "name": "循環論法",
            "description": "結論を根拠として使い、結論を正当化している",
            "severity": "high",
            "example": "Aは正しい。なぜならAだから。",
        },
        "false_premise": {
            "name": "誤った前提",
            "description": "事実と異なる前提に基づいて推論している",
            "severity": "high",
            "example": "Lambda は最大1時間実行できるので...（実際は15分）",
        },
        "inconsistency": {
            "name": "一貫性の欠如",
            "description": "推論の途中で矛盾する主張をしている",
            "severity": "medium",
            "example": "ステップ1で『Aが最適』と言い、ステップ3で『Aは不適切』と言う",
        },
        "non_sequitur": {
            "name": "非論理的飛躍",
            "description": "前提から結論が論理的に導かれていない",
            "severity": "medium",
            "example": "S3は安い → したがってS3はセキュアである",
        },
        "overgeneralization": {
            "name": "過度の一般化",
            "description": "限定的なケースから広い結論を導いている",
            "severity": "low",
            "example": "1つのベンチマークで速かった → すべてのケースで最速",
        },
    }

    def detect_errors(self, reasoning_steps, conclusion):
        """
        推論ステップと結論から論理エラーを検出する。

        Parameters:
            reasoning_steps: 構造化された推論ステップのリスト
            conclusion: 最終結論

        Returns:
            dict: 検出された論理エラーのリスト
        """
        # LLM-as-a-Judge で論理エラーを検出
        detection_prompt = f"""あなたは論理学の専門家です。以下の推論過程に論理的誤りがないか分析してください。

【推論ステップ】
{json.dumps(reasoning_steps, ensure_ascii=False, indent=2)}

【結論】
{conclusion}

以下の論理エラーを検出してください:
1. 循環論法: 結論が前提として使われていないか
2. 誤った前提: 事実と異なる前提はないか
3. 一貫性の欠如: ステップ間で矛盾はないか
4. 非論理的飛躍: 前提から結論が論理的に導かれているか
5. 過度の一般化: 限定的な根拠から広い結論を導いていないか

以下のJSON形式で回答してください:
{{
  "errors_found": [
    {{"type": "エラー種類", "location": "ステップN", "description": "具体的な説明", "severity": "high/medium/low"}}
  ],
  "logical_validity": 0.0-1.0,
  "overall_assessment": "総合評価"
}}"""

        try:
            response = bedrock.converse(
                modelId=EVALUATOR_MODEL_ID,
                messages=[{"role": "user", "content": [{"text": detection_prompt}]}],
                inferenceConfig={"temperature": 0.1, "maxTokens": 600}
            )
            eval_text = response['output']['message']['content'][0]['text']

            # JSON抽出
            start = eval_text.index('{')
            brace_count = 0
            end = start
            for i, c in enumerate(eval_text[start:], start):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i
                        break
            result = json.loads(eval_text[start:end + 1])

        except (ValueError, json.JSONDecodeError, Exception) as e:
            result = {
                "errors_found": [],
                "logical_validity": 0.5,
                "overall_assessment": f"解析エラー: {e}",
            }

        return result

    def cross_validate(self, question, reasoning_result):
        """
        相互チェック: 同じ質問を異なる方法で尋ねて推論を検証する。

        異なる角度から質問し、推論の一貫性を確認:
        - 元の質問 → 回答A
        - 逆方向の質問 → 回答B
        - 具体例で確認 → 回答C
        """
        # 逆方向の質問を生成
        reverse_prompt = f"""以下の質問の結論が正しいと仮定した場合、
どのような前提条件が必要ですか？
また、その結論が間違っている可能性があるケースを挙げてください。

元の質問: {question}
回答された結論: {reasoning_result.get('conclusion', '')}

JSON形式で回答:
{{"required_premises": ["前提1", "前提2"], "counterexamples": ["反例1", "反例2"], "validity_check": "valid/partially_valid/invalid", "reasoning": "理由"}}"""

        try:
            response = bedrock.converse(
                modelId=EVALUATOR_MODEL_ID,
                messages=[{"role": "user", "content": [{"text": reverse_prompt}]}],
                inferenceConfig={"temperature": 0.2, "maxTokens": 400}
            )
            eval_text = response['output']['message']['content'][0]['text']

            json_match = re.search(r'\{[^{}]*\}', eval_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {"validity_check": "unknown", "reasoning": "解析不能"}

        except Exception as e:
            result = {"validity_check": "unknown", "reasoning": f"エラー: {e}"}

        return result


# ============================================================
# メトリクス発行
# ============================================================

def publish_reasoning_metrics(logical_validity, error_count, reasoning_steps_count):
    """推論品質のメトリクスを CloudWatch に発行"""
    metrics_data = [
        {
            'MetricName': 'LogicalValidity',
            'Value': float(logical_validity),
            'Unit': 'None',
            'Timestamp': datetime.now(timezone.utc),
            'Dimensions': [
                {'Name': 'ModelId', 'Value': MODEL_ID},
                {'Name': 'Environment', 'Value': 'demo'},
            ],
        },
        {
            'MetricName': 'LogicalErrorCount',
            'Value': float(error_count),
            'Unit': 'Count',
            'Timestamp': datetime.now(timezone.utc),
            'Dimensions': [
                {'Name': 'ModelId', 'Value': MODEL_ID},
                {'Name': 'Environment', 'Value': 'demo'},
            ],
        },
        {
            'MetricName': 'ReasoningStepCount',
            'Value': float(reasoning_steps_count),
            'Unit': 'Count',
            'Timestamp': datetime.now(timezone.utc),
            'Dimensions': [
                {'Name': 'ModelId', 'Value': MODEL_ID},
                {'Name': 'Environment', 'Value': 'demo'},
            ],
        },
    ]

    try:
        cloudwatch.put_metric_data(Namespace=NAMESPACE, MetricData=metrics_data)
        return len(metrics_data)
    except Exception as e:
        print(f"  ⚠️  メトリクス送信エラー: {e}")
        return 0


# ============================================================
# デモ 1: AIロジックの透明性フロー（4段階）
# ============================================================

def demo_transparency_levels():
    """4段階の透明性レベルを比較するデモ"""
    print("=" * 70)
    print("  デモ 1: AI ロジックの透明性フロー")
    print("=" * 70)
    print("""
  同じ質問に対して、透明性レベルを段階的に上げていき、
  推論過程がどのように可視化されるかを示します。

  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
  │ ブラック     │   │ 思考の連鎖  │   │ 透明な推論  │   │ ユーザーの  │
  │ ボックス    │ → │ 分析ツール  │ → │ 明確な      │ → │ 信頼        │
  │             │   │             │   │ ステップ    │   │ 信頼度      │
  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
    Level 1            Level 2            Level 3            Level 4
""")

    extractor = ReasoningExtractor()

    question = "AWS で Web アプリケーションをホストする場合、EC2 と ECS のどちらを選ぶべきですか？チームは5人で Docker の経験が浅いです。"

    print(f"  質問: {question}\n")

    # Level 1: ブラックボックス
    print(f"{'─' * 70}")
    print(f"  📦 Level 1: ブラックボックス")
    print(f"     推論過程: 見えない / 検証: 不可能")
    print(f"{'─' * 70}")

    try:
        result_l1 = extractor.invoke_blackbox(question)
        print(f"  回答: {result_l1['answer'][:150]}...")
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        result_l1 = {"answer": "エラー"}

    time.sleep(2)

    # Level 2: 思考の連鎖
    print(f"\n{'─' * 70}")
    print(f"  🔗 Level 2: 思考の連鎖（Chain of Thought）")
    print(f"     推論過程: 見える / 検証: 手動で可能")
    print(f"{'─' * 70}")

    try:
        result_l2 = extractor.invoke_chain_of_thought(question)
        print(f"  推論ステップ数: {result_l2['step_count']}")
        for i, step in enumerate(result_l2['steps'][:4], 1):
            print(f"    ステップ{i}: {step[:80]}{'...' if len(step) > 80 else ''}")
        if result_l2['conclusion']:
            print(f"  結論: {result_l2['conclusion'][:100]}")
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        result_l2 = {"steps": [], "step_count": 0}

    time.sleep(2)

    # Level 3: 構造化推論
    print(f"\n{'─' * 70}")
    print(f"  📋 Level 3: 構造化推論（Structured Reasoning）")
    print(f"     推論過程: 構造化 / 検証: 自動化可能")
    print(f"{'─' * 70}")

    try:
        result_l3 = extractor.invoke_structured_reasoning(question)
        steps = result_l3.get("reasoning_steps", [])
        print(f"  推論ステップ数: {len(steps)}")
        for step in steps[:4]:
            confidence = step.get('confidence', 'N/A')
            step_type = step.get('type', 'N/A')
            claim = step.get('claim', 'N/A')
            print(f"    [{step_type}] {claim[:60]}... (確信度: {confidence})")
        print(f"  結論: {result_l3.get('conclusion', 'N/A')[:100]}")
        print(f"  総合確信度: {result_l3.get('overall_confidence', 'N/A')}")
        assumptions = result_l3.get('assumptions', [])
        if assumptions:
            print(f"  前提条件: {', '.join(str(a) for a in assumptions[:3])}")
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        result_l3 = {"reasoning_steps": [], "overall_confidence": 0.5}

    time.sleep(2)

    # Level 4: 説明可能な回答
    print(f"\n{'─' * 70}")
    print(f"  💡 Level 4: 説明可能な回答（Explainable AI）")
    print(f"     推論過程: ユーザー向けに翻訳 / 検証: 自動+人間")
    print(f"{'─' * 70}")

    try:
        result_l4 = extractor.invoke_explainable(question)
        print(f"  ユーザー向け説明:")
        for line in result_l4['user_explanation'].split('\n')[:8]:
            if line.strip():
                print(f"    {line}")
    except Exception as e:
        print(f"  ❌ エラー: {e}")

    # 比較サマリー
    print(f"\n{'═' * 70}")
    print(f"  📊 透明性レベル比較:")
    print(f"  {'─' * 60}")
    print(f"  {'レベル':<12} {'推論可視性':<12} {'自動検証':<12} {'ユーザー信頼':<12} {'コスト':<8}")
    print(f"  {'─' * 60}")
    print(f"  {'L1 ブラックボックス':<12} {'❌ なし':<12} {'❌ 不可':<12} {'低い':<12} {'1x':<8}")
    print(f"  {'L2 CoT':<12} {'✅ テキスト':<12} {'△ 手動':<12} {'中':<12} {'1.5x':<8}")
    print(f"  {'L3 構造化':<12} {'✅ JSON':<12} {'✅ 自動':<12} {'中-高':<12} {'2x':<8}")
    print(f"  {'L4 説明可能':<12} {'✅ 自然言語':<12} {'✅ 自動':<12} {'高い':<12} {'3x':<8}")
    print(f"  {'─' * 60}")
    print(f"  → Level 3 がコストと検証可能性のバランスが良い推奨レベル")


# ============================================================
# デモ 2: 体系的な論理エラーの検出
# ============================================================

def demo_logical_error_detection():
    """推論の連鎖から論理エラーを検出するデモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: 体系的な論理エラーの検出")
    print("=" * 70)
    print("""
  推論の連鎖を可視化し、以下の論理エラーを自動検出します:

  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │ 推論の連鎖       │     │ パターン照合     │     │ エラーの検出     │
  │                  │ →   │                  │ →   │                  │
  │ AI出力          │     │ 自動チェック     │     │ 問題の特定       │
  └──────────────────┘     └──────────────────┘     └──────────────────┘
                                                            ↓
                                                     • 循環論法
                                                     • 誤った前提
                                                     • 一貫性の欠如
""")

    extractor = ReasoningExtractor()
    detector = LogicalErrorDetector()

    # テストケース: 論理エラーが起きやすい質問
    test_cases = [
        {
            "title": "ケース 1: 技術選定の推論（正常なケース）",
            "question": "月間100万リクエストの REST API を構築する場合、API Gateway + Lambda と ECS + ALB のどちらが適切ですか？リクエストの平均処理時間は200msです。",
        },
        {
            "title": "ケース 2: 循環論法を誘発しやすい質問",
            "question": "NoSQL が SQL より優れている理由と、NoSQL が最適なデータベースである根拠を説明してください。すべてのケースで NoSQL を使うべき理由を述べてください。",
        },
        {
            "title": "ケース 3: 誤った前提を含む質問",
            "question": "AWS Lambda は無制限に同時実行できるので、スケーリングの心配は不要ですよね？Lambda でリアルタイム処理システムを構築する最善の方法を教えてください。",
        },
    ]

    all_results = []

    for case in test_cases:
        print(f"\n{'─' * 70}")
        print(f"  📋 {case['title']}")
        print(f"  質問: {case['question'][:60]}...")
        print(f"{'─' * 70}")

        # 構造化推論を取得
        print(f"  推論を構造化中...")
        try:
            structured = extractor.invoke_structured_reasoning(case["question"])
            steps = structured.get("reasoning_steps", [])
            conclusion = structured.get("conclusion", "")

            print(f"  推論ステップ: {len(steps)} 件")
            for step in steps[:3]:
                print(f"    → [{step.get('type', '?')}] {str(step.get('claim', ''))[:60]}")
            print(f"  結論: {conclusion[:80]}...")

        except Exception as e:
            print(f"  ❌ 推論取得エラー: {e}")
            steps = []
            conclusion = ""
            continue

        time.sleep(2)

        # 論理エラー検出
        print(f"\n  論理エラーを検出中...")
        try:
            error_result = detector.detect_errors(steps, conclusion)
            errors = error_result.get("errors_found", [])
            validity = error_result.get("logical_validity", 0.5)
            assessment = error_result.get("overall_assessment", "N/A")

            print(f"  論理的妥当性: {validity:.2f} {'🟢' if validity >= 0.8 else '🟡' if validity >= 0.5 else '🔴'}")
            print(f"  検出エラー数: {len(errors)}")

            if errors:
                for err in errors[:3]:
                    severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                        err.get("severity", "medium"), "⚪")
                    print(f"    {severity_icon} [{err.get('type', '?')}] {err.get('description', '')[:60]}")
                    if err.get("location"):
                        print(f"       位置: {err['location']}")
            else:
                print(f"    ✅ 論理エラーは検出されませんでした")

            print(f"  総合評価: {assessment[:80]}")

            all_results.append({
                "title": case["title"],
                "validity": validity,
                "error_count": len(errors),
            })

            # メトリクス発行
            publish_reasoning_metrics(validity, len(errors), len(steps))

        except Exception as e:
            print(f"  ❌ 検出エラー: {e}")
            all_results.append({
                "title": case["title"],
                "validity": 0.5,
                "error_count": -1,
            })

        time.sleep(2)

    # サマリー
    print(f"\n{'═' * 70}")
    print(f"  📊 論理エラー検出サマリー:")
    print(f"  {'─' * 55}")
    print(f"  {'ケース':<30} {'妥当性':<10} {'エラー数':<10} {'判定':<10}")
    print(f"  {'─' * 55}")
    for r in all_results:
        icon = "🟢" if r["validity"] >= 0.8 else "🟡" if r["validity"] >= 0.5 else "🔴"
        print(f"  {r['title'][:28]:<30} {r['validity']:<10.2f} {r['error_count']:<10} {icon}")


# ============================================================
# デモ 3: 相互検証（クロスバリデーション）
# ============================================================

def demo_cross_validation():
    """推論の相互チェックによる検証デモ"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: 推論の相互検証")
    print("=" * 70)
    print("""
  同じ質問を異なる方法で尋ね、推論の一貫性を検証します。

  検証手法:
  ┌────────────────────────────────────────────────────────────────┐
  │ 1. 元の質問 → 正方向の推論                                    │
  │ 2. 結論から逆方向に質問 → 必要な前提条件を確認               │
  │ 3. 反例の探索 → 結論が崩れるケースを確認                     │
  │                                                                │
  │ 3つが整合していれば推論は信頼できる                           │
  └────────────────────────────────────────────────────────────────┘
""")

    extractor = ReasoningExtractor()
    detector = LogicalErrorDetector()

    question = "スタートアップが最初のインフラとして AWS を選ぶべきですか？チームは3人のエンジニアで、MVP を3ヶ月で出したいです。"

    print(f"  質問: {question}\n")

    # 正方向の推論
    print(f"  [1/3] 正方向の推論を実行中...")
    try:
        structured = extractor.invoke_structured_reasoning(question)
        conclusion = structured.get("conclusion", "")
        print(f"  結論: {conclusion[:100]}")
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        structured = {"conclusion": "AWS を推奨", "reasoning_steps": []}
        conclusion = structured["conclusion"]

    time.sleep(2)

    # 逆方向の検証
    print(f"\n  [2/3] 逆方向の検証（結論から前提を確認）...")
    try:
        cross_result = detector.cross_validate(question, structured)
        validity = cross_result.get("validity_check", "unknown")
        reasoning = cross_result.get("reasoning", "N/A")

        validity_icon = {"valid": "🟢", "partially_valid": "🟡", "invalid": "🔴"}.get(validity, "⚪")
        print(f"  妥当性: {validity_icon} {validity}")
        print(f"  理由: {reasoning[:100]}")

        premises = cross_result.get("required_premises", [])
        if premises:
            print(f"  必要な前提条件:")
            for p in premises[:3]:
                print(f"    • {p}")

        counterexamples = cross_result.get("counterexamples", [])
        if counterexamples:
            print(f"  反例（この結論が間違うケース）:")
            for c in counterexamples[:3]:
                print(f"    ⚠️  {c}")

    except Exception as e:
        print(f"  ❌ エラー: {e}")

    time.sleep(2)

    # 別角度からの質問
    print(f"\n  [3/3] 別角度からの確認...")
    alternative_question = "AWS を選ばない方がよいスタートアップの条件は何ですか？"
    print(f"  別角度の質問: {alternative_question}")

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": alternative_question}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 300}
        )
        alt_answer = response['output']['message']['content'][0]['text']
        print(f"  回答: {alt_answer[:150]}...")
    except Exception as e:
        print(f"  ❌ エラー: {e}")

    print(f"""
  📊 相互検証の結果:
  ┌────────────────────────────────────────────────────────────────┐
  │ 正方向の推論と逆方向の検証が整合 → 推論は信頼性が高い        │
  │ 反例が元の結論の条件と矛盾しない → 結論のスコープが適切      │
  │                                                                │
  │ このプロセスを自動化することで、ハルシネーションに起因する    │
  │ 論理エラーを回答パイプラインに組み込んで検出できます          │
  └────────────────────────────────────────────────────────────────┘
""")


# ============================================================
# ベストプラクティスまとめ
# ============================================================

def print_best_practices():
    """推論経路分析のベストプラクティスを表示"""
    print("\n" + "=" * 70)
    print("  推論経路分析のベストプラクティス")
    print("=" * 70)
    print("""
  1. 推論の透明性は段階的に実装する:
     • まず Level 2（CoT）をすべての回答に適用
     • 高リスク回答のみ Level 3（構造化）で詳細検証
     • ユーザー対面は Level 4（説明可能）を検討

  2. 論理エラー検出の運用:
     • 全回答に適用するとコストが高いのでサンプリング
     • 「誤った前提」は質問時点で検出できる（入力フィルター）
     • 「循環論法」はプロンプト設計で軽減可能

  3. 相互検証のコスト管理:
     • 通常リクエスト: Level 2 のみ（追加コスト 0）
     • 定期品質チェック: Level 3 + 論理エラー検出（バッチ）
     • 高リスク判定時: Level 4 + 相互検証（リアルタイム）

  4. CloudWatch メトリクスとの連携:
     • LogicalValidity < 0.5 → アラート
     • LogicalErrorCount の急増 → モデルの挙動変化を示唆
     • ReasoningStepCount の異常 → プロンプトの問題

  5. モニタリングしきい値:
     ┌──────────────────────────┬──────────┬──────────────────────┐
     │ メトリクス               │ しきい値 │ アクション           │
     ├──────────────────────────┼──────────┼──────────────────────┤
     │ LogicalValidity          │ < 0.5    │ 回答を保留してレビュー│
     │ 循環論法の検出率         │ > 10%    │ プロンプト改善       │
     │ 誤った前提の検出率       │ > 5%     │ 入力検証の強化       │
     │ 一貫性エラー率           │ > 15%    │ モデル変更を検討     │
     └──────────────────────────┴──────────┴──────────────────────┘
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 8: 推論経路分析とデバッグ")
    print("🔷" * 35)
    print("\n  AI の推論過程を可視化し、論理エラーを体系的に検出する")
    print("  パイプラインを実装します。")
    print()

    # デモ 1: 透明性レベルの比較
    demo_transparency_levels()
    time.sleep(2)

    # デモ 2: 論理エラー検出
    demo_logical_error_detection()
    time.sleep(2)

    # デモ 3: 相互検証
    demo_cross_validation()

    # ベストプラクティス
    print_best_practices()
