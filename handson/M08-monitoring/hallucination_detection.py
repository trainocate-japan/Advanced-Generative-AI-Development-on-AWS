"""
モジュール 8: ハルシネーション検出と応答品質モニタリング
- 一貫性チェック: 同じ質問への回答の矛盾検出
- ソース検証: RAG 回答がソースに基づいているかの検証
- エンティティ検証: 生成された固有名詞・数値の妥当性チェック
- 信頼度スコア: モデルの不確実性を数値化
- 品質スコアの CloudWatch メトリクス発行
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
# ハルシネーション検出エンジン
# ============================================================

class HallucinationDetector:
    """
    複数の手法を組み合わせてハルシネーションを検出するエンジン

    検出手法:
    1. 一貫性チェック: 同じ質問を複数回投げて矛盾を検出
    2. ソース検証: 回答内容がソースドキュメントに含まれているか
    3. エンティティ検証: 固有名詞・数値の事実確認
    4. 信頼度スコア: LLM-as-a-Judge で品質スコアリング
    """

    def __init__(self):
        self.results = []

    def consistency_check(self, question, num_samples=3):
        """
        一貫性チェック: 同じ質問に複数回回答させ、矛盾を検出

        手法:
        - temperature を上げて多様な回答を生成
        - 回答間の矛盾をモデルに評価させる
        """
        print(f"\n  質問: 「{question}」")
        print(f"  {num_samples}回回答を生成して一貫性を検証...")

        answers = []
        for i in range(num_samples):
            try:
                response = bedrock.converse(
                    modelId=MODEL_ID,
                    messages=[{
                        "role": "user",
                        "content": [{"text": question}]
                    }],
                    inferenceConfig={"temperature": 0.7, "maxTokens": 300}
                )
                answer = response['output']['message']['content'][0]['text']
                answers.append(answer)
                print(f"    回答 {i+1}: {answer[:80]}...")
            except Exception as e:
                print(f"    回答 {i+1}: エラー - {e}")
            time.sleep(1)

        if len(answers) < 2:
            return {"score": 0, "consistent": False, "reason": "回答生成失敗"}

        # 矛盾検出（LLM-as-a-Judge）
        evaluation_prompt = f"""以下の{len(answers)}つの回答が同じ質問に対するものです。
回答間に事実の矛盾がないか評価してください。

質問: {question}

"""
        for i, ans in enumerate(answers, 1):
            evaluation_prompt += f"回答{i}: {ans}\n\n"

        evaluation_prompt += """評価基準:
- 数値や日付が一致しているか
- 固有名詞が一貫しているか
- 事実関係に矛盾がないか

以下のJSON形式で回答してください:
{"consistency_score": 0.0-1.0, "contradictions": ["矛盾点1", "矛盾点2"], "assessment": "一文の総合評価"}"""

        try:
            eval_response = bedrock.converse(
                modelId=EVALUATOR_MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [{"text": evaluation_prompt}]
                }],
                inferenceConfig={"temperature": 0.1, "maxTokens": 500}
            )
            eval_text = eval_response['output']['message']['content'][0]['text']

            # JSON 抽出
            json_match = re.search(r'\{[^{}]*\}', eval_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {"consistency_score": 0.5, "contradictions": [], "assessment": "解析不能"}

        except Exception as e:
            result = {"consistency_score": 0.5, "contradictions": [], "assessment": f"評価エラー: {e}"}

        return result

    def source_verification(self, question, source_text, answer):
        """
        ソース検証: RAG の回答がソースドキュメントに基づいているか確認

        Faithfulness Score を計算:
        - 回答の各主張がソースに裏付けられているか
        - ソースに存在しない情報が含まれていないか
        """
        verification_prompt = f"""あなたはファクトチェッカーです。
以下の「回答」が「ソース」の内容に忠実かどうかを評価してください。

【ソース】
{source_text}

【質問】
{question}

【回答】
{answer}

以下の基準で評価してください:
1. 回答の各主張がソースに明示的に記載されているか
2. ソースに記載されていない情報が含まれていないか（ハルシネーション）
3. 数値やデータがソースと一致しているか

