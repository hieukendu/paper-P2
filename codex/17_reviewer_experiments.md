# M17 — Kế hoạch thí nghiệm bổ sung theo reviewer

Ngày lập: **31/10/2026, Asia/Saigon**. Trạng thái hiện tại: **EXPERIMENTS + HF VERIFIED; REV-01–REV-09 complete, REV.10 manuscript-only rows và Git handoff còn mở**. Đây là phần bổ sung của [plan.md](plan.md), không thay thế các kết quả E0–E7 đã có. Checklist duy nhất vẫn là [checklist.md ở gốc](../checklist.md).

**Kết quả rà soát tiếp:** đã đối chiếu từng dòng PDF với kế hoạch: **9/9 nhóm thí nghiệm/đo bổ sung, 11/11 mục wording và 7/7 Questions for Authors đều có nơi xử lý**; xem bảng đầy đủ ở [mục 10](#10-đối-chiếu-đầy-đủ-với-pdf-reviewer). Bốn mục NO ACTION được giữ, mở rộng corpus là mục EXCLUDED duy nhất. Đây là xác nhận **đủ kế hoạch**, chưa phải đủ kết quả. Lần rà soát này đọc lại toàn bộ PDF và source local; không coi các kiểm tra HF mẫu đã ghi ở mục 2 là restore toàn bộ artifacts.

## 1. Phạm vi và nguồn yêu cầu

Đã đọc **toàn bộ 5 trang** của [reviewer_action_plan.pdf](../reviewer/reviewer_action_plan.pdf), PDF duy nhất trong `reviewer/` tại lúc lập kế hoạch. SHA256: `fafcc4131bd11d13321f470672d8626200e604ca6a7ade39ad802ba81b0ace43`.

Lập kế hoạch cho **tất cả các mục còn lại**: cả hai P0, các P1 và các P2 có điều kiện dữ liệu/tài nguyên. Không tự bỏ P2 chỉ vì PDF gọi là optional. PDF cho phép tối thiểu baseline **hoặc** ablation; kế hoạch chính ở đây thực hiện **cả hai**. Theo yêu cầu user nhắc lại, **REV-01–09 đều nằm trong kế hoạch thực thi**, không chỉ gói minimum/strong response; một gate chưa đạt phải để trạng thái chưa hoàn tất và giải thích cụ thể. Các mở rộng nhỏ hơn trong từng mục được ghi riêng để không mở ma trận vô hạn.

**EXCLUDED duy nhất về thí nghiệm mới: mở rộng corpus vượt các pool 50k đang khóa.** Không tạo MS MARCO/BEIR/AOL 100k/1M/full-corpus run, không đổi pool để tăng positive-qrel coverage. FiQA **57.638** và TREC-COVID **171.332** tài liệu là hai full-corpus anchors đã có: giữ nguyên để so sánh và thêm seed, không phải mở rộng corpus mới. Các mục “NO ACTION” của PDF giữ kết quả hiện hành, không trở thành yêu cầu rerun.

Yêu cầu bàn giao của user áp dụng cho toàn vòng revise: **mỗi kết quả hoàn tất → sync HF và verify; sau khi toàn bộ thí nghiệm trong phạm vi đã xong mới commit code, push và tạo/cập nhật đúng một PR từ một branch duy nhất**. Lượt này chỉ ghi kế hoạch/checklist; chưa tạo branch, commit hoặc PR.

| ID | Ưu tiên / câu hỏi | Nguồn PDF | Việc phải có |
|---|---|---|---|
| REV-00 | Chuẩn bị | tr. 1–5 | Khôi phục có chọn lọc kết quả cũ, khóa protocol và ma trận bổ sung |
| REV-01 | P0 / Q1 | tr. 1, 4–5 | Query-side baseline cùng access budget và paired training-pool size |
| REV-02 | P0 / Q4 | tr. 1, 4–5 | Ablation global mapping, regional affine, score calibration |
| REV-03 | P1 / Q2 | tr. 1–2, 4–5 | Sensitivity rho, safety on/off; tối đa một proxy bổ sung |
| REV-04 | P1 / Q5 | tr. 2, 4–5 | RBO và Overlap@{1,3,10,20} |
| REV-05 | P1 | tr. 2, 4–5 | TREC-COVID ít nhất ba seed cho các cấu hình có randomness |
| REV-06 | P1 / Q7 | tr. 2, 4–5 | Wall-clock, RAM/VRAM, storage; calibration/refit so với live encode/backfill |
| REV-07 | P2 | tr. 2, 4–5 | Đồng nhất scope khi kiểm tra thêm model transition |
| REV-08 | P2 | tr. 2, 4–5 | MS MARCO/ORCAS held-out queries, tách khỏi scheduling |
| REV-09 | P2 / Q6 | tr. 2, 4–5 | AOL click-derived proxy nếu signal đủ và join được |
| REV-10 | P0/P1 wording | tr. 2–4 | Toàn bộ clarification và giới hạn claim, gắn với bằng chứng |
| REV-11 | Bàn giao | Yêu cầu user | Aggregate, HF verified, commit sau experiments, một branch/một PR |

## 2. Kết quả cũ và cách lấy từ Hugging Face

Đọc [result/README.md](../result/README.md), [data scope](../result/01_data_scope.md), [statistics](../result/08_statistics.md), [code notes](../result/11_code_method_notes.md) và [sổ nguồn](../result/10_sources_and_coverage.md) trước khi lập jobs. Sổ nguồn hiện có 69 cấu hình/tác vụ E2–E7, không phải 69 lần lặp độc lập. Không chọn run có metric tốt nhất trong các bản lịch sử.

Trong lượt lập kế hoạch đã dùng `HF_TOKEN` từ `.env`, qua `load_dotenv(PROJECT_ROOT / '.env', override=False)`, để đọc trực tiếp HF. Connector HF hiện không có công cụ tải arbitrary result artifacts; việc đối chiếu tệp dùng SDK/API với token local. Không in token, không đưa `.env` vào source snapshot, commit hoặc bundle.

Đã đối chiếu metadata **cả năm run repos**; HEAD vẫn khớp sổ nguồn ngày 30/10:

| Kho kết quả | Revision đã đọc |
|---|---|
| [mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913) | `3fbcb0c15ea6f5a18d4995dc42c64ef568c02913` |
| [mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12) | `e998cf63802a03803afea6cf341841b33cd2ea12` |
| [mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1) | `f736e4591abb4b825779a99e19f28a91cd1fb6c1` |
| [mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1) | `4121dc49dd29e08bf303c8d8b4a7db73f73983e1` |
| [mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026) | `49d75f8f6919f07f074abe8f6f4a667352cff026` |

Đã tải manifest/config/summary/marker của sáu bundle mẫu **S082, S089, S107, S129, S147, S157** trong sổ nguồn; summary/config khớp SHA256 trong manifest và đều `COMPUTE_DONE`. Đã tải và kiểm checksum rankings của S082/S089/S129/S157: mỗi query/checkpoint chỉ có **10 ranks**. S107/E5 có sáu checkpoint metadata nhưng **không có root `metrics.parquet` hoặc `retrieval.trec.gz`**. Đây là kiểm tra mẫu phục vụ lập kế hoạch; chưa tải/verify toàn bộ graph/weights, chưa restore hoặc chạy lại GPU. Cache kiểm tra nằm ngoài repository, không phải accepted result mới.

Khi bắt đầu thực thi REV-00:

1. Tra đúng repo/revision/payload prefix từ sổ nguồn; đọc `COMPLETED.json` + `artifact_manifest.json`, resolve đầy đủ parts khi bundle chia qua nhiều repo. Giữ references về bundle cũ trong `reference_inputs.json` của kết quả mới.
2. Tải **metrics/rankings/config/splits cần dùng trước**, graph/vector checkpoint sau khi đã biết việc nào cần chúng. Verify bytes/SHA256 trước reuse; metadata listing không thay cho kiểm file tải về.
3. Dùng `hf_sync.restore_run` khi có receipt đủ parts; nếu chỉ có catalog/marker, resolve thành receipt tương thích trước, không bịa một local receipt `VERIFIED`.
4. Đóng băng danh sách accepted inputs theo config/model/data/pool/query hashes và method thực thi. Tái phân tích tạo run ID mới, không ghi đè bundle cũ hoặc đổi nhãn kết quả cũ thành thí nghiệm mới.
5. Không tải lại hàng trăm GB mọi repo theo mặc định. Với evaluation-only, restore trực tiếp stored index snapshot khi đủ state; không cần toàn bộ migration accessor chỉ để search.

| Việc | Có thể reuse | Phần cần đo/chạy mới |
|---|---|---|
| Overlap@1/@3/@10, RBO depth 10 | E2/E7 rankings; E6 nếu query joins hợp lệ | Post-hoc analysis + CI, không re-embed docs |
| Overlap@20, RBO depth 20 | Stored index và target reference checkpoint | Search lại top20; lấy/encode query vectors nếu chưa lưu |
| E5 within-workload / held-out | 12 trajectories và snapshots đã lưu | Search snapshots, xuất per-query metrics/rankings; không suy từ mean ARR |
| Component ablation / greedy sensitivity | Old/target vectors, document/query IDs, frozen profiles | Chạy migration variants mới; không sửa summary cũ |
| TREC seeds | Seed17 và target/old references | Bổ sung seed29/43, chỉ reuse cell khớp protocol |
| Cost | Timing/footprint cũ để xác định component | Benchmark cô lập và live target inference; cached lookup không đủ |
| AOL relevance proxy | Redacted IDs/qrels/events + E6 rankings nếu join được | Audit signal, tính proxy; không cần raw query text cho post-hoc joins |

## 3. Protocol chung trước khi chạy

- Tên study revision đề xuất: `reviewer_v1`. Giữ nguyên `compact_v1`/`e4e567_scale_v3_50k` của lịch sử; ghi supplemental revision riêng. Không sửa accepted tuning lock để hợp thức hóa variant mới.
- Core anchor: FiQA, MiniLM→MPNet, **648 eval groups**, scheduling/cal/tune roles cũ. Map seeds **17/29/43**, traffic seed **101**. Seed của RNG backfill phải ghi riêng; ba map seeds với cùng traffic seed không phải ba traffic orders độc lập.
- Endpoint chính mới: **10% total unique target-document accesses**. Lưu thêm bootstrap, 5%, 25%; số nguyên theo rule runner, báo cả actual count/fraction. Ma trận bổ sung mặc định dừng 25%; không tự kéo mọi run tới 100%. References 50/100% cũ chỉ dùng nếu cùng protocol; completion correctness kiểm bằng fixture và reference, không tạo số đo mới từ interpolation.
- `B = |unique target document IDs requested|`; `B_bootstrap` gồm train/val/cal đã thực đọc, `B_scheduled` là backfill thêm. Log roles và union để không cộng trùng. Target vectors đầy đủ chỉ ở evaluator/cache, scheduler phải qua `PaidEmbeddingAccessor`. Tách cả chi phí evaluator/reference khỏi serving/migration và báo query-encoder cost riêng.
- Rerun variants cùng IDs/pools/random prefix khi so thành phần; cùng search backend, dtype/prefix/token limit/model revision. Variant đổi learned component phải có profile/override cho đúng scope. Chọn lr/checkpoint trên validation, không chọn theo test, cal-check hoặc future AOL.
- Chỉ mở official supplemental jobs sau meaningful tests, một development smoke, input/source snapshot hash và freeze configs. Không sửa `src`/configs/tests giữa một cohort đang chạy: `source_hash()` kiểm toàn bộ source allowlist, thay file có thể làm run fail.
- H100 80GB là target; probe phần cứng/cgroup hiện tại trước chạy. Quality queue mặc định một compute job, tối đa hai khi tài nguyên đủ. Cost/latency windows chạy exclusive; không chạy upload nặng trong measurement window.

## 4. Các nhóm thí nghiệm

### REV-01 — Baseline query-side, P0 / Q1

**Mục tiêu:** có đối chứng học từ cùng số paired documents, cùng access budget, giữ index cũ và chuyển target query về không gian cũ. Nguồn phương pháp: [Drift-Adapter, Method §3](https://arxiv.org/html/2509.23471v1), [bản xuất bản](https://aclanthology.org/2025.emnlp-main.805/). Đây là hướng new-query→old-space; không dùng forward map như một adapter đảo chiều.

Thiết kế matched-pool chính gồm **query-side OP/LA/residual-MLP × 3 seeds** và **forward-global OP/LA/residual-MLP × 3 seeds**: **18 run configurations**, mỗi run có các budget checkpoints, không đếm checkpoint như seed.

1. Tạo một random acquisition order cố định, độc lập qrels test, dùng chung cho hai hướng. Tại mỗi `B`, tập paid là `U_B = T_B ∪ P_val`, disjoint; `T_B` tăng theo prefix, chứa cùng train document IDs cho hai hướng. Không thêm cal pools trong đối chứng này vì cả hai hướng không dùng regional/score calibration. Như vậy **actual unique accesses và training-pool size bằng nhau**, không chỉ cùng nhãn “10%”. `P_val` cố định và luôn tính vào budget. Bootstrap riêng của controls khoảng2,5% vì không có calibration pools; không gắn nó vào mốc bootstrap khoảng3,5% của main pipeline. So các hướng tại cùng actual5/10/25%.
2. Query-side fit **new→old** trên `T_B`, validation trên cùng `P_val`, normalize output; search unchanged old index. Forward control fit **old→new** trên đúng `T_B`, cùng map family/seed/bounded validation rule; phục vụ true vectors cho `U_B`, mapped vectors cho phần còn lại. Cả hai được refit ở các endpoint đã khóa, không nhìn test để chọn pool.
3. Đây là **supplemental matched-refit protocol**, khác main pipeline giữ M0 frozen và refit regional. Báo nó trong bảng riêng. Thêm main `G+R+C` từ REV-02 tại cùng actual budget để tham chiếu; ghi rõ phân bổ train/cal/refit khác nhau, không gọi hàng đó là matched-training-pool causal control.
4. MiniLM/MPNet khác chiều 384/768: OP cần quy tắc rectangular/zero-padding và MLP cần linear skip projection, phải mô tả và kiểm shape. Gọi đúng là **budget-matched adaptation of Drift-Adapter** khi khác công thức/optimizer bản gốc, không nhận là faithful published-protocol reproduction. Không dùng cosine trực tiếp giữa hai chiều.
5. Báo nDCG@10, Hit@10, NFR@1, Overlap@k, RBO; pair counts/actual accesses; train time, adapter query overhead và tổng search latency. Old/old, full-new là references, không tính inference toàn target vào budget của baseline.

**Gate:** assertions cùng `U_B/T_B/P_val`, không truy cập extra paired data; index cũ của query-side bất biến; output hữu hạn và normalized; restore weights/rankings khớp. Không thay thế baseline học bằng một phép transpose rồi gọi là reproduction.

**Phần mở rộng được lên kế hoạch:** đọc recipe/code chính thức của [Embedding-Converter](https://aclanthology.org/2025.acl-long.1237/) và [QDC](https://github.com/dipamgoswami/QDC) ở feasibility pass; nếu tương thích frozen-encoder/budget thì thêm một baseline sau 18 controls. QDC continual-training setup hoặc dimension mismatch không được tự biến thành mean-shift “QDC gốc”; adaptation phải ghi rõ. Không lấy pretrained converter được học bằng paired target data ngoài budget để so như matched-budget. Nếu không tương thích, ghi lý do và giữ taxonomy/limitation; P0 vẫn có đủ đối chứng chính ở trên.

### REV-02 — Component ablation, P0 / Q4

FiQA/MiniLM→MPNet, residual-MLP global, **random backfill prefix giống nhau**, ba seeds. Random tránh việc tắt calibration đồng thời đổi greedy thành fallback rồi nhầm đó là tác động calibration lên retrieval.

| Variant | Global | Regional | Score calibration | Câu hỏi |
|---|---|---|---|---|
| `G_R_C` | Learned | Full affine | On | Main pipeline |
| `G_R_0` | Learned | Full affine | Off | Calibration khi đã có regional |
| `G_0_C` | Learned | Off | On | Regional khi có calibration |
| `G_0_0` | Learned | Off | Off | Global-only; hoàn chỉnh 2×2 regional/cal |
| `Gfixed_R_C` | Fixed projection | Full affine | On | Bỏ learned global, giữ local/cal |
| `Gfixed_0_0` | Fixed projection | Off | Off | Mốc projection không học |

**18 configurations**, tối đa reuse ba `G_R_C` random cells cũ sau equivalence check; còn **15 mới** nếu reuse hợp lệ. Bốn tổ hợp đầu đã có config primitives trong `experiments_static.VARIANTS`, nhưng builder `compact_v1` hiện **chỉ lập primary**: cần supplemental task builder, không chỉ đổi YAML rồi nghĩ matrix đã đầy đủ.

`Gfixed` không phải identity giữa hai chiều: dùng **zero-padding cố định 384→768**, không học/no target data, chuẩn hóa như protocol. Nó là control về learned alignment, không phải một hệ tọa độ có semantic guarantee. Giữ region assignments từ cùng old-vector partition trong các variant có regional; refit cùng cadence/min-pairs/ridge. Có thể xác nhận global-off bằng identity trên FiQA/Nomic cùng chiều ở REV-07.

Giữ **paid union, train/val/cal IDs và served true rows như nhau**, kể cả khi C off; các pairs bỏ dùng cho calibration không được tái phân bổ vào training. Tách bảng matched-access ablation khỏi bảng cost “chỉ làm overhead thực sự cần”. Không dùng val/cal pairs vào regional fitting. Báo bootstrap→5/10/25%, đặc biệt degradation tại 10%; contrasts `G_R_C−G_R_0`, `G_R_C−G_0_C`, `G_R_C−Gfixed_R_C` và interaction regional×cal. Không tự nâng thành kết luận nhân quả tổng quát ngoài các can thiệp/pool này.

### REV-03 — Greedy rho/safety sensitivity, P1 / Q2

Trong code `rho` của reviewer tương ứng `calibration.radius = r`. Hiện candidate band là `r < slack ≤ 2r`; safety loại query có relevant proxy `slack > 2r`. Cả hai đang hard-code trong `scheduling.build_candidate_sets`.

- Khóa **λ ∈ {0.5, 1, 2} × safety ∈ {on, off} × seeds {17,29,43}**: **18 configurations**, tối đa reuse ba default `λ=1,safety=on`, còn **15 mới**.
- Fit base radius bằng protocol P95 hiện tại; chỉ multiplier trong scheduler thay đổi: `r_eff=λr`, candidate band `(r_eff,2r_eff]`, safety nếu on kiểm `slack>2r_eff`. Đây là thay đổi radius scale; không đồng thời đổi thành một cutoff band khác mà vẫn dùng cùng tên.
- Giữ main mapping/regional/score calibration, schedules/proxies/budget/refit. Nếu radius unavailable hoặc ≤0, ghi lý do/fallback; không chọn radius từ test để tạo gain dương.
- Báo relevance + agreement tại cùng budget, at-risk queries, positive-gain selections, fallback fraction/reason, refresh time. Random/read reference là kết quả cùng cohort hoặc old cells đã verify, không rerun chúng cho mỗi λ.
- Tối đa **một proxy thêm**, đề xuất per-region score-residual std fit từ **cal-fit**, min20 pairs, thiếu region thì global cal-fit std. Freeze công thức/thang đo trước test, dùng cùng band/safety convention; nếu đủ dữ liệu chạy thêm ba seeds. Không dùng cal-check/test để chọn proxy thắng.

**Gate:** default flags phải tái hiện candidate sets/counts/rankings cũ; test slack ngay ở r/2r, safety off, true rows không được backfill, exhausted-gain fallback và restart. Phải ghi negative/collapse-to-random đúng như kết quả.

### REV-04 — Rank-sensitive metrics, P1 / Q5

Chọn **RBO thay Kendall tau** vì các top-k lists có thể không cùng tập doc. Định nghĩa theo [Webber–Moffat–Zobel](https://codalism.com/research/papers/wmz10_tois.pdf); khóa `p=0.9`, báo **extrapolated RBO với observed depth 10 hoặc 20**, không gộp hai depth thành một cột. Với equal-length prefixes không ties sau ID tie-break, đặt `A_d = |top_d(current) ∩ top_d(target)| / d`, dùng `RBO_EXT@K = (1-p) × Σ[d=1..K](p^(d-1) × A_d) + p^K × A_K`. Thành phần cuối là extrapolation từ overlap tại cutoff, không phải quan sát toàn bộ tail. `Overlap@k = A_k`.

1. Post-hoc từ E2/E7 accepted `retrieval.trec.gz`: `Overlap@{1,3,10}` và RBO depth10 cho old/full-new/migration checkpoints. Đổi **display name** ARR thành **Overlap@10**; schema cũ `arr_at_10` được giữ như alias đọc lịch sử, không sửa immutable bundles.
2. Để có `Overlap@20`, restore cùng index/calibration/epoch rồi search top20 và full-new exact top20. Kiểm top10 prefix vẫn khớp ranking cũ; nếu không khớp, dừng reuse và điều tra backend/config/graph. Không pad thêm 10 doc, không suy từ top10, không rebuild HNSW rồi gọi đó là graph cũ.
3. E5 phải search lại snapshots trên **seen và held-out** queries, xuất per-query outputs mới; mean ARR cũ không đủ tính RBO hoặc paired CI. Query embedding chưa có thì encode query ở pinned revision; không re-embed documents nếu snapshot đủ.
4. E6 metric mới giữ record weights, weekly population và user blocks. Cấm gom query×seed×week thành iid samples. Kết quả post-hoc ghi exploratory và parent artifact refs.

Test các lists identical/disjoint/reversed-same-set, top1 khác nhưng Overlap@10=1, unique doc IDs/tie-break, rank depth thiếu và query populations lệch. Một metric mới cũng là run có artifacts/sync riêng.

### REV-05 — TREC-COVID multiple seeds, P1

Core matrix **OP/LA/MLP × random × ba seed tuples `(map_seed, traffic_seed) = {(17,101), (29,103), (43,109)}`**: **9 configurations**, reuse ba E2 `(17,101)` hợp lệ, thêm **6 cells**. Đây là ba lần lặp end-to-end với cả map/region RNG và random-backfill RNG thay đổi, không phải sweep chỉ map seed; giữ cùng tuple giữa các map families khi so paired. Trong `migration.bootstrap_migration`, `state.rng` được tạo từ **traffic_seed**, nên chỉ đổi map seed và giữ 101 sẽ không kiểm tra robustness của random policy. Không cần mở tích Descartes 3×3.

Giữ full corpus171.332, cùng50 eval queries và cùng document train/val IDs; không chia 50 test queries thành tuning/scheduling để tạo traffic giả. Dùng đúng T0.case và train/val rule theo document pairs. Trước official, kiểm config/receipt có cả hai seed và lưu paid/backfill order hashes: các tuples mới phải thực sự tới RNG của scheduler, resume phải tái lập cùng prefix.

TREC hiện không có independent schedule/cal-query population: các hàng greedy ở E7 là random fallback. Có thể ghi alias/equality check ở cùng seed tuple, **không chạy/đếm greedy duplicate như một policy có thông tin**. Không thêm read với traffic giả hoặc diễn giải degree không có edges như scheduler comparison hợp lệ.

Báo mean/std/range qua ba **seed tuples**, paired query CI có điều kiện trên seed grid với giới hạn chỉ50 queries. Không quy dispersion này riêng cho map initialization hoặc traffic. Lưu exact old/new references, rankings và actual access fractions như REV-04. Các comparison FiQA còn lại vẫn giữ traffic101 như mục 3; thay đổi riêng của TREC không làm invalid reuse FiQA.

### REV-06 — Compute/storage overhead, P1 / Q7

Đo trên FiQA main, matched query-side control và **stored MS MARCO50k snapshot**; tận dụng cùng checkpoint/paid IDs của quality runs. Không mở corpus mới. Khóa một warm-up, **ba measured repeats** trên cùng restored starting state; không cộng dồn updates giữa repeats.

| Scope | Đo trực tiếp |
|---|---|
| Mapping/calibration | Train M0, initial regional fit, cal-fit/check riêng; wall/CPU, peak RSS/VRAM |
| Migration | Access/encode, commit true vectors, regional solve, remap, calibration refresh, HNSW updates/rebuild |
| Query-side | Query encode, adapter transform, search, end-to-end query wall latency; batch1 và batch protocol |
| Storage | Learned map, regional stats, cal state, vector arrays, graph binary, restart checkpoint; bytes thực và file sharing |
| Reference compute | Live target-encoder encode trên đúng document IDs và length distribution, với pinned tokenizer/dtype/batch |

Tách cold/warm cache, fixed setup cost và marginal per-batch cost; CUDA synchronize khi timer bao GPU work. Không cộng timer cha/con. So `T_cal + T_refit + T_remap + T_index` với **live inference cost tránh được trên cùng tập documents** và overhead của full-target build trong đúng scope. Nếu chỉ đo sample, báo estimate với sample/tokens và uncertainty, không gọi GPU-hours saved đã đo trên toàn corpus. Toàn target reference có sẵn trong cache không đồng nghĩa encode time bằng0 cho cost claim.

Báo per-repeat values + median/range, peak memory, saved bytes và store tổng, không chỉ map weights. Không suy “một serving index” thành giảm nửa RAM; không suy query microbenchmark thành zero-downtime/production p99. Không cần rerun E3 fidelity hay synthetic cadence probes.

### REV-07 — Cross-transition generalization, P2 đã lên lịch

Giữ **FiQA full anchor và 648 query IDs giống nhau**, thêm **BGE base→M3 trên FiQA** (case mới), đồng thời chuẩn hóa sâu **Nomic v1→v1.5 trên FiQA** đã có. Đây là thêm transition trên cùng corpus, không tăng corpus và không gọi Nomic là transition chưa từng thử.

Ma trận đề xuất **2 pairs × {OP,MLP} × {random,read} × 3 seeds = 24 configurations** trước reuse. Case BGE cần T0.case mới; Nomic phải kiểm lại profile/cal/splits tương thích. Checkpoints/bootstrap/5/10/25, metrics/budget y hệt main pair; pin adapter/prefix/token/dtype, không dùng query samples khác nhau như các E7 reduced cases cũ. Identity-global control cho Nomic cùng chiều là thêm ba cells nếu cần xác nhận REV-02, ghi ngoài ma trận24.

Chạy sau P0/P1; đo smoke từng pair trước forecast, không lấy throughput MPNet cho model8k context. Nếu không đủ tài nguyên hiện có, ghi `DEFERRED_RESOURCE` với measured forecast và mục chưa chạy, giữ ô compute trống; không tự thuê GPU hoặc lặng lẽ bỏ khỏi plan. Claim giới hạn “evaluated transitions/settings” dù kết quả thuận lợi.

### REV-08 — ORCAS unseen-query split, P2 đã lên lịch

Giữ MS MARCO pool50k và đúng scheduling5k của12 E5 cells. Dùng **10.000 ORCAS groups đã phân vai eval** trong release làm held-out candidate pool; kiểm disjoint theo **normalized text group**, không chỉ query ID, với schedule/cal-fit/cal-check/tune. Freeze danh sách đủ điều kiện/hash trước đọc kết quả; giữ cả groups không có edge vào corpus trong denominator agreement.

Restore 12 E5 trajectories tại bootstrap/5/10/25% và đánh giá **seen + held-out** trên cùng stored HNSW snapshot. Đây là tối đa **48 snapshot-evaluation tasks**, không phải48 migration runs mới. Target exact reference cùng corpus; thêm Overlap/RBO và per-query output, coverage counts. Báo read−random và read−degree trên held-out, greedy là hỗ trợ; không suy relevance từ clicks hoặc từ agreement.

Nếu thiếu query vectors, encode queries riêng. Nếu checkpoint binary/parts thiếu, báo thiếu artifact; chỉ replay trajectory cần thiết bằng pinned source/IDs/config thành run mới khi không restore được. Không train/refit/schedule trên held-out và không đổi document pool cho held-out qrels. Bảng within-workload cũ giữ nhãn riêng, không thay bằng held-out mà bỏ provenance.

### REV-09 — AOL temporal relevance proxy, P2 / Q6 có gate dữ liệu

Feasibility pass đọc schema `qrels.parquet`, redacted temporal events, doc IDs và E6 rankings theo pinned release. Kiểm group/event/URL-doc joins và tín hiệu click cùng chronology. Public release thiếu raw query/doc text **không tự chặn post-hoc proxy** nếu IDs/labels đủ; nó chặn re-encode độc lập khi cần text.

- Nếu join hợp lệ: tính **ClickedHit@10** (ít nhất một clicked doc của record/group trong top10) và **clicked-doc Recall@10** (trên clicked-doc set có trong pool), cho bốn policies và full-new reference. Ghi rõ denominator, multi-click/raw-row grouping và distinction record-weighted/group-weighted; không gọi proxy là unbiased relevance/nDCG.
- Báo toàn bộ coverage funnel: selected rows → clicked rows → clicked docs trong50k → rows/groups eval hợp lệ; giữ agreement trên toàn population. Không trình bày metric chỉ từ4,14% clicked rows có doc trong pool như utility toàn AOL. Không đổi corpus để cứu coverage.
- Labels tuần tương lai chỉ vào evaluator sau scheduling cutoff. So Read−Random tuần8 bằng paired user-block bootstrap; thêm sensitivity theo day đã có, không phát minh thêm chronology. Ngân sách E6 cũ là **7,002% accessed / 3,502% scheduled**, không đổi thành7% scheduled.
- Nếu click fields không đủ join, labels không đáng tin, hoặc số user blocks quá ít để CI ổn định: ghi `BLOCKED_DATA`/`INSUFFICIENT_SIGNAL`, lưu missing fields/counts và limitation cụ thể. Không tạo click labels, không coi blocked là compute xong.

## 5. Clarification và sửa cách viết — REV-10

Đây là các task cần bàn giao cùng kết quả, **chưa sửa manuscript trong lượt chỉ lập kế hoạch này**. Rà `paper/main.tex`, tables, captions và `paper/make_figures.py`; chỉnh wording có thể làm sớm khi thực thi, chốt numerical claims sau aggregate.

| Mục từ PDF | Nội dung phải viết chính xác |
|---|---|
| ARR rename | Dùng **Overlap@10** xuyên suốt; legacy `arr_at_10` là alias schema, không phải Adaptation Recall Ratio |
| Degree / Q3 | Bipartite schedule-query/doc edges, `degree(d)=|{q:(q,d)∈E_schedule}|`; dedup occurrences, tie theo original doc ID; mỗi batch lọc mapped docs và xếp lại, edges E2/E5 giữ cố định, temporal history refresh theo cutoff riêng; không phải click frequency |
| Read-prioritized | Nguồn workload/window, query-group order, first occurrence/top10 traversal, cursor/pending và random fill; temporal hiện sắp theo group ID, không phải arrival order hay online read counts |
| Matched budget | Train/val/cal/backfill unique union, actual counts và train-pool size; tách matched-refit controls khỏi main fixed-M0 protocol |
| 50k/sparse qrels | Supporting reduced-pool setting; FiQA/TREC full anchors; không gọi full-BEIR/MS MARCO relevance benchmark hoặc “đã sửa scale concern” |
| Model generalization | Main pair là primary evidence; các pair khác supporting, chỉ nói evaluated settings |
| AOL | Agreement/operational replay; nếu có click proxy cũng chỉ là proxy trên covered subset, không user utility toàn population |
| Related work | Query-side adaptation vs forward conversion vs gradual true replacement; Drift-Adapter/QDC/Embedding-Converter và trade-offs còn thiếu |
| Procrustes/alignment theory | Khi orthogonal map có thể đủ, khi local/nonlinear cần; bounds nguồn ngoài không tự thành mixed-index retrieval guarantee |
| Greedy failure | Radius empirical heuristic; nêu positive-gain/fallback counts, không gọi ranking certificate hoặc universal greedy win |
| Causal language | Trước/sau ablation chỉ diễn giải đúng can thiệp; không gán degradation cho một thành phần chỉ từ correlation |

Giữ nguyên các điểm PDF đánh dấu **NO ACTION**: FiQA multi-seed/CI hiện có, tách HNSW fidelity khỏi exact target, core finding agreement–relevance mismatch và policy-activity instrumentation. Dùng chúng trong response; không rerun vì reviewer đã đánh giá tốt.

## 6. Thống kê và outputs bắt buộc

- Core relevance endpoint: nDCG@10 ở10% accessed; agreement endpoints: Overlap@10 và RBO depth10. Overlap@1/@3/@20, Hit/NFR và25% là hỗ trợ. Khóa contrast families trước chạy; không chọn metric/seed/threshold sau khi nhìn kết quả.
- FiQA/TREC/ORCAS: mean per-query difference qua matched seed cells trước (TREC dùng map/backfill tuples ở REV-05), paired query-group bootstrap10.000 draws, seed20261020; sign-flip/Holm khi family được khai báo. Báo seed mean/std/range riêng; CI có điều kiện trên corpus/split/seed design, không seed×query iid. TREC50 queries cần giới hạn rõ.
- Baseline family: ba contrast query-side−forward-global cùng map family. Ablation family: ba contrasts component chính ở REV-02; interaction là hỗ trợ. Sensitivity family: năm variants−default. Holm tách theo endpoint/family; curves còn lại descriptive/exploratory, không giả preregistration của study cũ.
- AOL dùng paired user-block và record weights, một chronology. Không suy paired significance từ CI marginal từng method. Không có per-query output thì không báo paired-query CI.
- Mỗi run dùng artifacts chuẩn hiện có: `config.lock.json`, source snapshot, input/model/profile references, `summary.json`, `metrics.parquet`, `retrieval.trec.gz`, compact IDs/events/timing, learned state/checkpoint khi cần, `sync.json`. Tổng hợp contrast tables vào một derived analysis bundle, không nhân bản provenance cho mỗi phép tính.
- Summary ghi `review_action`, `parent_run_ids`, `analysis_only`/`new_migration`/`live_measurement`, metric schema/depth/p, actual pools/budget và outcome. P2 ghi status/reason riêng. Không ghi run âm thành failed hoặc đổi finding để đạt kỳ vọng.

## 7. Công việc code phải có trước official jobs

Đây là **hạng mục implementation tương lai**, không phải các file/CLI đã tạo:

| Nơi sửa | Bổ sung cần thiết |
|---|---|
| `experiments_static.py` hoặc một `experiments_reviewer.py` mỏng | Supplemental task matrix, matched-refit controls, 6 ablations, TREC với 3 seed tuples map/backfill; giữ core primitives |
| `maps.py`, `migration.py` | Reverse-direction adapters và deterministic projection control; config/checkpoint metadata đầy đủ, fixed prefix reuse |
| `scheduling.py`, `migration.py` | Radius multiplier/safety flags, thread qua mọi refresh/resume; default tương đương code cũ |
| `evaluation.py`, E5/E6/E7 evaluation paths | RBO, Overlap@k, export depth≥20 khi cần; evaluator-only snapshot re-evaluation và per-query E5 output |
| `config.py`, `configs/base.yaml`, supplemental YAML | Đăng ký keys mới vì `_merge` hiện reject unknown keys; variant/profile validation và immutable `reviewer_v1` lock |
| `cli.py`, `queue.py` | Wire supplemental plan/run/analysis đúng capabilities; dry-run chỉ ghi ma trận, không auto-start |
| `hf_sync.py` | Whitelist derived tables/configs mới, snapshot cả script thực sự được chạy; `source_files` hiện không lấy arbitrary analysis scripts |
| `tests/` | Tests khoa học về metric, budgets/roles/leakage, direction/dimensions, flags/default parity, snapshot restore và artifacts được sync |

Không giả sử `mixindex plan --experiment REV-*` đã tồn tại: CLI hiện chỉ biết E2–E7 trong `plan`. Không gọi builder `compact_v1` rồi nhận nó đã sinh ablation/seeds mới. Reuse `finalize_run`, `snapshot_source`, HF verify/restore và queue hiện có; không dựng thêm orchestration framework.

Chạy targeted tests cho phần vừa sửa, Ruff/compile, rồi full suite một lượt khi toàn implementation khóa. Preflight so default với fixture/accepted snapshot và smoke từng input scope trước official; test pass không thay compute/sync checkbox.

## 8. Thứ tự chạy, số cell và ngân sách thực thi

1. **REV-00:** HF inventory/restore chọn lọc, kiểm inputs, ghi branch/base/source snapshot policy, freeze budget/matrix/contrasts; probe resources. Làm REV-10 wording definitions cùng lúc chuẩn bị.
2. **Code + preflight:** nối các hạng mục mục7, tests/smoke; đóng băng toàn bộ source/configs trước cohort chạy dài. Chỉ tái mở source để sửa technical failure, ghi revision mới và rerun affected cells.
3. **REV-04 rẻ trước:** post-hoc depth10 để kiểm evaluator; có thể làm analysis trong lúc đợi compute nếu source đã freeze và không tranh tài nguyên.
4. **P0:** REV-02 component ablation rồi REV-01 matched baseline; mỗi group chạy seed17 smoke kỹ thuật trước, sau đó đủ29/43. Không dùng kết quả seed17 để chọn bỏ controls.
5. **P1:** REV-03 sensitivity, REV-05 TREC seeds, REV-04 depth20/metrics trên snapshots mới, REV-06 exclusive cost. Không lấy synthetic E3 cadence thay cost/refit measurement thật.
6. **P2 vẫn trong kế hoạch:** feasibility REV-09 sớm; chạy REV-08 từ snapshots trước khi cân nhắc replay; REV-07 model cases sau core. P2 thiếu dữ liệu/tài nguyên phải có status/missing evidence và checklist trống tương ứng, không âm thầm coi scope đã xong.
7. **REV-11:** aggregate→verify tất cả HF bundles→restore sample bắt buộc→chốt wording/response matrix→commit/push→một PR.

| Nhóm | Số cấu hình trước reuse | Số chạy mới dự kiến khi reuse hợp lệ |
|---|---:|---:|
| REV-01 query-side + forward controls | 18 | 18 |
| REV-02 ablation | 18 | 15 |
| REV-03 rho×safety | 18 | 15 |
| REV-05 TREC | 9 | 6 |
| **Core P0/P1 migration/adapter runs** | **63** | **54** |
| Proxy thêm REV-03 | 3 | 0–3, sau feasibility |
| REV-07 hai transition scopes | 24 | Tối đa24, trừ cell tương đương đã verify |
| Nomic identity control | 3 | 0–3, nếu cần xác nhận |
| REV-04/08/09, REV-06 | Analysis/search/benchmark tasks | Ghi riêng; không cộng snapshot/repeat thành map seeds |

54 là số configurations dự kiến, **không phải cam kết GPU-hours**; không gồm controls tùy chọn, preflight, re-evaluation hay benchmark. Nếu không reuse được chín defaults lịch sử thì core là63. Mỗi configuration có nhiều checkpoint fits/searches; scheduler runtime khác nhau. Không đếm duplicate E7/TREC fallback hoặc run lịch sử thành repetition mới.

Trước enqueue, ghi ma trận cells đã resolve vào **một supplemental YAML** trong `configs/` và summary của bước preflight: mỗi cell có `REV ID`, dataset/pair, method/direction/variant, scheduler, cả hai seeds, budget checkpoints, pool/query hashes, source/profile refs, parent/reuse disposition và expected outputs. Kiểm không trùng cell, không thiếu tích ma trận; accepted historical default chỉ thay một cell sau khi kiểm semantic settings, paid-order/checkpoint equivalence và artifacts cần dùng. Khác content hash chỉ do metadata/schema bổ sung phải được giải thích; đổi scientific settings thì không reuse. YAML và run summary là nguồn chạy/đếm, không tạo checklist thứ hai hoặc một framework inventory riêng.

Sau mỗi smoke, lưu measured setup/fit/migration/search/I/O và estimate cho cells còn lại; báo measured/estimated/unmeasured, remaining queue và disk staging. Không chốt ETA theo placeholder docs/s hoặc nhân một greedy prefix ra toàn ma trận. Khi resource thiếu, giảm concurrency/batch hợp lệ trước; không đổi protocol hoặc tăng corpus.

### 8.1. Tiến độ compute/sync thực tế — 31/10/2026

Đã hoàn tất **REV-04 depth-10 post-hoc** từ rankings đã restore và đóng bốn derived bundles. Script chạy là `src/mixindex/reviewer_posthoc.py`; metric table có một dòng mỗi query/comparison, `p=0.9`, Overlap@1/@3/@10 và RBO extrapolated depth10. Các archive accepted đều chỉ có top-10 nên `rbo_ext_20`/`overlap_at_20` được để thiếu trong output (không suy top-20); ô `REV.04.depth20` vẫn mở cho lần search snapshot thực.

| Derived run | Parent scope | HF verification |
|---|---|---|
| `REV-04-fiqa-e2-op-rankmetrics-m17` | E2 FiQA OP random m17/t101, 7 labels × 648 queries | [HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/6330c7baaab6c9c63e5d1ecb23dffe84f241c517/runs/REV-04-fiqa-e2-op-rankmetrics-m17/0cafc3b1ea3a2f8b3e2d6821d08e607bf7a56ef5639a3161f152044c0b448612) — `VERIFIED` |
| `REV-04-fiqa-e2-mlp-greedy-rankmetrics-m17` | E2 FiQA residual-MLP greedy m17/t101, 7 labels × 648 queries | [HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/9c5910b58a94c6f53759ddffc9bf73a20b4a8b9b/runs/REV-04-fiqa-e2-mlp-greedy-rankmetrics-m17/e3b86546ef2735db652e85ccf898026b217a1761d76b3646a5ec70e5835b157f) — `VERIFIED` |
| `REV-04-fiqa-e7-op-greedy-rankmetrics-m17` | E7 FiQA OP greedy m17/t101, 7 labels × 648 queries | [HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/67afb03a05a6ac67fd7df3fded093679bd3aa9e3/runs/REV-04-fiqa-e7-op-greedy-rankmetrics-m17/2b808299347cf451963b19a44465f8ce1ecdc90b89f394cbf72adc0059f127f1) — `VERIFIED` |
| `REV-04-aol-e6-weekly-rankmetrics-m17` | E6 AOL random, 7 current/full-new weekly pairs, 165,581 query rows | [HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/bbf781eab37f899957a68b7e58decf241d92649b/runs/REV-04-aol-e6-weekly-rankmetrics-m17/1fbc8d68294e258c2e330560849ab878190a39be0ee57b207aa99c2e192e7cc4) — `VERIFIED` |

Đây là analysis-only/reuse, không phải migration rerun, không thêm corpus và không phải evidence cho depth20. `summary.json` ghi `COMPUTE_DONE`, parent SHA256, hardware scope MIG H100 2g.20gb và `performance_claim=false`.

### 8.2. REV-09 AOL proxy — 31/10/2026

Đã join release AOL redacted `76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae` với rankings E6 của đủ bốn policy **random/read/degree/greedy** và `full-new` target, trên cả 8 tuần. Bundle `REV-09-aol-click-proxy-m17-v2` có **1,324,648** dòng per-group/week/policy, `ClickedHit@10`, clicked-document `Recall@10`, group-macro và event-weighted summaries. Coverage funnel ghi 400,000 selected rows, 216,723 clicked rows và 8,971 clicked rows có document trong pool 50k (**4.14%**); pool recall chỉ được tính trên clicked-doc set intersected với pool. Đây là click-derived operational proxy trên covered subset, không phải relevance không thiên lệch hay user utility toàn AOL.

HF receipt đã `VERIFIED`: [REV-09 payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/46fe9355d218c05a53b2aefa2afaf9bd4e8c09c6/runs/REV-09-aol-click-proxy-m17-v2/ea4925e98707022fe0853c320fdda5b984c3927d70a0f7a25d3a846c081fcd71). Source snapshot gồm `src/mixindex/reviewer_aol_proxy.py`; summary ghi `SIGNAL_JOINED`, `COMPUTE_DONE`, `performance_claim=false`.

### 8.3. REV-01 matched query-side/forward controls — 31/10/2026

Ba seed bundles `REV-01-fiqa-query-controls-m17-t101`, `m29-t101` và `m43-t101` đã hoàn tất trên cùng FiQA full release, mỗi bundle có 6 raw configurations (OP/LA/residual-MLP theo query-side và forward direction), exact index, paired pools và locked `compact_v1` budgets; cả 18/18 raw bundles đều `COMPUTE_DONE + SYNC=VERIFIED`. Sau khi bổ sung checkpoint-level `M0.safetensors`, access/timing metadata và post-hoc Overlap/RBO, derived rank-metric bundles cũng đã `SYNC=VERIFIED`:

| Seed | Raw payload | Rank-metric payload |
|---|---|---|
| m17/t101 | [raw](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/a2df3ef57b4f8b88e1e4ca33d3c2fa832427e9ef/runs/REV-01-fiqa-query-controls-m17-t101/fb2607a8f8d8da00de8ca2f869e9c4c91712ac5d5a10a2268b324b1fdb09d4e4) | [metrics](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/606e6e9da30eed6c35ecf561934222b5fe9aab80/runs/REV-01-fiqa-query-controls-m17-t101-rankmetrics/698f75ad34c7486ac7710ad1c5103975c8230561625a183274c7d04f47c6f39d) |
| m29/t101 | [raw](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/7966697ac6fcccc89eb68059e0ef71d33091921e/runs/REV-01-fiqa-query-controls-m29-t101/9203185cd9589c1efa6e4c3518d62a33b9cbe2967a779e34676670d5f3b54497) | [metrics](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/f5fa6af8671be3cc04da6be670c09d5802d5dada/runs/REV-01-fiqa-query-controls-m29-t101-rankmetrics/5fb575e8515616d823b24eb990c3dfec18c5d2673570bab26d44bf2ea2a7f166) |
| m43/t101 | [raw](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/161e64a5618833d414ca227172821e7d7d5aa2bf/runs/REV-01-fiqa-query-controls-m43-t101/d5987cabb933ecd5dc5f4a92f67b945617df8779c3ead4bc4a0233ec3129a12a) | [metrics](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/272da114be1811c214adaa850767616413e7cac1/runs/REV-01-fiqa-query-controls-m43-t101-rankmetrics/7be440037f3f897b0cbbbd05f7075912a1ec3e7004246163264d048286c3b452) |

`REV.01.compute/sync` is therefore closed. The optional Embedding-Converter/QDC feasibility check remains a separate `REV.01.extra` gate.

### 8.4. REV-02 component ablation — tiến độ thực thi

Đã hoàn tất và remote-verify **18/18 cells**: cả sáu variants `G_R_C`, `G_R_0`, `G_0_C`, `G_0_0`, `Gfixed_R_C`, `Gfixed_0_0` cho seed17/traffic101, seed29/traffic103 và seed43/traffic109. Mỗi cell có 4 checkpoint rows (bootstrap/5/10/25%), 14,410 unique paid documents ở 25%, 648 eval groups, random scheduler, fixed calibration-pool parent, seed-specific old-vector regional partition và source snapshot. Mỗi cell hiện có checkpoint-level learned state/weights; một bundle `G_R_C` m17 giữ full restoreable index, các bundle còn lại dùng compact state-only checkpoints với sufficient statistics/paid order/calibration metadata. Fixed-projection serializer đã được sửa và retry 5 cell lỗi kỹ thuật đều `COMPUTE_DONE + SYNC=VERIFIED`. Aggregate contrasts và paired bootstrap/Holm corrections có trong `REV-AGGREGATE-fiqa-v4` và remote-verified ([HF](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/b600f9dfdbd5770c3d0099d12e800678f419ec5a/runs/REV-AGGREGATE-fiqa-v4/b95c3a4a2ab5a8a339faa15d760c368eb8aed5abc9e0b035a7d63fb35a275b26)). `REV.02.compute/sync` đã đóng.

### 8.5. REV-05 TREC-COVID multi-seed — 31/10/2026

Đã hoàn tất đủ **9/9** cấu hình OP/LA/residual-MLP × random × seed tuples `(17,101)`, `(29,103)`, `(43,109)`. Sáu supplemental cells chạy trên full 171,332-document TREC-COVID release và 50 evaluation queries; mỗi bundle có 6 checkpoints, exact completion agreement 1.0, paid-order/resume hashes và target-vector fidelity 1.0. Tất cả 6 cells mới đều `COMPUTE_DONE + SYNC=VERIFIED`:

| Cell | HF payload |
|---|---|
| OP m29/t103 | [payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/c6650fd0243f0123716faaeb7835ffdc58e1faf5/runs/REV-05-trec-covid-op-random-m29-t103/5657e2efbb3e9d17fc49a02d0467ae479435b4c5d378601f30c27c8c712e4aef) |
| LA m29/t103 | [payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/61e7586d46b425f37f4165fa4bef22007d4278bb/runs/REV-05-trec-covid-la-random-m29-t103/2e8aafab365df189021da01e8cf382ccc92e35d0e2574aa5b182e814cb4afd5c) |
| residual-MLP m29/t103 | [payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/978ab037539ac0b128864eb498afb0de3be5d574/runs/REV-05-trec-covid-residual_mlp-random-m29-t103/0fd91102a945c2fae8fc99dc939895e902c43ebad16f940eb33227888fa12c2d) |
| OP m43/t109 | [payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/df6cd15bd5f4f7166d0afaf25b95d1d81334f9e4/runs/REV-05-trec-covid-op-random-m43-t109/03dba31e3357fb848a528230da16a30c80c7efb73130ae4d771d8ee0dca1ce72) |
| LA m43/t109 | [payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/9d9350addba5c7d094f71d7413f2589ab39ae73a/runs/REV-05-trec-covid-la-random-m43-t109/14e7bc937ef9c2091d4a8d1a0a2c13ac3e6a8bc995fcfb31c5f3225e48b43475) |
| residual-MLP m43/t109 | [payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/df868a32a5ebd5906bff31db99d24831918d1dd1/runs/REV-05-trec-covid-residual_mlp-random-m43-t109/8be2d64ad87036323b0d8235c55537b5bf0eef20af5b7e896256f9421bce8472) |

Seed dispersion must be reported jointly over each `(map_seed, traffic_seed)` tuple; it is not attributed to map or traffic alone. Aggregate mean/std/range and paired 50-query CI remain a REV-11 analysis gate.

### 8.6. REV-03 uncertainty proxy — 31/10/2026

Feasibility trên checkpoint-level cal-fit state cho thấy đủ signal: 431 cal-fit pairs, tối thiểu 20 pairs ở 5 vùng, residual standard deviation giữa vùng có CV khoảng 7.6–11.0% trên ba seed. Proxy được khóa là `cal_fit_score_residual_std_min20`: mỗi vùng dùng độ lệch chuẩn residual của cal-fit; vùng dưới 20 pairs dùng global cal-fit std; candidate band/safety vẫn là `(r_proxy, 2*r_proxy]` với cùng paid-budget và fallback. Chạy đủ ba tuples `(17,101)/(29,103)/(43,109)`, tất cả `SIGNAL_OK`, `COMPUTE_DONE + SYNC=VERIFIED`; aggregate `REV-AGGREGATE-fiqa-v6` đã đưa proxy vào paired bootstrap/Holm. Kết quả proxy vẫn là sensitivity/feasibility evidence, không được gọi là calibrated uncertainty guarantee.

### 8.7. REV-06 exclusive cost/storage benchmark — 31/10/2026

`REV-06-fiqa-cost-m17` đã chạy độc quyền trên MIG H100 với một warm-up và **ba measured repeats** từ cùng FiQA pools/seed, dùng cached target access cho migration nhưng tách riêng live encoder work. Mỗi repeat chạy bootstrap/calibration, regional solve/refit/remap và exact-index updates đến 25% accessed; checkpoint storage dao động khoảng 296,968,783–296,968,794 bytes. Query-side residual-MLP adapter được đo trên 648 eval queries ở batch-1 và batch-32. Pinned MPNet live target encoding đo 4,096 length-stratified document rows (full-FiQA estimate khoảng 1,001 s, không gọi là full-corpus measured) và 648 query rows, kèm raw/effective tokens, peak RSS/VRAM và embedding digests. Storage inventory còn đối chiếu artifact manifest đã verify của snapshot MS MARCO reduced-50k E5; không quy cached vectors thành encoder time bằng0.

HF receipt đã `VERIFIED`: [REV-06 payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/7456f2ca85a72f77b2026e2d291956f805cea0b8/runs/REV-06-fiqa-cost-m17/0e065dd56eea52012377b141d745f6577a1ade62289d5de49e0a94bcfb90f677). Bundle gồm `metrics.parquet`, per-repeat/query/live/storage timing, config/reference và source snapshot; `performance_claim=false`.

### 8.9. REV-01.extra feasibility — 31/10/2026

Feasibility pass đã đọc source chính thức của Embedding-Converter và QDC. Không có pinned converter implementation/checkpoint tương thích cặp frozen MiniLM-v2 (384) → MPNet-base-v2 (768) trong inputs; dùng external target-trained weights sẽ vi phạm matched-budget/no-extra-target-data gate. QDC chính thức dùng Nomic embedding continual fine-tuning, contrastors environment, hard-negative task data và continual checkpoints, nên không phải frozen-encoder mapping baseline trong 18-control protocol. Kết quả được đóng là `COMPUTE_DONE`, `CLOSED_WITH_NEGATIVE_EVIDENCE`, `INCOMPATIBLE_PROTOCOL`, `quality_runs=0`; không tạo số quality giả và giữ taxonomy/limitation cho REV-10.related.

HF receipt đã `VERIFIED`: [REV-01.extra payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/b08c85ab7dd6fb6d4cd47fdfac9aef25ba1438fa/runs/REV-01-extra-feasibility/01fcb2b530bb5f28c3172c61ebb16b1dddc7e400389a25114ecfccd54e81cbe2). Bundle gồm method-level feasibility table, official-source commit/URL refs, config/reference/manifest và source snapshot; `performance_claim=false`.

### 8.8. REV-04.E5 replay + held-out foundation — 31/10/2026

`REV-04-e5-posthoc` đã replay trực tiếp các HNSW snapshots đã accepted trên common reduced manifest: Arctic v2 query encoder pinned revision, prefix `query: `, CLS pooling, 15,000 queries (5,000 seen schedule + 10,000 held-out eval) và `ef_search=2000`. Kết quả hiện có **1,080,000 per-query rows/rankings cho đủ 12/12 cells × 6 checkpoints**; split hash xác nhận normalized-text disjointness với schedule/cal-fit/cal-check/tune và không loại held-out eval nào vì overlap. Các rows gồm Overlap@1/@3/@10 và RBO extrapolated depth10, target là `f_1.00` stored-HNSW cùng cell; không dùng aggregate ARR hay paired CI cũ.

HF receipt đã `VERIFIED`: [REV-04.E5 payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/e2a82994cc4267265e175687de5001f70143ca95/runs/REV-04-e5-posthoc/7a2161e8b76fd6019c0d866cea089ce41ee6265059bd2eb7d3a15ca971862014). Cell `E5-scale-degree-m29-t101-ca194e98f844` đã được reconcile: marker `COMPLETED.json` ở [runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/ff52cc31a9e41f31abc2ca5a2ddd7c3ea3fd86b0/runs/E5-scale-degree-m29-t101-ca194e98f844/aa87818db8949896f43e63673043335bac08545583d2b19bfc0b11769dbacb1f) trỏ tới graph part pinned ở `mixindex-runs-004` revision `f7f765b7361de2e4a557c728a0aaa442cf81746d`, đủ sáu HNSW binaries; representative graph load pass. Bundle gồm `selection.parquet`, `metrics.parquet`, `retrieval.trec.gz`, config/reference/timing và source snapshot, `performance_claim=false`. Đây là input frozen cho REV-08 read−random/read−degree contrasts.

## 9. HF sync, commit và đúng một branch/PR — REV-11

Quy trình này ưu tiên hơn các hướng dẫn cũ về tạo PR trong lúc đang chạy:

1. **Chỉ một branch làm việc**, đề xuất `codex/reviewer-experiments`. Khi thực thi kiểm branch/PR hiện hành trước: nếu đã có branch/PR dành cho chính vòng revise này thì dùng lại, không tạo thứ hai. Ghi base SHA và giữ dirty files; không reset/clean, không commit thẳng main, không tạo branch riêng mỗi REV.
2. **Chưa commit trước hoặc trong lúc chạy thí nghiệm.** Để bảo đảm tái lập khi source chưa commit, đóng immutable source snapshot trước compute, lưu base commit + content hash/config/input refs. Snapshot phải chứa cả untracked files thực sự chạy, không chỉ Git SHA.
3. Mỗi completed run/checkpoint đóng payload rồi gọi/enqueue sync ngay. Dùng `.env`/HF_TOKEN hiện có; namespace xác nhận bằng quyền token, không hard-code account của token từ tên old repos. Old repos là nguồn read-only; new uploads vào project destination có quyền, `sync.private: false` theo project policy. Rollover theo policy hiện có, không tạo repo để né quota.
4. Kiểm payload/parts/revision/digests/marker/catalog và ghi `sync.json`. `COMPUTE_DONE` + `SYNC_PENDING` chưa phải đã bàn giao; retry sync đúng payload, không rerun compute chỉ vì upload lỗi. Giữ local artifacts sau verified. Source/metrics mới phải nằm trong whitelist, không chỉ tồn tại trên disk.
5. Sau **toàn bộ thí nghiệm đã chọn cho vòng revise** và analyses/benchmarks hoàn tất hợp lệ, review tất cả P2 status và missing evidence. Chỉ khi đủ required cells + tests + remote verification mới chốt kết quả; optional infeasible phải được báo rõ, không tick compute. Không dùng deadline làm lý do bỏ P0/P1 hoặc gọi một run chưa chạy là hoàn tất.
6. Cập nhật root checklist, results tables/response mapping và tài liệu phương pháp; kiểm no secrets/large caches trong diff. **Lúc này mới commit code/config/tests/docs/results summary**, trên chính branch đó. Source payload của commit phải khớp frozen tested source dùng trong runs; thay đổi khoa học sau run cần revision/rerun trước commit. Docs bàn giao cuối có thể thêm receipts/PR link mà không đổi scientific source.
7. Push branch, **tạo đúng một PR** về main (hoặc cập nhật PR cùng branch đã có). PR nêu problem/change, validation, actual cell counts, negative/inconclusive findings, P2 pending, HF pinned links và source snapshot hashes. Không auto-merge. Nếu cần sửa review thì tiếp tục commit vào cùng branch và cập nhật cùng PR, sau khi checks/affected experiments xong.

Vòng revise hiện đã **đóng phần experiments + HF verification**: protocol `reviewer_v1` có `165/165` cells completed; catalog audit pinned có `104/104` markers verified; REV-07 marker/parts đã reconcile; E5 degree-m29 đủ sáu graph checkpoints và representative load PASS; REV-04 E5 có `12/12` snapshot cells/`1,080,000` per-query rows; REV-08 có `960,000` held-out contrast rows trên map seeds `17/29/43`; aggregate v6 và Q1–Q7 status nằm trong [`reviewer/results/REV-11-final-audit.json`](../reviewer/results/REV-11-final-audit.json). REV.10 còn 5 dòng manuscript-only cố ý để sau theo scope hiện tại. Git delivery vẫn là bước còn lại.

## 10. Đối chiếu đầy đủ với PDF reviewer

Đối chiếu trên **PDF duy nhất, đủ 5 trang**, theo SHA256 ở mục 1. `CÓ PLAN` nghĩa là protocol/công việc và gate đã được viết; chưa chứng nhận đã implement, compute hoặc sync. P2 và các nhánh “nếu khả thi” vẫn nằm trong kế hoạch; chỉ được ghi thiếu điều kiện bằng evidence cụ thể. Gói minimum/strong response ở trang 4–5 là cách ưu tiên lại cùng các mục dưới, không phải thí nghiệm thứ mười.

### 10.1. Toàn bộ 9 yêu cầu chạy/đo — PDF mục 2

| # | Yêu cầu PDF / trang / câu hỏi | Nơi xử lý | Kiểm đầy đủ trước khi đóng yêu cầu |
|---|---|---|---|
| 1 | Matched query-side/conversion baseline — tr.1, Q1 | REV-01; checklist `REV.01.*` | CÓ PLAN: 18 query-side/forward controls, cùng paid/train/val IDs; relevance + agreement + latency/cost/access; feasibility converter/QDC riêng |
| 2 | Component ablation — tr.1, Q4 | REV-02; `REV.02.*` | CÓ PLAN: sáu variants tách learned global/regional/calibration, cùng paid union/random prefix; cả relevance/agreement, trọng tâm 10% |
| 3 | Coverage-greedy sensitivity — tr.1–2, Q2 | REV-03; `REV.03.*` | CÓ PLAN: 0.5ρ/ρ/2ρ × safety on/off ×3 seeds; activity/fallback; tối đa một proxy có feasibility gate |
| 4 | Rank-sensitive agreement — tr.2, Q5 | REV-04; `REV.04.*` | CÓ PLAN: RBO đáp ứng lựa chọn “RBO hoặc Kendall”; Overlap@1/@3/@20 ngoài @10; depth20 phải search thực, E5 có per-query outputs |
| 5 | TREC-COVID multiple seeds — tr.2 | REV-05; `REV.05.*` | CÓ PLAN: OP/LA/MLP × random ×3 map/backfill tuples, mean/std/range và CI; không đếm fallback alias như policy mới |
| 6 | Compute/storage overhead — tr.2, Q7 | REV-06; `REV.06.*` | CÓ PLAN: calibration/regional refit wall/batch, RAM/VRAM, artifact/storage bytes; đối chiếu live target encoding và migration/backfill, ba measured repeats |
| 7 | Cross-transition generalization — tr.2 | REV-07; `REV.07.*` | CÓ PLAN: hai additional transition scopes trên cùng FiQA648/query split/checkpoints/metrics; smoke/forecast và evidence nếu thiếu resource |
| 8 | MS MARCO/ORCAS unseen queries — tr.2 | REV-08; `REV.08.*` | CÓ PLAN: normalized-text-disjoint held-out, cùng 50k corpus; read vs random/degree trên cùng 12 trajectories, per-query agreement/CI và coverage |
| 9 | AOL temporal relevance proxy — tr.2, Q6 | REV-09; `REV.09.*` | CÓ PLAN CÓ ĐIỀU KIỆN: audit clicks/joins/cutoffs; proxy có denominators/coverage/user blocks hoặc ghi thiếu signal, không suy user utility |

Không ép metric relevance có nhãn vào ORCAS nếu chỉ có graph clicks; FiQA/TREC và REV-01–03/07 báo judged relevance cùng agreement, ORCAS giữ agreement, AOL chỉ có click-derived proxy khi đủ tín hiệu. Mọi bảng ghi rõ loại nhãn và population; không tạo thêm labels hoặc mở corpus để làm đầy bảng.

### 10.2. Toàn bộ 11 wording/clarification — PDF mục 3

| # | Yêu cầu PDF / trang | Nơi xử lý trong REV-10 / checklist | Evidence/nội dung cần gắn vào manuscript khi thực thi |
|---|---|---|---|
| 1 | Rename ARR@10 — tr.2–3 | `REV.10.rename` | Overlap@10 xuyên suốt abstract/method/results/figures; legacy alias một lần |
| 2 | Exact degree construction — tr.3, Q3 | `REV.10.degree` | Formal graph/node/edge source, distinct neighbors, duplicate/tie và recompute rule đúng code |
| 3 | Read-prioritized construction — tr.3 | `REV.10.read` | Workload/window/group duplicates, traversal/tie/cursor, fixed hoặc temporal refresh; không tự gọi read count nếu code không dùng |
| 4 | Matched-budget definition — tr.3 | `REV.10.budget` | Unique bootstrap/train/val/cal/backfill union, train-pool size và actual access của từng baseline |
| 5 | 50k pools + sparse judgments — tr.3 | `REV.10.corpus` | Supporting stress scope/coverage, full FiQA/TREC anchors, limitation về absolute relevance/generalization |
| 6 | Model-pair generalization — tr.3 | `REV.10.models` | Main pair primary, các transition khác supporting; chỉ evaluated settings |
| 7 | AOL agreement-only scope — tr.3 | `REV.10.aol` | Operational replay, click proxy có điều kiện, không agreement→relevance/user utility |
| 8 | Drift-Adapter/QDC/Embedding-Converter positioning — tr.3 | `REV.10.related` | Taxonomy query-side/forward conversion/gradual true replacement; protocol deviations và trade-offs |
| 9 | Procrustes/alignment theory — tr.3 | `REV.10.theory` | Điều kiện orthogonal/local/nonlinear; không biến bound bên ngoài thành guarantee mixed-index |
| 10 | Coverage-greedy failure — tr.4 | `REV.10.greedy` | Empirical radius, positive-gain/fallback counts, collapse-to-random và giới hạn claim |
| 11 | Temper causal language — tr.4 | `REV.10.causal` | Kết luận dựa trên contrasts ablation đã chạy; không gán nguyên nhân từ correlation |

### 10.3. Exclusion và bốn mục NO ACTION — PDF mục 4

| Mục PDF / trang 4 | Disposition | Kiểm khi bàn giao |
|---|---|---|
| Mở rộng corpus >50k | **EXCLUDED** | Không có job/pool expansion mới; full anchors sẵn có giữ nguyên |
| FiQA multi-seed + bootstrap CI | **NO ACTION** | Giữ evidence cũ; các variants reviewer mới vẫn cần repeats riêng |
| HNSW fidelity vs exact target | **NO ACTION** | Giữ separation; top20 re-evaluation không tự thành yêu cầu rerun E3 |
| Agreement tăng nhưng relevance giảm | **NO ACTION** | Giữ core finding và các giới hạn thống kê; không sửa outcome để đạt kỳ vọng |
| Policy activity instrumentation | **NO ACTION** | Giữ instrumentation; dùng counts trong sensitivity, không dựng study instrumentation riêng |

### 10.4. Kiểm trực tiếp đủ Q1–Q7 — PDF mục 6, trang 5

| Question | Task và checkbox phải có evidence khi thực thi |
|---|---|
| Q1 — Matched query-side adapter | REV-01; `REV.01.compute`, `REV.01.sync`, `REV.10.budget` |
| Q2 — rho/safety/uncertainty | REV-03; `REV.03.compute`, `REV.03.proxy`, `REV.03.sync`, `REV.10.greedy` |
| Q3 — Exact degree construction | REV-10; `REV.10.degree` |
| Q4 — Global/regional/calibration ablation | REV-02; `REV.02.compute`, `REV.02.sync`, `REV.10.causal` |
| Q5 — RBO/Kendall/overlap@k | REV-04; `REV.04.depth10`, `REV.04.depth20`, `REV.04.E5`, `REV.04.sync`, `REV.10.rename` |
| Q6 — AOL relevance proxy | REV-09; `REV.09.feasibility`, `REV.09.compute`, `REV.09.sync`, `REV.10.aol`; blocked vẫn chưa compute |
| Q7 — Compute/storage cost | REV-06; `REV.06.compute`, `REV.06.sync` |

**Kết luận kiểm độ phủ:** không thiếu nhóm thí nghiệm nào trong PDF sau khi loại corpus expansion. Phần còn thiếu là implementation, official measurements, verified sync và final response/manuscript evidence. Khi aggregate phải đi lại bảng này theo artifacts thực, ghi `completed/reused/blocked/deferred/excluded/no-action` cho từng yêu cầu và link run/receipt; không dùng trạng thái PLAN_READY để tick kết quả.
