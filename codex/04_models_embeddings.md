# M04 — Model downloads, adapters và vector access

Code `encoders.py`, `vectors.py`; registry `configs/models.yaml`. Dependencies M01/M03. Không fine-tune g/h; `.eval()`, `torch.inference_mode()`, output dense unit vectors float32.

## Checkpoints bắt buộc

| Pair | g → h | Dimension | Adapter |
|---|---|---|---|
| `minilm_mpnet` | `sentence-transformers/all-MiniLM-L6-v2` → `sentence-transformers/all-mpnet-base-v2` | 384→768 | SentenceTransformer pooling của checkpoint; native max tokens256/384 |
| `arctic` | `Snowflake/snowflake-arctic-embed-l` → `Snowflake/snowflake-arctic-embed-l-v2.0` | 1024→1024 | CLS; v1 query instruction; v2 query prompt; native limits512/8192 theo card |
| `nomic` | `nomic-ai/nomic-embed-text-v1` → `nomic-ai/nomic-embed-text-v1.5` | 768→768 | query prefix `search_query: `, doc prefix `search_document: `; masked mean/published pipeline |
| `bge` | `BAAI/bge-base-en-v1.5` → `BAAI/bge-m3` | 768→1024 | base query instruction theo card; M3 không prefix; chỉ dense, không sparse/ColBERT |

Tải MiniLM/MPNet trước E0/E1/T0.core; Arctic trước T0.scale; Nomic/BGE trước T0.case/E7 tương ứng. Resolve exact commit bằng `HfApi.model_info(repo_id).sha`, `snapshot_download(..., revision=sha)` và dùng lại snapshot offline cho rerun. Không hard-code SHA chưa kiểm tra. Không tải đồng thời pytorch/ONNX/TF/GGUF variants nếu chỉ dùng một format; cần config/tokenizer/ST modules/code referenced/weights. Model cần custom code thì pin cả code revision và chỉ bật `trust_remote_code` cho checkpoint đó sau khi inspect; không bật toàn cục.

## Model-specific semantics

- MiniLM/MPNet không tự chuyển thành CLS. Dùng SentenceTransformer snapshot modules và `normalize_embeddings=True`. Matched-limit256 cho hai model là sensitivity riêng.
- Arctic v1 query prefix theo card: `Represent this sentence for searching relevant passages: `; document không prefix. Arctic v2 dùng `prompt_name="query"` trong ST **hoặc** prepend `query: ` trong raw transformer adapter, không làm cả hai. Dùng CLS và normalize. [v1 card](https://huggingface.co/Snowflake/snowflake-arctic-embed-l), [v2 card](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0).
- Nomic v1.5 theo published path có layer normalization trước L2 normalization; giữ **đủ768 chiều**, không truncate Matryoshka. Nếu snapshot ST đã thực hiện bước đó thì không lặp hai lần; smoke đối chiếu reference path. Không bỏ attention mask khi mean pooling. [Nomic v1.5 card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5).
- Native limit phải đọc config/card của snapshot đã pin, tránh dùng sentinel tokenizer.model_max_length cực lớn. Long-context modifications/rope scaling chỉ theo card và phải ghi adapter params; không tự đổi mọi model về512 để tiết kiệm.
- Primary bắt đầu float32 batch8 trên server, batch grid tăng sau probe, một model được nạp trong mỗi task. BF16/FP16 hoặc token-limit chung là variant có output-cache key khác và quality smoke trước; không silently đổi primary.
- T0 runtime profile phải đo g/h trên chính pair/corpus và actual token lengths; không tái dùng timing MiniLM để dự báo Arctic/BGE. Padding/bucketing/batch changes kiểm ID alignment/embedding tolerance trước freeze; native limit/prefix/pooling giữ nguyên theo M14.

## Hàm cần implement

| Hàm | Logic/đầu ra |
|---|---|
| `resolve_model(spec, paths) -> ModelSpec` | model_info→commit, snapshot_download, đọc adapter config; ghi1 record lock/model |
| `build_encoder(spec, device) -> EncoderAdapter` | Load đúng pooling/prefix/limit, set eval/no-grad, không gộp2 model tự động |
| `EncoderAdapter.encode_documents(texts) -> array` | Text từ document_text, prefix document một lần, tokenize/forward/pool/normalize |
| `EncoderAdapter.encode_queries(texts) -> array` | Raw representative text, query prompt một lần, cùng dtype/normalization semantics |
| `smoke_encoder(encoder, examples) -> dict` | shape/dim/finite/unit norm, repeat consistency, document/query path khác prefix đúng |
| `vector_cache_key(data_manifest, spec, role) -> str` | Hash nội dung/version và adapter params/dtype/max_tokens; không chỉ tên model/dim |
| `encode_corpus(data, encoder, output) -> VectorStore` | Row-stable streaming shards, token/truncation counts, temporary shard rồi publish finite checks |
| `encode_query_pool(query_ids, encoder, output) -> VectorStore` | Cache theo raw representative + encoder key, không cache future queries như đã biết cho temporal |
| `open_vector_store(path, expected_key) -> VectorStore` | Readonly shards, verify shape/row alignment; mismatch refuse reuse |
| `PaidEmbeddingAccessor.request(rows, purpose, budget_limit)` | Kiểm role/pool/unique cap, lấy đúng rows bằng live encode hoặc cached service, ledger/cost |
| `build_full_new_reference_cache(data, h, output)` | Evaluator-owned task encode toàn corpus; ghi research cost riêng, không đưa handle cho migration |

`request` là **đường duy nhất** để migration lấy y_d. Chặn truy cập hold-out pool để train map, charge calibration/validation/bootstrap/backfill trong cùng paid union. Document đã paid không tăng unique count lần2; inference lại vẫn tăng calls/tokens/time. Nếu batch encode lỗi, ghi attempted cost/lỗi và không chuyển fidelity sang true trước khi vector tồn tại. Khi crash giữa truy cập và commit, không cho resume “quên” các quyền đã sử dụng: giữ pending IDs trong checkpoint/journal ngắn và reconcile trước khi tiếp tục.

`cached_access` dùng full target cache để so quality nhanh nhưng lookup time không gọi là GPU encode time. `live_encode` gọi thật h từ text, dùng để benchmark costs/latency. Reference computation nằm research cost; full-rebuild baseline lúc so cost phải trả encode/build đầy đủ. Không đặt oracle cost bằng0 rồi gọi tiết kiệm.

## Cache và song song

Immutable shard với row ranges và manifest nhỏ; writer lock theo cache key, publish temp→rename. Hai task có thể read cache chung, không cùng ghi. Vectors query refresh tái dùng `h(q)` vì h cố định, nhưng scheduling search/gain phải chạy lại khi snapshot đổi.

Không upload lại full pretrained weights sau từng E: model ID + pinned SHA đủ tải lại. **Weights cần sync là M0, regional maps/statistics, calibration và run state học được**; encoder snapshot mirror chỉ thêm khi thật sự cần và được quyền phân phối.

Nhận M04 khi smoke cả document/query path đúng và accessor test từ chối oracle rows/cap overflow. Không dùng vector random để pass model smoke.
