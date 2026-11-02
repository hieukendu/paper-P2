# Kết quả thí nghiệm chính và bổ sung theo reviewer

Ngày đối chiếu: **02/11/2026, Asia/Saigon**. Tài liệu này là mục lục kết quả đã có trong `result/` và phần reviewer supplemental đã được đối chiếu từ các artifact HF pinned. Không sao chép graph/weight nhị phân lớn vào Git; payload đầy đủ vẫn ở các HF revisions được liên kết bên dưới.

## Thí nghiệm chính

Các kết quả chính đã nằm trong các tài liệu hiện hữu:

| Nhóm | Kết quả | Tài liệu |
|---|---|---|
| E0/E1 | Input/model gates, budget, resume và exact-completion checks | [02_E0_E1.md](02_E0_E1.md) |
| E2 | 24 FiQA/TREC mapping và scheduler configurations, curves, relevance/agreement | [03_E2.md](03_E2.md) |
| E3/E4 | HNSW fidelity, same-ID update, footprint và 50k probes | [04_E3_E4.md](04_E3_E4.md) |
| E5 | 12 MS MARCO/ORCAS workload configurations và cost tables | [05_E5.md](05_E5.md) |
| E6 | AOL temporal replay, four policies và realized budget | [06_E6.md](06_E6.md) |
| E7 | 20 dataset/model transition configurations | [07_E7.md](07_E7.md) |
| Statistics | Paired contrasts, bootstrap/Holm và consistency checks | [08_statistics.md](08_statistics.md) |
| Full inventory | 166 recorded bundles và source/coverage index | [09_all_recorded_results.md](09_all_recorded_results.md), [10_sources_and_coverage.md](10_sources_and_coverage.md) |

Các kết quả lịch sử giữ nguyên schema `arr_at_10` trong inventory để bảo toàn provenance; manuscript hiện dùng tên **Overlap@10**.

## Reviewer supplemental matrix

`reviewer_v1` có **165/165 cells completed**. Counts dưới đây là số cell protocol, gồm cả cell reused/post-hoc; chúng không biến checkpoint thành seed mới.

| Nhóm | Cells | Nội dung đã có |
|---|---:|---|
| REV-01 | 19 | Query-side/forward matched controls, 3 seeds và feasibility negative evidence |
| REV-02 | 18 | Sáu component variants × 3 seeds, fixed-projection retry |
| REV-03 | 21 | 18 rho/safety sensitivity cells + 3 uncertainty-proxy cells |
| REV-04 | 19 | Depth-10/depth-20 metrics và E5 post-hoc replay |
| REV-05 | 9 | OP/LA/residual-MLP × 3 TREC seed tuples |
| REV-06 | 1 | FiQA cost/storage/live-encode sample benchmark |
| REV-07 | 27 | Transition feasibility, 24 transition cells và identity controls |
| REV-08 | 50 | ORCAS held-out trajectories, seen/held-out metrics và contrasts |
| REV-09 | 1 | AOL click-derived temporal proxy |
| **Tổng** | **165** | **Không còn supplemental compute cell chưa hoàn thành** |

## Final artifact checks

- Catalog `mixindex-runs-001` pinned audit: **104/104 markers verified**, không có unverified run.
- `REV-AGGREGATE-fiqa-v6`: 167,184 raw rows, 336 descriptive rows, 273 contrasts, 10,000 paired bootstrap draws, Holm correction, `performance_claim=false`; [pinned HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/90f4410b919149883b0285d5ea32ed58f5d9bd74/runs/REV-AGGREGATE-fiqa-v6/2c29c49125a4d005f440bb3d7038fc4e02fe54684a20f81074e0cdb4533686b6).
- `REV-04-e5-posthoc`: **12/12 snapshot cells**, 1,080,000 per-query rows, không còn missing cell; [pinned HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/e2a82994cc4267265e175687de5001f70143ca95/runs/REV-04-e5-posthoc/7a2161e8b76fd6019c0d866cea089ce41ee6265059bd2eb7d3a15ca971862014).
- `REV-08-heldout-e5`: 960,000 contrasts cho `read_minus_random` và `read_minus_degree`, map seeds 17/29/43; [pinned HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/ff52cc31a9e41f31abc2ca5a2ddd7c3ea3fd86b0/runs/REV-08-heldout-e5/27e2c03d161511b99268ca4fe273a22e7c599aa140a912a67a30299a2ba315b7).
- REV-07 representative `M0.safetensors` load: **PASS**; [reconciled HF payload](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/cf7580f234c61379b189873f28a0c6b0df20448c/runs/REV-07-bge-fiqa-op-read-m17-t101/c78ada8464624d2aa79875e042ff01bc4a9ad2e0d7d7d45d69d49645ed66a778).
- E5 degree-m29 marker split: six HNSW graph checkpoints in pinned `mixindex-runs-004`, representative graph load **PASS**.
- Machine-readable audit: [12_reviewer_final_audit.json](12_reviewer_final_audit.json).

Corpus expansion beyond the frozen 50k supplemental scope remains excluded. AOL and sampled cost findings retain their proxy/sample limitations; no aggregate is presented as a universal performance claim.