以下のJSON形式で回答してください:
{{"faithfulness_score": 0.0-1.0, "supported_claims": ["裏付けあり1"], "unsupported_claims": ["裏付けなし1"], "hallucinated_facts": ["捏造された事実1"], "assessment": "総合評価"}}"""

        try:
            response = bedrock.converse(
                modelId=EVALUATOR_MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [{"text": verification_prompt}]
                }],
                inferenceConfig={"temperature": 0.1, "maxTokens": 600}
            )
            eval_text = response['output']['message']['content'][0]['text']

            json_match = re.search(r'\{[^{}]*\}', eval_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {"faithfulness_score": 0.5, "assessment": "解析不能"}

        except Exception as e:
            result = {"faithfulness_score": 0.5, "assessment": f"エラー: {e}"}

        return result

    def entity_verification(self, answer):
        """
        エンティティ検証: 回答に含まれる固有名詞・数値の妥当性を確認

        チェック項目:
        - 存在する組織名・製品名か
        - 日付・数値が妥当な範囲か
        - URL やリファレンスが実在するか
        """
        verification_prompt = f"""以下の文章に含まれる固有名詞、数値、日付、URL を抽出し、
それぞれの妥当性を評価してください。

【テキスト】
{answer}

以下のJSON形式で回答してください:
{{"entities": [{{"entity": "名前", "type": "組織/人物/数値/日付/URL", "plausibility": "high/medium/low", "reason": "理由"}}], "overall_plausibility": 0.0-1.0, "suspicious_entities": ["怪しいエンティティ1"]}}"""

        try:
            response = bedrock.converse(
                modelId=EVALUATOR_MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [{"text": verification_prompt}]
                }],
                inferenceConfig={"temperature": 0.1, "maxTokens": 600}
            )
            eval_text = response['output']['message']['content'][0]['text']

            # JSON を抽出（ネストされたオブジェクトに対応）
            try:
                # 最初の { から最後の } までを取得
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
            except (ValueError, json.JSONDecodeError):
                result = {"overall_plausibility": 0.5, "entities": [], "suspicious_entities": []}

        except Exception as e:
            result = {"overall_plausibility": 0.5, "entities": [], "suspicious_entities": [], "error": str(e)}

        return result

    def compute_confidence_score(self, question, answer):
        """
        信頼度スコア: モデル自身の不確実性を数値化

        手法:
        - 回答の確信度をモデルに自己評価させる
        - ヘッジ表現（「かもしれない」「おそらく」）の頻度を分析
        - 回答の具体性と一般性のバランスを評価
        """
        # ヘッジ表現の検出
        hedge_patterns = [
            "かもしれません", "おそらく", "と思います", "可能性があり",
            "一般的に", "通常は", "場合によっては", "確実ではありません",
            "might", "probably", "perhaps", "possibly", "I think",
        ]
        hedge_count = sum(1 for pattern in hedge_patterns if pattern in answer)
        hedge_density = hedge_count / max(len(answer.split()), 1)

        # LLM による信頼度評価
        confidence_prompt = f"""以下の質問と回答について、回答の信頼度を評価してください。

【質問】{question}
【回答】{answer}

評価基準:
- 具体的なデータや根拠が示されているか
- 曖昧な表現や推測が多くないか
- 回答の範囲が質問に適切に対応しているか
- 事実と意見が明確に区別されているか

