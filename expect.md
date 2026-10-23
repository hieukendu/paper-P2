# Kỳ vọng và tiêu chí đọc kết quả thí nghiệm

File này mô tả **giả thuyết cần kiểm tra**, baseline phải so sánh và điều kiện nào được xem là đạt. Đây chưa phải kết quả thực nghiệm. Không được đưa các số trong file này vào paper như số đo trước khi pipeline chạy.

## Override scale đang dùng cho E5-E7

Khi chạy server theo plan downscale, áp dụng [codex/16_e567_downscale.md](codex/16_e567_downscale.md) với `scale_variant: e4e567_scale_v3_50k`. E4 cũng chạy lại trên manifest chung 50k documents/5k ORCAS groups, rồi phải đạt compute + sync verified trước khi làm parent; không trộn artifact/profile/hash cũ. Override này giữ nguyên cell count, scheduler, seed, budget, evaluator và checkpoint semantics. Vì vậy kết quả được đọc là reduced-scale pilot evidence, không phải full-corpus replication.

Trước E2–E7 phải hoàn tất T0 theo phạm vi của case: validate inputs, tuning có giới hạn trên development data và freeze profile theo [codex/14_presetup_tuning.md](codex/14_presetup_tuning.md). E1 là correctness smoke; T0 không thêm một E quality và không yêu cầu greedy thắng để mở official. T0.core cho FiQA, T0.scale trước E4/E5, T0.case cho dataset/model bổ sung.

## 1. Có mấy câu hỏi thực nghiệm?

Pipeline không chỉ hỏi “mô hình M có tốt hơn không”. Có bốn câu hỏi tách biệt:

1. **Map embedding:** map nào biến vector cũ thành vector gần không gian mới nhất: OP, LA, MLP, global, regional, calibration.
2. **Scheduler:** tại cùng ngân sách encode và cùng trạng thái index, chính sách nào chọn document có lợi hơn: random, degree-only, re-embed-on-read hay coverage greedy.
3. **Index/serving:** HNSW và cơ chế update có trả đúng kết quả, đủ recall và chịu được cập nhật đồng thời không.
4. **Trade-off vận hành:** chất lượng tăng bao nhiêu so với encoder calls, token/GPU time, RAM, disk, remap và latency.

Không được gộp bốn câu hỏi này thành một kết luận duy nhất. Ví dụ scheduler tốt hơn không có nghĩa HNSW tốt hơn; ARR cao hơn cũng không tự chứng minh relevance tốt hơn vì ARR đo agreement với full-new ranking.

## 1.1. Một core pipeline, nhiều execution branch

Không chạy cả bảy E bằng một cấu hình y hệt nhau. Quy tắc là:

- **Giữ cố định phần làm nên tính so sánh:** data manifest/split, encoder revision, ID join, budget ledger, evaluator độc lập, metric, seed, primary endpoint và provenance.
- **Cho phép thay đổi phần đang được kiểm tra:** exact hay ANN, subset hay full corpus, static hay temporal traffic, sequential hay concurrent serving, map/scheduler variant và mức cache/shard.
- **Mọi thay đổi phải được ghi trong `config.lock.json`** và không được âm thầm đổi paid budget, query population hoặc evaluation IDs.

| E | Core pipeline dùng chung | Nhánh được phép rút gọn/thay đổi | Không được dùng để kết luận |
|---|---|---|---|
| E0 | Manifest, split, evaluator, budget definitions | Chưa cần encoder/index; chỉ khóa config và environment | Quality hoặc scheduler ranking |
| E1 | Loader, encoder accessor, map semantics, exact evaluator | Subset nhỏ, exact search, OP/global map; chưa cần HNSW/concurrency | Full-scale throughput |
| E2 | Cùng map/evaluator/budget semantics | FiQA/TREC-COVID, exact trước ANN; mapping variants; TREC-COVID có thể calibration/greedy N/A | Temporal hoặc full-corpus claim |
| E3 | Cùng stored-vector semantics và evaluator | ANN/HNSW, update lock, refit cadence, workload concurrency; scheduler giữ cố định | Scheduler quality nếu chưa giữ systems state chung |
| E4 | Cùng data access, budget và cost instrumentation | MS MARCO subset, streaming/shard, ORCAS sample; không cần full matrix | Full MS MARCO quality |
| E5 | Full primary pipeline | Full MS MARCO/Arctic/ORCAS static; đổi scheduler nhưng giữ mixed-index state và budget | Temporal traffic |
| E6 | Cùng map/scheduler/evaluator semantics | AOL-IA chronological replay, rolling cutoff và future evaluation; không đọc tương lai | Static ORCAS kết luận ngược lại |
| E7 | Cùng primary pipeline và comparison rules | Đổi collection/model pair theo compact representative matrix; seed set rút gọn và khai báo trước | Chỉ báo một mean gộp nếu các collection trái dấu |

