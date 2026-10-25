# M10 — Queue một host, tối đa2 thí nghiệm và resume

Code `queue.py` + resource helpers `runtime.py`. User yêu cầu có thể chèn task và chạy2 thí nghiệm nếu còn tài nguyên. Dùng subprocess và một queue file; không cluster scheduler/daemon framework.

## TaskSpec và job file

`configs/jobs.yaml` có list records: `task_id`, `experiment`, `config`, `depends_on`, `priority`, `resources`, `measurement_mode`, `phase`, `tuning_scope`. Resource request gồm `gpu_device`, `gpu_memory_gib`, `host_ram_gib`, `cpu_cores`, `disk_scratch_gib`, `io_heavy`; request lấy từ probe/ước lượng working set, không set0 để ép admission.

Queue state `state/tasks.json` lưu task status, PID, process birth time, run_dir và reason ngắn. Worker không ghi queue; parent cập nhật atomic. New jobs được thêm bằng CLI `enqueue` dùng file lock; parent reload pending tasks mỗi vòng, nên có thể chèn E7 nhỏ khi E5 waiting data. Không cần restart job đang chạy.

## Các hàm cần code

| Hàm | Logic |
|---|---|
| `load_jobs(path) -> list[TaskSpec]` | Validate unique IDs, dependency graph không cycle, resource fields và mode; merge vào state hiện có, không xóa jobs đã enqueue ở terminal khác |
| `enqueue_tasks(specs, state_path)` | Atomic merge theo task_id; existing running ID không overwrite config |
| `probe_capacity() -> Capacity` | Effective cgroup CPU/RAM, device-wide visible GPU free, actual output-volume free; không dùng physical host totals |
| `estimate_request(spec, probes) -> Resources` | Cache/shape/pair model memory + stats/index + peak from probes, scratch và headroom; unknown GPU profile thì serialize trước |
| `can_admit(task, running, capacity) -> (bool, reason)` | Dependencies done, slots≤2, reservations+external usage+headroom đủ; exclusive handling bên dưới |
| `launch_task(task) -> ProcessHandle` | `subprocess.Popen` argv list gọi hidden CLI `_worker --task-file ...`→run_single trực tiếp, shell=False; set thread limits/own stdout, không truyền token trên argv; worker không enqueue lại chính task |
| `poll_task(handle)` | Poll process thật/PID birth time, timeout/OOM, đọc completed summary; lock file hoặc status cũ không chứng minh còn sống |
| `run_queue(jobs, max_compute_jobs=2)` | Admission/poll, prioritize eligible tasks, gọi sync worker/progress; vòng poll khoảng5s, không busy loop |
| `reconcile_after_restart(state)` | Reattach đúng PID+birth time nếu alive; missing handle/exit terminal mới xét resume; không launch duplicate vì một poll timeout |
| `resume_task(task_id, checkpoint)` | Validate checkpoint/config/inputs, RNG/ledger/index complete rồi continue cùng run ID |

T0 và official tasks dùng cùng queue. Enqueue task có prerequisite chưa xong là hợp lệ, giữ PENDING; chỉ reject graph cycle/config bất hợp lệ. Admission và worker đều gọi `validate_tuning_profile` trước official execution: đúng scoped T0 compute, input/policy/profile hash, branch gate và allowed ablation overrides theo M14. Không chờ T0.scale/AOL để mở E2 exact khi T0.core đã qua. Sync pending không khóa compute dependency.

E4 readiness là producer của search/profile evidence cho reduced common pool trong `e4e567_scale_v3_50k`; cần T0.scale prerequisite/profile, exact 50k/5k manifest và target-size reservation để build/check. E5 là consumer, cần verified E4 v3 entry; không đặt E4 phụ thuộc chính full entry chưa được tạo.

Thứ tự priority mặc định: prerequisite/smoke > ready primary > optional ablations; không bỏ cells âm. Task lớn không vừa thì ghi reason và cho task nhỏ đủ tài nguyên chạy; không ép launch để vừa đủ2.

## Admission tài nguyên

