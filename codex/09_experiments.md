# M09 — Runner E0–E7 và output mỗi thí nghiệm

## Override đang áp dụng cho E5-E7

Server execution dùng `scale_variant: e4e567_scale_v3_50k` theo [16_e567_downscale.md](16_e567_downscale.md). Variant này giữ nguyên 3 E4 tasks, 12 E5 cells, 4 E6 cells và 20 E7 cells; chỉ thu nhỏ document/query/event workload. E4 phải chạy lại trên common 50k/5k manifest và chỉ trở thành parent input sau khi artifact/profile/hash của nó verified.

Runner phải tạo subset/case manifests trước official quality run, ghi hash vào `summary.json`, dùng subset view thay vì load full graph rồi mới lọc, và chặn kết quả nếu manifest/coverage không hợp lệ. Các aggregate E5-E7 của variant này không được trộn với full-scale aggregate.

Code `experiments.py`, `configs/experiments/e0.yaml`…`e7.yaml` và `t0.yaml`. Bắt buộc đọc đầy đủ `report.md`, `expect.md`, [M14](14_presetup_tuning.md) và [M15](15_run_budget.md) trước khi implement; bảng này là wiring, không thay tài liệu khoa học. Runner mặc định phải expand `compact_v1`, không tự nhân full factorial.

## API runner

| Hàm | Cần implement |
|---|---|
| `build_task_specs(experiment_id, cfg) -> list[TaskSpec]` | Expand dataset/pair/map/scheduler/seeds/mode thành task IDs ổn định, phase development/official, required/diagnostic/N/A và đúng T0 scope/dependencies |
| `make_run_id(spec) -> str` | Experiment + dataset + pair + variant + seeds + config digest; resume dùng lại ID, config thay đổi tạo ID mới |
| `run_single(spec) -> RunResult` | Validate dependencies/profile trước inputs/evaluation→bootstrap/run/evaluate→validate outputs→finalize; T0 dispatch run_presetup, không dựng test evaluator |
| `run_e0` … `run_e7` | Thin functions chọn stage/data/branches, dùng chung core; không copy migration loop bảy lần |
| `run_presetup(task, inputs, cfg)` | T0.core/scale/case theo M14, bounded selection/probes/estimate/freeze; cùng finalize/sync |
| `run_temporal_replay(spec)` | Lịch history/week đã khóa, gọi shared migration primitives theo M07 |
| `finalize_run(run_dir, result)` | Đóng files, ghi summary, verify required output, update root checklist compute, enqueue auto-sync |
| `stage_is_complete(stage, tasks) -> bool` | Required cells/gates compute done và sync verified; negative outcomes vẫn tính completed |

Runner xuất status có exit code: failed technical != negative scientific. `finalize_run` cũng đóng và sync error summary của failed run nếu có; partial checkpoint label partial, không marker completed giả.

## Stage matrix và gates

| Stage | Dataset/model | So sánh và expected output | Dependency |
|---|---|---|---|
| E0 | Source registries, server H10080; chưa cần tải full matrix | config/env/splits/accessor contracts; khóa recipes/metrics, token check và HF round-trip tiny bundle | M01, minimal M02/M03/M04/M11 |
| E1 | FiQA subset cố định, MiniLM→MPNet | OP/global + random, exact; ID/budget/no-leak, lazy/eager toy,100% true exact agreement | E0 + core M04–M08 |
| T0.core | FiQA/MiniLM–MPNet, development pools | lr selection, cal roles, HNSW/core runtime profile | E1 + implementation M05–M08/M10–M14; không phụ thuộc E2/E3 |
| T0.scale | Arctic/MS MARCO + ORCAS validated, runtime subset100k | full-corpus paid-pool lr, subset timing4 schedulers, forecast; diagnostic | E3 correctness + validated scale inputs; không phụ thuộc E4 |
| T0.case | Dataset/model bổ sung của E2/E6/E7 | Đúng-case map/index/runtime profile hoặc explicit transfer/N/A | Core code + validated case inputs; không phụ thuộc chính E đang chuẩn bị |
| E2 | Full FiQA và TREC-COVID, MiniLM→MPNet | Compact 24 cells theo M15: mapping FiQA 9, scheduler FiQA 12, TREC mapping 3; exact trước ANN | E1 + T0.core; TREC thêm T0.case tương ứng; ANN path cần ANN_PASS |
| E3 | Pilot snapshots | 6 systems tasks theo M15: exact/HNSW, cadence, synchronized serving và save/load recovery | E2 + T0.core/case ANN profile + M06 |
| E4 | Common 50k MS MARCO manifest + 5k ORCAS groups, Arctic; reduced-pool bootstrap gate | 3 tasks theo M15: subset/greedy probe, actual reduced stored-graph readiness và restore/footprint | E3 + T0.scale; subset PASS không tự là full gate |
| E5 | `e4e567_scale_v3_50k`: common MS MARCO pool50k, Arctic, ORCAS tối đa5k groups | Compact 12-cell primary scheduler comparison; ARR at10% accessed, judged-dev nDCG **secondary** khi coverage đạt, cost/contrasts | Verified E4 v3 parent artifact/profile/hash + common manifest |
| E6 | `e4e567_scale_v3_50k`: recovered AOL-IA, Arctic default, document/event caps50k | 4×7-decision chronological replay, week8 weighted ARR at7% scheduled, coverage/time split | E3 + verified E4 v3 parent + T0.case AOL + actual recovery; không đợi E5 xong |
| E7 | `e4e567_scale_v3_50k`: 8 representative BEIR/model cases, large-case pools50k | 20 compact cells: MLP random/greedy trên 8 cases + OP greedy cross-check trên 4 cases; per-case tables | E2/E3 + T0.case tương thích + verified E4 v3 parent |

