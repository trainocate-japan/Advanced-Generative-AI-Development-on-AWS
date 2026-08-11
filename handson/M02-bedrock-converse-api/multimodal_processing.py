"""
モジュール 2: マルチモーダルデータ処理
- テキスト + 画像の統合処理（Bedrock Converse API）
- 形式検証と前処理
- 処理パターンの比較（順次/並列/ハイブリッド）
"""

import boto3
import json
import base64
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# AWS クライアント
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

MODEL_ID = "amazon.nova-lite-v1:0"


def create_sample_image_base64():
    """デモ用のサンプル画像データ（100x100ピクセルのPNG グラデーション）を生成"""
    # Bedrock モデルが受け付ける十分なサイズ・内容の画像を生成
    # 本番では S3 から取得した実際の画像を使用します
    import struct
    import zlib

    # 100x100 ピクセルのカラフルなグラデーション PNG を生成
    width, height = 100, 100

    def make_png(w, h):
        """有効な PNG を生成する（グラデーション画像）"""
        # IHDR
        ihdr_data = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)  # 8bit RGB
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)

        # IDAT - グラデーションピクセルデータ（モデルが認識しやすい）
        raw_data = b''
        for y in range(h):
            raw_data += b'\x00'  # filter byte (None)
            for x in range(w):
                r = int(255 * x / w)
                g = int(255 * y / h)
                b_val = int(255 * (1 - x / w))
                raw_data += bytes([r, g, b_val])
        compressed = zlib.compress(raw_data)
        idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
        idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)

        # IEND
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)

        return b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend

    png_bytes = make_png(width, height)
    return base64.b64encode(png_bytes).decode('utf-8')


def validate_image(image_data_base64, max_size_mb=5):
    """画像の形式とサイズを検証する"""
    print("  [検証] 画像データの検証中...")
    
    # Base64 デコード
    try:
        image_bytes = base64.b64decode(image_data_base64)
    except Exception as e:
        return {"valid": False, "error": f"Base64デコードエラー: {e}"}
    
    # サイズチェック
    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > max_size_mb:
        return {"valid": False, "error": f"画像サイズ超過: {size_mb:.2f}MB (上限: {max_size_mb}MB)"}
    
    # フォーマットチェック（マジックバイト）
    format_detected = None
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        format_detected = "png"
    elif image_bytes[:2] == b'\xff\xd8':
        format_detected = "jpeg"
    elif image_bytes[:4] == b'GIF8':
        format_detected = "gif"
    else:
        return {"valid": False, "error": "サポートされていない画像形式"}
    
    print(f"    ✅ 形式: {format_detected.upper()}")
    print(f"    ✅ サイズ: {size_mb:.4f} MB")
    
    return {
        "valid": True,
        "format": format_detected,
        "size_mb": size_mb,
        "size_bytes": len(image_bytes)
    }


def process_text_only(query, context=""):
    """テキストのみの処理"""
    start_time = time.time()
    
    prompt = f"{context}\n\n{query}" if context else query
    
    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{
            "role": "user",
            "content": [{"text": prompt}]
        }],
        inferenceConfig={"temperature": 0.3, "maxTokens": 512}
    )
    
    latency = time.time() - start_time
    output = response['output']['message']['content'][0]['text']
    usage = response['usage']
    
    return {
        "type": "text_only",
        "response": output,
        "latency": latency,
        "input_tokens": usage['inputTokens'],
        "output_tokens": usage['outputTokens']
    }


def process_multimodal(query, image_base64, image_format="png"):
    """テキスト + 画像のマルチモーダル処理"""
    start_time = time.time()
    
    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{
            "role": "user",
            "content": [
                {
                    "image": {
                        "format": image_format,
                        "source": {
                            "bytes": base64.b64decode(image_base64)
                        }
                    }
                },
                {
                    "text": query
                }
            ]
        }],
        inferenceConfig={"temperature": 0.3, "maxTokens": 512}
    )
    
    latency = time.time() - start_time
    output = response['output']['message']['content'][0]['text']
    usage = response['usage']
    
    return {
        "type": "multimodal",
        "response": output,
        "latency": latency,
        "input_tokens": usage['inputTokens'],
        "output_tokens": usage['outputTokens']
    }


def process_sequential(tasks):
    """順次処理パターン"""
    start_time = time.time()
    results = []
    
    for task in tasks:
        result = process_text_only(task["query"], task.get("context", ""))
        results.append(result)
    
    total_time = time.time() - start_time
    return {"pattern": "sequential", "total_time": total_time, "results": results}