- H10080 là target; probe torch/NVML phải xác nhận full/MIG của device process dùng. Unknown free memory/permissions → chỉ1 GPU task và probe trước, không giả có80GiB usable.
- Default headroom vận hành: GPU max(4GiB,10% visible VRAM), RAM max(8GiB,10% effective limit), CPU1 core. Đây là configurable planning defaults; ghi config, không gọi benchmark requirements của paper.
- Free memory hiện tại đã chứa allocations của jobs đang chạy. Tránh double-count: `remaining_reservation_i=max(0,requested_peak_i-observed_usage_i)`; admit nếu `new_request + sum(remaining_reservations) + headroom <= free_now`. Nếu không đo được usage theo job, dùng cách conservative serialize, không optimistic trừ nhầm.
- CPU quota/cpuset lấy effective min; sum requested CPU≤quota−headroom. Set thread limits cả BLAS, torch, sklearn và hnswlib để2 processes không mỗi process tạo128 threads.
- RAM request gồm text lookup, old/stored/reference shards, HNSW, regional float64 stats, heap và **hai independent mutable indices** nếu2 runs. Sharing read-only cache không làm mutable arrays miễn phí.
- Disk capacity kiểm đúng mounts cho raw/cache/runs/staging; cộng pending sync bytes/scratch. Để staging dùng hardlink chỉ cho files immutable hoặc stream upload trực tiếp; không copy toàn corpus thành bundle.
- Chỉ admit job thứ2 sau resource probe đủ. Chưa có probes thì default1 GPU compute job, nhưng CPU preprocessing/evaluation độc lập có request cụ thể vẫn có thể chiếm slot thứ2 khi fit.

## Kết quả scientific và measurement

| Task | Có thể chạy song song? |
|---|---|
| Download/preprocess FiQA trong khi encode immutable dataset khác | Có nếu CPU/I/O/RAM đủ; một writer/cache key |
| Hai `cached_access` quality runs khác run_dir/seeds/datasets | Có sau memory/CPU probe, không dùng chung mutable state |
| CPU fit/aggregate và GPU encode khác | Có nếu task fit không tranh GPU và request hợp lệ |
| Hai GPU encoder tasks | Có nếu peak memory/reservations đủ, gắn `co_scheduled`; không dùng throughput của chúng làm primary isolated GPU time |
| `live_encode` để báo cost, T0 timing, E3 p99/throughput/stall, E4 capacity probe | **Exclusive toàn measurement window**: không compute/download/upload nặng cùng host/device |

`measurement_mode=exclusive` đợi jobs cũ hoàn tất và tạm dừng admission/upload nặng; không tự kill hay preempt job. Không coi GPU còn trống là đủ nếu CPU/I/O đang tranh chấp. Nếu chỉ có một GPU, chạy2 quality jobs là optional throughput optimization, không là gate phải đạt.

Một sync worker nhẹ có thể chạy ngoài2 compute slots, nhưng phải có CPU/I/O budget và nhường measurement exclusive. Mặc định không bật HF_XET_HIGH_PERFORMANCE, vì có thể chiếm hết CPU/bandwidth. Đo measurements xong enqueue upload ngay; không đợi hoàn thành E0–E7 mới bắt đầu sync.

## Checkpoint/retry

Save checkpoint tại fixed quality checkpoints và refit/restart boundaries hữu ích, không từng minibatch. Lưu full learned state + paid/backfill IDs + fidelity/index/base+delta refs + Python/NumPy/torch/CUDA RNG + pending regional stats. Không chỉ lưu model weights rồi gọi resume migration được.

Checkpoint complete marker publish cuối cùng; resume exact fixture phải cùng lựa chọn doc/metric với uninterrupted run. Process crash không tự rerun từ đầu. Nếu OOM, mark FAILED và enqueue variant batch nhỏ hơn sau khi kiểm semantics; không âm thầm đổi config dưới cùng run ID. Network upload retry độc lập, không retrain.

Exact fixture là gate cho trajectory equality. Với stock HNSW, kiểm phục hồi đúng binary/vector/fidelity/epoch trước phục vụ; backend thread/RNG behavior có thể làm các updates tương lai khác uninterrupted run. Giữ measured graph snapshots và ordered paid IDs, ghi resumed status; không hứa bitwise trajectory equality cho ANN khi backend chưa chứng minh được.
