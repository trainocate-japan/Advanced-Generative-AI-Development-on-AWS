"""
モジュール 8: 回答パターン分析 - 長さと複雑さのモニタリング
- 回答の長さの異常検出（ベースラインからの偏差）
- 複雑さパターンの分析（繰り返し検出、コヒーレンス低下、構造異常）
- パターンベースのハルシネーション兆候の検出
- 品質メトリクスの CloudWatch 発行
"""

import boto3
import json
import time
import re
import math
from datetime import datetime, timezone
from collections import Counter

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

MODEL_ID = "amazon.nova-lite-v1:0"
NAMESPACE = "GenAI/Bedrock"


# ============================================================
# 回答の長さのモニタリング
# ============================================================

class ResponseLengthMonitor:
    """
    回答の長さを監視し、異常を検出するクラス。

    ハルシネーションとの関連:
    - 回答が異常に長い: モデルが関係ない情報を生成し続けている兆候
    - 回答が異常に短い: モデルが回答できず曖昧に逃げている兆候
    - 同カテゴリの質問で長さが大きくばらつく: 事実に基づかない回答の可能性

    ベースラインの確立:
    - 質問カテゴリ別に正常な回答長の分布を記録
    - 移動平均と標準偏差で動的ベースラインを維持
    """

    def __init__(self):
        # カテゴリ別のベースライン（文字数）
        # 実運用では過去データから学習する
        self.baselines = {
            "factual_short": {"mean": 150, "std": 50, "description": "事実の短答（定義、数値）"},
            "factual_detail": {"mean": 400, "std": 120, "description": "事実の詳細説明"},
            "comparison": {"mean": 500, "std": 150, "description": "比較・対比の説明"},
            "how_to": {"mean": 600, "std": 200, "description": "手順・方法の説明"},
            "analysis": {"mean": 700, "std": 250, "description": "分析・考察"},
        }
        self.history = []

    def classify_question(self, question):
        """質問をカテゴリに分類（シンプルなルールベース）"""
        question_lower = question.lower()

        if any(w in question_lower for w in ["とは", "what is", "定義", "意味"]):
            return "factual_short"
        elif any(w in question_lower for w in ["違い", "比較", "difference", "vs"]):
            return "comparison"
        elif any(w in question_lower for w in ["方法", "手順", "how to", "やり方", "設定"]):
            return "how_to"
        elif any(w in question_lower for w in ["分析", "なぜ", "理由", "考察", "影響"]):
            return "analysis"
        else:
            return "factual_detail"

    def analyze_length(self, question, response_text):
        """
        回答の長さを分析し、異常度を返す。

        Returns:
            dict: 分析結果
                - char_count: 文字数
                - token_estimate: 推定トークン数
                - category: 質問カテゴリ
                - z_score: 標準偏差からの偏差
                - is_anomalous: 異常かどうか
                - anomaly_type: 異常の種類（too_long / too_short / normal）
                - risk_level: リスクレベル
        """
        char_count = len(response_text)
        # 日本語: 約1.5文字/トークン、英語: 約4文字/トークン（概算）
        token_estimate = int(char_count / 1.5)
        sentence_count = len(re.split(r'[。.!！?？\n]', response_text))

        category = self.classify_question(question)
        baseline = self.baselines.get(category, self.baselines["factual_detail"])

        # Z-score の計算
        z_score = (char_count - baseline["mean"]) / baseline["std"] if baseline["std"] > 0 else 0

        # 異常判定
        if z_score > 3.0:
            anomaly_type = "too_long"
            risk_level = "high"
        elif z_score > 2.0:
            anomaly_type = "too_long"
            risk_level = "medium"
        elif z_score < -2.0:
            anomaly_type = "too_short"
            risk_level = "medium"
        elif z_score < -3.0:
            anomaly_type = "too_short"
            risk_level = "high"
        else:
            anomaly_type = "normal"
            risk_level = "low"

        result = {
            "char_count": char_count,
            "token_estimate": token_estimate,
            "sentence_count": sentence_count,
            "category": category,
            "category_description": baseline["description"],
            "baseline_mean": baseline["mean"],
            "baseline_std": baseline["std"],
            "z_score": round(z_score, 2),
            "is_anomalous": abs(z_score) > 2.0,
            "anomaly_type": anomaly_type,
            "risk_level": risk_level,
        }

        self.history.append(result)
        return result

    def detect_length_drift(self, window_size=10):
        """
        直近のレスポンスの長さのドリフト（傾向変化）を検出。

        回答がだんだん長くなっている/短くなっている場合、
        モデルの挙動が変化している兆候。
        """
        if len(self.history) < window_size:
            return {"drift_detected": False, "reason": "データ不足"}

        recent = self.history[-window_size:]
        lengths = [r["char_count"] for r in recent]

        # 線形回帰の傾き（簡易版）
        n = len(lengths)
        x_mean = (n - 1) / 2
        y_mean = sum(lengths) / n
        numerator = sum((i - x_mean) * (lengths[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator > 0 else 0

        # 変動係数
        std = (sum((l - y_mean) ** 2 for l in lengths) / n) ** 0.5
        cv = std / y_mean if y_mean > 0 else 0

        drift_detected = abs(slope) > 20 or cv > 0.5

        return {
            "drift_detected": drift_detected,
            "slope": round(slope, 2),
            "coefficient_of_variation": round(cv, 3),
            "mean_length": round(y_mean, 0),
            "interpretation": (
                f"回答長が1リクエストあたり{slope:.0f}文字{'増加' if slope > 0 else '減少'}傾向"
                if abs(slope) > 20
                else f"変動が大きい（CV={cv:.2f}）" if cv > 0.5
                else "安定"
            ),
        }


# ============================================================
# 複雑さのパターン分析
# ============================================================

class ComplexityAnalyzer:
    """
    回答の複雑さパターンを分析し、ハルシネーションの兆候を検出する。

    検出する異常パターン:
    1. 繰り返し（ループ）: 同じフレーズが何度も出現
    2. コヒーレンス低下: 文間の論理的つながりが薄い
    3. 構造異常: 箇条書きの途中で突然別の話題に飛ぶ
    4. 過度の修飾: 実質的な情報がなく修飾語だけが多い
    """

    def __init__(self):
        pass

    def detect_repetition(self, text):
        """
        繰り返しパターンの検出。

        ハルシネーションの兆候:
        - 同じ文が繰り返される（モデルがループに入った）
        - 同じ単語・フレーズが異常に高頻度で出現
        - パラフレーズされた同じ内容が繰り返される
        """
        # 文単位で分割
        sentences = [s.strip() for s in re.split(r'[。.!！?？\n]', text) if s.strip()]

        if not sentences:
            return {"repetition_score": 0, "repeated_phrases": [], "details": "テキストなし"}

        # 完全一致の文の繰り返し
        sentence_counts = Counter(sentences)
        exact_duplicates = {s: c for s, c in sentence_counts.items() if c > 1}

        # N-gram ベースの繰り返し検出（3-gram）
        words = re.findall(r'\w+', text)
        if len(words) < 3:
            trigram_repetition_rate = 0
        else:
            trigrams = [tuple(words[i:i+3]) for i in range(len(words) - 2)]
            trigram_counts = Counter(trigrams)
            repeated_trigrams = sum(c - 1 for c in trigram_counts.values() if c > 1)
            trigram_repetition_rate = repeated_trigrams / len(trigrams) if trigrams else 0

        # 文の類似度による繰り返し検出（Jaccard 類似度）
        similar_pairs = []
        for i in range(len(sentences)):
            for j in range(i + 1, min(i + 5, len(sentences))):  # 近い文同士を比較
                words_i = set(re.findall(r'\w+', sentences[i]))
                words_j = set(re.findall(r'\w+', sentences[j]))
                if words_i and words_j:
                    jaccard = len(words_i & words_j) / len(words_i | words_j)
                    if jaccard > 0.7:
                        similar_pairs.append((sentences[i][:40], sentences[j][:40], round(jaccard, 2)))

        # 繰り返しスコア（0.0 = 繰り返しなし、1.0 = 全文繰り返し）
        repetition_score = min(1.0, (
            len(exact_duplicates) * 0.3
            + trigram_repetition_rate * 0.4
            + len(similar_pairs) * 0.1
        ))

        return {
            "repetition_score": round(repetition_score, 3),
            "exact_duplicate_sentences": len(exact_duplicates),
            "trigram_repetition_rate": round(trigram_repetition_rate, 3),
            "similar_sentence_pairs": len(similar_pairs),
            "examples": similar_pairs[:3],
            "is_looping": repetition_score > 0.3,
            "risk_level": "high" if repetition_score > 0.5 else "medium" if repetition_score > 0.3 else "low",
        }

    def analyze_coherence(self, text):
        """
        コヒーレンス（文間の論理的つながり）を分析。

        ハルシネーションの兆候:
        - 前の文と次の文に論理的つながりがない
        - 突然話題が飛ぶ
        - 接続詞が不適切に使われている
        """
        sentences = [s.strip() for s in re.split(r'[。.!！?？\n]', text) if s.strip()]

        if len(sentences) < 2:
            return {"coherence_score": 1.0, "topic_shifts": 0, "details": "文が少なすぎる"}

        # 隣接文間のキーワード重複率でコヒーレンスを推定
        overlap_scores = []
        topic_shifts = []

        for i in range(len(sentences) - 1):
            words_current = set(re.findall(r'\w{2,}', sentences[i]))
            words_next = set(re.findall(r'\w{2,}', sentences[i + 1]))

            if words_current and words_next:
                overlap = len(words_current & words_next) / len(words_current | words_next)
                overlap_scores.append(overlap)

                # 話題の急変を検出（重複率がほぼゼロ）
                if overlap < 0.05 and len(words_current) > 3 and len(words_next) > 3:
                    topic_shifts.append({
                        "position": i + 1,
                        "before": sentences[i][:50],
                        "after": sentences[i + 1][:50],
                    })

        avg_overlap = sum(overlap_scores) / len(overlap_scores) if overlap_scores else 0

        # コヒーレンススコア（高い = 一貫性あり）
        coherence_score = min(1.0, avg_overlap * 5)  # 0.2 のオーバーラップで 1.0

        return {
            "coherence_score": round(coherence_score, 3),
            "avg_sentence_overlap": round(avg_overlap, 3),
            "topic_shifts": len(topic_shifts),
            "topic_shift_details": topic_shifts[:3],
            "sentence_count": len(sentences),
            "is_incoherent": coherence_score < 0.3,
            "risk_level": "high" if coherence_score < 0.2 else "medium" if coherence_score < 0.4 else "low",
        }

    def analyze_information_density(self, text):
        """
        情報密度の分析。

        ハルシネーションの兆候:
        - 修飾語だけが多く実質的な情報がない（情報密度が低い）
        - 数値や固有名詞が異常に多い（でたらめに生成している可能性）
        - 同じ情報を言い換えているだけ（水増し）
        """
        words = re.findall(r'\w+', text)
        total_words = len(words)

        if total_words == 0:
            return {"density_score": 0, "details": "テキストなし"}

        # ユニーク単語率（語彙の多様性）
        unique_words = set(words)
        type_token_ratio = len(unique_words) / total_words

        # 情報語の割合（数値、固有名詞的なもの）
        numbers = re.findall(r'\d+[\d,.]*', text)
        # 英大文字始まりの単語（固有名詞の概算）
        proper_nouns = re.findall(r'[A-Z][a-zA-Z]{2,}', text)

        info_word_ratio = (len(numbers) + len(proper_nouns)) / total_words

        # フィラー表現の検出
        filler_patterns = [
            "ということ", "というもの", "と言え", "基本的に",
            "一般的に", "通常", "いわゆる", "すなわち",
            "つまり", "要するに", "言い換えると",
        ]
        filler_count = sum(text.count(f) for f in filler_patterns)
        filler_ratio = filler_count / max(len(re.split(r'[。.!！?？]', text)), 1)

        # 情報密度スコア（高い = 情報が濃い）
        density_score = min(1.0, type_token_ratio * 0.5 + info_word_ratio * 3.0 + (1 - filler_ratio) * 0.3)

        return {
            "density_score": round(density_score, 3),
            "type_token_ratio": round(type_token_ratio, 3),
            "total_words": total_words,
            "unique_words": len(unique_words),
            "numbers_found": len(numbers),
            "proper_nouns_found": len(proper_nouns),
            "filler_ratio": round(filler_ratio, 3),
            "is_low_density": density_score < 0.3,
            "risk_level": "high" if density_score < 0.2 else "medium" if density_score < 0.4 else "low",
        }

    def compute_composite_complexity(self, text):
        """全ての複雑さ指標を統合した総合スコアを計算"""
        repetition = self.detect_repetition(text)
        coherence = self.analyze_coherence(text)
        density = self.analyze_information_density(text)

        # 異常スコア（高い = より異常）
        anomaly_score = (
            repetition["repetition_score"] * 0.4
            + (1 - coherence["coherence_score"]) * 0.35
            + (1 - density["density_score"]) * 0.25
        )

        # リスク判定
        risk_factors = []
        if repetition["is_looping"]:
            risk_factors.append("繰り返しループ検出")
        if coherence["is_incoherent"]:
            risk_factors.append("コヒーレンス低下")
        if density["is_low_density"]:
            risk_factors.append("情報密度不足")

        return {
            "anomaly_score": round(anomaly_score, 3),
            "repetition": repetition,
            "coherence": coherence,
            "density": density,
            "risk_factors": risk_factors,
            "overall_risk": "high" if anomaly_score > 0.5 else "medium" if anomaly_score > 0.3 else "low",
            "hallucination_suspicion": anomaly_score > 0.4,
        }


# ============================================================
# メトリクス発行
# ============================================================

def publish_pattern_metrics(length_result, complexity_result):
    """回答パターンのメトリクスを CloudWatch に発行"""
    metrics_data = []
    timestamp = datetime.now(timezone.utc)
    dimensions = [
        {'Name': 'ModelId', 'Value': MODEL_ID},
        {'Name': 'Environment', 'Value': 'demo'},
    ]

    # 長さのメトリクス
    metrics_data.append({
        'MetricName': 'ResponseCharCount',
        'Value': float(length_result["char_count"]),
        'Unit': 'Count',
        'Timestamp': timestamp,
        'Dimensions': dimensions,
    })
    metrics_data.append({
        'MetricName': 'ResponseLengthZScore',
        'Value': float(abs(length_result["z_score"])),
        'Unit': 'None',
        'Timestamp': timestamp,
        'Dimensions': dimensions,
    })

    # 複雑さのメトリクス
    metrics_data.append({
        'MetricName': 'RepetitionScore',
        'Value': float(complexity_result["repetition"]["repetition_score"]),
        'Unit': 'None',
        'Timestamp': timestamp,
        'Dimensions': dimensions,
    })
    metrics_data.append({
        'MetricName': 'CoherenceScore',
        'Value': float(complexity_result["coherence"]["coherence_score"]),
        'Unit': 'None',
        'Timestamp': timestamp,
        'Dimensions': dimensions,
    })
    metrics_data.append({
        'MetricName': 'InformationDensity',
        'Value': float(complexity_result["density"]["density_score"]),
        'Unit': 'None',
        'Timestamp': timestamp,
        'Dimensions': dimensions,
    })
    metrics_data.append({
        'MetricName': 'PatternAnomalyScore',
        'Value': float(complexity_result["anomaly_score"]),
        'Unit': 'None',
        'Timestamp': timestamp,
        'Dimensions': dimensions,
    })

    try:
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=metrics_data
        )
        return len(metrics_data)
    except Exception as e:
        print(f"  ⚠️  メトリクス送信エラー: {e}")
        return 0


# ============================================================
# デモ 1: 回答の長さのモニタリング
# ============================================================

def demo_length_monitoring():
    """回答長の異常検出デモ"""
    print("=" * 70)
    print("  デモ 1: 回答の長さのモニタリング")
    print("=" * 70)
    print("""
  同じカテゴリの質問に対する回答の長さを監視し、
  ベースラインからの偏差でハルシネーションの兆候を検出します。

  異常パターン:
  ┌────────────────────────────────────────────────────────────────┐
  │ 異常に長い回答:                                                │
  │   → モデルが関係ない情報を生成し続けている                    │
  │   → 事実に基づかない「もっともらしい」文章の水増し            │
  │                                                                │
  │ 異常に短い回答:                                                │
  │   → モデルが回答できず曖昧に逃げている                        │
  │   → 知識がないのに無理に回答した結果                          │
  │                                                                │
  │ ばらつきが大きい:                                              │
  │   → 同じカテゴリなのに安定していない = 事実に基づいていない   │
  └────────────────────────────────────────────────────────────────┘
""")

    monitor = ResponseLengthMonitor()

    # テストクエリ（カテゴリ別に正常/異常を混在）
    test_cases = [
        {
            "question": "AWS S3とは何ですか？",
            "context": "短答カテゴリ（factual_short）",
            "max_tokens": 150,
        },
        {
            "question": "DynamoDBのパーティションキーとソートキーの違いは何ですか？",
            "context": "比較カテゴリ（comparison）",
            "max_tokens": 300,
        },
        {
            "question": "VPCの設定方法を教えてください。",
            "context": "手順カテゴリ（how_to）",
            "max_tokens": 400,
        },
        {
            # 意図的にトークン上限を大きくして長い回答を誘発
            "question": "クラウドコンピューティングの歴史と、AWS、Azure、GCPそれぞれの特徴、各サービスの料金体系の比較、マルチクラウド戦略のメリットデメリット、今後の展望について詳しく教えてください。",
            "context": "異常に長い回答を誘発するケース",
            "max_tokens": 1000,
        },
        {
            "question": "Lambda とは？",
            "context": "短答カテゴリ（factual_short）",
            "max_tokens": 50,
        },
    ]

    print(f"  {len(test_cases)} 件のテストケースを実行中...\n")

    for i, case in enumerate(test_cases, 1):
        print(f"  {'─' * 66}")
        print(f"  [{i}/{len(test_cases)}] {case['context']}")
        print(f"  質問: 「{case['question'][:50]}{'...' if len(case['question']) > 50 else ''}」")

        try:
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": case["question"]}]}],
                inferenceConfig={"temperature": 0.3, "maxTokens": case["max_tokens"]}
            )
            answer = response['output']['message']['content'][0]['text']
        except Exception as e:
            answer = f"エラー: {e}"
            print(f"  ❌ {e}")
            continue

        # 長さ分析
        result = monitor.analyze_length(case["question"], answer)

        icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}[result["risk_level"]]
        print(f"  {icon} 文字数: {result['char_count']} | "
              f"推定トークン: {result['token_estimate']} | "
              f"カテゴリ: {result['category']}")
        print(f"     ベースライン: {result['baseline_mean']}±{result['baseline_std']} | "
              f"Z-score: {result['z_score']} | "
              f"判定: {result['anomaly_type']}")

        if result["is_anomalous"]:
            print(f"     ⚠️  異常検出: 回答が{'長すぎ' if result['anomaly_type'] == 'too_long' else '短すぎ'}ます")

        time.sleep(1)

    # ドリフト検出
    drift = monitor.detect_length_drift(window_size=5)
    print(f"\n{'─' * 70}")
    print(f"  📊 長さのドリフト分析:")
    print(f"     傾き: {drift.get('slope', 'N/A')} 文字/リクエスト")
    print(f"     変動係数: {drift.get('coefficient_of_variation', 'N/A')}")
    print(f"     判定: {drift.get('interpretation', 'N/A')}")

    return monitor


