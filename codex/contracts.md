# Contracts giữa các module

Các signature dưới đây là API **cần implement**, không phải API đã có. Dùng type hints/dataclass đơn giản trong `config.py` hoặc module sở hữu kiểu đó. Không cần sinh code framework từ tài liệu.

## Các record dùng chung

| Kiểu | Trường cốt lõi |
|---|---|
| `DatasetSpec` | name, source URLs/release, expected counts, parser, license link |
| `PreparedData` | dataset_id, manifest_path, document_store, queries/qrels/traffic paths, split IDs |
| `ModelSpec` | repo_id, resolved_revision, dim, adapter, query/doc prefix, pooling, max_tokens, inference_dtype |
| `VectorStore` | cache_key, row IDs, dtype/dim, shard paths, `get_rows(rows)`, `iter_batches()` |
| `SplitBundle` | P_train/P_val, cal query/document/pair IDs, Q_schedule/Q_tune/Q_eval, weights, time boundaries |
| `MigrationState` | paid ledger, stored vectors, fidelity, region assignments/stats, M0, calibration, index, epoch, backfilled count, RNG |
| `SearchResult` | qid, raw candidates/row IDs, calibrated top11 scores, top10 IDs, epoch; chỉ giữ tạm trong RAM |
| `TaskSpec` | task_id, experiment/run_id, config_path, depends_on, resources, measurement_mode, phase (`development/official`), tuning_scope/profile refs, status |
| `RunResult` | run_id, output_dir, compute_status, gate_status, outcome, sync_status |
| `TuningProfile` | scope/case/input refs, policy hash, immutable profile hash, selected lr/search/runtime, gate/transfer/N/A status, source T0 run |

Document/query **ID gốc là string**, row ID là int64 liên tục và ổn định theo ingestion order. Không thay MS MARCO D-IDs bằng passage IDs. Tie-break tăng dần theo ID gốc (lexicographic), không theo thứ tự HNSW trả về. Encode dùng text đại diện raw đã khóa; grouping dùng normalized query riêng.

## Các hàm nối pipeline

```python
def load_config(path: Path, overrides: dict | None = None) -> dict: ...
def prepare_dataset(spec: DatasetSpec, paths: Paths) -> PreparedData: ...
def build_splits(data: PreparedData, cfg: dict) -> SplitBundle: ...
def resolve_model(spec: ModelSpec, paths: Paths) -> ModelSpec: ...
def build_encoder(spec: ModelSpec, device: str) -> EncoderAdapter: ...
def encode_corpus(data: PreparedData, encoder: EncoderAdapter, output: Path) -> VectorStore: ...
def bootstrap_migration(data, splits, old_vectors, paid_accessor, cfg) -> MigrationState: ...
def run_migration(state, traffic, checkpoint_targets, evaluator_callback, cfg) -> RunResult: ...
def evaluate_snapshot(snapshot_reader, eval_inputs, reference_reader, cfg) -> dict: ...
def finalize_run(run_dir: Path, result: RunResult) -> RunResult: ...
def auto_sync_experiment(run_dir: Path, sync_cfg: dict) -> dict: ...
def update_checklist(project_root: Path, task_id: str, result: RunResult) -> None: ...
def run_presetup(task, inputs, cfg) -> RunResult: ...
def validate_tuning_profile(task, cfg, profiles) -> None: ...
```

`Paths` là tập Path nhỏ được resolve một lần; không hard-code user/server path. `EncoderAdapter` chỉ cần `encode_documents(texts)`/`encode_queries(texts)` và metadata. Evaluator callback không trả labels/Y_full cho migration; nó ghi metric vào output và chỉ trả gate kỹ thuật đã khai báo, không quyết định scheduler dựa trên test score.

## Phân tách vector mới

```python
class PaidEmbeddingAccessor:
    def request(
        self,
        doc_rows: list[int],
        purpose: str,  # train / validation / cal_fit / cal_check / backfill
        budget_limit: int,
    ) -> np.ndarray: ...
```

Accessor kiểm split role + unique paid budget **trước khi** đọc/encode. ID đã trả phí được cache lại, không tính unique hai lần; encode lại vẫn tính token/call/time. `cached_access` lấy target rows từ evaluator-owned cache qua accessor; `live_encode` thật sự gọi h. Không cho caller nhận handle toàn `Y_full`.

`reference_reader` chỉ được xây bên evaluator. Phân tách này là API/process boundary trong nghiên cứu, không tuyên bố sandbox bảo mật chống code độc hại. Test dùng sentinel source kiểm xem có truy cập trái phép hay không.

T0 không dựng test evaluator; chỉ nhận đúng train/val/cal/Q_tune cho scope. Policy hash mô tả quy tắc chung, profile hash mô tả selected settings của case, run config hash gồm cả seed/method/mode nên khác nhau giữa cells. Official task chỉ execute sau đúng T0 dependency và local profile verification; ablation overrides phải có allowlist/variant ID. Xem [M14](14_presetup_tuning.md).

## Commit và checkpoint

Một commit migration gồm vectors, fidelity, calibration epoch và HNSW cùng phiên bản. Prepare encode/remap ngoài lock; writer lock publish logical update, epoch sau cùng. Nếu commit lỗi thì ngừng serving state đó và resume từ checkpoint nguyên vẹn; không giả có rollback.

Checkpoint phải chứa số batch/refit boundary, ordered paid/backfill IDs, RNG states, M0, regional statistics, calibration, pending region updates, stored/fidelity arrays hoặc base+delta đủ dựng lại và HNSW đã dùng. Có thể tham chiếu immutable old/base vector cache thay vì nhân đôi. `checkpoint.json` ghi `complete=true` cuối cùng bằng atomic rename; thư mục thiếu marker không được resume/sync như completed checkpoint.

## Trạng thái và checklist

Task: `PENDING -> RUNNING -> COMPUTE_DONE | FAILED | BLOCKED_DATA`.

Sync: `NOT_READY -> PENDING -> UPLOADING -> VERIFIED | RETRYABLE_ERROR | AUTH_ERROR | QUOTA_ERROR`.

Run có outcome độc lập: `positive`, `negative`, `inconclusive`, `diagnostic`, `not_applicable`. `FAILED` kỹ thuật không được đổi thành negative result khoa học.

`finalize_run` luôn đóng writers, validate outputs, ghi summary rồi cập nhật compute status/checklist; chỉ output đã đóng mới sync. Sync thất bại không chạy lại training. Tick stage E chỉ sau mọi required cells/gates của stage đã compute-done và các bundle bắt buộc đã sync verified; ô compute riêng vẫn được tick trước khi upload xong.
