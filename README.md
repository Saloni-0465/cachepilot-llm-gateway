# CachePilot LLM Gateway

An LLM gateway with exact and semantic caching. The project will measure when prompt reuse is safe and how much latency and estimated cost it can save.

## Run locally

Activate the virtual environment and configure a development API key in the same terminal:

```bash
source .venv/bin/activate
export CACHEPILOT_API_KEY="replace-this-with-a-long-random-value"
uvicorn cachepilot.main:app --reload
```

`GET /health` is public. Gateway routes under `/v1` require an `Authorization: Bearer <key>` header. For example:

```bash
curl http://127.0.0.1:8000/v1/status \
  -H "Authorization: Bearer $CACHEPILOT_API_KEY"
```

The environment variable is a local development configuration. The planned persistent key management will store hashed keys in the database.

## Automated tests

Install the development dependencies and run the suite with:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The tests use in-memory Redis and request-log fakes; they do not require Docker or call an external LLM provider.

## Try a mock chat completion

The first chat endpoint uses a local mock provider, so it makes no external model calls and has no provider cost. With the server running and `CACHEPILOT_API_KEY` set in that terminal, send a request from another terminal:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $CACHEPILOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-model","messages":[{"role":"user","content":"Hello, CachePilot"}]}'
```

The response uses the chat-completion response shape and includes `X-Provider: mock`. Token counts are rough estimates for this mock only; a real provider adapter will use the provider's returned usage.

## Exact-response cache

Start the local Redis service before sending chat requests:

```bash
docker compose up -d redis postgres
```

The gateway caches the full response for an identical supported request for 300 seconds by default. The cache key includes the model, messages, and temperature, and is scoped to a SHA-256 hash of the caller's API key. Unknown request fields are rejected so an unkeyed generation option cannot silently affect cache reuse. Responses include `X-Cache: MISS` on the first request and `X-Cache: HIT` on a repeat. If Redis is unavailable, the gateway calls the mock provider and returns `X-Cache: UNAVAILABLE`.

Configure `REDIS_URL` or `CACHE_TTL_SECONDS` to change the Redis connection or cache duration.

## Per-key rate limiting

Chat-completion requests are limited per authenticated API key using a shared Redis fixed window. The defaults allow 60 requests per 60 seconds. Configure `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS` to change these values. Responses include `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, and `X-RateLimit-Status`; callers over the limit receive HTTP `429 Too Many Requests` with `Retry-After`. If Redis is unavailable, requests continue and `X-RateLimit-Status: UNAVAILABLE` signals that enforcement could not run.


## Usage logging

PostgreSQL stores request metadata in the `request_logs` table: request ID, a hash of the API key, model, cache status, provider, estimated token counts, latency, estimated cost fields, HTTP status, and timestamp. Prompt and response text are not stored. The mock provider has no model billing, so its estimated cost and savings are recorded as zero; its token counts are rough estimates. Database schema creation runs when the API starts.

`X-Usage-Log: RECORDED` means the metadata was persisted. If PostgreSQL is unavailable while handling a request, the completion still returns and the header is `X-Usage-Log: UNAVAILABLE`; the API log records the failure.


## Semantic-cache safety experiment

The live endpoint still uses exact matching only. Before enabling semantic reuse, run the offline threshold experiment against a small hand-labeled pilot set containing safe paraphrases and unsafe near-matches. The evaluator uses Sentence Transformers embeddings and cosine similarity. See the [official semantic textual similarity documentation](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html) for the embedding-and-similarity approach.

Install the optional dependency and run a development threshold sweep:

```bash
python -m pip install -e ".[semantic]"
export HF_HOME=.cache/huggingface
python scripts/evaluate_semantic_cache.py --show-pairs
```

Choose a threshold using the development rows, favoring a low unsafe-hit rate. Then report that fixed threshold on the holdout split, for example:

```bash
python scripts/evaluate_semantic_cache.py --threshold 0.90 --show-pairs
```

The included set is an exploratory, manually labeled pilot—not a production-quality benchmark. Review the labels, add examples from the intended application, and keep holdout examples out of threshold selection. The script does not yet enable semantic hits in the API or persist embeddings in pgvector.


### Initial pilot result

Using `sentence-transformers/all-MiniLM-L6-v2` on 64 manually curated prompt pairs (32 development and 32 holdout, balanced between safe and unsafe reuse), a 0.90 similarity threshold accepted 4 safe and 3 unsafe development pairs (57.1% safe precision; 25.0% safe-pair recall; 18.8% unsafe-hit rate). At that same threshold, the holdout set produced 7 safe and 4 unsafe matches (63.6% safe precision; 43.8% safe-pair recall; 25.0% unsafe-hit rate). This small pilot shows that a single embedding-similarity threshold is not yet safe enough for serving semantic cache hits. Semantic caching therefore remains offline and disabled in the API. Expand and independently review the labels, especially examples involving dates, ambiguity, and safety context, before reconsidering. The pilot compares prompt text only; a live implementation must also account for full message context and generation settings.


## Use the OpenAI provider

The mock remains the default and makes no provider calls. To switch to OpenAI, install the project dependencies, set the provider and API key in the same terminal, then restart Uvicorn:

```bash
python -m pip install -e .
export LLM_PROVIDER=openai
export OPENAI_API_KEY="your-provider-api-key"
uvicorn cachepilot.main:app --reload
```

Keep the key private and out of Git. Send a real model name in the request's `model` field; `mock-model` is only for the mock adapter. The official OpenAI Python SDK supplies the Chat Completions adapter. The request API currently supports text messages and optional temperature; streaming and tools are not implemented.

For real-provider usage logs, configure current model-specific rates per million tokens with `OPENAI_INPUT_PRICE_USD_PER_1M_TOKENS` and `OPENAI_OUTPUT_PRICE_USD_PER_1M_TOKENS`. If either is unset, real-provider cost and cache-savings estimates are recorded as unknown (`NULL`) rather than guessed. A cache hit records zero current provider cost and estimates the avoided cost when rates are configured.