def process_parallel(tasks):
    """並列処理パターン"""
    start_time = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(process_text_only, task["query"], task.get("context", "")): i
            for i, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            results.append(future.result())
    
    total_time = time.time() - start_time
    return {"pattern": "parallel", "total_time": total_time, "results": results}


def run_multimodal_demo():
    """マルチモーダル処理デモの実行"""
    print("=" * 70)
    print("  マルチモーダルデータ処理デモ")
    print("=" * 70)
    
    # パート 1: 画像検証
    print("\n" + "─" * 70)
    print("  パート 1: 画像データの検証")
    print("─" * 70)
    
    sample_image = create_sample_image_base64()
    validation = validate_image(sample_image)
    
    if not validation["valid"]:
        print(f"  ❌ 画像検証失敗: {validation['error']}")
        return
    
    print(f"  ✅ 画像検証合格")
    
    # パート 2: テキストのみ vs マルチモーダル
    print("\n" + "─" * 70)
    print("  パート 2: テキストのみ vs マルチモーダル処理の比較")
    print("─" * 70)
    
    query = "この文書の内容を要約し、重要なポイントを3つ挙げてください。"
    context = "以下は患者向けの薬の説明書です。投与量、副作用、注意事項について記載されています。"
    
    print(f"\n  クエリ: {query}")
    
    # テキストのみ
    print("\n  ▶ テキストのみで処理中...", end="", flush=True)
    try:
        text_result = process_text_only(query, context)
        print(f" 完了 ({text_result['latency']:.2f}秒)")
        print(f"    入力トークン: {text_result['input_tokens']}")
        print(f"    出力トークン: {text_result['output_tokens']}")
        print(f"    応答: {text_result['response'][:100]}...")
    except Exception as e:
        print(f" エラー: {e}")
        text_result = None
    
    # マルチモーダル（テキスト + 画像）
    print("\n  ▶ マルチモーダル (テキスト+画像) で処理中...", end="", flush=True)
    try:
        mm_result = process_multimodal(query, sample_image, "png")
        print(f" 完了 ({mm_result['latency']:.2f}秒)")
        print(f"    入力トークン: {mm_result['input_tokens']}")
        print(f"    出力トークン: {mm_result['output_tokens']}")
        print(f"    応答: {mm_result['response'][:100]}...")
    except Exception as e:
        print(f" エラー: {e}")
        mm_result = None
    
    # パート 3: 処理パターン比較
    print("\n" + "─" * 70)
    print("  パート 3: 処理パターンの比較（順次 vs 並列）")
    print("─" * 70)
    
    tasks = [
        {"query": "AWSのリージョンについて簡潔に説明してください。"},
        {"query": "サーバーレスアーキテクチャの利点を3つ挙げてください。"},
        {"query": "Amazon Bedrockとは何ですか？"},
    ]
    
    print(f"\n  タスク数: {len(tasks)}")
    
    # 順次処理
    print("\n  ▶ 順次処理...", end="", flush=True)
    try:
        seq_result = process_sequential(tasks)
        print(f" 完了 (合計: {seq_result['total_time']:.2f}秒)")
    except Exception as e:
        print(f" エラー: {e}")
        seq_result = {"total_time": 0}
    
    # 並列処理
    print("  ▶ 並列処理...", end="", flush=True)
    try:
        par_result = process_parallel(tasks)
        print(f" 完了 (合計: {par_result['total_time']:.2f}秒)")
    except Exception as e:
        print(f" エラー: {e}")
        par_result = {"total_time": 0}
    
    # 比較結果
    if seq_result["total_time"] > 0 and par_result["total_time"] > 0:
        speedup = seq_result["total_time"] / par_result["total_time"]
        print(f"\n  比較結果:")
        print(f"    順次処理: {seq_result['total_time']:.2f}秒")
        print(f"    並列処理: {par_result['total_time']:.2f}秒")
        print(f"    高速化率: {speedup:.1f}x")
    
    # まとめ
    print(f"\n\n{'=' * 70}")
    print("  まとめ")
    print(f"{'=' * 70}")
    print("""
  マルチモーダル処理のベストプラクティス:
  
  1. 画像の前処理: 形式検証 → サイズ最適化 → Base64エンコード
  2. 処理パターンの選択:
     - 独立タスク → 並列処理（レイテンシー削減）
     - 依存関係あり → 順次処理（データ整合性確保）
     - 複合ワークロード → ハイブリッド
  3. エラーハンドリング: 各モダリティで個別にフォールバックを実装
  4. コスト管理: 画像トークンは高コスト → 必要な場合のみ使用
""")


if __name__ == "__main__":
    run_multimodal_demo()