Các tối ưu kỹ thuật như streaming, memory-map, shard, cache query embedding, batch sizing và reader/writer lock được phép dùng để chạy được trên H100 80GB. Chúng phải giữ nguyên kết quả logic và được đo riêng về cost/latency; chưa cleanup local trong phase này. Không được tối ưu riêng cho greedy bằng cách cấp thêm encoder budget, query refresh miễn phí hoặc evaluator access mà baseline không có.

## 2. Vai trò của từng baseline

| Baseline/reference | Dùng để trả lời | Cách diễn giải |
|---|---|---|
| **Full-new exact** | Hệ thống sẽ đạt được bao nhiêu nếu mọi document dùng `h(d)` thật | Reference chính; không phải một đối thủ công bằng vì nó trả giá encode toàn corpus |
| **Old query + old index** | Không migrate thì chất lượng nền là bao nhiêu | Baseline không nâng cấp |
| **OP/LA/MLP global** | Map đơn giản hay map học được giữ quality tốt hơn | So trên cùng paid pairs và cùng evaluator |
| **Global + regional + calibration** | Correction địa phương/cutoff có giúp không | Ablation của mapping, giữ scheduler cố định |
| **Random** | Chọn document không có thông tin gain đạt mức nào | Scheduler baseline bắt buộc |
| **Degree/popularity-only** | Lợi ích có chỉ đến từ document phổ biến/có nhiều edge không | Baseline kiểm confound của click graph |
| **Re-embed-on-read** | Ưu tiên thứ tự query/candidate có tốt hơn random không | Baseline online có chi phí encode khác, phải ghi rõ |
| **Coverage greedy** | Gain/slack/coverage có giúp chọn batch tốt hơn không | Scheduler primary |
| **Uncertainty/margin/extra-clicked** | Nguồn gain nào thực sự đóng góp | Ablation, không phải primary claim |
| **Dual-index** | Tách lợi ích của scheduler khỏi lợi ích giữ old/new index riêng | Systems comparison riêng, không trộn vào mixed-index claim |
| **Hindsight oracle** | Trần tham khảo khi biết tương lai | Diagnostic; không phải hệ thống online và không được gọi là nghiệm tối ưu |

Tất cả scheduler primary phải dùng cùng initial vectors, graph, map/refit policy, calibration, candidate settings, paid budget, query IDs và seed set của cell compact tương ứng. Nếu một baseline dùng thêm anchor/unpaired vectors thì phải cộng chi phí đó vào ngân sách của baseline.

## 3. E0–E7 làm gì và kết quả nào được mong đợi?

### E0 — Khóa protocol và môi trường

**Mục tiêu:** tạo manifest dataset/model, split IDs, checksum, config, metric definitions, budget accessor và environment lock.

**Không có so sánh quality ở E0.** Đây là gate trước thí nghiệm.

**Đạt khi:**

- corpus/query/qrels/ID/dimension không nhầm;
- evaluator full-new tách khỏi migration và không bị scheduler đọc;
- paid documents, token counts và ngân sách được log;
- server H100 80GB, phiên bản CUDA/PyTorch/hnswlib/model và storage được ghi rõ.

Nếu E0 chưa đạt thì mọi curve sau đó chỉ là smoke output, chưa phải kết quả nghiên cứu.

### E1 — Smoke và logic exact

**Mục tiêu:** kiểm tra FiQA nhỏ, MiniLM → MPNet, exact search, OP/global map và các tình huống heap/scheduler.

**So sánh:** old/old, full-new exact, mapped vector; chưa dùng E1 để tuyên bố scheduler thắng.

**Kỳ vọng bắt buộc:**

- vector finite, đúng dimension và unit norm;
- budget cap, batch cap và stop reason đúng;
- không đọc test qrels/future target để chọn batch;
- khi `f_true=100%`, exact stored-vector ranking trùng full-new reference trong tolerance và tie-break đã khóa;
- lazy và eager gain cho cùng fixed snapshot cho cùng batch.

