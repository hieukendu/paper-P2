# M02 — Download và validate file nguồn

Code `data/download.py`, adapters đọc file nguồn trong `data/prepare.py`, registry `configs/datasets.yaml`. Tải một lần, validate trước preprocessing. Link là source để agent tải lúc triển khai; chưa có file dữ liệu trong phiên viết đặc tả.

## Dataset registry và thứ tự

| Key | Files và URL | Expected counts để đối chiếu |
|---|---|---|
| `fiqa` | [fiqa.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip) | corpus57,638; test648 |
| `trec-covid` | [trec-covid.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/trec-covid.zip) | corpus171,332; test50 |
| `nq` | [nq.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nq.zip) | corpus2,681,468; test3,452 |
| `hotpotqa` | [hotpotqa.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/hotpotqa.zip) | corpus5,233,329; test7,405 |
| `fever` | [fever.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fever.zip) | corpus5,416,568; test6,666; test qrels7,937 vs dev8,079 |

BEIR download phải có `corpus.jsonl`, `queries.jsonl`, `qrels/<split>.tsv`; HF corpus-only không thay release đủ. Dùng BEIR-preprocessed NQ/HotpotQA/FEVER, không đổi sang dataset QA gốc. [BEIR registry](https://github.com/beir-cellar/beir).

MS MARCO scale phải có **document ranking v1**, không BEIR `msmarco` passage corpus:

```text
https://msmarco.z22.web.core.windows.net/msmarcoranking/msmarco-docs.tsv.gz
https://msmarco.z22.web.core.windows.net/msmarcoranking/msmarco-docdev-queries.tsv.gz
https://msmarco.z22.web.core.windows.net/msmarcoranking/msmarco-docdev-qrels.tsv.gz
https://msmarco.z22.web.core.windows.net/msmarcoranking/orcas.tsv.gz
```

Expect documents3,213,835; judged dev queries5,193; dev qrel records5,478. ORCAS expect18,823,602 edge records và10,405,342 source query IDs trước normalize/filter. Registry schema: `qid, query, did, url`. Source MD5 `orcas.tsv.gz`: `4b9350bf997c5c0eaa562be81c796981`; đối chiếu [ORCAS registry](https://github.com/microsoft/msmarco/blob/master/ORCAS.md) trước ingest, không áp checksum này cho derived file. File top100 ~10.7GB và training triples không cần cho primary. [MS MARCO registry](https://microsoft.github.io/msmarco/Datasets.html).

AOL-IA chỉ chuẩn bị khi làm E6: dùng [aolia-tools](https://github.com/terrierteam/aolia-tools) và [ir_datasets AOL-IA](https://ir-datasets.com/aol-ia.html) để khôi phục corpus Internet Archive. Không bịa link corpus ZIP. Pin tool commit/source release; lưu recovered IDs/failed URL IDs, counts và coverage. Metadata chuẩn khoảng1,525,586 docs/36,389,567 qlog entries chỉ là reference; file khôi phục thực tế có thể thiếu. Không thay corpus AOL bằng MS MARCO.

## Hàm cần code

| Hàm | Input → output và logic |
|---|---|
| `dataset_spec(name) -> DatasetSpec` | Registry local; trả URLs, parser, release, expected counts, known checksum nếu có |
| `download_file(url, destination, expected_digest=None) -> Path` | Stream ra `.part`, bounded timeouts/retries, progress theo MB; resume HTTP Range chỉ khi ETag/length phù hợp và server trả206, nếu không restart chính file part; atomic rename sau checksum |
| `verify_source_file(path, spec) -> dict` | Check gzip/zip integrity, expected digest khi nguồn cung cấp; luôn tính local SHA256 một lần; local checksum không đồng nghĩa source-certified |
| `extract_beir(archive, output) -> Path` | Validate relative paths của ZIP nằm trong output; không overwrite processed release đã khóa |
| `download_dataset(spec, paths) -> list[Path]` | Tải required files theo stage; dùng per-dataset lock tránh 2 jobs tải trùng |
| `inspect_release(files, spec) -> dict` | Schema và split availability, corpus/query/qrels counts sau full stream; không chỉ sample100 dòng rồi gọi validated |
| `prepare_aol_source(spec, paths) -> dict` | Gọi công cụ nguồn có checkpoint/URL failure list; nếu source unavailable trả BLOCKED_DATA thay synthetic |

Retry network tối đa3 lần với backoff; 404/permission lỗi source báo rõ không lặp vô hạn. Missing checksum nguồn ghi `source_checksum=null`, vẫn giữ local digest. Counts khác registry: giữ file, phân biệt raw/filtered/dedup counts; chỉ chốt release khi giải thích được khác biệt. Không sửa expected counts để làm check xanh.

## Output và gate

Raw file immutable ở `data/raw/<key>/`. Preprocess M03 sinh một manifest/release, gồm source URLs/revision/date/checksum và ingest statistics; không có báo cáo audit riêng cho mỗi file. Download/raw files không nằm trong upload run mặc định, vì có thể tải lại từ source và có điều khoản riêng.

Tải/pin model và tải dataset của scope trước inference/tuning; hai download tasks có thể overlap. FiQA + MiniLM/MPNet trước E0/E1/T0.core; TREC-COVID sau smoke và trước T0.case/E2 tương ứng; MS MARCO/ORCAS + Arctic **trước T0.scale**, không đợi E4 mới tải; AOL trước T0.case/E6; ba BEIR lớn và Nomic/BGE trước T0.case/E7 tương ứng. Mọi scope phải full ingest/schema/count/join/split validation xong mới dùng inputs. Không yêu cầu tải mọi thứ để pass E0 hoặc T0.core.