以下のJSON形式で回答してください:
{{"confidence_score": 0.0-1.0, "specificity": "high/medium/low", "hedging_level": "none/mild/heavy", "reasoning": "理由"}}"""

        try:
            response = bedrock.converse(
                modelId=EVALUATOR_MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [{"text": confidence_prompt}]
                }],
                inferenceConfig={"temperature": 0.1, "maxTokens": 300}
            )
            eval_text = response['output']['message']['content'][0]['text']

            json_match = re.search(r'\{[^{}]*\}', eval_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {"confidence_score": 0.5, "reasoning": "解析不能"}

        except Exception as e:
            result = {"confidence_score": 0.5, "reasoning": f"エラー: {e}"}

        result["hedge_count"] = hedge_count
        result["hedge_density"] = hedge_density
        return result

    def publish_quality_metrics(self, scores):
        """品質スコアを CloudWatch メトリクスとして発行"""
        metrics_data = []

        metric_mappings = {
            "faithfulness_score": ("FaithfulnessScore", "None"),
            "consistency_score": ("ConsistencyScore", "None"),
            "confidence_score": ("ConfidenceScore", "None"),
            "overall_plausibility": ("EntityPlausibility", "None"),
            "hallucination_detected": ("HallucinationRate", "Percent"),
            "answer_relevancy": ("AnswerRelevancy", "None"),
        }

        for key, (metric_name, unit) in metric_mappings.items():
            if key in scores:
                value = scores[key]
                if key == "hallucination_detected":
                    value = 100.0 if value else 0.0
                elif isinstance(value, bool):
                    value = 1.0 if value else 0.0

                metrics_data.append({
                    'MetricName': metric_name,
                    'Value': float(value),
                    'Unit': unit,
                    'Timestamp': datetime.now(timezone.utc),
                    'Dimensions': [
                        {'Name': 'ModelId', 'Value': MODEL_ID},
                        {'Name': 'Environment', 'Value': 'demo'},
                    ]
                })

        if metrics_data:
            try:
                cloudwatch.put_metric_data(
                    Namespace=NAMESPACE,
                    MetricData=metrics_data
                )
                return len(metrics_data)
            except Exception as e:
                print(f"  ⚠️  メトリクス送信エラー: {e}")
                return 0
        return 0


# ============================================================
# デモ 1: 一貫性チェックによるハルシネーション検出
# ============================================================

def demo_consistency_check():
    """同じ質問への複数回答の一貫性を検証"""
    print("=" * 70)
    print("  デモ 1: 一貫性チェックによるハルシネーション検出")
    print("=" * 70)
    print("""
  同じ質問に対して複数回回答を生成し、回答間の矛盾を検出します。
  矛盾がある場合、モデルが事実に基づかない情報を生成している
  （ハルシネーション）可能性が高いと判断します。

  検出ロジック:
  ┌────────────────────────────────────────────────────────────────┐
  │  質問 Q を temperature=0.7 で N 回投げる                       │
  │  ↓                                                             │
  │  回答 A1, A2, ..., An を取得                                   │
  │  ↓                                                             │
  │  LLM-as-a-Judge で回答間の矛盾を検出                          │
  │  ↓                                                             │
  │  consistency_score が閾値以下 → ハルシネーション疑い           │
  └────────────────────────────────────────────────────────────────┘
