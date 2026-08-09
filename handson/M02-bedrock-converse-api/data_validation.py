"""
モジュール 2: データ検証と品質保証パイプライン
- 入力データの完全性・形式検証
- Amazon Comprehend による PII 検出とマスキング
- 品質スコアリング
"""

import boto3
import json
import re
from datetime import datetime

# AWS クライアント
comprehend = boto3.client('comprehend', region_name='us-east-1')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

# テストデータ（PII を含むサンプル）
SAMPLE_DATA = [
    {
        "id": "feedback-001",
        "timestamp": "2024-11-15T10:30:00Z",
        "source": "web_form",
        "content": "田中太郎です。電話番号は090-1234-5678です。先日の診察について質問があります。処方された薬の副作用が気になります。メールアドレスはtanaka@example.comです。",
        "category": "medical_inquiry",
        "language": "ja"
    },
    {
        "id": "feedback-002",
        "timestamp": "2024-11-15T11:00:00Z",
        "source": "web_form",
        "content": "予約の変更をお願いします。次回は来週の火曜日に変更したいです。",
        "category": "appointment",
        "language": "ja"
    },
    {
        "id": "feedback-003",
        "timestamp": "",  # 意図的に空 - 検証エラーを発生させる
        "source": "web_form",
        "content": "",  # 意図的に空 - 検証エラーを発生させる
        "category": "general",
        "language": "ja"
    },
    {
        "id": "feedback-004",
        "timestamp": "2024-11-15T14:00:00Z",
        "source": "phone_transcription",
        "content": "私のマイナンバーは123456789012です。保険証番号は12345678で、住所は東京都渋谷区神宮前1-2-3です。検査結果を郵送してください。",
        "category": "personal_info",
        "language": "ja"
    }
]

# 必須フィールド定義
REQUIRED_FIELDS = ["id", "timestamp", "source", "content", "category", "language"]


def validate_completeness(record):
    """完全性検証: 必須フィールドの存在と非空チェック"""
    issues = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            issues.append(f"フィールド '{field}' が存在しません")
        elif not record[field]:
            issues.append(f"フィールド '{field}' が空です")
    
    score = (len(REQUIRED_FIELDS) - len(issues)) / len(REQUIRED_FIELDS) * 100
    return {"score": score, "issues": issues}


def validate_format(record):
    """形式検証: データ型、長さ、パターンのチェック"""
    issues = []
    
    # タイムスタンプ形式の検証
    if record.get("timestamp"):
        try:
            datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            issues.append("タイムスタンプの形式が不正です (ISO 8601 が必要)")
    
    # コンテンツの長さ検証
    content = record.get("content", "")
    if len(content) > 10000:
        issues.append(f"コンテンツが長すぎます ({len(content)} 文字 / 上限 10000)")
    elif len(content) < 5 and content:
        issues.append(f"コンテンツが短すぎます ({len(content)} 文字)")
    
    # カテゴリの検証
    valid_categories = ["medical_inquiry", "appointment", "general", "personal_info", "complaint"]
    if record.get("category") and record["category"] not in valid_categories:
        issues.append(f"無効なカテゴリ: {record['category']}")
    
    score = max(0, 100 - len(issues) * 25)
    return {"score": score, "issues": issues}


def detect_pii(text):
    """Amazon Comprehend で PII を検出する"""
    if not text:
        return {"entities": [], "score": 100}
    
    try:
        response = comprehend.detect_pii_entities(
            Text=text,
            LanguageCode='ja'
        )
        
        entities = []
        for entity in response.get('Entities', []):
            entities.append({
                "type": entity['Type'],
                "score": entity['Score'],
                "begin": entity['BeginOffset'],
                "end": entity['EndOffset'],
                "text": text[entity['BeginOffset']:entity['EndOffset']]
            })
        
        return {"entities": entities, "pii_detected": len(entities) > 0}
    
    except Exception as e:
        # Comprehend が利用できない場合のフォールバック（正規表現ベース）
        print(f"  ⚠ Comprehend 呼び出しエラー: {e}")
        print("  → 正規表現ベースのフォールバック検出を使用します")
        return detect_pii_fallback(text)


def detect_pii_fallback(text):
    """正規表現ベースの PII 検出（フォールバック）"""
    entities = []
    
    patterns = {
        "PHONE": r'0\d{1,4}-\d{1,4}-\d{3,4}',
        "EMAIL": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "MY_NUMBER": r'\d{12}',
        "ADDRESS": r'(東京都|大阪府|北海道|.{2,3}県).{2,}[0-9\-]+',
    }
    
    for pii_type, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            entities.append({
                "type": pii_type,
                "score": 0.85,
                "begin": match.start(),
                "end": match.end(),
                "text": match.group()
            })
    
    return {"entities": entities, "pii_detected": len(entities) > 0}


