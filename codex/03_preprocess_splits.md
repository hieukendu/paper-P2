# M03 — Preprocess, validation và split chống leakage

Code `data/store.py`, `prepare.py`, `splits.py`. Output `PreparedData`/`SplitBundle` dùng trực tiếp cho M04/M05; raw nguồn không sửa.

## Text, ID và storage

- Corpus text: `title + '\n' + body` nếu title khác rỗng, ngược lại chỉ body; BEIR `text` là body. Không thêm URL, lowercase, stem hoặc chunk. Một vector/document.
- Giữ ID string gốc và row int64 theo source ingestion order ổn định. Text encode không NFKC; normalized query chỉ dùng grouping/splits.
- BEIR parse JSONL `_id,title,text`, query `_id,text`, qrels TSV đúng header. MS MARCO docs parse tối đa4 fields `docid,url,title,body`, giữ body nếu có tab; query2 fields; qrels TREC4 columns. ORCAS4 fields như M02.
- Duplicate ID cùng nội dung: count rồi canonical một record; ID cùng tên nhưng nội dung khác hoặc qrel conflicting grade thì fail ingest, không chọn ngẫu nhiên. Duplicate qrel/edge giống hệt collapse và count. Qrels phải join vào query/doc IDs; missing không âm thầm bỏ.
- Empty text vẫn giữ ID, count và encode theo tokenizer đã khóa; invalid record không được làm shift vector-row alignment. Corpus count và filtered count tách rõ.
- Stream JSONL/TSV thành `documents.jsonl`, Parquet row groups và stdlib SQLite lookup; tránh pandas toàn corpus. `lookup.sqlite` index doc_id→row/byte_offset và query grouping cho ORCAS lớn; không biến SQLite thành database kết quả.

## Hàm cần implement

| Hàm | Logic cần code |
|---|---|
| `iter_source_documents(spec, files)` | Adapter trả `(doc_id,title,body)` streaming |
| `document_text(title, body) -> str` | Một policy ghép text cho mọi encoder |
| `build_document_store(records, output) -> DocumentStore` | Ghi normalized JSONL + offsets + row-ID mapping; atomic publish khi ingest/count check xong |
| `get_documents(rows) -> list[Document]` | Lookup offsets, đọc đúng text/ID; trả theo thứ tự rows caller |
| `normalize_query(text) -> str` | `NFKC -> casefold -> whitespace collapse -> strip`; không stem/bỏ dấu câu |
| `group_queries(records) -> path` | Group theo normalized string, stable group_id=SHA256(UTF8 string); giữ raw representative có source ID nhỏ nhất lexicographic; ID/text conflict fail |
| `join_edges(edges, doc_lookup, query_groups) -> path` | ORCAS edge tới row và group; count missing docs, dedup source/normalized edges; không diễn giải edge count là event frequency |
| `build_static_splits(data, seed) -> SplitBundle` | Rules bên dưới, không nhìn relevance score/test results |
| `sample_document_pools(N, cfg) -> SplitBundle` | Chọn train/val uniform; để cal pools pending trước khi OP proposal được fit |
| `finalize_calibration_pools(splits, proposal_pairs, caps) -> SplitBundle` | Nhận OP candidate IDs từ bootstrap, enforce disjoint/caps, freeze cal IDs; data module không tự load/fit map |
| `build_temporal_splits(events, cfg) -> SplitBundle` | Timeline8 tuần từ ngày hợp lệ sớm nhất, time boundary chính xác |
| `validate_prepared(data, splits) -> dict` | Full ID joins, split disjointness, counts, coverage và dates |

## Static query splits

Master seed **20261020**. Stable sampling dùng SHA256(seed+purpose+group_id) hoặc seeded sample trên sorted IDs; lưu IDs một lần để rerun không phụ thuộc filesystem/Python hash.