""")

    detector = HallucinationDetector()

    # ハルシネーションが起きやすい質問（具体的な数値や事実を問う）
    test_questions = [
        "Amazon Bedrockが最初にリリースされた正確な日付と、リリース時に対応していたモデルの数を教えてください。",
        "AWS Lambda の最大同時実行数のデフォルト値と、最大メモリサイズは何MBですか？",
    ]

    all_scores = []
    for question in test_questions:
        print(f"\n{'─' * 70}")
        result = detector.consistency_check(question, num_samples=3)

        score = result.get("consistency_score", 0.5)
        all_scores.append(score)
        contradictions = result.get("contradictions", [])
        assessment = result.get("assessment", "N/A")

        hallucination_detected = score < 0.7

        print(f"\n  📊 評価結果:")
        print(f"     一貫性スコア: {score:.2f} {'🔴 低い' if score < 0.7 else '🟢 良好'}")
        print(f"     ハルシネーション判定: {'⚠️ 疑いあり' if hallucination_detected else '✅ 問題なし'}")
        if contradictions:
            print(f"     矛盾点:")
            for c in contradictions[:3]:
                print(f"       • {c}")
        print(f"     総合評価: {assessment}")

        # メトリクス発行
        detector.publish_quality_metrics({
            "consistency_score": score,
            "hallucination_detected": hallucination_detected,
        })

        time.sleep(2)

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    print(f"\n{'─' * 70}")
    print(f"  📈 平均一貫性スコア: {avg_score:.2f}")
    if avg_score < 0.7:
        print(f"  ⚠️  一貫性が低い → プロンプト改善またはモデル変更を検討")


# ============================================================
# デモ 2: ソース検証（RAG のハルシネーション検出）
# ============================================================

def demo_source_verification():
    """RAG の回答がソースに忠実かを検証"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: ソース検証（RAG のハルシネーション検出）")
    print("=" * 70)
    print("""
  RAG システムでは、検索されたソースに基づかない回答（ハルシネーション）が
  特に問題です。回答の各主張がソースで裏付けられているかを検証します。

  Faithfulness Score:
  ┌────────────────────────────────────────────────────────────────┐
  │  回答を主張（claim）に分解                                     │
  │  ↓                                                             │
  │  各主張がソースに裏付けられているかチェック                     │
  │  ↓                                                             │
  │  Score = 裏付けあり主張数 / 全主張数                           │
  └────────────────────────────────────────────────────────────────┘
""")

    detector = HallucinationDetector()

    # テストケース: ソースドキュメントと質問
    source_document = """【AWS Lambda 料金体系 2024年版】

AWS Lambda の料金は、リクエスト数と実行時間に基づいて計算されます。

リクエスト料金:
- 最初の100万リクエスト/月: 無料（Free Tier）
- 以降: $0.20/100万リクエスト

実行時間料金（1GBメモリの場合）:
- 最初の40万GB秒/月: 無料（Free Tier）
- 以降: $0.0000166667/GB秒

メモリ設定:
- 最小: 128MB
- 最大: 10,240MB（10GB）
- 増分: 1MB単位

タイムアウト:
- 最大実行時間: 900秒（15分）
- デフォルト: 3秒

同時実行:
- アカウントのデフォルト上限: 1,000
- リクエストにより上限引き上げ可能
"""

    question = "AWS Lambda の料金と制限について教えてください。"

    # まず回答を生成
    print(f"  ソース文字数: {len(source_document)} 文字")
    print(f"  質問: {question}")
    print(f"\n{'─' * 70}")
    print(f"  回答を生成中...")

    rag_prompt = f"""以下のソースドキュメントのみに基づいて質問に回答してください。
ソースに記載されていない情報は含めないでください。

【ソース】
{source_document}

【質問】
{question}"""

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": rag_prompt}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 400}
        )
        faithful_answer = response['output']['message']['content'][0]['text']
        print(f"\n  💬 忠実な回答（ソースに基づく）:")
        for line in faithful_answer.split('\n')[:8]:
            print(f"    {line}")
    except Exception as e:
        faithful_answer = "回答生成に失敗しました"
        print(f"  ❌ エラー: {e}")

    time.sleep(2)

    # ソース検証実行
    print(f"\n{'─' * 70}")
    print(f"  ソース検証を実行中...")
    result = detector.source_verification(question, source_document, faithful_answer)

    faithfulness = result.get("faithfulness_score", 0.5)
    supported = result.get("supported_claims", [])
    unsupported = result.get("unsupported_claims", [])
    hallucinated = result.get("hallucinated_facts", [])
    assessment = result.get("assessment", "N/A")

    print(f"\n  📊 忠実性評価:")
    print(f"     Faithfulness Score: {faithfulness:.2f} {'🟢 良好' if faithfulness >= 0.8 else '🟡 注意' if faithfulness >= 0.5 else '🔴 低い'}")
    if supported:
        print(f"     裏付けあり ({len(supported)}):")
        for s in supported[:3]:
            print(f"       ✅ {s}")
    if unsupported:
        print(f"     裏付けなし ({len(unsupported)}):")
        for u in unsupported[:3]:
            print(f"       ⚠️  {u}")
    if hallucinated:
        print(f"     捏造された事実 ({len(hallucinated)}):")
        for h in hallucinated[:3]:
            print(f"       🔴 {h}")
    print(f"     総合評価: {assessment}")

    time.sleep(2)

    # 意図的にハルシネーションを誘発するケース
    print(f"\n{'─' * 70}")
    print(f"  ⚠️  意図的にハルシネーションを誘発するテスト:")
    print(f"     ソースにない情報を聞いて回答させます...")

    hallucination_prompt = f"""以下の質問に詳しく回答してください。

【質問】
AWS Lambda の GPU サポートの料金体系と、対応している GPU の種類、
また GPU Lambda で TensorFlow を使う場合の推奨メモリ設定を教えてください。"""

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": hallucination_prompt}]}],
            inferenceConfig={"temperature": 0.5, "maxTokens": 400}
        )
        hallucinated_answer = response['output']['message']['content'][0]['text']
        print(f"\n  💬 回答（ハルシネーションの可能性）:")
        for line in hallucinated_answer.split('\n')[:6]:
            print(f"    {line}")
    except Exception as e:
        hallucinated_answer = "回答生成に失敗しました"
        print(f"  ❌ エラー: {e}")

    time.sleep(2)

    # ソース検証（ソースにない情報の検出）
    print(f"\n  ソース検証を実行中...")
    result2 = detector.source_verification(
        "Lambda GPU サポートの料金",
        source_document,
        hallucinated_answer
    )

    faithfulness2 = result2.get("faithfulness_score", 0.5)
    hallucinated2 = result2.get("hallucinated_facts", [])

    print(f"\n  📊 忠実性評価（ハルシネーション誘発ケース）:")
    print(f"     Faithfulness Score: {faithfulness2:.2f} {'🟢 良好' if faithfulness2 >= 0.8 else '🟡 注意' if faithfulness2 >= 0.5 else '🔴 低い'}")
    if hallucinated2:
        print(f"     捏造された事実:")
        for h in hallucinated2[:5]:
            print(f"       🔴 {h}")
    print(f"     → ソースに存在しない情報が生成されました = ハルシネーション")

    # メトリクス発行
    detector.publish_quality_metrics({
        "faithfulness_score": faithfulness,
        "hallucination_detected": faithfulness2 < 0.5,
    })


