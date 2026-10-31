# Dữ liệu và phạm vi đánh giá

Một kho dữ liệu có toàn corpus không có nghĩa mọi thí nghiệm đã dùng toàn corpus đó.

| Dữ liệu | Tài liệu trong release | Nhóm query hoặc dòng log | Eval groups | Schedule groups | Phạm vi đánh giá hiện có |
|---|---|---|---|---|---|
| aol-ia | 50000 | 400000 | N/A | N/A | 50.000 tài liệu; 400.000 dòng log |
| fever | 5416568 | 115351 | 6577 | 81810 | 50.000/trường hợp |
| fiqa | 57638 | 6648 | 648 | 4400 | 57.638; toàn corpus |
| hotpotqa | 5233329 | 97844 | 7405 | 67993 | 50.000 |
| msmarco-docs-v1 | 3213835 | 5193 | 5193 | 0 | 50.000 |
| nq | 2681468 | 3452 | 3452 | 0 | 50.000/trường hợp |
| orcas | 3213835 | 10404672 | 10000 | 5200800 | 5.000 nhóm scheduling |
| trec-covid | 171332 | 50 | 50 | 0 | 171.332; toàn corpus |


FiQA có 648 query test, 500 tune, 4.400 scheduling, 550 cal-fit và 550 cal-check. TREC-COVID có 50 test query và không có tập truy vấn phát triển/lập lịch độc lập; NQ tương tự không có schedule trong release hiện tại. FEVER có 6.577 nhóm test sau gộp văn bản, khác 6.666 query ID nguồn.

MS MARCO dùng **document ranking v1**, không phải passage ranking. ORCAS là đồ thị query–document tĩnh; mọi nhóm query có trọng số bằng nhau trong E5. Số cạnh không phải số lượt click hay tần suất thời gian. Có 10.000 nhóm ORCAS được phân vai held-out trong release, nhưng runner E5 không đánh giá chúng.

Các corpus lớn ở E7 được chọn nền đều theo hash trước đánh giá, không chọn riêng tài liệu relevant. Vì thế chỉ 4–14/500 query có positive qrel còn trong pool. Không dùng nDCG đã tính trên những pool này làm số BEIR chuẩn; bảng chính của chúng chỉ báo ARR kèm phạm vi reduced corpus. NQ có các query mẫu khác nhau giữa Arctic và BGE; FEVER cũng khác query mẫu giữa Nomic và BGE. So model trên những hàng này không phải thí nghiệm thay duy nhất encoder.

AOL công khai chỉ có metadata đã bỏ văn bản, qrels và dòng log; không có văn bản query hay recovered documents để chạy lại encoder độc lập. Đã đọc toàn bộ 400.000 dòng metadata, không xuất user/group IDs hay query text vào tài liệu này. Khoảng chọn thực tế là 01/03–25/04/2006; ngày 31/05 trong manifest là cuối nguồn gốc, không phải cuối replay tám tuần.

