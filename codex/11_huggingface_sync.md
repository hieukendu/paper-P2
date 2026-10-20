# M11 — Auto-sync Hugging Face sau mỗi run/checkpoint

Code `hf_sync.py`, progress hooks trong `experiments.py`/`progress.py`. Đây là chức năng bắt buộc, **triển khai từ đầu trước các run dài**. User đã yêu cầu tự upload và tạo repo tiếp theo khi cần; không cần hỏi lại mỗi upload trong phạm vi artifacts này. Chưa upload gì ở giai đoạn soạn Markdown.

## Auth và namespace

`load_runtime_env(PROJECT_ROOT)` đọc `.env`; lấy biến **HF_TOKEN**, không có một file riêng tên HF_TOKEN. Dùng `HfApi(token=token)` và `whoami`; token ở memory, không argv/log/config/receipt. Chọn namespace `HF_NAMESPACE` nếu có quyền write/create, nếu rỗng dùng authenticated username. Org không có quyền thì AUTH_ERROR, không âm thầm đổi sang account khác. Dùng SDK `huggingface_hub` đã pin; E0 kiểm signature thực tế của version.

Repo bundle loại `dataset`, mặc định private; tên `<namespace>/mixindex-runs-001`, `-002`… Không cần mỗi run một model repo. Dataset repo chứa metrics/configs/learned weights với README ngắn mô tả artifacts, không tự gán license corpus cho learned bundle. Với SDK hiện hành dùng create_repo với visibility private; nếu version pinned dùng private=True thì wrapper ánh xạ một lần ở E0, rồi giữ một code path đã test. Không tự public hoặc thay đổi repo đã tồn tại để giấu xung đột tên.

## Hàm bắt buộc và call graph

| Hàm | Cần code cụ thể |
|---|---|
| `get_hf_client(root) -> (HfApi, namespace)` | Load/auth như trên; thiếu token→SYNC_PENDING/AUTH_ERROR, giữ local |
| `collect_run_artifacts(run_dir, checkpoint=None) -> ArtifactBundle` | Whitelist các outputs đã đóng/complete; paths/bytes/SHA256 một manifest; ignore secret/raw data; source snapshot cần tái lập |
| `prepare_bundle(bundle) -> Path` | Immutable staging theo run_id/checkpoint_id/content hash; không follow symlink ra ngoài allowlist; shard file lớn khi cần |
| `choose_upload_repo(bundle, registry, cfg) -> list[Destination]` | Rollover theo logical policy bytes/files; giữ mapping part→repo/path; không đổi đích giữa retry |
| `ensure_repo(api, repo_id, cfg)` | Create private dataset nếu thiếu, exist_ok; verify namespace/type/visibility của repo existing; không overwrite repo không do project quản lý |
| `upload_bundle(api, destinations, bundle) -> receipt` | upload_folder/upload_file hoặc create_commit theo SDK pinned; serialize một writer, có retry, upload marker cuối |
| `verify_remote_bundle(api, receipt, manifest) -> dict` | Remote revision/path/files/size/digest kiểm từng artifact; không chỉ check HTTP200 |
| `auto_sync_experiment(run_dir, sync_cfg, checkpoint=None) -> dict` | Collect→choose/ensure→upload→verify→ghi sync.json→checklist; idempotent |
| `retry_pending_sync(state_path)` | Tìm pending receipts và retry đúng payload/đích, không chạy lại thí nghiệm |
| `restore_run(receipt_or_catalog, output, checkpoint=None)` | Tải pinned revisions/parts→verify→reassemble→restore config/weights/state/code; không chạy target code tự động từ download |
| `update_remote_catalog(api, registry)` | Catalog gọn tại repo001, chứa run/checkpoint/parts/commits/status; giúp tìm được mọi repo từ một URL |

`finalize_run` và `emit_checkpoint` ở M07/M09 luôn gọi/enqueue `auto_sync_experiment`. Khi một run xong, được ghi compute xong ngay; sync xong mới tick verified. Không fire-and-forget Future rồi exit process: parent queue phải drain uploads hoặc ghi pending để lần sau tiếp tục.

## Upload những gì

| Bắt buộc | Ghi chú |
|---|---|
| Config, environment reference, source snapshot và dependency lock | Snapshot source/config/tests đủ tái lập, kể cả file chưa git commit; không chỉ git SHA khi dirty/untracked code có ảnh hưởng |
| T0 selected profile/policy và development selection/timing tables | Run/case refs, immutable selected entries, phase timings/estimate; một profile snapshot theo run, không upload file state đang mutate |
| Dataset/model manifest references và actual split/pair/subset IDs | Không cần copy raw corpora hoặc frozen pretrained weights đã tải được bằng revision |
| Learned weights | M0.safetensors, regional A/b và statistics/counts, calibration a/b/r; không chỉ final scalar metrics |
| Per-query/checkpoint metrics, run rankings, contrast tables | Run IDs/eval IDs và cost summary; gz/Parquet gọn |
| Paid/backfill IDs/order, RNG và restart state | Đủ replay/resume map/index; pending stats và mode live/cached rõ |
| Index/state tại primary endpoint hoặc measurement snapshot | Giữ HNSW binary đã thực sự đo khi muốn tái hiện ANN snapshot; không giả rebuild graph là cùng graph |
| Failed/negative run summary và completed partial checkpoints | Nhãn partial/negative đúng; không marker full-complete nếu thiếu artifacts |

