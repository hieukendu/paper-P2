# M15 — Ma trận run compact cho E2–E7

Đây là **policy mặc định để giảm số run**, áp dụng trước khi tạo `TaskSpec`. Mục tiêu là giữ các câu hỏi khoa học chính và các gate correctness/scale, nhưng không chạy toàn bộ factorial matrix của bản paper. Mọi số dưới đây là số **independent run cells**; checkpoint bootstrap, 5%, 10%, 25%, 50% accessed và 100% true nằm trong cùng một run, không tính thành run mới.

## Quy tắc chung

- E0, E1 và T0 vẫn giữ nguyên vì chúng là gate correctness, chọn profile và đo khả năng chạy; không được bỏ để tiết kiệm run.
- Một cell phải giữ nguyên dataset manifest, split, encoder revision, budget, evaluator và profile đã freeze. Không được giảm run bằng cách đổi protocol giữa các cell.
- `cached_access` dùng cho quality cells; `live_encode` chỉ chạy ở cost/timing probes đã chỉ định. Không nhân mỗi quality cell thành một bản live-encode riêng.
- Các seed bị bỏ khỏi compact matrix không được dùng ngầm. Nếu chạy thêm, phải ghi `optional_sensitivity` và không nhập vào primary aggregate.
- Các kết quả compact không được mô tả như full seed-grid replication của paper gốc. Bảng aggregate phải ghi rõ `compact_v1`.

## Ma trận mặc định

| Stage | Cell/task bắt buộc | Cách expand | Mục tiêu và giới hạn kết luận |
|---|---:|---|---|
| E2 | **24 cells** | FiQA mapping: OP/LA/MLP × map seeds `{17,29,43}` với random = 9. FiQA scheduler: MLP × `{random, degree, re-embed-on-read, greedy}` × 3 map seeds, traffic `101` = 12. TREC-COVID mapping: OP/LA/MLP × map seed `17`, scheduler N/A = 3. | Pilot quality và kiểm tra xu hướng. Không claim interaction đầy đủ map×scheduler, không suy luận mạnh từ TREC 50 queries. Calibration/regional ablation chạy trong T0 hoặc một diagnostic riêng, không nhân vào 24 cell. |
| E3 | **6 tasks** | Exact reference = 1; HNSW fixed snapshot = 1; cadence `{1%,5%,10%}` = 3; synchronized serving/failed-update save-load probe = 1. | Systems/fidelity gate. Không phải scheduler-quality study. |
| E4 | **3 tasks** | One 50k-document common-manifest probe với greedy; one actual reduced-pool bootstrap stored-graph gate; one checkpoint/restore and footprint probe. Scheduler timing của random/degree/read/greedy đã nằm trong T0.scale, không lặp lại ngoài probe cần thiết của E4. | Readiness gate cho E5. Không gọi reduced pool là full quality result. |
| E5 | **12 primary cells** | Full MS MARCO + Arctic + ORCAS: schedulers `{random, degree, re-embed-on-read, greedy}` × map seeds `{17,29,43}` × traffic seed `101`. Mỗi cell tiếp tục đến các checkpoint bắt buộc trong cùng run. | Primary static result tại 10% accessed. Có map-seed robustness; traffic-seed robustness chỉ là sensitivity. |
| E5-sensitivity | **tối đa 4 optional cells** | Chỉ `random` và `greedy`, map seed `17`, traffic seeds `{103,109}`. Chỉ chạy khi 12 primary cells đã hợp lệ và thời gian còn đủ. | Không bắt buộc để tick E5; báo riêng, không dùng để chọn lại method/profile. |
| E6 | **4 cells** | Một timeline AOL-IA đã khôi phục, map seed `17`, bốn scheduler `{random, degree, re-embed-on-read, greedy}`. Mỗi cell chạy đủ 7 quyết định tuần. | Temporal case trên một chronology thật. Không tạo traffic seeds giả bằng cách shuffle thời gian; nếu recovery thiếu thì BLOCKED_DATA. |
| E7 | **20 cells** | Tám case đại diện: MiniLM/MPNet trên FiQA và TREC-COVID; Arctic trên NQ và HotpotQA; Nomic trên FEVER và FiQA; BGE trên NQ và FEVER. Mỗi case chạy MLP với `{random, greedy}` = 16 cells. Thêm OP với `greedy` trên bốn case cross-check cố định `{fiqa/minilm_mpnet, nq/arctic, fever/nomic, fever/bge}` = 4 cells. Một map seed `17`, traffic seed `101`; scheduler N/A nếu case không có split hợp lệ. | Representative generalization pilot, không còn claim đủ 20 dataset×model cases hoặc đủ seed-grid. Các FiQA/TREC cells chỉ reuse E2 khi toàn bộ hash khớp. |