Nguồn dữ liệu/phương pháp: [BEIR](https://arxiv.org/abs/2104.08663), [MS MARCO](https://microsoft.github.io/msmarco/Datasets.html), [ORCAS](https://microsoft.github.io/msmarco/ORCAS), [AOL-IA](https://ir-datasets.com/aol-ia.html). Số release dưới đây được đọc từ các kho dự án, không suy từ registry gốc.

## aol-ia


| Đại lượng trong release | Giá trị |
|---|---|
| clicked_doc_pool_coverage | 0.041394 |
| clicked_docs_in_pool | 8971 |
| clicked_events | 216723 |
| documents | 50000 |
| end_date | 2006-05-31 |
| recovered_documents | 74958 |
| recovery_candidate_documents | 75000 |
| recovery_unavailable_documents | 4 |
| selected_events | 400000 |
| selected_events_by_week | {"0": 50000, "1": 50000, "2": 50000, "3": 50000, "4": 50000, "5": 50000, "6": 50000, "7": 50000} |
| source_events | 36389567 |
| source_events_by_week | {"0": 3287451, "1": 3226862, "2": 3221340, "3": 3195994, "4": 2862778, "5": 2525902, "6": 2037733, "7": 2284932} |
| source_users | 657427 |
| start_date | 2006-03-01 |
| weeks | 8 |


## fever


| Đại lượng trong release | Giá trị |
|---|---|
| documents | 5416568 |
| duplicate_documents | 0 |
| duplicate_qrels | 0 |
| empty_documents | 0 |
| query_groups | 115351 |
| query_ids | 123142 |
| raw_documents | 5416568 |
| raw_queries | 123142 |
| role_groups | {"cal_check": 10227, "cal_fit": 10226, "eval": 6577, "schedule": 81810, "tune": 6511} |
| split_queries | {"dev": 6666, "test": 6666, "train": 109810} |
| test_qrels | 7937 |
| test_queries | 6666 |


## fiqa


| Đại lượng trong release | Giá trị |
|---|---|
| documents | 57638 |
| duplicate_documents | 0 |
| duplicate_qrels | 0 |
| empty_documents | 38 |
| query_groups | 6648 |
| query_ids | 6648 |
| raw_documents | 57638 |
| raw_queries | 6648 |
| role_groups | {"cal_check": 550, "cal_fit": 550, "eval": 648, "schedule": 4400, "tune": 500} |
| split_queries | {"dev": 500, "test": 648, "train": 5500} |
| test_qrels | 1706 |
| test_queries | 648 |


## hotpotqa


| Đại lượng trong release | Giá trị |
|---|---|
| documents | 5233329 |
| duplicate_documents | 0 |
| duplicate_qrels | 0 |
| empty_documents | 0 |
| query_groups | 97844 |
| query_ids | 97852 |
| raw_documents | 5233329 |
| raw_queries | 97852 |
| role_groups | {"cal_check": 8500, "cal_fit": 8499, "eval": 7405, "schedule": 67993, "tune": 5447} |
| split_queries | {"dev": 5447, "test": 7405, "train": 85000} |
| test_qrels | 14810 |
| test_queries | 7405 |


## msmarco-docs-v1


| Đại lượng trong release | Giá trị |
|---|---|
| documents | 3213835 |
| duplicate_documents | 0 |
| duplicate_qrels | 0 |
| empty_documents | 239 |
| judged_dev_qrels | 5193 |
| judged_dev_queries | 5193 |
| query_groups | 5193 |
| query_ids | 5193 |
| raw_documents | 3213835 |
| raw_queries | 5193 |
| role_groups | {"cal_check": 0, "cal_fit": 0, "eval": 5193, "schedule": 0, "tune": 0} |
| split_queries | {"dev": 5193} |
| test_qrels | 5193 |
| test_queries | 5193 |


## nq


| Đại lượng trong release | Giá trị |
|---|---|
| documents | 2681468 |
| duplicate_documents | 0 |
| duplicate_qrels | 0 |
| empty_documents | 0 |
| query_groups | 3452 |
| query_ids | 3452 |
| raw_documents | 2681468 |
| raw_queries | 3452 |
| role_groups | {"cal_check": 0, "cal_fit": 0, "eval": 3452, "schedule": 0, "tune": 0} |
| split_queries | {"test": 3452} |
| test_qrels | 4201 |
| test_queries | 3452 |


## orcas


| Đại lượng trong release | Giá trị |
|---|---|
| documents | 3213835 |
| documents_ref | ../msmarco-docs-v1 |
| duplicate_edges | 270 |
| eligible_groups | 10404672 |
| empty_query_records | 11 |
| excluded_dev_groups | 598 |
| missing_documents | 0 |
| query_groups | 10404672 |
| raw_records | 18823602 |
| records | 18823602 |
| role_groups | {"cal_check": 512, "cal_fit": 512, "eval": 10000, "schedule": 5200800, "tune": 512} |
| source_query_ids | 10405342 |
| unique_edges | 18821730 |


## trec-covid


| Đại lượng trong release | Giá trị |
|---|---|
| documents | 171332 |
| duplicate_documents | 0 |
| duplicate_qrels | 0 |
| empty_documents | 1 |
| query_groups | 50 |
| query_ids | 50 |
| raw_documents | 171332 |
| raw_queries | 50 |
| role_groups | {"cal_check": 0, "cal_fit": 0, "eval": 50, "schedule": 0, "tune": 0} |
| split_queries | {"test": 50} |
| test_qrels | 66336 |
| test_queries | 50 |