E1 thất bại nếu có leakage, loop vô hạn, ID update sai hoặc full-new completion không khớp reference.

### E2 — Pilot quality trên corpus nhỏ

**Mục tiêu:** kiểm tra map và scheduler trên FiQA khoảng 57k document, TREC-COVID khoảng 171k document bằng compact matrix 24 cell theo [codex/15_run_budget.md](codex/15_run_budget.md). E2 là pilot; không mở toàn bộ traffic grid hoặc factorial map×scheduler.

**So sánh mapping:** OP, LA, residual MLP; global, regional, calibration; exact search trước ANN.

FiQA mapping chạy OP/LA/MLP trên ba map seeds với random; scheduler comparison chỉ dùng MLP trên random/degree/re-embed-on-read/greedy và traffic seed101. TREC chỉ chạy OP/LA/MLP tại map seed17, scheduler là N/A. Regional/calibration/diagonal controls là T0 hoặc diagnostic riêng, không nhân vào required cells.

**Kỳ vọng nghiên cứu:** residual MLP/global-regional có thể giảm vector error và tăng absolute nDCG hoặc retained quality so với OP/LA; đây là giả thuyết. Calibration có thể cải thiện residual/cutoff behavior, cần đo trên population đã khai báo; nó có thể đổi ranking trong mixed-fidelity. Invariant giữ ranking của positive affine calibration chỉ áp cho exact diagnostic toàn mapped.

**Đọc kết quả:**

- full-new exact là reference;
- old/old là baseline đo riêng, không bảo đảm là sàn quality;
- map được đánh giá bằng sai số, quality/cost và agreement; full-new cũng không bảo đảm upper bound relevance, nên không ép mọi metric nằm giữa old/new;
- nếu regional/calibration làm xấu test quality thì giữ nguyên primary đã freeze và báo kết quả âm; global/identity là controls/ablations. Chỉ dùng fallback vì dữ liệu/số học theo protocol, không đổi primary sau test.

TREC-COVID chỉ có 50 test queries trong protocol hiện tại: primary dùng mapping và random backfill, calibration/greedy có thể là N/A. Không dùng thay đổi nhỏ trên bộ này làm bằng chứng scheduler.

### E3 — Systems pilot và HNSW

**Mục tiêu:** đo cấu hình HNSW đã chọn ở T0 trên Q_tune, kiểm candidate/serving recall, same-ID update, lock và refit/remap. E3 không chọn lại settings theo test.

**So sánh:** exact stored-vector search với HNSW; các cặp `(L, ef_effective)`; sequential với synchronized serving; cadence refit 1%, 5%, 10%; graph update với fresh graph cùng snapshot.

**Gate quality:** candidate recall@11 và serving recall@10 trên Q_tune phải đạt ít nhất **0.99 trung bình** cho cấu hình được chọn. Đây là fidelity gate, không phải kết quả chất lượng cuối của migration.

**Kỳ vọng vận hành:**

- same-ID update trả đúng vector/ID và không tạo mixed epoch;
- reader/writer lock không gây race hoặc snapshot không nhất quán;
- refit cadence thưa hơn có thể giảm write amplification nhưng có nguy cơ giảm quality; cadence 5% là primary cần đo, không mặc định tốt nhất;
- phải báo stall, queue, RSS/VRAM và bytes written; không được gọi hệ thống “zero downtime” chỉ vì update không crash.

### E4 — Scale feasibility

**Mục tiêu:** chạy MS MARCO subset có manifest và ORCAS query sample tách biệt để đo join, query encoding/search, scheduler memory, throughput và cost.

**Không dùng E4 để kết luận full-scale quality.** E4 trả lời “có thể chạy với tài nguyên hiện tại không?”.

**Đạt khi:**

- join coverage, checksum và document counts khớp manifest;
- H100 80GB không bị out-of-memory;
- peak RSS/VRAM, CPU, disk, write throughput và wall time cho phép dự báo full run;
- scheduler memory và refresh cost không tăng vượt khả năng host;
- subset được ghi nhãn rõ, không gọi là full 3.2M MS MARCO.

Nếu E4 không đạt, phải shard/stream/giảm concurrency hoặc điều chỉnh storage trước E5; không lấy kết quả subset để thay cho full-scale claim.

Sau T0.scale/subset feasible, E4 còn kiểm **actual full bootstrap stored graph của reduced pool 50k**: footprint và Q_tune recall trước E5. Đây là readiness gate, không phải quality evidence của compact E5 study. Timing/recall của100k docs không được tự xem là kết quả cho50k hoặc3.21M.

