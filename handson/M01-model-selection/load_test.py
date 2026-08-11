"""
モジュール 1: 動的モデル選択 API 負荷テスト
さまざまな複雑度のクエリ100件を一括送信し、ルーティング結果を確認する

使い方:
  python3.12 load_test.py <API_URL>

例:
  python3.12 load_test.py https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/prod
"""

import json
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================================================
# テストクエリ (100件: simple=40, medium=30, complex=30)
# =============================================================================
QUERIES = [
    # --- simple (40件) ---
    {"query": "AWSのリージョンとは何ですか？", "complexity": "simple"},
    {"query": "S3の料金体系を教えてください", "complexity": "simple"},
    {"query": "EC2のインスタンスタイプを一覧で教えて", "complexity": "simple"},
    {"query": "Lambdaの最大実行時間は？", "complexity": "simple"},
    {"query": "VPCとは何ですか？", "complexity": "simple"},
    {"query": "IAMロールとIAMユーザーの違いは？", "complexity": "simple"},
    {"query": "CloudFrontの用途を教えてください", "complexity": "simple"},
    {"query": "DynamoDBの主キーの種類は？", "complexity": "simple"},
    {"query": "Route 53とは何ですか？", "complexity": "simple"},
    {"query": "ECSとEKSの違いを教えて", "complexity": "simple"},
    {"query": "AWS CLIのインストール方法は？", "complexity": "simple"},
    {"query": "セキュリティグループとNACLの違いは？", "complexity": "simple"},
    {"query": "CloudWatchで何ができますか？", "complexity": "simple"},
    {"query": "S3のストレージクラスを挙げてください", "complexity": "simple"},
    {"query": "Elastic IPとは何ですか？", "complexity": "simple"},
    {"query": "RDSでサポートされるデータベースエンジンは？", "complexity": "simple"},
    {"query": "SNSとSQSの違いは？", "complexity": "simple"},
    {"query": "AWS Organizationsの目的は？", "complexity": "simple"},
    {"query": "CloudTrailとは何ですか？", "complexity": "simple"},
    {"query": "Auto Scalingの基本的な仕組みを教えて", "complexity": "simple"},
    {"query": "Amazon Bedrockとは何ですか？", "complexity": "simple"},
    {"query": "生成AIのトークンとは？", "complexity": "simple"},
    {"query": "プロンプトエンジニアリングとは？", "complexity": "simple"},
    {"query": "RAGとは何の略ですか？", "complexity": "simple"},
    {"query": "基盤モデルの種類を教えてください", "complexity": "simple"},
    {"query": "ハルシネーションとは何ですか？", "complexity": "simple"},
    {"query": "Amazon Novaシリーズの特徴は？", "complexity": "simple"},
    {"query": "Converse APIとInvokeModel APIの違いは？", "complexity": "simple"},
    {"query": "埋め込みモデルとは何ですか？", "complexity": "simple"},
    {"query": "ナレッジベースの用途を教えて", "complexity": "simple"},
    {"query": "Guardrailsで何ができますか？", "complexity": "simple"},
    {"query": "ファインチューニングとRAGの違いは？", "complexity": "simple"},
    {"query": "Lambdaのメモリ設定の範囲は？", "complexity": "simple"},
    {"query": "AWS SAMとは何ですか？", "complexity": "simple"},
    {"query": "CloudFormationの基本概念は？", "complexity": "simple"},
    {"query": "Amazon SageMakerとBedrockの違いは？", "complexity": "simple"},
    {"query": "APIGatewayのスロットリング設定は？", "complexity": "simple"},
    {"query": "Step Functionsの用途は？", "complexity": "simple"},
    {"query": "EventBridgeとは何ですか？", "complexity": "simple"},
    {"query": "KMSの基本的な使い方を教えて", "complexity": "simple"},

    # --- medium (30件) ---
    {"query": "S3のライフサイクルポリシーを設計するとき、コストとアクセスパターンのバランスをどう考えればよいですか？", "complexity": "medium"},
    {"query": "マイクロサービスアーキテクチャでサービス間通信をどう設計すべきですか？同期と非同期それぞれのメリットを踏まえて説明してください。", "complexity": "medium"},
    {"query": "DynamoDBのパーティションキー設計で、ホットパーティション問題を回避するためのベストプラクティスを教えてください。", "complexity": "medium"},
    {"query": "Lambda関数のコールドスタートを最小化するための具体的な手法を5つ挙げてください。", "complexity": "medium"},
    {"query": "マルチAZ構成とマルチリージョン構成の違い、それぞれの使い分け基準を説明してください。", "complexity": "medium"},
    {"query": "CI/CDパイプラインでBlue/GreenデプロイとCanaryデプロイをどう使い分けるべきですか？", "complexity": "medium"},
    {"query": "VPCエンドポイントのGateway型とInterface型の使い分けと、セキュリティ上の考慮点を教えてください。", "complexity": "medium"},
    {"query": "CloudWatchのカスタムメトリクスとアラームを使った効果的なモニタリング戦略を提案してください。", "complexity": "medium"},
    {"query": "Amazon Bedrockでプロンプトキャッシングを使う場合の最適なキャッシュポイント設計を説明してください。", "complexity": "medium"},
    {"query": "RAGシステムでチャンキング戦略が検索品質に与える影響と、ドキュメントタイプ別の最適な設定を教えてください。", "complexity": "medium"},
    {"query": "生成AIアプリケーションのコストを月間50%削減するための具体的な戦略を提案してください。", "complexity": "medium"},
    {"query": "Amazon Bedrock Guardrailsのコンテンツフィルターとトピック制御の設計方針を、ヘルスケア業界向けに説明してください。", "complexity": "medium"},
    {"query": "エージェントのツール呼び出しで失敗した場合のリトライ戦略とフォールバック設計について解説してください。", "complexity": "medium"},
    {"query": "CloudFrontとAPI Gatewayを組み合わせたキャッシュ戦略で、動的コンテンツと静的コンテンツの最適な扱い方を教えてください。", "complexity": "medium"},
    {"query": "IAMのリソースベースポリシーとアイデンティティベースポリシーの使い分けを、Bedrockアクセス制御の例で説明してください。", "complexity": "medium"},
    {"query": "Terraformとaws CDKの比較、チーム規模や既存スキルに応じた選定基準を教えてください。", "complexity": "medium"},
    {"query": "生成AIのハルシネーション検出パイプラインを設計する場合、どのようなメトリクスと検出手法を組み合わせるべきですか？", "complexity": "medium"},
    {"query": "マルチテナントSaaSアプリケーションでDynamoDBのテーブル設計をどのように行うべきですか？", "complexity": "medium"},
    {"query": "Amazon OpenSearch Serviceでベクトル検索を実装する際のインデックス設計とパフォーマンスチューニングについて教えてください。", "complexity": "medium"},
    {"query": "生成AIのA/Bテストをプロダクション環境で安全に実施するためのアーキテクチャを提案してください。", "complexity": "medium"},
    {"query": "Bedrock AgentCoreのGatewayとMemoryを組み合わせたエージェント設計のベストプラクティスを教えてください。", "complexity": "medium"},
    {"query": "プロンプトフローで条件分岐を使って顧客の問い合わせを適切にルーティングする設計例を教えてください。", "complexity": "medium"},
    {"query": "セマンティックキャッシュの類似度しきい値をチューニングする方法と、誤ヒットのリスク管理について説明してください。", "complexity": "medium"},
    {"query": "AWS Well-Architected FrameworkのAIレンズにおけるコスト最適化の柱の要点をまとめてください。", "complexity": "medium"},
    {"query": "EventBridgeとStep Functionsを組み合わせたイベント駆動アーキテクチャの設計パターンを3つ教えてください。", "complexity": "medium"},
    {"query": "生成AIアプリケーションのレイテンシーを50%削減するための具体的なアプローチを教えてください。", "complexity": "medium"},
    {"query": "Bedrock ナレッジベースのメタデータフィルタリングを活用したアクセス制御の実装方法を教えてください。", "complexity": "medium"},
    {"query": "サーバーレスアーキテクチャで大量の非同期ジョブを処理する場合のSQS + Lambda構成の設計指針を教えてください。", "complexity": "medium"},
    {"query": "プロンプトのバージョン管理とCI/CDパイプラインの統合方法を具体的に説明してください。", "complexity": "medium"},
    {"query": "LLMの出力を構造化JSON形式で安定的に取得するためのプロンプト設計テクニックを教えてください。", "complexity": "medium"},

    # --- complex (30件) ---
    {"query": "金融サービス企業向けに、規制コンプライアンス（GDPR、金融庁ガイドライン）を満たしつつ、AIベースの融資審査システムのアーキテクチャを設計してください。マルチリージョン対応、監査証跡、説明可能性の確保を含めてください。", "complexity": "complex"},
    {"query": "月間1000万リクエストを処理する生成AIチャットボットのTCO分析を行ってください。プロンプトキャッシング、セマンティックキャッシュ、モデルダウングレードの各最適化手法を適用した場合のコスト削減効果を定量的に算出してください。", "complexity": "complex"},
    {"query": "ヘルスケア企業が患者データを扱うAIアシスタントを構築する場合、HIPAA準拠のアーキテクチャを設計してください。PII保護、監査ログ、データレジデンシー、暗号化、アクセス制御の各要素を含めてください。", "complexity": "complex"},
    {"query": "マルチエージェントシステムで旅行予約、ホテル手配、現地ガイドの3つのエージェントが協調して動作するアーキテクチャを、AgentCoreのコンポーネントを使って設計してください。障害耐性とスケーラビリティも考慮してください。", "complexity": "complex"},
    {"query": "既存のオンプレミスERPシステム（SAP）とAmazon Bedrockを統合するハイブリッドアーキテクチャを設計してください。リアルタイムデータ同期、セキュリティ境界、フェイルオーバー、段階的移行計画を含めてください。", "complexity": "complex"},
    {"query": "RAGシステムの品質を継続的に改善するMLOpsパイプラインを設計してください。RAGAS評価、自動チャンキング最適化、埋め込みモデルの更新管理、A/Bテスト、ロールバック機能を含む完全なパイプラインを提案してください。", "complexity": "complex"},
    {"query": "グローバルに展開する大企業のAIガバナンスフレームワークを設計してください。プロンプト管理、モデル評価、バイアス検出、インシデント対応、規制対応（EU AI Act、日本のAI戦略）を包括的に提案してください。", "complexity": "complex"},
    {"query": "プロバイダー障害に対してRTO 5分、RPO 1分を達成するマルチリージョン生成AIシステムのDR設計を行ってください。Route53フェイルオーバー、DynamoDBグローバルテーブル、S3クロスリージョンレプリケーションの統合設計を含めてください。", "complexity": "complex"},
    {"query": "1日50万件のカスタマーサポート問い合わせを処理するAIシステムの容量計画を行ってください。ピーク時の同時リクエスト数、必要なBedrock APIスループット、コスト予測、オートスケーリング戦略を含めてください。", "complexity": "complex"},
    {"query": "サプライチェーン最適化のためのAIシステムを設計してください。需要予測、在庫最適化、配送ルート計算を生成AIで支援し、既存のWMS/TMSシステムとの統合を含むエンドツーエンドのアーキテクチャを提案してください。", "complexity": "complex"},
    {"query": "生成AIを活用した自動コードレビューシステムを設計してください。GitHubとの統合、セキュリティ脆弱性検出、コーディング規約チェック、パフォーマンス分析を含み、誤検知率を5%以下に抑える設計を提案してください。", "complexity": "complex"},
    {"query": "エンタープライズ向けAIプラットフォームのマルチテナントアーキテクチャを設計してください。テナント分離、リソース制限、コスト配分、カスタマイズ性、SLA管理を含む包括的な設計を提案してください。", "complexity": "complex"},
    {"query": "リアルタイム不正検知システムにおいて、生成AIとルールベースエンジンを組み合わせたハイブリッドアプローチを設計してください。レイテンシー100ms以内、誤検知率1%以下、年間10億トランザクション処理の要件を満たしてください。", "complexity": "complex"},
    {"query": "大規模言語モデルの推論コストを80%削減しながらサービス品質を維持するための包括的最適化戦略を提案してください。モデル選択、キャッシュ、バッチ処理、プロンプト圧縮、蒸留の各手法のROI分析を含めてください。", "complexity": "complex"},
    {"query": "IoTセンサーデータと生成AIを組み合わせた予測保全システムを設計してください。リアルタイムデータストリーミング、異常検知、自然言語レポート生成、技術者向けアクション推奨を含むアーキテクチャを提案してください。", "complexity": "complex"},
    {"query": "法律文書の自動レビューシステムを設計してください。契約書のリスク条項検出、規制準拠チェック、類似判例検索、修正提案生成を含み、弁護士のワークフローに統合される設計を提案してください。", "complexity": "complex"},
    {"query": "教育機関向けのアダプティブラーニングAIシステムを設計してください。学習者の理解度推定、パーソナライズされたコンテンツ生成、進捗追跡、教師向けダッシュボードを含む設計を提案してください。", "complexity": "complex"},
    {"query": "マルチモーダルAIを活用した製造業の品質管理システムを設計してください。画像認識による外観検査、テキスト分析による異常報告、音声認識による作業者報告の統合処理を含めてください。", "complexity": "complex"},
    {"query": "生成AIのセキュリティ脅威モデリングを実施してください。プロンプトインジェクション、データポイズニング、モデル窃取、側チャネル攻撃の各脅威に対する防御戦略とモニタリング計画を提案してください。", "complexity": "complex"},
    {"query": "大企業のナレッジマネジメントシステムにRAGを導入する際の移行計画を作成してください。既存Wiki/Confluenceからの移行、50万ドキュメントの処理、部門別アクセス制御、多言語対応を含めてください。", "complexity": "complex"},
    {"query": "生成AIを活用したカスタマーサクセスプラットフォームを設計してください。顧客ヘルススコア予測、解約リスク検知、パーソナライズされた提案生成、CSMワークフロー自動化を含むアーキテクチャを提案してください。", "complexity": "complex"},
    {"query": "動的モデル選択システムの本番運用における課題と解決策を包括的に分析してください。レイテンシーオーバーヘッド、コスト管理、品質一貫性、モニタリング、障害対応の各観点を含めてください。", "complexity": "complex"},
    {"query": "Amazon Bedrockを使った音声AIアシスタントのエンドツーエンドアーキテクチャを設計してください。音声認識、意図理解、対話管理、応答生成、音声合成の各コンポーネントと、レイテンシー最適化を含めてください。", "complexity": "complex"},
    {"query": "ESG（環境・社会・ガバナンス）レポートの自動生成システムを設計してください。多ソースからのデータ収集、KPI計算、規制フレームワーク（GRI、SASB、TCFD）への準拠チェック、ステークホルダー向けレポート生成を含めてください。", "complexity": "complex"},
    {"query": "生成AIの出力品質を保証するためのテスト戦略を包括的に設計してください。単体テスト、統合テスト、回帰テスト、負荷テスト、カオスエンジニアリングの各フェーズでのAI固有のアプローチを含めてください。", "complexity": "complex"},
    {"query": "データメッシュアーキテクチャにおける生成AIの活用方法を設計してください。ドメイン別のAIサービス、フェデレーテッドガバナンス、セルフサービスデータ基盤、品質メトリクスの自動追跡を含めてください。", "complexity": "complex"},
    {"query": "生成AIを活用した新薬開発支援システムを設計してください。論文要約、化合物構造解析、臨床試験データ分析、規制当局提出文書生成を含み、再現性と監査性を確保するアーキテクチャを提案してください。", "complexity": "complex"},
    {"query": "リアルタイム翻訳・通訳システムにおいて、専門用語の正確性を保ちながら低レイテンシーを実現するアーキテクチャを設計してください。ドメイン辞書管理、用語一貫性チェック、フィードバックループを含めてください。", "complexity": "complex"},
    {"query": "保険会社向けのクレーム処理自動化システムを設計してください。ドキュメント理解、損害査定、不正検知、顧客コミュニケーション生成を含み、既存のコアシステムとの統合を考慮してください。", "complexity": "complex"},
    {"query": "生成AIのコンプライアンス監査フレームワークを設計してください。モデルの透明性確保、バイアス監視、データプロバナンス追跡、定期的な品質評価、規制当局への報告自動化を含む包括的なフレームワークを提案してください。", "complexity": "complex"},
]