# ============================================================
# デモ 2: 複雑さのパターン分析
# ============================================================

def demo_complexity_analysis():
    """回答の複雑さパターンを分析してハルシネーション兆候を検出"""
    print("\n\n" + "=" * 70)
    print("  デモ 2: 複雑さのパターン分析")
    print("=" * 70)
    print("""
  回答の構造を分析し、ハルシネーションに特有のパターンを検出します。

  検出パターン:
  ┌────────────────────────────┬────────────────────────────────────┐
  │ パターン                   │ ハルシネーションとの関連             │
  ├────────────────────────────┼────────────────────────────────────┤
  │ 繰り返し（ループ）         │ モデルが生成ループに入っている      │
  │ コヒーレンス低下           │ 事実でない情報をつなぎ合わせている  │
  │ 情報密度の低下             │ 具体的事実がなく修飾語で埋めている  │
  │ 話題の急変                 │ 回答を構成できず脱線している        │
  └────────────────────────────┴────────────────────────────────────┘
""")

    analyzer = ComplexityAnalyzer()

    # テスト 1: 正常な回答
    print(f"  テスト 1: 正常な回答の分析")
    print(f"  {'─' * 60}")

    normal_question = "Amazon S3 のストレージクラスの種類と使い分けを教えてください。"
    print(f"  質問: {normal_question}")

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": normal_question}]}],
            inferenceConfig={"temperature": 0.3, "maxTokens": 400}
        )
        normal_answer = response['output']['message']['content'][0]['text']
        print(f"  回答（先頭100文字）: {normal_answer[:100]}...")
    except Exception as e:
        normal_answer = "S3にはStandard、Standard-IA、Glacier、Glacier Deep Archiveなどのクラスがあります。Standard は頻繁にアクセスするデータに適しています。Standard-IA は低頻度アクセスデータ向けで、保存コストが安くなります。Glacier は長期アーカイブ向けで、取り出しに時間がかかりますがコストが最も安くなります。"
        print(f"  ⚠️  フォールバック回答を使用")

    time.sleep(1)

    result_normal = analyzer.compute_composite_complexity(normal_answer)
    print(f"\n  📊 正常回答の分析結果:")
    print(f"     異常スコア: {result_normal['anomaly_score']} (低い = 正常)")
    print(f"     繰り返し: {result_normal['repetition']['repetition_score']}")
    print(f"     コヒーレンス: {result_normal['coherence']['coherence_score']}")
    print(f"     情報密度: {result_normal['density']['density_score']}")
    print(f"     リスク: {result_normal['overall_risk']}")

    time.sleep(2)

    # テスト 2: ハルシネーションが起きやすい質問
    print(f"\n\n  テスト 2: ハルシネーションを誘発する質問")
    print(f"  {'─' * 60}")

    hallucination_question = "2026年に発表されたAWS Quantumサービスの新機能と、量子コンピューティングにおけるAWSの市場シェア、競合他社との詳細な技術比較、および今後5年間のロードマップを教えてください。"
    print(f"  質問: {hallucination_question[:60]}...")

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": hallucination_question}]}],
            inferenceConfig={"temperature": 0.7, "maxTokens": 600}
        )
        suspicious_answer = response['output']['message']['content'][0]['text']
        print(f"  回答（先頭100文字）: {suspicious_answer[:100]}...")
    except Exception as e:
        suspicious_answer = "AWS Quantum サービスは2026年に大きな進展がありました。" * 5 + "量子コンピューティングの市場は急速に成長しています。AWSは市場の約35%のシェアを持っています。競合のGoogleやIBMと比較して、AWSの優位性は安定性にあります。今後5年間でさらなる投資が予想されます。"
        print(f"  ⚠️  フォールバック回答を使用")

    time.sleep(1)

    result_suspicious = analyzer.compute_composite_complexity(suspicious_answer)
    print(f"\n  📊 疑わしい回答の分析結果:")
    print(f"     異常スコア: {result_suspicious['anomaly_score']} (高い = 異常)")
    print(f"     繰り返し: {result_suspicious['repetition']['repetition_score']}")
    print(f"     コヒーレンス: {result_suspicious['coherence']['coherence_score']}")
    print(f"     情報密度: {result_suspicious['density']['density_score']}")
    print(f"     リスク: {result_suspicious['overall_risk']}")
    if result_suspicious['risk_factors']:
        print(f"     リスク要因:")
        for factor in result_suspicious['risk_factors']:
            print(f"       ⚠️  {factor}")

    time.sleep(2)

    # テスト 3: 意図的に繰り返しを含む回答を分析
    print(f"\n\n  テスト 3: 繰り返しパターンの検出（シミュレーション）")
    print(f"  {'─' * 60}")

    looping_text = """AWS Lambda はサーバーレスコンピューティングサービスです。
Lambda を使用するとサーバーの管理が不要になります。
AWS Lambda はサーバーレスのコンピューティングサービスです。
サーバーの管理が不要になるのが Lambda の利点です。
Lambda ではサーバーレスでコードを実行できます。
サーバーを管理する必要がないのが大きなメリットです。
AWS Lambda はサーバーレスなコンピューティングを提供します。"""

    print(f"  （意図的に繰り返しを含むテキストを入力）")

    result_loop = analyzer.compute_composite_complexity(looping_text)
    print(f"\n  📊 繰り返しテキストの分析結果:")
    print(f"     異常スコア: {result_loop['anomaly_score']}")
    print(f"     繰り返しスコア: {result_loop['repetition']['repetition_score']}")
    print(f"     完全一致文: {result_loop['repetition']['exact_duplicate_sentences']} 件")
    print(f"     類似文ペア: {result_loop['repetition']['similar_sentence_pairs']} 件")
    print(f"     ループ検出: {'🔴 YES' if result_loop['repetition']['is_looping'] else '🟢 NO'}")
    if result_loop['repetition'].get('examples'):
        print(f"     類似例:")
        for ex in result_loop['repetition']['examples'][:2]:
            print(f"       「{ex[0]}...」≈「{ex[1]}...」(類似度: {ex[2]})")

    # 比較サマリー
    print(f"\n\n{'═' * 70}")
    print(f"  📊 パターン分析比較サマリー:")
    print(f"  {'─' * 60}")
    print(f"  {'テスト':<20} {'異常スコア':<12} {'繰り返し':<10} {'コヒーレンス':<12} {'判定':<10}")
    print(f"  {'─' * 60}")
    print(f"  {'正常な回答':<20} {result_normal['anomaly_score']:<12} "
          f"{result_normal['repetition']['repetition_score']:<10} "
          f"{result_normal['coherence']['coherence_score']:<12} "
          f"{'🟢 正常' if result_normal['overall_risk'] == 'low' else '🟡 注意'}")
    print(f"  {'疑わしい回答':<18} {result_suspicious['anomaly_score']:<12} "
          f"{result_suspicious['repetition']['repetition_score']:<10} "
          f"{result_suspicious['coherence']['coherence_score']:<12} "
          f"{'🔴 要注意' if result_suspicious['overall_risk'] == 'high' else '🟡 注意'}")
    print(f"  {'繰り返し回答':<18} {result_loop['anomaly_score']:<12} "
          f"{result_loop['repetition']['repetition_score']:<10} "
          f"{result_loop['coherence']['coherence_score']:<12} "
          f"{'🔴 要注意' if result_loop['overall_risk'] == 'high' else '🟡 注意'}")

    return analyzer