E0–E7 là8 milestone, E1–E7 là7 experimental stages. T0 là nhóm prep tasks theo scope, không thêm một E quality. E0/E1/T0 có phase development; E2–E7 có phase official và dùng profile đã freeze. Required dependency là task ID cụ thể (ví dụ T0.core), không phải một T0 tổng chờ mọi dataset. Exact diagnostics không cần HNSW; ANN claims cần đúng ANN profile và E3 gate. E6 unavailable không được thay synthetic hoặc tick complete.

## Config matrix cụ thể

- E1: map seed17/traffic101, fixed subset IDs (default2,000 documents, đủ11 neighbors), debug queries/splits lấy từ FiQA train/dev đúng vai trò. Qrels restricted vào subset chỉ cho diagnostic; không gọi quality như full FiQA. Chạy100% true completion.
- E2: dùng M15 compact matrix. FiQA mapping OP/LA/MLP × map seeds17/29/43 với random và traffic101 (9); FiQA scheduler chỉ dùng MLP × random/degree/read/greedy × map seeds17/29/43 với traffic101 (12); TREC mapping OP/LA/MLP tại map seed17, scheduler N/A (3). Global/regional/cal/diagonal ablations là T0 hoặc diagnostic riêng, không nhân vào required matrix.
- E3: fixed snapshot comparisons để chỉ đổi search/graph. Cadence ablation dùng cùng start state và one locked scheduler; scale seeds chỉ mở sau diagnostic1 cell pass. Threads/seed của HNSW nằm config, không default theo CPU vật lý.
- E4: fixed **50k-document common manifest** derived from the frozen uniform T0 scale order and exactly 5k ORCAS schedule groups, hashed before official results; subset/greedy probe, reduced-pool full bootstrap and restore stay serial.
- E5: `e4e567_scale_v3_50k` giữ all4 schedulers×3 map seeds×traffic101 =12 run cells trên common manifest. Mỗi cell tiếp tục tới bootstrap,5/10/25/50% accessed và100% true trong cùng run ID/prefix. Tối đa4 traffic-sensitivity cells random/greedy×map17×traffic{103,109} là optional; không bắt chạy full3×5 grid hoặc nhân live encode. `E5.primary_done` không đồng nghĩa `E5.compute` hoàn tất continuation nếu checkpoint còn thiếu. Uncertainty/margin/extra-clicked/hindsight không thuộc compact required matrix.
- E6: `e4e567_scale_v3_50k` chạy all4 primary schedulers trên cùng recovered chronology với map seed17, document cap50k và event cap50k/tuần; không tạo traffic/random seeds bằng cách shuffle chronological events. Mỗi cell có 7 decisions, budget báo cả scheduled/accessed/true.
- E7: `e4e567_scale_v3_50k` gồm 8 case theo M15; large NQ/HotpotQA/FEVER dùng 50k documents và 500 queries/case, FiQA/TREC chỉ reuse exact scope. Mỗi case MLP×{random,greedy}, map17/traffic101 (16 cells); OP+greedy trên4 case cross-check (4 cells). Reuse E2 FiQA/TREC chỉ khi resolved hashes khớp. Không gọi đây là đủ20 cases hoặc full-corpus BEIR; không train/dev hợp lệ → scheduler N/A/transfer có nhãn. Complete extra published baselines theo M08 recipe task; thiếu source recipe ghi incomplete-baselines.

Các defaults subset/seed diagnostic là engineering choices mới, phải lưu trước run. Không tune subset theo kết quả. E2/E7 trùng case chỉ reuse outputs khi toàn bộ resolved scientific inputs/config/mode/seed/profile giống, có thể khác stage label. So content hash loại stage/run path labels; lưu source run reference, không giả đã chạy một run khác. T0 development outputs không reuse làm official quality cells.

Required static checkpoint targets ở E2/E5/E7 đều theo report: bootstrap,5/10/25/50% accessed và100% true (bỏ mốc thấp hơn bootstrap với reason). Primary hypothesis ở10% vẫn cố định; không cần giả thuyết dương mới chạy các mốc sau. Queue được chia primary/continuation để upload sớm và không chặn task khác, nhưng stage checkbox compute tổng chỉ tick khi required targets/cells đủ. E6 dùng weekly targets riêng, không ép10%/100% trong8 tuần.

## Expected output và kết luận

Mỗi stage có một aggregate table generated từ completed run outputs. Mỗi run lưu config, summary, metrics/retrieval, IDs/events, learned checkpoint cần thiết và sync receipt. Không tạo thêm20 báo cáo văn xuôi.

Outcome đọc theo `expect.md`: pipeline hợp lệ + effect không rõ là inconclusive, effect âm là negative; cả hai vẫn hoàn thành. Correctness/leakage/budget/ANN gate fail là technical failure cần sửa trước claim. E2/E5 không thắng không phải lý do bỏ E7 hoặc đổi primary theo test.

Checkpoint5/10/25/50% accessed là checkpoints chất lượng; refit theo5% **backfill** là một lịch khác. E5 primary ARR không phải judged relevance, và judged-dev nDCG không được gọi BEIR endpoint. BEIR endpoints thuộc E2/E7. Đây là cách đọc rõ hơn cho các đoạn mô tả ngắn trong expect/report.

## Hooks sau run

`finalize_run -> update_checklist(compute) -> auto_sync_experiment -> verify -> update_checklist(sync)`.

Ở checkpoint dài, hook cũng enqueue bundle immutable để không chờ xong toàn bộ matrix mới upload. Queue có thể chạy task kế tiếp khi compute còn chỗ; sync không giữ GPU reservation. Khi measurement exclusive đang chạy, đợi measurement kết thúc mới xử lý upload nặng. Không dọn local sau hook.