def send_query(api_url, query_data, index):
    """1件のクエリを送信"""
    url = f"{api_url}/query"
    payload = json.dumps(query_data).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - start
            return {
                "index": index,
                "success": True,
                "complexity": query_data["complexity"],
                "model_used": body.get("model_used", "unknown"),
                "latency": elapsed,
                "fallback": body.get("fallback_used", False),
                "query_preview": query_data["query"][:50],
            }
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        elapsed = time.time() - start
        return {
            "index": index,
            "success": False,
            "complexity": query_data["complexity"],
            "error": str(e)[:80],
            "latency": elapsed,
            "query_preview": query_data["query"][:50],
        }


def run_load_test(api_url, concurrency=5):
    """負荷テスト実行"""
    print("=" * 70)
    print("  動的モデル選択 API 負荷テスト")
    print("=" * 70)
    print(f"  API URL: {api_url}")
    print(f"  クエリ数: {len(QUERIES)}")
    print(f"  同時実行数: {concurrency}")
    print(f"  複雑度内訳: simple={sum(1 for q in QUERIES if q['complexity']=='simple')}, "
          f"medium={sum(1 for q in QUERIES if q['complexity']=='medium')}, "
          f"complex={sum(1 for q in QUERIES if q['complexity']=='complex')}")
    print("=" * 70)

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(send_query, api_url, q, i): i
            for i, q in enumerate(QUERIES)
        }

        completed = 0
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1

            status = "✅" if result["success"] else "❌"
            model = result.get("model_used", "N/A")[:20]
            print(f"  [{completed:3d}/100] {status} {result['complexity']:<8} "
                  f"→ {model:<22} {result['latency']:.1f}s  "
                  f"{result['query_preview']}...")

    total_time = time.time() - start_time

    # サマリー
    print("\n" + "=" * 70)
    print("  結果サマリー")
    print("=" * 70)

    success_results = [r for r in results if r["success"]]
    failed_results = [r for r in results if not r["success"]]

    print(f"\n  成功: {len(success_results)} / {len(results)}")
    print(f"  失敗: {len(failed_results)}")
    print(f"  合計時間: {total_time:.1f}秒")
    print(f"  スループット: {len(results) / total_time:.1f} req/s")

    if success_results:
        avg_latency = sum(r["latency"] for r in success_results) / len(success_results)
        print(f"  平均レイテンシー: {avg_latency:.2f}秒")

    # 複雑度別の集計
    print(f"\n  {'複雑度':<10} {'件数':<8} {'成功率':<10} {'平均レイテンシー':<15} {'主なルーティング先'}")
    print(f"  {'─' * 65}")

    for complexity in ["simple", "medium", "complex"]:
        c_results = [r for r in success_results if r["complexity"] == complexity]
        c_total = sum(1 for r in results if r["complexity"] == complexity)
        if c_results:
            avg_lat = sum(r["latency"] for r in c_results) / len(c_results)
            # 最頻出モデル
            models = {}
            for r in c_results:
                m = r.get("model_used", "unknown")
                models[m] = models.get(m, 0) + 1
            top_model = max(models, key=models.get) if models else "N/A"
            top_model_short = top_model.split(".")[-1][:25] if "." in top_model else top_model[:25]
            success_rate = f"{len(c_results)}/{c_total}"
            print(f"  {complexity:<10} {c_total:<8} {success_rate:<10} {avg_lat:<15.2f}s {top_model_short}")

    # モデル別の集計
    print(f"\n  {'モデル':<35} {'呼び出し回数':<12} {'平均レイテンシー'}")
    print(f"  {'─' * 60}")

    model_stats = {}
    for r in success_results:
        m = r.get("model_used", "unknown")
        if m not in model_stats:
            model_stats[m] = {"count": 0, "total_latency": 0}
        model_stats[m]["count"] += 1
        model_stats[m]["total_latency"] += r["latency"]

    for model, stats in sorted(model_stats.items(), key=lambda x: -x[1]["count"]):
        avg = stats["total_latency"] / stats["count"]
        model_short = model.split("/")[-1][:33] if "/" in model else model[:33]
        print(f"  {model_short:<35} {stats['count']:<12} {avg:.2f}s")

    # フォールバック統計
    fallback_count = sum(1 for r in success_results if r.get("fallback"))
    if fallback_count:
        print(f"\n  フォールバック発生: {fallback_count} 件")

    # 失敗詳細
    if failed_results:
        print(f"\n  失敗詳細:")
        for r in failed_results[:5]:
            print(f"    [{r['index']}] {r.get('error', 'unknown')}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python3.12 load_test.py <API_URL>")
        print("例:     python3.12 load_test.py https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/prod")
        sys.exit(1)

    api_url = sys.argv[1].rstrip("/")
    run_load_test(api_url, concurrency=5)
