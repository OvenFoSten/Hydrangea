# Hydrangea

[English](README.md) | 日本語

Hydrangea は、軽量で小さな LLM ゲートウェイです。

> [!WARNING]
> Hydrangea は現在、初期段階のプロトタイプです。公開 API は予告なく変更される可能性があります。

## 特徴

Cooperative Context（`CoopContext`）は、呼び出し側が定義した Context Area による一時的なメッセージの追加と、明示的なスケジューリング、ライフサイクル、回収のセマンティクスを提供します。

## 現在の対応範囲

- `google-genai` 2.10.0 を利用した Google Gemini
- `openai` 2.x の Responses API を利用した OpenAI
- OpenAI 互換の埋め込みエンドポイント

## 開発用インストール

```bash
python -m pip install -e .
```

インストールされたパッケージは、現在のソースツリーを直接参照します。

## OpenAI のレスポンスと推論

OpenAI の `LLM.invoke()` は SDK の完全な `Response` を返します。
`context.push_back(response)` で追加すると、暗号化された推論と関数呼び出しを含む
すべての出力項目を、1 つのネイティブコンテキスト要素として保持します。
リクエストは `store=False` を使用し、`previous_response_id` に依存せず、
ローカルで履歴を管理して再送します。関数の結果は元の `call_id` を持つ
`function_call_output` として送信します。接続先は `/v1/responses` に対応する必要があります。

`GeminiResponse` と同様に、`hydrangea.openai.OpenAIResponse(response)` は
`output`、`thoughts`（推論の要約）、`tool_calls`、元の `content` を提供します。
`response.model_dump_json()` で保存し、
`openai.types.responses.Response.model_validate_json(snapshot)` で復元できます。
完全なオブジェクトを復元すると、次の呼び出しで暗号化された推論を再送できます。
`OpenAIContext.input` は再送用の項目を提供します。従来の Chat Completions の
`messages` プロパティと `ChatCompletionMessage` の戻り値型は置き換わりました。

## なぜ Hydrangea を作ったのか？

Hydrangea は、もともと Aster 向けの内部モジュールとして始まりました。より大きなフレームワークに任せるのではなく、LLM のコンテキストを自分で管理したかったからです。別のプロジェクトでも同じコードが必要になったため、複数のコピーを管理するより、小さなパッケージとして切り出す方が素直だと考えました。

## LangChain を使えばいいのでは？

正直なところ、その方がよいかもしれません。;)

Hydrangea は、フル機能のフレームワークを置き換えるためのものではありません。コンテキストを明示的に制御し、プロバイダーごとの差異を薄い抽象化で吸収しつつ、プロバイダー固有のレスポンスをそのまま扱うために、私のプロジェクトが必要とした小さなゲートウェイにすぎません。

## 名前の由来

アジサイは、丸く大きな花の集まりと、土壌の酸性度によって花色が変わることで知られる植物です。Hydrangea という名前は、この花にちなんで付けました。[ウィキペディア](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%82%B8%E3%82%B5%E3%82%A4)