# ============================================================
# デモ 3: 総合品質スコアリングとモニタリング
# ============================================================

def demo_quality_scoring():
    """総合品質スコアの計算とダッシュボード連携"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: 総合品質スコアリングとダッシュボード連携")
    print("=" * 70)
    print("""
  複数の品質指標を組み合わせた総合品質スコアを計算し、
  CloudWatch ダッシュボードで継続的にモニタリングします。

  品質スコア構成:
  ┌──────────────────────┬──────┬────────────────────────────────┐
  │ 指標                 │ 重み │ 説明                           │
  ├──────────────────────┼──────┼────────────────────────────────┤
  │ Faithfulness         │ 30%  │ ソースへの忠実性               │
  │ Answer Relevancy     │ 25%  │ 質問への回答適切性             │
  │ Consistency          │ 20%  │ 回答の一貫性                   │
  │ Entity Plausibility  │ 15%  │ エンティティの妥当性           │
  │ Confidence           │ 10%  │ モデルの信頼度                 │
  └──────────────────────┴──────┴────────────────────────────────┘
""")

    detector = HallucinationDetector()

    # テストケースの実行
    test_question = "Amazon DynamoDB の料金モデルと、オンデマンドモードとプロビジョンドモードの違いを教えてください。"

    print(f"  テスト質問: {test_question}")
    print(f"\n{'─' * 70}")

    # 回答生成
    print(f"  回答を生成中...")
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": test_question}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 400}
        )
        answer = response['output']['message']['content'][0]['text']
        print(f"  💬 回答: {answer[:100]}...")
    except Exception as e:
        answer = "DynamoDB はオンデマンドとプロビジョンドの2つの料金モードがあります。"
        print(f"  ⚠️  フォールバック回答を使用: {e}")

    time.sleep(2)

    # 各品質指標の計算
    print(f"\n  品質指標を計算中...")
    print(f"{'─' * 70}")

    # 信頼度スコア
    print(f"  [1/3] 信頼度スコア計算中...")
    confidence_result = detector.compute_confidence_score(test_question, answer)
    confidence_score = confidence_result.get("confidence_score", 0.5)
    print(f"         → {confidence_score:.2f}")

    time.sleep(2)

    # エンティティ検証
    print(f"  [2/3] エンティティ検証中...")
    entity_result = detector.entity_verification(answer)
    entity_score = entity_result.get("overall_plausibility", 0.5)
    suspicious = entity_result.get("suspicious_entities", [])
    print(f"         → {entity_score:.2f}")
    if suspicious:
        for s in suspicious[:3]:
            print(f"           ⚠️  疑わしいエンティティ: {s}")

    time.sleep(2)

    # 回答関連性（LLM-as-a-Judge）
    print(f"  [3/3] 回答関連性を評価中...")
    relevancy_prompt = f"""質問に対する回答の関連性を0.0〜1.0で評価してください。

質問: {test_question}
回答: {answer}