# ============================================================
# デモ 3: 統合モニタリング（長さ + 複雑さ）
# ============================================================

def demo_integrated_monitoring():
    """長さと複雑さを統合したハルシネーション検出パイプライン"""
    print("\n\n" + "=" * 70)
    print("  デモ 3: 統合パターンモニタリング")
    print("=" * 70)
    print("""
  回答の長さと複雑さのパターンを統合して、
  ハルシネーションの総合リスクを判定します。

  判定ロジック:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  回答受信 → 長さチェック → 複雑さ分析 → 統合リスク判定       │
  │                                            ↓                   │
  │                                    CloudWatch メトリクス発行    │
  │                                            ↓                   │
  │                                    閾値超過 → アラート         │
  └────────────────────────────────────────────────────────────────┘
""")

    length_monitor = ResponseLengthMonitor()
    complexity_analyzer = ComplexityAnalyzer()

    # 連続クエリのシミュレーション
    queries = [
        "EC2 インスタンスタイプの選び方を教えてください。",
        "CloudFormation と Terraform の違いは？",
        "S3 のライフサイクルポリシーの設定方法は？",
        "AWS の全リージョンの名前と場所、各リージョンで利用可能な全サービスのリスト、それぞれのリージョンの料金差、パフォーマンスの違い、レイテンシーのベンチマーク結果を全て詳しく教えてください。",
    ]

    print(f"  {len(queries)} 件のクエリを連続実行して統合分析...\n")

    results = []
    for i, query in enumerate(queries, 1):
        print(f"  {'─' * 66}")
        print(f"  [{i}] 「{query[:45]}{'...' if len(query) > 45 else ''}」")

        try:
            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": query}]}],
                inferenceConfig={"temperature": 0.5, "maxTokens": 500}
            )
            answer = response['output']['message']['content'][0]['text']
        except Exception as e:
            print(f"      ❌ エラー: {e}")
            continue

        # 統合分析
        length_result = length_monitor.analyze_length(query, answer)
        complexity_result = complexity_analyzer.compute_composite_complexity(answer)

        # 統合リスクスコア
        integrated_risk = (
            (1.0 if length_result["is_anomalous"] else 0.0) * 0.3
            + complexity_result["anomaly_score"] * 0.7
        )

        risk_label = "🔴 HIGH" if integrated_risk > 0.5 else "🟡 MEDIUM" if integrated_risk > 0.25 else "🟢 LOW"

        print(f"      長さ: {length_result['char_count']}文字 (Z={length_result['z_score']}) | "
              f"異常スコア: {complexity_result['anomaly_score']} | "
              f"統合リスク: {integrated_risk:.3f} {risk_label}")

        # メトリクス発行
        publish_pattern_metrics(length_result, complexity_result)

        results.append({
            "query": query[:40],
            "length": length_result["char_count"],
            "z_score": length_result["z_score"],
            "anomaly_score": complexity_result["anomaly_score"],
            "integrated_risk": integrated_risk,
        })

        time.sleep(1)

    # 統合サマリー
    print(f"\n{'═' * 70}")
    print(f"  📊 統合モニタリング結果:")
    print(f"  {'─' * 60}")

    high_risk_count = sum(1 for r in results if r["integrated_risk"] > 0.5)
    medium_risk_count = sum(1 for r in results if 0.25 < r["integrated_risk"] <= 0.5)
    low_risk_count = sum(1 for r in results if r["integrated_risk"] <= 0.25)

    print(f"  総リクエスト数: {len(results)}")
    print(f"  🔴 高リスク: {high_risk_count} 件")
    print(f"  🟡 中リスク: {medium_risk_count} 件")
    print(f"  🟢 低リスク: {low_risk_count} 件")

    if high_risk_count > 0:
        print(f"\n  ⚠️  高リスクの回答が検出されました。")
        print(f"     推奨アクション:")
        print(f"     • 該当回答の詳細なファクトチェック")
        print(f"     • プロンプトの制約強化（回答長の上限設定）")
        print(f"     • RAG の導入/強化によるソースベースの回答生成")

    print(f"""
  📋 パターンベース検出のしきい値設定:
  ┌──────────────────────────────┬──────────┬────────────────────────┐
  │ メトリクス                   │ しきい値 │ アクション             │
  ├──────────────────────────────┼──────────┼────────────────────────┤
  │ 回答長 Z-score              │ > 3.0    │ 自動レビューキューへ   │
  │ 繰り返しスコア              │ > 0.3    │ ループ検出アラート     │
  │ コヒーレンススコア          │ < 0.3    │ 品質低下アラート       │
  │ 情報密度                    │ < 0.2    │ 水増し回答の警告       │
  │ 統合リスクスコア            │ > 0.5    │ ハルシネーション疑い   │
  └──────────────────────────────┴──────────┴────────────────────────┘

  💡 ベストプラクティス:
  • しきい値は控えめに始めて、誤検出に基づいて調整する
  • クリエイティブ系タスクは医療系タスクより許容幅を広くする
  • 最初の2週間はアラートを「観察モード」で運用し、
    誤検出率を確認してからエスカレーションを有効化する
""")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔷" * 35)
    print("  モジュール 8: 回答パターン分析 - 長さと複雑さのモニタリング")
    print("🔷" * 35)
    print("\n  回答の長さと構造的パターンからハルシネーションの兆候を")
    print("  検出するモニタリングシステムを実装します。")
    print()

    # デモ 1: 回答の長さのモニタリング
    demo_length_monitoring()
    time.sleep(2)

    # デモ 2: 複雑さのパターン分析
    demo_complexity_analysis()
    time.sleep(2)

    # デモ 3: 統合モニタリング
    demo_integrated_monitoring()