### E5 — Scale chính, static ORCAS

**Mục tiêu:** so scheduler trên cùng mixed-index state và cùng paid budget trong workload `e4e567_scale_v3_50k`: MS MARCO common manifest uniform 50k và ORCAS manifest tối đa 5k groups. Đây là reduced-scale static study; không gọi là full MS MARCO result.

E5 dùng parent E4 artifact/profile/hash đã freeze và common view/manifest đã hash trước quality run. Full rebuild, nếu được tính, là full rebuild của reduced pool 50k. Primary ARR@10 vẫn ở 10% accessed; judged-dev nDCG/Hit/NFR chỉ báo khi coverage gate của manifest đạt, nếu không ghi `N/A_REDUCED_COVERAGE`.

**Primary contrasts:**

1. coverage greedy vs random;
2. coverage greedy vs degree-only;
3. coverage greedy vs re-embed-on-read.

Uncertainty, margin-only, extra-clicked và hindsight oracle là ablation/diagnostic.

Compact E5 bắt buộc 12 cells: bốn scheduler × ba map seeds `{17,29,43}` × traffic seed `101`. Mỗi cell tiếp tục đến 100% true trong cùng run. Tối đa bốn traffic-sensitivity cells của random/greedy tại map seed17 và traffic `{103,109}` được chạy riêng nếu còn tài nguyên; chúng không chặn E5.

**Primary endpoint:**

- ORCAS: `ARR@10` ở tổng `10% accessed`;
- secondary MS MARCO judged-dev: absolute `nDCG@10`, kèm retained nDCG, Hit@10 và NFR@1; BEIR quality endpoints thuộc E2/E7;
- chi phí: encoder calls/tokens/GPU time, remap bytes, HNSW update time, time-to-first-serve và latency.

**Kỳ vọng chính của paper:** greedy đạt ARR/nDCG cao hơn các scheduler baseline ở cùng budget, đồng thời không vi phạm candidate/serving recall gate. Greedy có thể tốn scheduler refresh/remap nhiều hơn; vì vậy “tốt hơn” chỉ hợp lệ khi báo cả quality và cost.

**Quy tắc kết luận:**

- **Có bằng chứng tích cực:** paired effect của greedy > 0, CI95% không cắt 0 và contrast hợp lệ sau correction đã khai báo; quality gate và budget gate đều đạt. Vì compact matrix chỉ có một traffic seed primary, traffic robustness phải ghi là giới hạn.
- **Không kết luận:** CI95% cắt 0, seed variation lớn, hoặc quality tăng nhưng chi phí không đo/không ngang budget.
- **Kết quả âm:** greedy thấp hơn hoặc đắt hơn mà không bù được quality; giữ nguyên kết quả, không đổi scheduler sau khi xem test.

Không có ngưỡng được phép dùng các số placeholder như 98.6%, 89% tiết kiệm, 1.9 GPU-hour hoặc p99 2.9 ms. Các số đó chỉ được dùng nếu run thật sinh ra và truy được về artifact.

### E6 — Temporal AOL-IA

**Mục tiêu:** kiểm tra traffic có thời gian thật, không chỉ query graph tĩnh, trên workload capped của `e4e567_scale_v3_50k`. Tuần `t` chỉ dùng lịch sử đến `t`, backfill tối đa 1% tại boundary, rồi đánh giá tuần `t+1`.

**Primary endpoint:** weighted ARR ở tuần 8 tại cùng 7% scheduled nếu đủ 8 tuần và coverage hợp lệ.

E6 giữ 8 tuần/7 quyết định và bốn scheduler nhưng giới hạn document pool ở 50k recovered documents và 50k events mỗi tuần bằng manifest sampling cố định. Sampling phải giữ chronology, timestamp và user/session block; không shuffle hoặc đọc future. AOL-IA không recovered đủ thì vẫn `BLOCKED_DATA`.

E6 compact chạy bốn scheduler trên cùng một chronology AOL-IA với map seed17; mỗi cell bao phủ đủ bảy quyết định tuần. Không tạo traffic seeds bằng cách shuffle timestamp. Kỳ vọng scheduler có sử dụng tần suất lịch sử có thể tốt hơn uniform/random trên future traffic, nhưng chỉ được kết luận nếu:

- không đọc future events/weights/labels;
- event frequency đến từ AOL-IA thật;
- corpus/query/event recovery coverage được báo;
- block bootstrap theo user và sensitivity theo ngày được thực hiện.