JSON形式で回答: {{"relevancy_score": 0.0-1.0, "reasoning": "理由"}}"""

    try:
        rel_response = bedrock.converse(
            modelId=EVALUATOR_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": relevancy_prompt}]}],
            inferenceConfig={"temperature": 0.1, "maxTokens": 200}
        )
        rel_text = rel_response['output']['message']['content'][0]['text']
        rel_match = re.search(r'\{[^{}]*\}', rel_text, re.DOTALL)
        if rel_match:
            rel_result = json.loads(rel_match.group())
            relevancy_score = rel_result.get("relevancy_score", 0.7)
        else:
            relevancy_score = 0.7
    except Exception:
        relevancy_score = 0.7
    print(f"         → {relevancy_score:.2f}")

    # 総合スコア計算
    weights = {
        "faithfulness": 0.30,
        "relevancy": 0.25,
        "consistency": 0.20,
        "entity": 0.15,
        "confidence": 0.10,
    }

    # 一貫性は前のデモで計算済みと想定、ここではデフォルト値を使用
    consistency_score = 0.8  # デモ用デフォルト値

    composite_score = (
        0.85 * weights["faithfulness"]  # 前のデモからの仮値
        + relevancy_score * weights["relevancy"]
        + consistency_score * weights["consistency"]
        + entity_score * weights["entity"]
        + confidence_score * weights["confidence"]
    )

    # 結果表示
    print(f"\n{'─' * 70}")
    print(f"  📊 総合品質スコアレポート:")
    print(f"  {'─' * 50}")
    print(f"  {'指標':<25} {'スコア':<10} {'重み':<8} {'加重スコア':<10}")
    print(f"  {'─' * 50}")
    print(f"  {'Faithfulness':<25} {'0.85':<10} {'30%':<8} {0.85*0.30:<10.3f}")
    print(f"  {'Answer Relevancy':<25} {relevancy_score:<10.2f} {'25%':<8} {relevancy_score*0.25:<10.3f}")
    print(f"  {'Consistency':<25} {consistency_score:<10.2f} {'20%':<8} {consistency_score*0.20:<10.3f}")
    print(f"  {'Entity Plausibility':<25} {entity_score:<10.2f} {'15%':<8} {entity_score*0.15:<10.3f}")
    print(f"  {'Confidence':<25} {confidence_score:<10.2f} {'10%':<8} {confidence_score*0.10:<10.3f}")
    print(f"  {'─' * 50}")
    print(f"  {'総合品質スコア':<25} {composite_score:<10.3f}")
    print(f"  {'─' * 50}")

    quality_level = "🟢 良好" if composite_score >= 0.8 else "🟡 注意" if composite_score >= 0.6 else "🔴 要改善"
    print(f"  判定: {quality_level}")

    # CloudWatch メトリクス発行
    print(f"\n  CloudWatch にメトリクスを発行中...")
    sent = detector.publish_quality_metrics({
        "faithfulness_score": 0.85,
        "consistency_score": consistency_score,
        "confidence_score": confidence_score,
        "overall_plausibility": entity_score,
        "answer_relevancy": relevancy_score,
        "hallucination_detected": composite_score < 0.6,
    })
    print(f"  ✅ {sent} 件のメトリクスを送信完了")

    # アラートルール
    print(f"""
  📋 品質アラートルール:
  ┌────────────────────────────────┬──────────┬──────────────────────┐
  │ 条件                           │ レベル   │ アクション           │
  ├────────────────────────────────┼──────────┼──────────────────────┤
  │ ハルシネーション率 > 5%        │ 警告     │ 管理者通知           │
  │ ハルシネーション率 > 10%       │ 緊急     │ モデル切り替え検討   │
  │ Faithfulness < 0.7             │ 警告     │ RAG パイプライン確認 │
  │ 総合品質スコア < 0.6           │ 緊急     │ サービス一時停止検討 │
  │ 信頼度スコア低下 > 20%        │ 注意     │ プロンプト改善       │
  └────────────────────────────────┴──────────┴──────────────────────┘
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 8: ハルシネーション検出と応答品質モニタリング")
    print("🔷" * 35)
    print("\n  LLM の応答品質を多角的に評価し、ハルシネーションを")
    print("  検出・モニタリングするパイプラインを実装します。")
    print()

    # デモ 1: 一貫性チェック
    demo_consistency_check()
    time.sleep(2)

    # デモ 2: ソース検証
    demo_source_verification()
    time.sleep(2)

    # デモ 3: 総合品質スコアリング
    demo_quality_scoring()