Source snapshot chỉ lấy allowlisted `src/`, `configs/`, tests cần thiết, pyproject/lock và command metadata; không tar toàn project. Không `.env`, HF credentials, SSH, raw AOL users/query text, file cơ sở không liên quan. Split IDs/opaque user clusters đủ tái tạo từ source được phép. Model upstream không train nên chỉ reference repo+SHA; khi model không tải lại được, ghi rõ dependency này chứ không giả bundle tự chứa mọi thứ.

Checkpoint bundle tham chiếu common inputs và previous immutable parts để tránh upload lại toàn vectors mỗi epoch. Chỉ latest restart state + primary checkpoints cần giữ; không upload every-minibatch. Không xóa local sau sync trong phase này.

Artifact manifest không hash chính nó, local `sync.json`, remote catalog hoặc marker; các file receipt đó không thuộc immutable payload để tránh self-reference/đệ quy sync. Checkpoint đang chạy dùng bản copy đã đóng của config/summary/events prefix, không hardlink file vẫn bị append/mutate. Các checkpoint weight/metric đã đo ở5/10/25/50%/completion được lưu; latest restart state giữa các mốc có thể chỉ là local checkpoint, không cần đẩy từng batch lên Hub.

## Nhiều repo và quota

Config defaults do project chọn: `repo_target_gib=50`, `repo_target_files=5000`, `artifact_shard_gib=2`. Đây là ngưỡng **tổ chức bundle**, không phải hard limit của Hugging Face. Nếu repo001 vượt policy thì allocate repo002… Nếu một run vượt target, tách parts trên nhiều repos, catalog ghi đủ cách reassemble.

Quan trọng: **quota tính tổng tài khoản/organization**; tạo repo002 không tăng quota. Khi account quota/billing/capacity hết, ghi QUOTA_ERROR, dừng thêm uploads, giữ local/pending và báo user. Không tạo loop repo003… để né quota; không tự nâng cấp gói trả phí. Policy rollover chỉ giúp tổ chức dung lượng/files trong quota đã có.

Không upload lại vào cùng path với nội dung khác. Dùng immutable `runs/<run_id>/<checkpoint_id>/...`; mutation config/code→run_id mới. Nếu payload digest đã remote verified thì return receipt cũ. Retry interrupted upload dùng manifest và catalog mapping cũ; không copy payload sang repo khác để tránh kiểm trạng thái upload.

## Verify, marker và retry

1. Whitelist files trước khi đóng gói; small source/config có thể tar.gz để giảm tiny files. Files lớn split≤2GiB và manifest có whole-file SHA + ordered part SHA/bytes.
2. Upload payload + artifact_manifest. Resolve remote commit revision sau khi upload hoàn tất (SDK có thể tạo nhiều commits).
3. Verify remote file list/size; dùng remote LFS SHA256 nếu có, git blob ID phù hợp cho small files, hoặc download/hash nếu remote không cung cấp digest dùng được. ETag không mặc nhiên là SHA256. Không gọi verified chỉ từ listing/size.
4. Download manifest + một learned-weight file trong E0/first real run để test round-trip load/hash. Artifact không có remote checksum phải đọc lại đủ bytes để verify; không chỉ sample đầu file.
5. Với run/checkpoint hoàn tất hợp lệ, upload `COMPLETED.json` cuối cùng, chứa manifest digest và parts/revisions; không chứa SHA của chính marker gây self-reference. Failed run hoặc incomplete snapshot chỉ có `FAILED.json`/`PARTIAL.json` kèm status, không dùng completed marker. Local sync receipt ghi marker revision sau bước này. Multi-repo chỉ có full marker sau khi **mọi part** verified.
6. Cập nhật catalog repo001, local sync.json và root checklist. Trạng thái SYNC_VERIFIED chỉ khi payload/marker/catalog references đủ; upload timeout có thể đã commit phía server, phải reconcile trước retry.

Retry network/5xx/429 tối đa3 lần, honor Retry-After, backoff; quá thì RETRYABLE_ERROR và giữ pending. 401/403 AUTH_ERROR, account quota QUOTA_ERROR, path-policy conflict là lỗi config; không retry vô hạn. Một worker đảm bảo registry/catalog/checklist không race; không cần message broker. Sync failures không làm mất hoặc nhân đôi compute run.

## API/source tham khảo đã đối chiếu

- [Hugging Face upload guide](https://huggingface.co/docs/huggingface_hub/guides/upload): upload_file/upload_folder và resumable behavior; agent dùng SDK pinned, không dựa vào CLI flag đoán.
- [Repository creation](https://huggingface.co/docs/huggingface_hub/guides/repository): repo type/visibility và quyền tạo.
- [HF_TOKEN/env](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables): token env và Xet performance setting; không bật performance mode khi cần tránh tranh tài nguyên.
- [Storage limits](https://huggingface.co/docs/hub/storage-limits): quota tổng account/org, không coi mỗi repo là dung lượng miễn phí riêng.
- [HfApi reference](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api): verify metadata/download tại pinned version.

Nhận M11 khi tests fake API cover idempotency/rollover/partial/quota và một live tiny private bundle đã upload→verify→download/load thành công. Không đánh dấu upload thật khi chỉ chạy mock tests.
