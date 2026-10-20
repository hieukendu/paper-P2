# M09 — Runner E0–E7 và output mỗi thí nghiệm

Code `experiments.py`, `configs/experiments/e0.yaml`…`e7.yaml` và `t0.yaml`. Bắt buộc đọc đầy đủ `report.md`, `expect.md` và [M14](14_presetup_tuning.md) trước khi implement; bảng này là wiring, không thay tài liệu khoa học.

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
| E2 | Full FiQA và TREC-COVID, MiniLM→MPNet | OP/LA/residual MLP; global/regional/cal/diagonal variants; FiQA eligible schedulers; TREC cal/greedy N/A | E1 + T0.core; TREC thêm T0.case tương ứng; ANN path cần ANN_PASS |
| E3 | Pilot snapshots | exact/HNSW, same-ID/fresh graph, lock, cadence1/5/10%; cost/latency/write amplification | E2 + T0.core/case ANN profile + M06 |
| E4 | MS MARCO subset + sampled ORCAS, Arctic; full bootstrap gate | subset refresh100k-query probes/forecast rồi actual full stored-graph readiness trước E5 | E3 + T0.scale; subset PASS không tự là full gate |
| E5 | Full3,213,835 MS MARCO docs, Arctic, sampled static ORCAS | greedy/random/degree/read primary; ARR at10% accessed, judged-dev nDCG **secondary**, cost/contrasts | E4 full-bootstrap gate + full-corpus profile; không yêu cầu E2 thắng |
| E6 | Actual recovered AOL-IA, Arctic default |8×7-day chronological replay, week8 weighted ARR at7% scheduled, coverage/time split | E3/E4 + T0.case AOL dùng tuần1 + actual recovery; không đợi E5 xong |
| E7 |5 BEIR×4 model pairs |20 mapping/generalization cases, eligible schedulers, baselines/diagnostics; per-case/seed tables | E2/E3 + T0.case tương thích; large cases cần đúng-case scale readiness; không cần E5 thắng |

E0–E7 là8 milestone, E1–E7 là7 experimental stages. T0 là nhóm prep tasks theo scope, không thêm một E quality. E0/E1/T0 có phase development; E2–E7 có phase official và dùng profile đã freeze. Required dependency là task ID cụ thể (ví dụ T0.core), không phải một T0 tổng chờ mọi dataset. Exact diagnostics không cần HNSW; ANN claims cần đúng ANN profile và E3 gate. E6 unavailable không được thay synthetic hoặc tick complete.

## Config matrix cụ thể

- E1: map seed17/traffic101, fixed subset IDs (default2,000 documents, đủ11 neighbors), debug queries/splits lấy từ FiQA train/dev đúng vai trò. Qrels restricted vào subset chỉ cho diagnostic; không gọi quality như full FiQA. Chạy100% true completion.
- E2: core flow đã kiểm ở E1/T0, chạy đủ map seeds17/29/43 với selected lr chung của case. Mapping comparisons OP/LA/MLP với random scheduler; ablations global-only/global+regional/global+cal/both và diagonal regional control giữ bootstrap pools chung. FiQA eligible schedulers random/degree/read/greedy, grid3×5; TREC mapping/random, scheduler primary N/A.
- E3: fixed snapshot comparisons để chỉ đổi search/graph. Cadence ablation dùng cùng start state và one locked scheduler; scale seeds chỉ mở sau diagnostic1 cell pass. Threads/seed của HNSW nằm config, không default theo CPU vật lý.
- E4: fixed **100k-document subset** uniform seed20261020 trước khi nhìn click/quality; giữ subset IDs. ORCAS edges restrict subset và report missing due to subset; scale query-count probe lên tối đa100k nhóm hợp lệ khi có. Không lấy only-clicked subset để gọi đại diện corpus; length/I/O probe có thể dùng full-corpus samples không encode toàn bộ.
- E5: all4 primary schedulers×3 map seeds×5 traffic seeds =60 run cells, primary contrast tại10% accessed. Required quality checkpoints vẫn là bootstrap,5/10/25/50% accessed và100% true như report. Chạy primary10% trước, rồi continuation tasks từ cùng run ID/prefix để đủ checkpoints; không reset RNG/map. `E5.primary_done` không đồng nghĩa `E5.compute` hoàn tất cả protocol. Không bắt chạy60×100% **live encode** khi research-quality mode dùng cached-access. Uncertainty/margin/extra-clicked/hindsight là nhánh bổ sung riêng; mỗi method có state/index/RNG độc lập.
- E6: all4 primary schedulers trên cùng recovered corpus/timeline; cùng map seeds và traffic/random seeds khi có đủ compute. Không shuffle chronological events để tạo5 logs giả. Primary7 decisions, budget báo cả scheduled/accessed/true.
- E7: pair `{minilm_mpnet, arctic, nomic, bge}`×collection `{fiqa,trec-covid,nq,hotpotqa,fever}`. Mapping ít nhất3 map seeds; eligible scheduler matrix đủ3×5. Không train/dev hợp lệ → mapping/random và greedy N/A, không giả đủ20 greedy cases. Complete extra published baselines theo M08 recipe task; thiếu source recipe ghi incomplete-baselines.

Các defaults subset/seed diagnostic là engineering choices mới, phải lưu trước run. Không tune subset theo kết quả. E2/E7 trùng case chỉ reuse outputs khi toàn bộ resolved scientific inputs/config/mode/seed/profile giống, có thể khác stage label. So content hash loại stage/run path labels; lưu source run reference, không giả đã chạy một run khác. T0 development outputs không reuse làm official quality cells.

Required static checkpoint targets ở E2/E5/E7 đều theo report: bootstrap,5/10/25/50% accessed và100% true (bỏ mốc thấp hơn bootstrap với reason). Primary hypothesis ở10% vẫn cố định; không cần giả thuyết dương mới chạy các mốc sau. Queue được chia primary/continuation để upload sớm và không chặn task khác, nhưng stage checkbox compute tổng chỉ tick khi required targets/cells đủ. E6 dùng weekly targets riêng, không ép10%/100% trong8 tuần.

## Expected output và kết luận

Mỗi stage có một aggregate table generated từ completed run outputs. Mỗi run lưu config, summary, metrics/retrieval, IDs/events, learned checkpoint cần thiết và sync receipt. Không tạo thêm20 báo cáo văn xuôi.

Outcome đọc theo `expect.md`: pipeline hợp lệ + effect không rõ là inconclusive, effect âm là negative; cả hai vẫn hoàn thành. Correctness/leakage/budget/ANN gate fail là technical failure cần sửa trước claim. E2/E5 không thắng không phải lý do bỏ E7 hoặc đổi primary theo test.

Checkpoint5/10/25/50% accessed là checkpoints chất lượng; refit theo5% **backfill** là một lịch khác. E5 primary ARR không phải judged relevance, và judged-dev nDCG không được gọi BEIR endpoint. BEIR endpoints thuộc E2/E7. Đây là cách đọc rõ hơn cho các đoạn mô tả ngắn trong expect/report.

## Hooks sau run

`finalize_run -> update_checklist(compute) -> auto_sync_experiment -> verify -> update_checklist(sync)`.

Ở checkpoint dài, hook cũng enqueue bundle immutable để không chờ xong toàn bộ matrix mới upload. Queue có thể chạy task kế tiếp khi compute còn chỗ; sync không giữ GPU reservation. Khi measurement exclusive đang chạy, đợi measurement kết thúc mới xử lý upload nặng. Không dọn local sau hook.