- FiQA: ưu tiên giữ test rồi dev rồi train khi loại text overlap. Official train groups chia80/10/10 scheduling/cal-fit/cal-check; dev làm Q_tune; test chỉ evaluator. Thiếu dev thì reserve10% train làm tune trước, phần còn lại chia80/10/10. Qrels test không vào scheduler.
- TREC-COVID primary: không có independent train/dev → mapping + random, calibration tắt, greedy N/A. Không chế query từ test. Search settings kế thừa FiQA cùng model pair hoặc fixed L100/ef200 label UNTUNED_TRANSFER.
- BEIR E7: kiểm từng release có train/dev thật. Có thì áp policy tương tự, thiếu thì mapping/random, greedy N/A. Pseudoquery/auxiliary là nhánh bổ sung có nguồn và label, không lấp số thiếu của primary.
- ORCAS: bỏ normalized overlap với toàn judged MS MARCO dev trước; chia50/50 theo normalized groups bằng master seed. Scheduling half reserve512 groups mỗi cal-fit/cal-check/Q_tune; phần còn lại chọn uniform tối đa100k groups theo traffic seed. Held-out half lấy uniform tối đa10k fixed groups cho ARR. Source query IDs khác nhau nhưng normalized text trùng phải cùng group.
- ORCAS `w_q=1` cho mỗi unique query group. Degree baseline đếm số query neighbors trong đúng scheduling sample; không dùng held-out edges hoặc source record count làm traffic frequency. Shared document qua hai half là hợp lệ; không gọi đây là unseen-document test.

## Document pools và calibration proposals

```text
n_train = min(10000, ceil(.02*N))
n_val = min(2000, ceil(.005*N))
cap_cal_fit = cap_cal_check = min(1000, ceil(.005*N))
batch_cap = ceil(.01*N)
```

Train/val/cal-fit/cal-check document pools đôi một disjoint. Sample train/val uniform không dùng qrels. Fit **một OP proposal chung** từ train paid pairs; rank đúng calibration query groups, ưu tiên raw ranks6–20, tối đa4 pairs/query và1,000 pairs/pool; cấp quyền new embedding tới unique-doc cap. Thiếu dữ liệu giữ thực tế, không đọc oracle để fill. Cal-fit và cal-check không chung query group/document; khóa pair IDs chung cho map variants và seed cells. Calibration-off vẫn được cùng bootstrap true docs để so công bằng.

FiQA theo N chuẩn: train1,153/val289/cal mỗi pool≤289, tổng≤2,020 (~3.505%); TREC train3,427/val857, cal off; MS MARCO train10k/val2k/cal mỗi pool≤1k, tổng≤14k (~0.436%). Recompute từ N file thật sau validation. Mọi paid pool phục vụ true ngay bootstrap; val/cal **không trở thành map-training pairs**.

## AOL temporal

Mỗi qlog entry là **một query event** dù items chứa nhiều clicks. Thời gian khởi đầu00:00 ngày hợp lệ sớm nhất theo source timezone (unknown thì ghi unknown, không tự gán UTC); tám khoảng7 ngày `[start,end)`, tuần t chỉ đọc lịch sử `time < end_t`, đánh giá tuần t+1.

Cal-fit/check/tune chỉ reserve query groups từ tuần1; các groups này không dùng làm scheduling gain ở các tuần sau. Query lặp từ quá khứ sang tương lai vẫn được giữ trong evaluation; không áp unseen-query split của ORCAS. Future queries không xuất hiện trước cutoff trong cache scheduling/weights. Weighted future ARR denominator giữ cả cold/no-click/no-recovered-click events, không chỉ query có A(q). Full-new ranking dùng recovered corpus thật.

Xuất coverage corpus/clicked items/events và số dropped/missing; thông tin user cho bootstrap chỉ là stable opaque cluster ID trong outputs, không upload raw logs/text. Nếu không recover corpus thì `BLOCKED_DATA` E6; không thay timestamp synthetic.

## Nhận module

Tests phải có duplicated query text khác ID, missing join, conflicting ID, crossed split, source counts trước/sau normalize và event nhiều clicked items. Manifest ngắn + split ID arrays là đủ, không viết thêm một provenance report.