Nếu AOL-IA không khôi phục đủ, E6 là **chưa thực hiện**, không thay bằng timestamp synthetic.

### E7 — Mở rộng BEIR và kiểm tra độ bền

**Mục tiêu:** chạy compact representative matrix tám dataset/model cases theo [codex/15_run_budget.md](codex/15_run_budget.md) với scale override `e4e567_scale_v3_50k`, thay cho full 4 model pairs × 5 collections. Case lớn NQ/HotpotQA/FEVER dùng 50k documents và 500 queries cố định; FiQA/TREC-COVID chỉ reuse exact validated scope khi hash khớp. Đây là pilot tổng quát hóa, không đủ để tuyên bố phủ toàn bộ 20 cases hoặc full-corpus BEIR.

**So sánh:** cùng mapping/scheduler protocol trên nhiều domain và model pair; báo từng dataset/model, không chỉ một mean gộp.

Mỗi case chạy MLP với random và greedy tại map seed17/traffic101; OP+greedy chạy trên bốn case cross-check. Nếu phương pháp tổng quát, hướng hiệu ứng trong các case đại diện có thể ổn định; kết quả này không được ngoại suy thành full 20-case claim. Nếu một số domain âm hoặc không có gain, đó là bằng chứng giới hạn của compact pilot.

E7 chỉ đạt khi mọi số trong bảng truy được về per-query/per-seed runfile, split/checksum/revision và có thể rerun. E7 không cần viết lại paper trong phạm vi thí nghiệm này.

## 4. Khi nào được nói “thí nghiệm thành công”?

Thành công có nhiều tầng, không phải một con số duy nhất:

1. **Correctness:** E0–E1 không leakage; full-new completion khớp exact reference.
2. **Fidelity:** E3 đạt candidate recall@11 và serving recall@10 ≥0.99.
3. **Quality:** E5 có contrast greedy được pre-register so với các baseline ở cùng budget; effect, CI, p-value và seed variation đều được báo.
4. **Operability:** E4/E5 có peak RAM/VRAM, disk, throughput, latency, stall và cost thật.
5. **Generalization:** E7 giữ toàn bộ kết quả theo dataset/model, không chỉ collection thuận lợi.
6. **Temporal validity:** E6 chỉ được gọi thành công khi dùng event timeline thật và không leakage tương lai.

Nếu chỉ đạt correctness nhưng greedy không thắng, đó vẫn là một thí nghiệm hợp lệ; kết luận khi đó là pipeline đúng nhưng giả thuyết scheduler chưa được ủng hộ. Nếu quality tăng nhưng ANN recall, budget hoặc provenance sai, cũng không được gọi là bằng chứng hợp lệ.

## 5. Gói kết quả tối thiểu cần bàn giao

Mỗi E phải giữ:

- `config.lock.json`, `summary.json`, policy/profile refs, dataset/model revisions và checksum; không thêm `provenance.json` trùng nội dung;
- per-query/per-seed metrics, retrieval runs và evaluation IDs;
- encoder access, token/GPU time, remap/HNSW/update logs;
- peak RSS/VRAM, disk/write amplification, latency/stall/error;
- negative/failed runs và reason codes;
- bảng so sánh absolute, retained, ARR, cost và CI/p-value.

Chỉ sau khi có gói này mới được trả lời “cái gì mạnh hơn cái gì”. Trước đó chỉ được nói đây là hypothesis hoặc gate thiết kế, không phải outcome.

## 6. Thứ tự đọc kết quả nên dùng

Đọc **E1 → T0.core → E2 → E3 → T0.scale → E4 → E5**, rồi E6/E7 sau T0.case tương ứng; các nhánh độc lập có thể xen kẽ theo resource. Nếu correctness hoặc ANN gate fail thì chặn đúng branch, không giả đã scale PASS. Nếu E4 fail thì chưa chạy E5 full. Với `e4e567_scale_v3_50k`, E4 phải được chạy trên common 50k/5k manifest và parent artifact/profile/hash phải hợp lệ trước khi mở E5-E7. E5 không có bằng chứng tích cực vẫn chạy E7 để biết giới hạn tổng quát; E6 báo riêng, không sửa kết luận static sau khi xem kết quả.

Tham chiếu protocol gốc: [report.md](report.md) mục8.3/9/10/15; thứ tự thực thi tại [codex/plan.md](codex/plan.md).