def mask_pii(text, entities):
    """PII をマスキングする"""
    masked_text = text
    # 後ろから置換（オフセットがずれないように）
    for entity in sorted(entities, key=lambda x: x['begin'], reverse=True):
        pii_type = entity['type']
        masked_text = (
            masked_text[:entity['begin']] +
            f"[{pii_type}]" +
            masked_text[entity['end']:]
        )
    return masked_text


def calculate_quality_score(completeness, format_check, pii_result):
    """総合品質スコアを計算する"""
    weights = {
        "completeness": 0.3,
        "format": 0.3,
        "privacy": 0.4
    }
    
    privacy_score = 0 if pii_result.get("pii_detected") else 100
    
    total_score = (
        completeness["score"] * weights["completeness"] +
        format_check["score"] * weights["format"] +
        privacy_score * weights["privacy"]
    )
    
    return round(total_score, 1)


def run_validation_pipeline():
    """検証パイプラインを実行する"""
    print("=" * 70)
    print("  データ検証・品質保証パイプライン")
    print("=" * 70)
    
    results = []
    
    for record in SAMPLE_DATA:
        print(f"\n{'─' * 70}")
        print(f"  レコード ID: {record['id']}")
        print(f"{'─' * 70}")
        
        # 1. 完全性検証
        completeness = validate_completeness(record)
        print(f"\n  [1] 完全性検証: {completeness['score']:.0f}%")
        for issue in completeness["issues"]:
            print(f"      ❌ {issue}")
        if not completeness["issues"]:
            print(f"      ✅ すべての必須フィールドが存在")
        
        # 2. 形式検証
        format_check = validate_format(record)
        print(f"\n  [2] 形式検証: {format_check['score']:.0f}%")
        for issue in format_check["issues"]:
            print(f"      ❌ {issue}")
        if not format_check["issues"]:
            print(f"      ✅ すべての形式チェックに合格")
        
        # 3. PII 検出
        content = record.get("content", "")
        if content:
            pii_result = detect_pii(content)
            print(f"\n  [3] PII 検出:")
            if pii_result["entities"]:
                print(f"      ⚠ {len(pii_result['entities'])} 件の PII を検出")
                for entity in pii_result["entities"]:
                    print(f"        - {entity['type']}: '{entity['text']}' (信頼度: {entity['score']:.2f})")
                
                # マスキング処理
                masked = mask_pii(content, pii_result["entities"])
                print(f"\n      マスキング前: {content[:80]}...")
                print(f"      マスキング後: {masked[:80]}...")
            else:
                print(f"      ✅ PII は検出されませんでした")
                pii_result = {"entities": [], "pii_detected": False}
        else:
            pii_result = {"entities": [], "pii_detected": False}
            print(f"\n  [3] PII 検出: スキップ（コンテンツなし）")
        
        # 4. 総合品質スコア
        quality_score = calculate_quality_score(completeness, format_check, pii_result)
        status = "✅ 合格" if quality_score >= 70 else "❌ 要修正"
        print(f"\n  [総合] 品質スコア: {quality_score}% {status}")
        
        results.append({
            "id": record["id"],
            "quality_score": quality_score,
            "completeness": completeness["score"],
            "format": format_check["score"],
            "pii_detected": pii_result.get("pii_detected", False),
            "pii_count": len(pii_result.get("entities", [])),
            "status": "pass" if quality_score >= 70 else "fail"
        })
    
    # サマリー
    print(f"\n\n{'=' * 70}")
    print("  検証結果サマリー")
    print(f"{'=' * 70}")
    
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = len(results) - passed
    avg_score = sum(r["quality_score"] for r in results) / len(results)
    total_pii = sum(r["pii_count"] for r in results)
    
    print(f"\n  処理件数: {len(results)}")
    print(f"  合格: {passed} 件 / 不合格: {failed} 件")
    print(f"  平均品質スコア: {avg_score:.1f}%")
    print(f"  検出された PII: {total_pii} 件")
    
    print(f"\n  {'ID':<15} {'スコア':<10} {'完全性':<10} {'形式':<10} {'PII':<10} {'ステータス'}")
    print(f"  {'─'*65}")
    for r in results:
        pii_str = f"{r['pii_count']}件" if r['pii_detected'] else "なし"
        print(f"  {r['id']:<15} {r['quality_score']:<10.1f} {r['completeness']:<10.0f} {r['format']:<10.0f} {pii_str:<10} {r['status']}")
    
    print(f"\n{'=' * 70}")
    print("  推奨アクション:")
    print("  • PII が検出されたレコードはマスキング処理後に基盤モデルへ送信")
    print("  • 品質スコア 70% 未満のレコードは人間によるレビューを実施")
    print("  • 完全性不足のレコードはデータソースへ差し戻し")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    run_validation_pipeline()