Tổng mặc định là **69 required cells/tasks**, cộng tối đa 4 E5 sensitivity cells. E7 có thể chỉ tạo thêm các cell chưa được reuse từ E2; reuse phải trỏ tới source run bằng content hash và không được đếm lại như một run compute mới.

## Thứ tự chạy và stop rule

1. Chạy E2 mapping 9 FiQA cells trước. Nếu correctness, budget hoặc evaluator fail thì dừng branch và sửa code; không mở scheduler matrix.
2. Chạy E2 scheduler 12 cells, sau đó TREC 3 cells. Kết quả âm hoặc inconclusive vẫn là kết quả hợp lệ.
3. Chạy E3 sáu systems tasks và chỉ mở E4 khi ANN/fidelity gate đạt. Exact branch được giữ nếu ANN fail.
4. Base `compact_v1` chạy E4 ba tasks và mở E5 sau full-bootstrap graph, footprint và Q_tune profile pass. Với `e4e567_scale_v3_50k`, E4 cũng chạy trên common manifest 50k/5k và phải được verified trước khi mở E5-E7.
5. Chạy 12 E5 primary cells trước. E5-sensitivity chỉ được enqueue sau khi primary cells đã có artifact hợp lệ; không chạy để cứu một kết quả âm.
6. E6 và E7 có thể chạy xen kẽ khi đúng-case T0 và dữ liệu đã sẵn sàng. Không mở thêm model/dataset chỉ vì một compact cell có kết quả tốt.

## Thay đổi về diễn giải thống kê

- E2, E3, E4 và E7 compact là pilot/diagnostic hoặc representative evidence; báo từng cell, effect và dispersion, không gọi là replication đầy đủ.
- E5 dùng paired query bootstrap và sign-flip như protocol chung, nhưng seed robustness chỉ có ba map seeds trong primary; traffic sensitivity phải ghi là giới hạn của compact design.
- Không dùng Holm correction để tạo ảo giác rằng compact matrix có cùng power với full 3×5 grid. Nếu số contrast vẫn giữ ba scheduler contrasts, ghi rõ đây là exploratory compact analysis.
- Không được dùng compact result để loại dataset/model, thay hyperparameter hoặc sửa primary endpoint. Mọi mở rộng sau compact phải có variant ID mới.

## Output và checklist

`summary.json` phải ghi `run_budget_policy: compact_v1`, stage, cell role (`required` hoặc `optional_sensitivity`) và source run nếu reuse. `checklist.md` chỉ tick E-stage khi đủ required cells/tasks của bảng trên; optional sensitivity không chặn hoàn tất stage.

## Scale override đã khóa cho server: E5-E7

Khi chạy server theo yêu cầu downscale, dùng [16_e567_downscale.md](16_e567_downscale.md) với `scale_variant: e4e567_scale_v3_50k`. Đây là override cho E4, E5, E6 và E7; không thay đổi số cell của M15.

- E4 dùng exact common 50k/5k manifest và tạo artifact/profile/hash mới; E5-E7 admission phải chờ parent E4 đạt gate thật.
- E5 giữ 12 cell nhưng dùng MS MARCO child manifest uniform 50k và ORCAS manifest tối đa 5k groups từ T0.scale/E4 IDs; checkpoint vẫn bootstrap/5/10/25/50/100% trong cùng run.
- E6 giữ 4 cell, chronology 8 tuần và 7 quyết định; dùng document cap 50k và event cap 50k/tuần, chỉ khi AOL-IA thật đã recovered.
- E7 giữ 20 cell; NQ/HotpotQA/FEVER dùng 50k documents và 500 queries/case; FiQA/TREC-COVID chỉ reuse exact validated scope khi hash khớp.
- Mọi summary E4-E7 phải ghi `run_budget_policy: compact_v1`, `scale_variant: e4e567_scale_v3_50k`, `official_doc_pool: 50000`, `orcas_group_cap: 5000`, common manifest hash và E4 artifact/hash (E5-E7 ghi thêm parent fields).

Kết quả variant này là reduced-scale pilot evidence. Không trộn aggregate với full-scale result và không diễn giải là full-corpus replication.
