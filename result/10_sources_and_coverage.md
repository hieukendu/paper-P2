# Nguồn và phạm vi kiểm tra nội bộ

Đối chiếu 30/10/2026. Đây là sổ tra cứu cho người viết, **không phải nội dung manuscript**. Không đưa các mã Sxxx, run names, revisions, hashes hoặc các trạng thái upload vào paper.

## Cây kho Hugging Face đã kiểm kê đầy đủ

| Kho tại revision cố định | Revision | Tệp | Thư mục | Bytes metadata | Summary |
|---|---|---|---|---|---|
| [deadgod3005/mixindex-data-aol-ia](https://huggingface.co/datasets/deadgod3005/mixindex-data-aol-ia/tree/f7f87745e9d8fc46c4a78b95aac1df11100bf313) | f7f87745e9d8fc46c4a78b95aac1df11100bf313 | 12 | 3 | 45805898 | 0 |
| [deadgod3005/mixindex-data-fever](https://huggingface.co/datasets/deadgod3005/mixindex-data-fever/tree/f1f326e3ca213dc7ca93357492473d137769b1eb) | f1f326e3ca213dc7ca93357492473d137769b1eb | 67 | 4 | 1521180102 | 0 |
| [deadgod3005/mixindex-data-fiqa](https://huggingface.co/datasets/deadgod3005/mixindex-data-fiqa/tree/983622cbc33cd546a1d5d9fa12909c354e278be2) | 983622cbc33cd546a1d5d9fa12909c354e278be2 | 12 | 3 | 49053844 | 0 |
| [deadgod3005/mixindex-data-hotpotqa](https://huggingface.co/datasets/deadgod3005/mixindex-data-hotpotqa/tree/8f27ea9502d7c4e092d6cbe2235cff0742fa0af5) | 8f27ea9502d7c4e092d6cbe2235cff0742fa0af5 | 65 | 4 | 774610996 | 0 |
| [deadgod3005/mixindex-data-msmarco-docs-v1](https://huggingface.co/datasets/deadgod3005/mixindex-data-msmarco-docs-v1/tree/da3d374e2521cd7ca96a62dd51d3ac36038a7913) | da3d374e2521cd7ca96a62dd51d3ac36038a7913 | 45 | 4 | 9247487100 | 0 |
| [deadgod3005/mixindex-data-nq](https://huggingface.co/datasets/deadgod3005/mixindex-data-nq/tree/6897fa6dd99fe69f94cf559eb0116a9eea12106f) | 6897fa6dd99fe69f94cf559eb0116a9eea12106f | 39 | 4 | 586534944 | 0 |
| [deadgod3005/mixindex-data-orcas](https://huggingface.co/datasets/deadgod3005/mixindex-data-orcas/tree/d5ec9562e5a1ef4cecd909a5986b1999f8eade56) | d5ec9562e5a1ef4cecd909a5986b1999f8eade56 | 13 | 3 | 1871459841 | 0 |
| [deadgod3005/mixindex-data-trec-covid](https://huggingface.co/datasets/deadgod3005/mixindex-data-trec-covid/tree/3edade23e6858351f14b831d19a52487977f8e0e) | 3edade23e6858351f14b831d19a52487977f8e0e | 12 | 3 | 200483814 | 0 |
| [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913) | 3fbcb0c15ea6f5a18d4995dc42c64ef568c02913 | 4899 | 1058 | 51859418709 | 48 |
| [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12) | e998cf63802a03803afea6cf341841b33cd2ea12 | 3514 | 706 | 52697709748 | 31 |
| [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1) | f736e4591abb4b825779a99e19f28a91cd1fb6c1 | 3385 | 581 | 53605418845 | 37 |
| [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1) | 4121dc49dd29e08bf303c8d8b4a7db73f73983e1 | 3413 | 513 | 53617352065 | 30 |
| [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026) | 49d75f8f6919f07f074abe8f6f4a667352cff026 | 2810 | 441 | 43547799980 | 20 |


Đã liệt kê mọi path trong 13 cây kho và đọc toàn bộ 166 summary; các số reported được lấy từ root result/config/timing/data metadata và mọi bảng metrics/selection. Có bốn bundle bị chia qua hai kho; đã đối chiếu theo **cùng payload prefix** và completed marker ở phần đầu, không xem phần sau thiếu marker là mất kết quả.

Tổng 69 cấu hình/tác vụ hiện hành: E2=24, E3=6, E4=3, E5=12, E6=4, E7=20. E2 được chọn theo nhóm cùng source của 24 cấu hình trong checklist/jobs hiện hành; không chọn theo metric tốt nhất. E4 chọn đúng ba tác vụ 50k có chung manifest với các E5 children. Tất cả E5/E6/E7 trong phạm vi này được giữ, không loại case xấu.

165 bundle có completed marker; một E2 Read lịch sử có summary FAILED và không marker, bị loại khỏi primary. Manifest/marker digest khớp cho các bundle có marker. So metadata file-size và LFS digest trên tất cả parts; các JSON và bảng tải về được đối chiếu digest thực. Đã kiểm 99 metrics tables (1.074.908 dòng) và tính lại 24 E2 retrieval tables từ qrels. Đã đọc metadata checkpoint/index để kiểm những state summaries còn lại.

**Giới hạn xác minh:** đã tải kết quả số, config, source snapshots, metadata dữ liệu và checkpoint metadata phục vụ tổng hợp; không tải lại hàng trăm GB graph binaries/vectors/pretrained weights, không encode lại corpus hay chạy lại thí nghiệm trên H100. LFS checksum metadata không phải tự đọc mọi tensor. Full raw corpora không được coi là đã tái-validate toàn nội dung trong lượt này. Với AOL, public metadata đủ tính lại các ARR có sẵn, không đủ tái chạy encoder vì văn bản không công khai. Các tệp kết quả đã tải được tổng hợp thành Markdown ở đây; dữ liệu nhị phân phục vụ phân tích nằm trong cache tạm của lượt làm việc, không phải một release artifact mới của dự án.

## Từng thư mục dữ liệu và tệp nguồn
### deadgod3005/mixindex-data-aol-ia

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2638 |
| .mixindex.json | 34 |
| README.md | 861 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/COMPLETED.json | 236 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/README.md | 861 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/artifact_manifest.json | 1174 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/doc_ids.txt | 650000 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/manifest.json | 3495 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/publication.json | 472 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/qrels.parquet | 5789552 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/splits/query_roles.json | 24045365 |
| releases/76cb4e5dc216bc99cd612a193462b8de3fc07f74077044a62a6e5765666123ae/temporal_events_redacted.parquet | 15311210 |


### deadgod3005/mixindex-data-fever

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2626 |
| .mixindex.json | 34 |
| README.md | 2193 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/COMPLETED.json | 236 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/README.md | 2193 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/artifact_manifest.json | 9575 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/doc_ids.txt | 111888334 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00000.parquet | 17691724 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00001.parquet | 20281353 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00002.parquet | 24042818 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00003.parquet | 25142281 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00004.parquet | 25321859 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00005.parquet | 24978500 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00006.parquet | 25492168 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00007.parquet | 26044557 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00008.parquet | 25167714 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00009.parquet | 24813863 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00010.parquet | 25699566 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00011.parquet | 26791954 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00012.parquet | 25389753 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00013.parquet | 26120758 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00014.parquet | 26381509 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00015.parquet | 26018302 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00016.parquet | 25683999 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00017.parquet | 26624533 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00018.parquet | 26300197 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00019.parquet | 25440363 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00020.parquet | 25219626 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00021.parquet | 26066128 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00022.parquet | 27418855 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00023.parquet | 27732719 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00024.parquet | 26220570 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00025.parquet | 25612868 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00026.parquet | 23283146 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00027.parquet | 23414031 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00028.parquet | 25760616 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00029.parquet | 25722921 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00030.parquet | 25053027 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00031.parquet | 25035179 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00032.parquet | 25271281 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00033.parquet | 25213563 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00034.parquet | 25108369 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00035.parquet | 25877306 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00036.parquet | 25655610 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00037.parquet | 25227002 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00038.parquet | 25715353 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00039.parquet | 25139835 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00040.parquet | 26598040 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00041.parquet | 26118241 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00042.parquet | 24117736 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00043.parquet | 24818323 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00044.parquet | 26280562 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00045.parquet | 26390796 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00046.parquet | 25667865 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00047.parquet | 25866750 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00048.parquet | 26812005 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00049.parquet | 26080153 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00050.parquet | 26303948 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00051.parquet | 25206757 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00052.parquet | 27207793 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00053.parquet | 22605629 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/documents/part-00054.parquet | 3743260 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/manifest.json | 2215 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/publication.json | 2723 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/qrels.parquet | 10399481 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/queries.parquet | 17340493 |
| releases/36e787667533843237fb713b8afbe7ec05406f184f4c195c203ae69b7c7e8cde/splits/query_roles.json | 8536365 |


### deadgod3005/mixindex-data-fiqa

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2630 |
| .mixindex.json | 34 |
| README.md | 1630 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/COMPLETED.json | 236 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/README.md | 1630 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/artifact_manifest.json | 1156 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/doc_ids.txt | 392714 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/documents.jsonl | 46303377 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/manifest.json | 2177 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/qrels.parquet | 766865 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/queries.parquet | 1089052 |
| releases/584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058/splits/query_roles.json | 492343 |


### deadgod3005/mixindex-data-hotpotqa

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2626 |
| .mixindex.json | 34 |
| README.md | 2216 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/COMPLETED.json | 236 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/README.md | 2216 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/artifact_manifest.json | 9271 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/doc_ids.txt | 45307720 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00000.parquet | 14170186 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00001.parquet | 17478309 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00002.parquet | 16629797 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00003.parquet | 16329292 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00004.parquet | 16490923 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00005.parquet | 16071326 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00006.parquet | 15834267 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00007.parquet | 15597972 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00008.parquet | 15298550 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00009.parquet | 15270089 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00010.parquet | 14433742 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00011.parquet | 14189402 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00012.parquet | 14646274 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00013.parquet | 14646123 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00014.parquet | 14344162 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00015.parquet | 13777250 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00016.parquet | 12025422 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00017.parquet | 11894372 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00018.parquet | 12473317 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00019.parquet | 10911917 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00020.parquet | 13291382 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00021.parquet | 12623398 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00022.parquet | 11824266 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00023.parquet | 12572924 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00024.parquet | 11729314 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00025.parquet | 12014629 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00026.parquet | 12132485 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00027.parquet | 12682080 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00028.parquet | 12510540 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00029.parquet | 11973946 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00030.parquet | 12381203 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00031.parquet | 12831773 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00032.parquet | 12963125 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00033.parquet | 13136876 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00034.parquet | 12066298 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00035.parquet | 12646190 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00036.parquet | 11889074 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00037.parquet | 11406522 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00038.parquet | 12252071 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00039.parquet | 12470473 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00040.parquet | 12033199 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00041.parquet | 11753632 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00042.parquet | 12168538 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00043.parquet | 11610941 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00044.parquet | 11742433 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00045.parquet | 12260155 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00046.parquet | 12248448 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00047.parquet | 12458404 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00048.parquet | 12534397 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00049.parquet | 11689879 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00050.parquet | 11630608 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00051.parquet | 11589564 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/documents/part-00052.parquet | 3798614 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/manifest.json | 2220 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/publication.json | 2653 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/qrels.parquet | 11070209 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/queries.parquet | 23540675 |
| releases/6c30fc0ee0f114df38898df00640b76d88cc5b58222da28bae8cc2dc1b6f8d1d/splits/query_roles.json | 7240847 |


### deadgod3005/mixindex-data-msmarco-docs-v1

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2626 |
| .mixindex.json | 34 |
| README.md | 1357 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/COMPLETED.json | 236 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/README.md | 1357 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/artifact_manifest.json | 6246 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/doc_ids.txt | 27917221 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00000.parquet | 289180743 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00001.parquet | 286289450 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00002.parquet | 284841925 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00003.parquet | 290460650 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00004.parquet | 286636833 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00005.parquet | 285052240 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00006.parquet | 286938456 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00007.parquet | 286798860 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00008.parquet | 287827902 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00009.parquet | 289482341 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00010.parquet | 289389774 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00011.parquet | 284865146 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00012.parquet | 287118365 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00013.parquet | 286616167 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00014.parquet | 287048016 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00015.parquet | 287858288 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00016.parquet | 289370511 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00017.parquet | 287014555 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00018.parquet | 289406263 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00019.parquet | 285530998 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00020.parquet | 287135860 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00021.parquet | 283471543 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00022.parquet | 287854094 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00023.parquet | 285393744 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00024.parquet | 286725860 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00025.parquet | 288010239 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00026.parquet | 287265993 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00027.parquet | 285289940 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00028.parquet | 283755335 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00029.parquet | 282676520 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00030.parquet | 284925889 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00031.parquet | 289010033 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/documents/part-00032.parquet | 39232454 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/manifest.json | 2526 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/publication.json | 2261 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/qrels.parquet | 270940 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/queries.parquet | 422727 |
| releases/200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68/splits/query_roles.json | 384582 |


### deadgod3005/mixindex-data-nq

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2626 |
| .mixindex.json | 34 |
| README.md | 2239 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/COMPLETED.json | 236 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/README.md | 2239 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/artifact_manifest.json | 5283 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/doc_ids.txt | 28385038 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00000.parquet | 22493361 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00001.parquet | 21724301 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00002.parquet | 21555132 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00003.parquet | 21371325 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00004.parquet | 21404216 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00005.parquet | 20894927 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00006.parquet | 21279970 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00007.parquet | 21017081 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00008.parquet | 20909892 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00009.parquet | 20858623 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00010.parquet | 20931922 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00011.parquet | 20534669 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00012.parquet | 20885359 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00013.parquet | 20568265 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00014.parquet | 20601708 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00015.parquet | 20460775 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00016.parquet | 20722298 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00017.parquet | 20383326 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00018.parquet | 20465166 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00019.parquet | 20586325 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00020.parquet | 20131102 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00021.parquet | 20033805 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00022.parquet | 20190417 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00023.parquet | 20449537 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00024.parquet | 20295623 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00025.parquet | 19891193 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/documents/part-00026.parquet | 16418746 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/manifest.json | 2076 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/publication.json | 1711 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/qrels.parquet | 308915 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/queries.parquet | 509659 |
| releases/7d93e804cfd1ea372e97a0f74cd04f50a2af64f5a0ae93aaffede19f8515480b/splits/query_roles.json | 255824 |


### deadgod3005/mixindex-data-orcas

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2638 |
| .mixindex.json | 34 |
| README.md | 1654 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/COMPLETED.json | 236 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/README.md | 1654 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/artifact_manifest.json | 1311 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/manifest.json | 2169 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/publication.json | 651 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/qrels.parquet | 1071 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/queries.parquet | 670189877 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/source_queries.parquet | 386068400 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/splits/query_roles.json | 385713243 |
| releases/124f5775a791cea49a66881753f3a5381cc43d4870e5778c8124f8e65c62d583/traffic.parquet | 429476903 |


### deadgod3005/mixindex-data-trec-covid

| Tệp trong từng thư mục | Bytes |
|---|---|
| .gitattributes | 2630 |
| .mixindex.json | 34 |
| README.md | 2024 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/COMPLETED.json | 236 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/README.md | 2024 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/artifact_manifest.json | 1160 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/doc_ids.txt | 1541988 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/documents.jsonl | 198116264 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/manifest.json | 2145 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/qrels.parquet | 800343 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/queries.parquet | 10890 |
| releases/40f5aed7c5d1f9af84ba4fa000b545ff7097621a6397a87293cda76940a644ed/splits/query_roles.json | 4076 |


## Tất cả bundle và liên kết cố định

Các link mở đúng revision đã đọc, không phụ thuộc nhánh main có thể thay đổi.
### S001

`CORE_SMOKE-debug-fiqa-f661ce715552` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/CORE_SMOKE-debug-fiqa-f661ce715552/a03c1418cfb58ac955b4f6e937da2ca8220b358dabd95637ad4ec6031cdd2c99).

Phạm vi: CORE_SMOKE / fiqa / MiniLM → MPNet / MLP / Greedy / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 107; completed marker: True.

### S002

`CORE_SMOKE-fiqa-04985698e65b` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/CORE_SMOKE-fiqa-04985698e65b/01533d0572b302b6596ffa9cf168fa53f44e899fd3e39b7e1bffc5ef377f0cc0).

Phạm vi: CORE_SMOKE / fiqa / MiniLM → MPNet / MLP / Greedy / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 109; completed marker: True.

### S003

`CORE_SMOKE-fiqa-3db596c22bef` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/CORE_SMOKE-fiqa-3db596c22bef/fe3771fe1461028285a3912ca96d22e53441a84b4379004cf061b39abdc7a8fb).

Phạm vi: CORE_SMOKE / fiqa / MiniLM → MPNet / MLP / Greedy / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 109; completed marker: True.

### S004

`E0-fiqa-93d6f570216b` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E0-fiqa-93d6f570216b/0c619da2768d0bf09326b1daec65e0934aa2e96c1afd4277c7cb4f8ae8e6e9b6).

Phạm vi: E0 / fiqa / MiniLM → MPNet / MLP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 50; completed marker: True.

### S005

`E0-fiqa-d766450f861d` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E0-fiqa-d766450f861d/003ca54c50bbc1e62acbe16d3b1091c75fe40977d18a77ff530c6e0a62c19cde).

Phạm vi: E0 / fiqa / MiniLM → MPNet / MLP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 50; completed marker: True.

### S006

`E1-debug-fiqa-0658190b91b1` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E1-debug-fiqa-0658190b91b1/b7816fa98f86c55d12fbec9385971e67d289b168bb63726556d24c82d833367f).

Phạm vi: E1 / fiqa / MiniLM → MPNet / OP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 86; completed marker: True.

### S007

`E1-debug-fiqa-182b57d9b856` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E1-debug-fiqa-182b57d9b856/85ab2017880d55da613d1a6dfa415953e073a4fc9d28b68a7158285cfeefd5c0).

Phạm vi: E1 / fiqa / MiniLM → MPNet / OP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 89; completed marker: True.

### S008

`E1-debug-fiqa-e690dfc90eb5` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E1-debug-fiqa-e690dfc90eb5/4c7aba85abcbf74d3f6c2037b0709ea6742c0b48816243875ea24f35bc3898ab).

Phạm vi: E1 / fiqa / MiniLM → MPNet / OP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 87; completed marker: True.

### S009

`E1-fiqa-65e9ba9de35d` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E1-fiqa-65e9ba9de35d/e014c0890b4ba90527ee75f0a0b6528d7b5f021b68b08488b38e7e535f31d0fd).

Phạm vi: E1 / fiqa / MiniLM → MPNet / OP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 108; completed marker: True.

### S010

`E1-fiqa-b68e354ee3f3` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E1-fiqa-b68e354ee3f3/6f522e5545e90d33bea1def7ebd5d2f11651a402e8050c783ff098d30e74d0ca).

Phạm vi: E1 / fiqa / MiniLM → MPNet / OP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 108; completed marker: True.

### S011

`E2-fiqa-la-diagonal-random-m17-t101-db4ac5ad0130` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-la-diagonal-random-m17-t101-db4ac5ad0130/ac90e259759ac3228d51c2b006c6847ec570126f8a68b346dbdb1f8e1d484386).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 113; completed marker: True.

### S012

`E2-fiqa-la-diagonal-random-m29-t101-b25fae438a16` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-la-diagonal-random-m29-t101-b25fae438a16/abc3b6dfc873c2693d70c68fdea839b87ac61bf0ccefd86ef4283be922094dfa).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 29. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 113; completed marker: True.

### S013

`E2-fiqa-la-diagonal-random-m43-t101-2fd748dab54c` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-la-diagonal-random-m43-t101-2fd748dab54c/7658eab326134e8a6546215742672b6aec8e2ab4d5964e7477d7eb6271120b6f).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 43. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 113; completed marker: True.

### S014

`E2-fiqa-la-global-random-m17-t101-a263e90edbc4` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-la-global-random-m17-t101-a263e90edbc4/8981461218aadd678eff1a0425fe40fe3f2120584cc887c08a9814d058bbdda7).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 113; completed marker: True.

### S015

`E2-fiqa-la-global-random-m29-t101-39c15fbe39a2` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-la-global-random-m29-t101-39c15fbe39a2/528a1f8ea6e6de602406999883f80751f795d2d9b0cece5c0b1de5a1f3049d0f).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 29. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 113; completed marker: True.

### S016

`E2-fiqa-mapping-la-primary-random-m17-t101-1269a948823d` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-la-primary-random-m17-t101-1269a948823d/53d2be83151b01d720f9876f96d5d75a1acd097e5e4b3e164250441276502d47).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 17 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S017

`E2-fiqa-mapping-la-primary-random-m17-t101-c9bab415c1b2` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-la-primary-random-m17-t101-c9bab415c1b2/72961324aebb9a7d28597f21da376bf0863920bc86c1c18978a4da0947d5b061).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 17 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S018

`E2-fiqa-mapping-la-primary-random-m29-t101-4f9831c839df` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-la-primary-random-m29-t101-4f9831c839df/42cb0f2325b0c790257b1a1e8745548767c2b07ed9bd47ba7fd234bafe843834).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 29 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S019

`E2-fiqa-mapping-la-primary-random-m29-t101-afa81f6ceef6` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-la-primary-random-m29-t101-afa81f6ceef6/ee1a1934059293516b5516e2bc572d2e7294c0577e66d3c326926db49e169724).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 29 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S020

`E2-fiqa-mapping-la-primary-random-m43-t101-9be6b1098bae` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-la-primary-random-m43-t101-9be6b1098bae/a2e12b1fb52943d7cc8b26d5c16d626e1c0e18e0c8f16c5b00a04d718ded2f2e).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 43 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S021

`E2-fiqa-mapping-op-primary-random-m17-t101-e9a387b8bdba` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-op-primary-random-m17-t101-e9a387b8bdba/5a7d9012148b0dbdca0832814e342754b921350eb7097e5bac39397660d5b13b).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 17 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S022

`E2-fiqa-mapping-op-primary-random-m17-t101-f0f3e61dec2c` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-op-primary-random-m17-t101-f0f3e61dec2c/68cf5f3fbcbb0bb7b68e1e92cf1cb31952f2e153a0b0c6e84c0aba44121ee04b).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 17 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S023

`E2-fiqa-mapping-op-primary-random-m29-t101-035ee8511b31` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-op-primary-random-m29-t101-035ee8511b31/92922dfa48d61f0ffac9d98cdcaf8a153e541af59b4dfe94bdeaea438283b116).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 29 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S024

`E2-fiqa-mapping-op-primary-random-m29-t101-c88183e6e7b5` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-op-primary-random-m29-t101-c88183e6e7b5/fe5338d59e7b5d5fa1286645d01549ca191ec39bc29b4816c011e4b0dda93534).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 29 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S025

`E2-fiqa-mapping-op-primary-random-m43-t101-4475af29ec23` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-op-primary-random-m43-t101-4475af29ec23/6a2ab57f55fa5239714a3d9c0504929ddb2958687330a072f4a6ecb283c579f5).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 43 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S026

`E2-fiqa-mapping-op-primary-random-m43-t101-e74681acb89f` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-op-primary-random-m43-t101-e74681acb89f/3223fd52eabf15b46fb833ddd42f4769a328f85a4f4a1ac21af7083cf8fcbb87).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 43 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S027

`E2-fiqa-mapping-residual_mlp-primary-random-m17-t101-8bde0254405d` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-residual_mlp-primary-random-m17-t101-8bde0254405d/2eff6825f672bd3a51cbdb629a08c6e667866d8792dbed8fb877cf4143a16caa).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S028

`E2-fiqa-mapping-residual_mlp-primary-random-m29-t101-83a43ff343ce` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-residual_mlp-primary-random-m29-t101-83a43ff343ce/4236bb4c92ff470b52c8d0cd4925b60e4b585fc75fd49853fba6923bb81dfc7d).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 29 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S029

`E2-fiqa-mapping-residual_mlp-primary-random-m43-t101-ae07307473ee` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-mapping-residual_mlp-primary-random-m43-t101-ae07307473ee/0be09526196f28185bf9f46ee9ef44136e422961b5d0082098bb7375b2b18a77).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 43 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S030

`E2-fiqa-residual_mlp-primary-greedy-m17-t101-0b0e24d75fc0` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-residual_mlp-primary-greedy-m17-t101-0b0e24d75fc0/e3b6e73c640f676f378c7ce4bc9d8001c59d9fb91f2a39d2d86d9932a0b64f22).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 113; completed marker: True.

### S031

`E2-fiqa-scheduler-residual_mlp-primary-degree-m17-t101-5c77ea584b68` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m17-t101-5c77ea584b68/f46151b99488cc44a5a97a60fda36bae8399e2a75eeaf946753be343abc3bda4).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 17 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S032

`E2-fiqa-scheduler-residual_mlp-primary-degree-m29-t101-9b508ead9970` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m29-t101-9b508ead9970/a0b12c017c1eb1e407bf9bcaf963279903bffacb869a549c9edacec16601948d).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 29 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S033

`E2-fiqa-scheduler-residual_mlp-primary-degree-m43-t101-7487b5243374` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m43-t101-7487b5243374/6324d4689492caec79b86131595d2f0aa569fef4b64be34a0ebc6f104919304e).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 43 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S034

`E2-fiqa-scheduler-residual_mlp-primary-random-m17-t101-d3bf59f236f7` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m17-t101-d3bf59f236f7/cf4340a16036d8c2a269fb3a53e25a7bc4fa559127a4784d067a621d86cd3cac).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S035

`E2-fiqa-scheduler-residual_mlp-primary-random-m29-t101-9546dcc7b6de` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m29-t101-9546dcc7b6de/e78c3ae4afc8e2cad96e7000241d1c6bba4ad9c27c7ebf7aebfef49362b31e4b).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 29 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S036

`E2-fiqa-scheduler-residual_mlp-primary-random-m43-t101-ba059a343c66` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m43-t101-ba059a343c66/06179bd95e4e55b40f2b1dac3ee6a47fe40db190bd06385727b28c851224b115).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 43 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S037

`E2-fiqa-scheduler-residual_mlp-primary-read-m17-t101-81a4467b1b48` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2-fiqa-scheduler-residual_mlp-primary-read-m17-t101-81a4467b1b48/2001005c7ca48e2528ae3f663f7691d1cfca8b7e700fb74584c05993446f7214).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Read / seed 17 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `FAILED`. Parts: 0; manifest entries: 114; completed marker: False.

### S038

`E2_PREFLIGHT-fiqa-2db1f38f9b30` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2_PREFLIGHT-fiqa-2db1f38f9b30/a038d85e97c1cd99b67a4f38f4038bf90b5570dd29ac8f8e15f391612f1cdfac).

Phạm vi: E2_PREFLIGHT / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 83; completed marker: True.

### S039

`E2_PREFLIGHT-fiqa-3a0a1a13deb8` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2_PREFLIGHT-fiqa-3a0a1a13deb8/0bb283a5afc0a6414b8255b46a891daa929d8d59e6d74ef27f5fbace8f4a2c70).

Phạm vi: E2_PREFLIGHT / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 83; completed marker: True.

### S040

`E2_PREFLIGHT-fiqa-6679266cd070` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2_PREFLIGHT-fiqa-6679266cd070/36f81de466a012dbc6cc65519e0584e2cdb3ea7b5c5f55590d5bae700231a4f4).

Phạm vi: E2_PREFLIGHT / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 83; completed marker: True.

### S041

`E2_PREFLIGHT-fiqa-830a9304efc3` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2_PREFLIGHT-fiqa-830a9304efc3/9362d7ac473671f19d6d3ad835abeeff1839fa0a6c96ab20dbe5399d617f5778).

Phạm vi: E2_PREFLIGHT / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 83; completed marker: True.

### S042

`E2_PREFLIGHT-fiqa-889d06a882c6` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/E2_PREFLIGHT-fiqa-889d06a882c6/c756ac540b91168ab560d8ac6a65159171d59c93954876143c81fc8d57dcd104).

Phạm vi: E2_PREFLIGHT / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 154; completed marker: True.

### S043

`RUNTIME_PROBE-fiqa-minilm_mpnet-80c49dd823f1` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/RUNTIME_PROBE-fiqa-minilm_mpnet-80c49dd823f1/7209256bb4a77465a93821272a57a6180aeb0973b83927f5ac5a55af6ab6bf21).

Phạm vi: RUNTIME_PROBE / fiqa / MiniLM → MPNet / MLP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 49; completed marker: True.

### S044

`RUNTIME_PROBE-fiqa-minilm_mpnet-fb16c618c9df` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/RUNTIME_PROBE-fiqa-minilm_mpnet-fb16c618c9df/307b6d81a413f3cbfcaad2941596367be1f3bb5acb991fbaaaf29e2a3479672d).

Phạm vi: RUNTIME_PROBE / fiqa / MiniLM → MPNet / MLP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 49; completed marker: True.

### S045

`T0-core-fiqa-b9698dc39c17` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/T0-core-fiqa-b9698dc39c17/b70b9f54756ecb6e157b800273ed3940d9ad03ff93c224de098593f804c9a61c).

Phạm vi: T0 / fiqa / MiniLM → MPNet / MLP / Random / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 81; completed marker: True.

### S046

`hf-self-test-79ee52b83bbf` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/hf-self-test-79ee52b83bbf/f0a08b0be59ab42146cba7a43319b47622a619bd3d19c80918f40930bd9ea22b).

Phạm vi: hf / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 42; completed marker: True.

### S047

`hf-self-test-7c746880428b` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/hf-self-test-7c746880428b/043c6ba80bfb8c5fa789632c75229d202ff04424df8489f46d49875f0276c329).

Phạm vi: hf / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 40; completed marker: True.

### S048

`hf-self-test-v1` — [deadgod3005/mixindex-runs-001](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/3fbcb0c15ea6f5a18d4995dc42c64ef568c02913/runs/hf-self-test-v1/62c91d289122fd3c48401a5bc97bbe893715c653fc40d4e565c01845e31cd7c7).

Phạm vi: hf / seed N/A. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 26; completed marker: True.

### S049

`E2-fiqa-mapping-la-primary-random-m17-t101-311675c6f74a` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-la-primary-random-m17-t101-311675c6f74a/8c03fe445786d43d4aeaa25ef73eb17b9e0ddbf5da714bbbe4418578ca8de7da).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 17 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S050

`E2-fiqa-mapping-la-primary-random-m29-t101-5093d90920a2` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-la-primary-random-m29-t101-5093d90920a2/e0e26e486677a6e3085f918a79686176c399bba570cd2097ebc89d245193e574).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 29 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S051

`E2-fiqa-mapping-la-primary-random-m43-t101-3b5a217f890d` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-la-primary-random-m43-t101-3b5a217f890d/260a5e600d6c9a24e74781f2ccf90cbf39857e5248f9c409a9537ae9575c0ec5).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 43 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S052

`E2-fiqa-mapping-la-primary-random-m43-t101-a9d9217d5cad` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-la-primary-random-m43-t101-a9d9217d5cad/b66ef151a908e01ab8f92ba8f1a6233ca623ab893743a9a90238394cb3f11408).

Phạm vi: E2 / fiqa / MiniLM → MPNet / LA / Random / seed 43 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 2; manifest entries: 114; completed marker: True.

### S053

`E2-fiqa-mapping-op-primary-random-m17-t101-697da2441ba2` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-op-primary-random-m17-t101-697da2441ba2/ba9571b87723b54b519fc36d3244136ce402f5e75ac4834e50e5620ebaeb349d).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 17 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S054

`E2-fiqa-mapping-op-primary-random-m29-t101-6e412daf9dce` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-op-primary-random-m29-t101-6e412daf9dce/949ddb02e9e0b0d9496fc82866f6e5d1e1dc4ccc5ed732300f1a321ada8fb559).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 29 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S055

`E2-fiqa-mapping-op-primary-random-m43-t101-7b67c0b6f23f` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-op-primary-random-m43-t101-7b67c0b6f23f/8dd8d38709c3671ad98df90e30a17048c520061a576da91e15bc99e0ef9a0b18).

Phạm vi: E2 / fiqa / MiniLM → MPNet / OP / Random / seed 43 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S056

`E2-fiqa-mapping-residual_mlp-primary-random-m17-t101-3c505c2b6c27` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-residual_mlp-primary-random-m17-t101-3c505c2b6c27/3286b080205e3d95f45c3b1f9ecff4bd71bde47a1ab4d7f02a66f4abb53d4ee8).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S057

`E2-fiqa-mapping-residual_mlp-primary-random-m17-t101-8965bb4ceacf` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-residual_mlp-primary-random-m17-t101-8965bb4ceacf/a55d096fe5db04de7766079fc6365a5ddf38984285049c79e6cb88455af75fa3).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S058

`E2-fiqa-mapping-residual_mlp-primary-random-m29-t101-51d94c776f31` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-residual_mlp-primary-random-m29-t101-51d94c776f31/91f484b91e425bab0719915fc8be40b84f1d318a2901e036f9944c71f2e965f9).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 29 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S059

`E2-fiqa-mapping-residual_mlp-primary-random-m29-t101-e0b7543299a8` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-residual_mlp-primary-random-m29-t101-e0b7543299a8/b09fd8b5705c7f1375a35ca1eeb4b28cf8139b69fcd4b0e64374befc263e6b7f).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 29 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S060

`E2-fiqa-mapping-residual_mlp-primary-random-m43-t101-b46c61929bb6` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-residual_mlp-primary-random-m43-t101-b46c61929bb6/64c83fd01be83614802b0d93f0ad5328b40231284766e4fa48a1f4f7132f665a).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 43 / mapping. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S061

`E2-fiqa-mapping-residual_mlp-primary-random-m43-t101-bcfbeac54bd2` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-mapping-residual_mlp-primary-random-m43-t101-bcfbeac54bd2/4cf23830e1de0261afb559fc2666b39848e42cc967ac277fec728083d283dad3).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 43 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S062

`E2-fiqa-scheduler-residual_mlp-primary-degree-m17-t101-740afd9ec98e` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m17-t101-740afd9ec98e/a15cfe6e1492aca28c5daaea123d23315778c5bd1a060576f7141b4418329dac).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 17 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S063

`E2-fiqa-scheduler-residual_mlp-primary-degree-m17-t101-864c333483fc` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m17-t101-864c333483fc/37eca20c50719a58468a98175ed3f74052fce4dde55f605fa5af2c3ad266f2ed).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 17 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S064

`E2-fiqa-scheduler-residual_mlp-primary-degree-m29-t101-d833817bc2ca` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m29-t101-d833817bc2ca/3a38798580809dcdde36ef3d35e835601a17399619aab4767d7b275abdc927f9).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 29 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S065

`E2-fiqa-scheduler-residual_mlp-primary-degree-m43-t101-b2c9ae3ee2c4` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m43-t101-b2c9ae3ee2c4/30d3d49982d54e956e07255f68ce8071cd27a8a34f6e2fec79722538c1f6fd39).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 43 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S066

`E2-fiqa-scheduler-residual_mlp-primary-greedy-m17-t101-306a6c3b4b13` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-greedy-m17-t101-306a6c3b4b13/b62d9ce48fc683f59f4e59b08f4ba187f35642d657535b4e743976aad7ab1f99).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S067

`E2-fiqa-scheduler-residual_mlp-primary-greedy-m29-t101-bc8c157a168f` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-greedy-m29-t101-bc8c157a168f/f862a21ea03ecafd10365f923d18ecace9186d93f1852bfc2f7a41f0c056d9a9).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 29 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S068

`E2-fiqa-scheduler-residual_mlp-primary-greedy-m43-t101-ba474face30a` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-greedy-m43-t101-ba474face30a/7ccbce884e70fe85f6510e5657ae915eff0d08326bf7a5ffe2deb2595c1dd121).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 43 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S069

`E2-fiqa-scheduler-residual_mlp-primary-random-m17-t101-9e978e5700de` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m17-t101-9e978e5700de/404965a8e284b057285a85eeab0c9e4f43e795931f3313475689f32831e6030a).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S070

`E2-fiqa-scheduler-residual_mlp-primary-random-m17-t101-c1a258adbec7` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m17-t101-c1a258adbec7/6b8148c06d47061ad300befcfdb96cf4617bb08ef8cc2a9eb44366b6df3e50b6).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S071

`E2-fiqa-scheduler-residual_mlp-primary-random-m29-t101-79b5ffd91640` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m29-t101-79b5ffd91640/c2e39fff63e941e4544c2e9ccbdea151b163954bdb2bbdcfe0371c22ca974462).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 29 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S072

`E2-fiqa-scheduler-residual_mlp-primary-random-m29-t101-8e34628e6344` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m29-t101-8e34628e6344/53d2ddd6ecca95feee6c24ca5d687507afb023e217ad53f31d730ee4427d223e).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 29 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S073

`E2-fiqa-scheduler-residual_mlp-primary-random-m43-t101-836cd480e2ad` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m43-t101-836cd480e2ad/3fb1ce91b5f2cb3dacbe65a70cc215188c5f42272f6004bbb35b36319968a37a).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 43 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S074

`E2-fiqa-scheduler-residual_mlp-primary-random-m43-t101-c45cdf079800` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-random-m43-t101-c45cdf079800/1ccf2e5e6fdb15ec6a4601c199a4715905aca1e06300681c5b5b096c198aad9f).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Random / seed 43 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S075

`E2-fiqa-scheduler-residual_mlp-primary-read-m17-t101-8825a3ec84bc` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-read-m17-t101-8825a3ec84bc/bf6bf29a9029e399271c4085e26c62e45299eac2309e0ebbd573a62ac1d51555).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Read / seed 17 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S076

`E2-fiqa-scheduler-residual_mlp-primary-read-m29-t101-00fe42363050` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-read-m29-t101-00fe42363050/f15110d69d67c82ee79994680848a146cc1bad1cefca7d54938fb48c569f8ddc).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Read / seed 29 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S077

`E2-fiqa-scheduler-residual_mlp-primary-read-m43-t101-8a21681a7212` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2-fiqa-scheduler-residual_mlp-primary-read-m43-t101-8a21681a7212/4975c6cdcde1d0b155c124276e84717c64c09621b11c96f55d2ebe51179d1316).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Read / seed 43 / scheduler. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S078

`E2_PREFLIGHT-fiqa-4149a52e5a42` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/E2_PREFLIGHT-fiqa-4149a52e5a42/c519cdd6c112eb91e2056a6c5593a3a0e115df5e2f3a9c97d00aeb6ddc917bb7).

Phạm vi: E2_PREFLIGHT / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 83; completed marker: True.

### S079

`T0-case-trec-covid-minilm_mpnet-0b33f894078e` — [deadgod3005/mixindex-runs-002](https://huggingface.co/datasets/deadgod3005/mixindex-runs-002/tree/e998cf63802a03803afea6cf341841b33cd2ea12/runs/T0-case-trec-covid-minilm_mpnet-0b33f894078e/4b7c4e71f1ac4f6533a45500089edba2f55fbd2d7f344987fee213b9497b4948).

Phạm vi: T0 / trec-covid / MiniLM → MPNet / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 67; completed marker: True.

### S080

`E2-fiqa-scheduler-residual_mlp-primary-degree-m29-t101-7b5632f1fb4c` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m29-t101-7b5632f1fb4c/a9c7f3e335b5e330f66d5f775f24bebca831d72359a0ae8e5ff6d94859041a87).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 29 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 2; manifest entries: 114; completed marker: True.

### S081

`E2-fiqa-scheduler-residual_mlp-primary-degree-m43-t101-d06e259c8f04` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-degree-m43-t101-d06e259c8f04/46d4f40fca8c55220836b1717292c54c4d2e66ac77efd6430ad86a148e76eba4).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Degree / seed 43 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S082

`E2-fiqa-scheduler-residual_mlp-primary-greedy-m17-t101-0fd1bbbcb763` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-greedy-m17-t101-0fd1bbbcb763/4d996d2502a563ea035de006369ac1ab12a1596e30acc95217feb13df6b0e53d).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S083

`E2-fiqa-scheduler-residual_mlp-primary-greedy-m29-t101-e36e6de1c27c` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-greedy-m29-t101-e36e6de1c27c/65ec62579bf1496d555e1655199cfdfa12ea6f7c7eb36299386b5fa0148250e0).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 29 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S084

`E2-fiqa-scheduler-residual_mlp-primary-greedy-m43-t101-c061198c469a` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-greedy-m43-t101-c061198c469a/26ca821a7bca14b1c17382f5a519c1d9f68e0084f514a5fd508d34bb0f1e9e1f).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 43 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S085

`E2-fiqa-scheduler-residual_mlp-primary-read-m17-t101-b7fb3e5c985f` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-read-m17-t101-b7fb3e5c985f/7d0dfb4b432b244fca4ffdaf6168ed408da60845f52a1fa6f3153ce7b4a91c59).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Read / seed 17 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S086

`E2-fiqa-scheduler-residual_mlp-primary-read-m29-t101-67f93e34a63d` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-read-m29-t101-67f93e34a63d/2080ece61411c9bfeaffb40955edc0166df7a4ed62eeb3aedee60fe1e9bea490).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Read / seed 29 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S087

`E2-fiqa-scheduler-residual_mlp-primary-read-m43-t101-44461f61827d` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-fiqa-scheduler-residual_mlp-primary-read-m43-t101-44461f61827d/aa5ec6c7a2631e0faecf84285f67c3a960323aeb32836c785fc09a8e08aa5b1e).

Phạm vi: E2 / fiqa / MiniLM → MPNet / MLP / Read / seed 43 / scheduler. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S088

`E2-trec-covid-mapping-la-primary-random-m17-t101-6560f5868ce7` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-trec-covid-mapping-la-primary-random-m17-t101-6560f5868ce7/33f64889a05e3a1ca8d22220db7ba464d435e533d750b2479b092f2505581d65).

Phạm vi: E2 / trec-covid / MiniLM → MPNet / LA / Random / seed 17 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S089

`E2-trec-covid-mapping-op-primary-random-m17-t101-d40a3f423627` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-trec-covid-mapping-op-primary-random-m17-t101-d40a3f423627/047b6758ba56686622f41bb94170ce1dcc68be28c38b7021a6f9f8712c73dba4).

Phạm vi: E2 / trec-covid / MiniLM → MPNet / OP / Random / seed 17 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S090

`E2-trec-covid-mapping-residual_mlp-primary-random-m17-t101-26524a10c9b1` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E2-trec-covid-mapping-residual_mlp-primary-random-m17-t101-26524a10c9b1/54612b116fc7ae072965a8dd0983c7e66921072747d2db4e50f5b26646a37b58).

Phạm vi: E2 / trec-covid / MiniLM → MPNet / MLP / Random / seed 17 / mapping. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S091

`E3-fiqa-systems-cadence_10pct-0121de08c402` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E3-fiqa-systems-cadence_10pct-0121de08c402/992521cec5d44e0d3bd7703234e11989c1121d9949953f857a400759c0600e68).

Phạm vi: E3 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / cadence_10pct. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 58; completed marker: True.

### S092

`E3-fiqa-systems-cadence_1pct-014d7688f265` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E3-fiqa-systems-cadence_1pct-014d7688f265/92d9809a910c4d41b4d8f78eea4e7f4eeffcef739be451b51902a7dcb0e17591).

Phạm vi: E3 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / cadence_1pct. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 58; completed marker: True.

### S093

`E3-fiqa-systems-cadence_5pct-55468915b7b0` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E3-fiqa-systems-cadence_5pct-55468915b7b0/c0957ac4856e398545f629c8861552bc76fde9aff4cbbbfb2c58f60437a565c3).

Phạm vi: E3 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / cadence_5pct. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 58; completed marker: True.

### S094

`E3-fiqa-systems-exact_reference-3747acd629dc` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E3-fiqa-systems-exact_reference-3747acd629dc/dcf847b34206d94b74b7e2523172f51e00cd53f4a931e329bfd69ba1bb61532a).

Phạm vi: E3 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / exact_reference. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 58; completed marker: True.

### S095

`E3-fiqa-systems-hnsw_fixed_snapshot-fdb97e3a6541` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E3-fiqa-systems-hnsw_fixed_snapshot-fdb97e3a6541/b7916534fbca63299c434e1052804b396a57d6ae80cd6d1c7f035c9447d363f6).

Phạm vi: E3 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / hnsw_fixed_snapshot. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 58; completed marker: True.

### S096

`E3-fiqa-systems-serving_save_load-a90c5c18cd17` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E3-fiqa-systems-serving_save_load-a90c5c18cd17/5302597c6b5773742d6afc673abfdfb9cc436a5d74fb1436442b4f3f6a757922).

Phạm vi: E3 / fiqa / MiniLM → MPNet / MLP / Random / seed 17 / serving_save_load. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 58; completed marker: True.

### S097

`E4-scale-full_bootstrap-057a9480199a` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-full_bootstrap-057a9480199a/54aafdef4cf612f9d8f9d974d6590e1d7021c4316215e8043dcd2202857b461c).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / full_bootstrap. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 74; completed marker: True.

### S098

`E4-scale-restore_footprint-cc569795553d` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-restore_footprint-cc569795553d/e3365357895502a6c8519f2c5dcba8033b5414119a7ed584ef45e6855984022b).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / restore_footprint. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 74; completed marker: True.

### S099

`E4-scale-subset_probe-04677934dc04` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-04677934dc04/e7d3e15ddd3b86a9426aa7a11f6380fe85094cd8b1769380a45bc63ab261631a).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 71; completed marker: True.

### S100

`E4-scale-subset_probe-32895ea6c259` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-32895ea6c259/0f28ed2982b2cea2abbfbc7a98a13f77d31e01c0c30015f06ad0bbf2ffa317e0).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 71; completed marker: True.

### S101

`E4-scale-subset_probe-4d493a5f8c3f` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-4d493a5f8c3f/ad83266749aa8414e2d2ada3f38ae920f121f1527e2e81ebe639879584bc5364).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 70; completed marker: True.

### S102

`E4-scale-subset_probe-5565e4dfc816` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-5565e4dfc816/3935d416a63b6386c41d428f35af70609982100043df2a98fc912f6174f70c7d).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 70; completed marker: True.

### S103

`E4-scale-subset_probe-62a55a977ab5` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-62a55a977ab5/9fab50c22a251e5d689f6c2a4897cd8b5a6b8b2b82e2a18322375306363944f4).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S104

`E4-scale-subset_probe-aff6b601ca9e` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-aff6b601ca9e/40c052efc2801ee128e40fdb5d03e37af1eacbbb4bce200a486b8e1828e48540).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 71; completed marker: True.

### S105

`E4-scale-subset_probe-b0154c3b704b` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-b0154c3b704b/0dc83e72fd00b9df6b7a85b1af818f210f53f9322520779482bb29898b773f5f).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 68; completed marker: True.

### S106

`E4-scale-subset_probe-d5a20b00e975` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E4-scale-subset_probe-d5a20b00e975/66e8637c7c3460b052ba90067e946913090464567c20a270487ac3d8cdacc897).

Phạm vi: E4 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / subset_probe. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 71; completed marker: True.

### S107

`E5-scale-degree-m17-t101-310142bb1ee2` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E5-scale-degree-m17-t101-310142bb1ee2/fb2f8ea41477faa712ad8a803acd72dfe2fea9f74c93177b7af86c35b87d5c7a).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Degree / seed 17 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S108

`E5-scale-random-m17-t101-59baabdbf9f2` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E5-scale-random-m17-t101-59baabdbf9f2/9a850c198610aa8edf5be8653d4095fd54ef791319641071906efc27b7f3834a).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S109

`E5-scale-random-m29-t101-ca30a574a09c` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E5-scale-random-m29-t101-ca30a574a09c/d067e46159bc6fb75a1c66fc8b79b3accdb49d0253aedd5d351c0c0526702ca0).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 29 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S110

`E5-scale-random-m43-t101-2cc4feda61a0` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/E5-scale-random-m43-t101-2cc4feda61a0/1c8634e5d6be0e7aa564b7586c285da4390b7bec62ef2d7f14f1dabe98df278f).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 43 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S111

`RUNTIME_PROBE-msmarco-docs-v1-arctic-5e9e239a2aac` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/RUNTIME_PROBE-msmarco-docs-v1-arctic-5e9e239a2aac/e55687a535da6774a9350648a00c51fde64e27983d1423e505ff40bf52380844).

Phạm vi: RUNTIME_PROBE / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 64; completed marker: True.

### S112

`RUNTIME_PROBE-msmarco-docs-v1-arctic-7202d429d884` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/RUNTIME_PROBE-msmarco-docs-v1-arctic-7202d429d884/39a78c5ab75c4bcf14f2632377e652a5c002dc4712c46d59898d24e98c34e41c).

Phạm vi: RUNTIME_PROBE / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 64; completed marker: True.

### S113

`RUNTIME_PROBE-msmarco-docs-v1-arctic-cf2b50024d92` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/RUNTIME_PROBE-msmarco-docs-v1-arctic-cf2b50024d92/c5bcd6fe8e122828546c62e3baf95d0cfa919b0dfc3712ea7cc76183d410d197).

Phạm vi: RUNTIME_PROBE / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 64; completed marker: True.

### S114

`RUNTIME_PROBE-msmarco-docs-v1-arctic-d0b2489257db` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/RUNTIME_PROBE-msmarco-docs-v1-arctic-d0b2489257db/79d5d193c766e8a89b122a0c1ea2bb2ffc66de4c536c5104b93c9c6811ee7b72).

Phạm vi: RUNTIME_PROBE / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 64; completed marker: True.

### S115

`RUNTIME_PROBE-msmarco-docs-v1-arctic-eb1f742a6662` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/RUNTIME_PROBE-msmarco-docs-v1-arctic-eb1f742a6662/0e4d9126ac4e08b24f14707156f7578c25a538433cebc783c791aeef527ae63a).

Phạm vi: RUNTIME_PROBE / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 64; completed marker: True.

### S116

`T0-scale-msmarco-arctic-58d2b8be46c0` — [deadgod3005/mixindex-runs-003](https://huggingface.co/datasets/deadgod3005/mixindex-runs-003/tree/f736e4591abb4b825779a99e19f28a91cd1fb6c1/runs/T0-scale-msmarco-arctic-58d2b8be46c0/abe1e46a295b5237440d622cad8db249d59fc96dd24ee0c222b41c612d70c04d).

Phạm vi: T0 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 114; completed marker: True.

### S117

`E5-scale-degree-m29-t101-ca194e98f844` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-degree-m29-t101-ca194e98f844/aa87818db8949896f43e63673043335bac08545583d2b19bfc0b11769dbacb1f).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Degree / seed 29 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 2; manifest entries: 139; completed marker: True.

### S118

`E5-scale-degree-m43-t101-49ef754eb2c6` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-degree-m43-t101-49ef754eb2c6/73991f98614231fc3c9a73d82a44d99bca2f1045505525208225aa1830689d72).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Degree / seed 43 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S119

`E5-scale-greedy-m17-t101-29c55cf5dc0c` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-greedy-m17-t101-29c55cf5dc0c/c0a2b6e2b5c2f40ef54508a82f0aaecc2579b247b01132a3fac77c3b2f453d4d).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Greedy / seed 17 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S120

`E5-scale-greedy-m29-t101-87682640c62c` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-greedy-m29-t101-87682640c62c/db5aae2495eecb9b1eb7842fee83149cb1f6d1fdd2a14488b40f251a03535be6).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Greedy / seed 29 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S121

`E5-scale-greedy-m43-t101-b57b9d5f86c1` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-greedy-m43-t101-b57b9d5f86c1/d3542af2c8715554d7146a3bb1a2c026edd51e41f8ceb9c4aa0a7d081f805377).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Greedy / seed 43 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S122

`E5-scale-read-m17-t101-2f342e8fe56d` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-read-m17-t101-2f342e8fe56d/cb2c303ec9e8d03a5daa20ccb7efabfdf8fe4cb1c1b4f63f31fb2b060867aa0f).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Read / seed 17 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S123

`E5-scale-read-m29-t101-019dd03645c4` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-read-m29-t101-019dd03645c4/c3fe19c68d8fa1949e6fffff698034555079ed9f10092d1cc83c5680d0c748e3).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Read / seed 29 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S124

`E5-scale-read-m43-t101-98c382eb2ba7` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E5-scale-read-m43-t101-98c382eb2ba7/bba829be28be1681b6e76820471bd67531e9d047027d15449226bf9c28b4a2a4).

Phạm vi: E5 / msmarco-docs-v1 / Arctic v1 → v2 / MLP / Read / seed 43 / required. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 139; completed marker: True.

### S125

`E7-fiqa-minilm_mpnet-op-greedy-m17-t101-493da14150a2` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E7-fiqa-minilm_mpnet-op-greedy-m17-t101-493da14150a2/3328de4328ff94b2a15b77f08163a1d41d7c4576308890853668bc2f068ee1d2).

Phạm vi: E7 / fiqa / MiniLM → MPNet / OP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S126

`E7-fiqa-minilm_mpnet-residual_mlp-greedy-m17-t101-fd5d75c38d27` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E7-fiqa-minilm_mpnet-residual_mlp-greedy-m17-t101-fd5d75c38d27/32a430cf57b23d3fa1f965699bd4280f4f90c6072d0a819035506ce98d4a8953).

Phạm vi: E7 / fiqa / MiniLM → MPNet / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S127

`E7-fiqa-minilm_mpnet-residual_mlp-random-m17-t101-d98a4312e0e2` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E7-fiqa-minilm_mpnet-residual_mlp-random-m17-t101-d98a4312e0e2/d46cc40ad10369d9dd36d0ee42fdd920867701c0e7359913a665b6180d27b1ff).

Phạm vi: E7 / fiqa / MiniLM → MPNet / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S128

`E7-nq-arctic-residual_mlp-random-m17-t101-50907878a75f` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E7-nq-arctic-residual_mlp-random-m17-t101-50907878a75f/0518ea3476afef829102701cc9b001eccbba9a4d9826a83254ea8fb0190b1a06).

Phạm vi: E7 / nq / Arctic v1 → v2 / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S129

`E7-trec-covid-minilm_mpnet-residual_mlp-greedy-m17-t101-ebfe1bc2702e` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E7-trec-covid-minilm_mpnet-residual_mlp-greedy-m17-t101-ebfe1bc2702e/90e1b56597f87078993a7214aa9fc4312232df579160b1ff77165be3f6d15a35).

Phạm vi: E7 / trec-covid / MiniLM → MPNet / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S130

`E7-trec-covid-minilm_mpnet-residual_mlp-random-m17-t101-fae4d6cb7bc8` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/E7-trec-covid-minilm_mpnet-residual_mlp-random-m17-t101-fae4d6cb7bc8/7546f6a9b26aad29eb90ef2a48f971d026bd05c4df2d86f10bbb80a7561a3c20).

Phạm vi: E7 / trec-covid / MiniLM → MPNet / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S131

`RUNTIME_PROBE-fever-bge-9dcb1528d669` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-fever-bge-9dcb1528d669/024dfc0e0307290b42c30f7321bb78d35d0ac88c262d2669bc4c9786644478e9).

Phạm vi: RUNTIME_PROBE / fever / BGE base → M3 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 79; completed marker: True.

### S132

`RUNTIME_PROBE-fever-bge-f30bfe831e03` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-fever-bge-f30bfe831e03/ea67158f027ba96aa9f8c111dfbb76b83c2bc3c3c9f605641615f9ddf55db964).

Phạm vi: RUNTIME_PROBE / fever / BGE base → M3 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 79; completed marker: True.

### S133

`RUNTIME_PROBE-fever-nomic-e43d724dac96` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-fever-nomic-e43d724dac96/6c11924193ce95e80ad37826d44548f1a5d78000e5e59b1646d7712d2442db0c).

Phạm vi: RUNTIME_PROBE / fever / Nomic v1 → v1.5 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 78; completed marker: True.

### S134

`RUNTIME_PROBE-fiqa-minilm_mpnet-de5ba3b4bb6b` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-fiqa-minilm_mpnet-de5ba3b4bb6b/c956ecd2b16c695959eb7ad7f965bff4d4901b548a3b9ea5099845488eb94f46).

Phạm vi: RUNTIME_PROBE / fiqa / MiniLM → MPNet / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 78; completed marker: True.

### S135

`RUNTIME_PROBE-fiqa-nomic-0629746003d1` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-fiqa-nomic-0629746003d1/3ae8c5894e356f6c60e88866b2f9d0ce70ed63ceec584ad45eb7931c1e953bb9).

Phạm vi: RUNTIME_PROBE / fiqa / Nomic v1 → v1.5 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 78; completed marker: True.

### S136

`RUNTIME_PROBE-hotpotqa-arctic-1131c69762bb` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-hotpotqa-arctic-1131c69762bb/b568453259e5966203b6828dafa03d4d85e264d869def143dba1e4fe5e20bbc0).

Phạm vi: RUNTIME_PROBE / hotpotqa / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 78; completed marker: True.

### S137

`RUNTIME_PROBE-hotpotqa-arctic-2f50fa232465` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-hotpotqa-arctic-2f50fa232465/455067c400c6892d01e709799b7e52c6a03c4e34a9ebb60710fd3a2d8bbb0695).

Phạm vi: RUNTIME_PROBE / hotpotqa / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 78; completed marker: True.

### S138

`RUNTIME_PROBE-nq-arctic-e9bb6cc93c4b` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-nq-arctic-e9bb6cc93c4b/38614d4056f6c2192ba6e47c38df347a83dfaca17abf4cfc7a717b50b4e31b82).

Phạm vi: RUNTIME_PROBE / nq / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 78; completed marker: True.

### S139

`RUNTIME_PROBE-nq-bge-6bdf92df61d5` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/RUNTIME_PROBE-nq-bge-6bdf92df61d5/8b5c5f875e84497a522877fa81dd67f8d8fbffecef7de5620d352e7c82471a49).

Phạm vi: RUNTIME_PROBE / nq / BGE base → M3 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 79; completed marker: True.

### S140

`T0-case-fever.bge-197871a92024` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/T0-case-fever.bge-197871a92024/683ca91a2609900a98ac7974145d18beeeec02ff6be64a0c0ae5a68bb378d8d1).

Phạm vi: T0 / fever / BGE base → M3 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 94; completed marker: True.

### S141

`T0-case-fever.nomic-2c29350c14bc` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/T0-case-fever.nomic-2c29350c14bc/730ab077c5337b3b0e62a8b37a9e09689d9d62ee84e3f45675ba17ab0c2cbbb6).

Phạm vi: T0 / fever / Nomic v1 → v1.5 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 93; completed marker: True.

### S142

`T0-case-fiqa.minilm_mpnet-541418396b0f` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/T0-case-fiqa.minilm_mpnet-541418396b0f/7d9012ddfbed9fcf323b8eb4d774085e10ad73df07e1f35ceaa673cc2c5b0980).

Phạm vi: T0 / fiqa / MiniLM → MPNet / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 93; completed marker: True.

### S143

`T0-case-fiqa.nomic-8915fd52e76a` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/T0-case-fiqa.nomic-8915fd52e76a/826aa38c5240f23e2d8b54c8021a3d5c6b99766ced77154f13f985645ae8d9ea).

Phạm vi: T0 / fiqa / Nomic v1 → v1.5 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 93; completed marker: True.

### S144

`T0-case-hotpotqa.arctic-32846d363eaf` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/T0-case-hotpotqa.arctic-32846d363eaf/f47a48d49085954f37fb1a2fae96ddca4b37744eb4e296427333277a0c4593d2).

Phạm vi: T0 / hotpotqa / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 93; completed marker: True.

### S145

`T0-case-nq.arctic-38a7a64b2035` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/T0-case-nq.arctic-38a7a64b2035/ce7b5962c0493015fb29bb0c94cfeb42d2a6f59a22e9b3647421e976c6472736).

Phạm vi: T0 / nq / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 93; completed marker: True.

### S146

`T0-case-nq.bge-b133550f5a16` — [deadgod3005/mixindex-runs-004](https://huggingface.co/datasets/deadgod3005/mixindex-runs-004/tree/4121dc49dd29e08bf303c8d8b4a7db73f73983e1/runs/T0-case-nq.bge-b133550f5a16/33c4452c5eab4f4a3815caa24fd80cc97341926d23b85f0b8f9b49364e9177b0).

Phạm vi: T0 / nq / BGE base → M3 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 94; completed marker: True.

### S147

`E6-aol-ia-arctic-degree-m17-t101-dbfc74cb0c52` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E6-aol-ia-arctic-degree-m17-t101-dbfc74cb0c52/2c961c62f9cbbad619b4af5fe8810fd621bd62fdc09073320a9b979106329c53).

Phạm vi: E6 / aol-ia / Arctic v1 → v2 / MLP / Degree / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 154; completed marker: True.

### S148

`E6-aol-ia-arctic-greedy-m17-t101-6e116e9ade54` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E6-aol-ia-arctic-greedy-m17-t101-6e116e9ade54/087a0d999b9ae66d36de96a2d1f6924b976abc6160d5a99c003d04e2de9292d2).

Phạm vi: E6 / aol-ia / Arctic v1 → v2 / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 155; completed marker: True.

### S149

`E6-aol-ia-arctic-random-m17-t101-6d82ad3b6b42` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E6-aol-ia-arctic-random-m17-t101-6d82ad3b6b42/39efecf3a85fef58f29cecb904d25db6b5987a5ab62492e1aada8be655d54c32).

Phạm vi: E6 / aol-ia / Arctic v1 → v2 / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 154; completed marker: True.

### S150

`E6-aol-ia-arctic-read-m17-t101-5b343ecaa50f` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E6-aol-ia-arctic-read-m17-t101-5b343ecaa50f/d0eb52ddc1335555bbd18d31936c417a7b9de41f0173e4b60851c94485ebc22b).

Phạm vi: E6 / aol-ia / Arctic v1 → v2 / MLP / Read / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 155; completed marker: True.

### S151

`E7-fever-bge-op-greedy-m17-t101-32184a73f105` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fever-bge-op-greedy-m17-t101-32184a73f105/9d73d0d150ca283f7b386cd0588dbc6fab13a9c42edd7fe733c1b2701c15fb7f).

Phạm vi: E7 / fever / BGE base → M3 / OP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S152

`E7-fever-bge-residual_mlp-greedy-m17-t101-dc4a3fc901cf` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fever-bge-residual_mlp-greedy-m17-t101-dc4a3fc901cf/641396e621d5162d57aab8a4be608ebc3701caf0ab15248b2fb1f9bf40c36413).

Phạm vi: E7 / fever / BGE base → M3 / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S153

`E7-fever-bge-residual_mlp-random-m17-t101-ef1d95a51b3e` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fever-bge-residual_mlp-random-m17-t101-ef1d95a51b3e/d432a132480d1783c42d981a900589244833aac9761e78c2d756739a3f1006b2).

Phạm vi: E7 / fever / BGE base → M3 / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S154

`E7-fever-nomic-op-greedy-m17-t101-2c5df6d2a0a4` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fever-nomic-op-greedy-m17-t101-2c5df6d2a0a4/23dc01bfe9eb8445fb0ac673af3891f5cf0f07f54fe0c70d3a7d8f19a79962b1).

Phạm vi: E7 / fever / Nomic v1 → v1.5 / OP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S155

`E7-fever-nomic-residual_mlp-greedy-m17-t101-8da408168677` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fever-nomic-residual_mlp-greedy-m17-t101-8da408168677/699202fcec25c327fa3b26cbea1e21d18ef66c7b0484bd8883eac5c2fc8048c9).

Phạm vi: E7 / fever / Nomic v1 → v1.5 / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S156

`E7-fever-nomic-residual_mlp-random-m17-t101-94af0274cce5` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fever-nomic-residual_mlp-random-m17-t101-94af0274cce5/e4a1497f87af5e6c71100fab7b7cc95d323e97bcac793ffc040394efb53fec56).

Phạm vi: E7 / fever / Nomic v1 → v1.5 / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S157

`E7-fiqa-nomic-residual_mlp-greedy-m17-t101-380e4313f65f` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fiqa-nomic-residual_mlp-greedy-m17-t101-380e4313f65f/bf05515805be2488aa63c4e34e8990c1bffd02df650f822a2009bb545da74e26).

Phạm vi: E7 / fiqa / Nomic v1 → v1.5 / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S158

`E7-fiqa-nomic-residual_mlp-random-m17-t101-006947a5b14b` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-fiqa-nomic-residual_mlp-random-m17-t101-006947a5b14b/211d5f4071d620faa1a19ec2700f81f7d39d77f2d9cf4458b27206974404f5e7).

Phạm vi: E7 / fiqa / Nomic v1 → v1.5 / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S159

`E7-hotpotqa-arctic-residual_mlp-greedy-m17-t101-36e13d9e8eed` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-hotpotqa-arctic-residual_mlp-greedy-m17-t101-36e13d9e8eed/43a637c6fad87ec5cd204bf19d54de5249d175c24c9b62f99c948e3f3d30cf4e).

Phạm vi: E7 / hotpotqa / Arctic v1 → v2 / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S160

`E7-hotpotqa-arctic-residual_mlp-random-m17-t101-2de2ee7a8a3b` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-hotpotqa-arctic-residual_mlp-random-m17-t101-2de2ee7a8a3b/90d8b372ac82d6c45ebc0ce81bca948592f174f6b58f578d804f0ad67533e9a6).

Phạm vi: E7 / hotpotqa / Arctic v1 → v2 / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S161

`E7-nq-arctic-op-greedy-m17-t101-2d8b03d48387` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-nq-arctic-op-greedy-m17-t101-2d8b03d48387/eaecd61b23dd13a8b01872a2acbc937dc43cccf69280c21db93c6e3fb401510a).

Phạm vi: E7 / nq / Arctic v1 → v2 / OP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S162

`E7-nq-arctic-residual_mlp-greedy-m17-t101-69e152858f2e` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-nq-arctic-residual_mlp-greedy-m17-t101-69e152858f2e/ab647353122ef933eb46aae79cd63ec622428f73921cdc63f5573b47b9572ca0).

Phạm vi: E7 / nq / Arctic v1 → v2 / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 2; manifest entries: 143; completed marker: True.

### S163

`E7-nq-bge-residual_mlp-greedy-m17-t101-83a7f24390f5` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-nq-bge-residual_mlp-greedy-m17-t101-83a7f24390f5/10672c9abbc5c68086b99be015b1bb92f279a058557c158e3a17e9c4f1e2b20d).

Phạm vi: E7 / nq / BGE base → M3 / MLP / Greedy / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S164

`E7-nq-bge-residual_mlp-random-m17-t101-be6f76d742d0` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/E7-nq-bge-residual_mlp-random-m17-t101-be6f76d742d0/9ae852d96021ee2f71392d7a4cca931e0fa4585eb997fa6ca1bd1d0fa24391b4).

Phạm vi: E7 / nq / BGE base → M3 / MLP / Random / seed 17. Được dùng trong tập hiện hành.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 143; completed marker: True.

### S165

`RUNTIME_PROBE-aol-ia-arctic-c4210cd04207` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/RUNTIME_PROBE-aol-ia-arctic-c4210cd04207/07fbc3df349812f87d53925400094c818c70009de7def9a1787ace2fe3bac49a).

Phạm vi: RUNTIME_PROBE / aol-ia / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 81; completed marker: True.

### S166

`T0-case-aol-ia.arctic-29683b205745` — [deadgod3005/mixindex-runs-005](https://huggingface.co/datasets/deadgod3005/mixindex-runs-005/tree/49d75f8f6919f07f074abe8f6f4a667352cff026/runs/T0-case-aol-ia.arctic-29683b205745/8b979ee14293045d5478ff6cd91f1dc52205c09fb6c137589a1031bfe0e0639d).

Phạm vi: T0 / aol-ia / Arctic v1 → v2 / MLP / Random / seed 17. Giữ để tham khảo/phát triển/lịch sử, không gộp primary.
Summary status: `COMPUTE_DONE`. Parts: 1; manifest entries: 96; completed marker: True.

## Mã nguồn và cấu hình local đã kiểm tra

Đã đọc/kiểm tra tĩnh toàn bộ Python package, scripts và tests; parse tất cả config/job/profile và tài liệu trong codex. Core scientific code được so với source snapshots của các stage đang report. Tập local thống kê 109 tệp văn bản / 26243 dòng, không gồm `.env` hay nội dung credentials. Bảng dưới là coverage file-level, không tuyên bố test suite đã chạy trên Windows.

| Tệp | Dòng | Nội dung được kiểm tra |
|---|---|---|
| src/mixindex/__init__.py | 3 | tài liệu/phương pháp |
| src/mixindex/calibration.py | 138 | Calibration, fit_score_calibration, compute_radius, calibrate_scores, fit_with_roles, make_calibration_proposal, validate_calibration_pools, score_shadow_pairs, refresh_calibration |
| src/mixindex/cli.py | 253 | main |
| src/mixindex/config.py | 193 | project_root, load_runtime_env, _merge, load_config, validate_config, redacted_config, config_hash, tuning_policy, load_tuning_profiles, freeze_tuning_profile, validate_tuning_profile |
| src/mixindex/data/__init__.py | 1 | tài liệu/phương pháp |
| src/mixindex/data/download.py | 138 | dataset_spec, verify_source_file, download_file, extract_beir, download_dataset |
| src/mixindex/data/prepare.py | 513 | iter_source_documents, _iter_aol_log_records, _iter_aol_recovered_documents, _select_aol_documents, _aol_user_cluster, _write_aol_parquet, prepare_aol_dataset, validate_prepared, prepare_dataset, open_validated_data |
| src/mixindex/data/publish.py | 624 | verify_document_parquet, stage_document_parquet, _copy_scale_files, _verify_scale_sources, stage_scale_payload, stage_aol_payload, _aol_card, _scale_card, publish_scale_dataset, publish_aol_dataset, publish_dataset |
| src/mixindex/data/scale.py | 326 | _artifact_manifest, _empty_qrels, _write_rows, _prepare_msmarco, _read_dev_normalized, _write_orcas_query_rows, _write_orcas_source_queries, _write_orcas_edges, _prepare_orcas, prepare_scale_dataset |
| src/mixindex/data/splits.py | 102 | normalize_query, stable_key, group_queries, build_static_splits, sample_document_pools, finalize_calibration_pools |
| src/mixindex/data/store.py | 140 | Document, document_text, DocumentStore, RowSubsetDocumentStore, build_document_store |
| src/mixindex/encoders.py | 240 | model_specs, resolve_model, EncoderAdapter, build_encoder, validate_vectors, smoke_encoder |
| src/mixindex/evaluation.py | 126 | StaticEvaluator, agreement_at_10, ndcg_hit_nfr, retained_metric, quality_auc, paired_analysis, holm |
| src/mixindex/experiments.py | 1032 | source_hash, finalize_run, _encode_subset, select_map_hyperparameters, hardware_identity, _completed_prerequisite, run_e0, build_presetup_tasks, estimate_experiment_time, _run_case_trec_presetup, run_presetup, run_encoder_probes, run_e1, run_core_smoke, _run_static_smoke |
| src/mixindex/experiments_e4.py | 513 | _scale_paths, _profile_context, _run_dir, _peak_rss_bytes, _artifact_hash, _write_header, _subset_probe, _encode_full_vectors, _full_bootstrap, _restore_footprint, run_scale_task, build_scale_tasks |
| src/mixindex/experiments_e5.py | 573 | _peak_rss_bytes, _scale_pipeline_hash, _find_verified_e4_parent, _find_parent_release_attestation, _find_verified_e4_tail, _query_context, _common_calibration, _reference_rows, _arr_at_10, _write_events, _run_dir, run_e5_cell, _cost, build_e5_tasks |
| src/mixindex/experiments_e6.py | 603 | _peak_rss_bytes, _load_case_profile, _load_temporal_events, _group_query_records, _encode_temporal_queries, _gpu_top10, _history_traffic, _temporal_step, _evaluate_week, _user_block_bootstrap, _day_sensitivity, run_e6_cell, build_e6_tasks |
| src/mixindex/experiments_e7.py | 803 | _peak_rss_bytes, case_scope, case_manifest_path, _select_role, freeze_case_manifest, _validate_case_manifest, load_case_manifest, _case_inputs, _case_vector_store, _query_records, _encode_queries, _read_qrels, _schedule_traffic, run_case_presetup, _scale_parent, _load_profile, _verified_case_t0_task, _run_id, run_e7_cell, build_e7_tasks |
| src/mixindex/experiments_scale.py | 333 | _scale_paths, _scale_inputs, _uniform_subset, _encode_rows, _query_records, _traffic_proxies, _encode_queries, _run_scale_scheduler_probe, run_scale_presetup |
| src/mixindex/experiments_static.py | 589 | compact_e2_cell_count, _profile_context, _old_vectors, _common_bootstrap, _variant_config, _accessor, _development_traffic, run_static_preflight, _preflight_for_cell, _build_evaluator, run_static_cell, build_static_tasks |
| src/mixindex/experiments_systems.py | 418 | _absolute, _complete_checkpoint, _snapshot_context, _record_fidelity, _make_hnsw, _save_restore, _exact_task, _hnsw_task, _cadence_task, _synchronized_and_failure_task, run_systems_task, _find_verified_task, build_systems_tasks |
| src/mixindex/hf_sync.py | 444 | ArtifactBundle, SyncError, get_hf_client, _safe_relative, _inventory, collect_run_artifacts, prepare_bundle, choose_upload_repo, ensure_repo, _retry, upload_bundle, verify_remote_bundle, update_remote_catalog, auto_sync_experiment, restore_run, source_files, snapshot_source, sync_self_test |
| src/mixindex/index.py | 308 | ReadWriteLock, SearchResult, ExactIndex, HnswIndex, load_index, validate_ann_snapshot, select_search_config |
| src/mixindex/io.py | 56 | digest, file_digest, atomic_bytes, write_json, read_json, file_lock |
| src/mixindex/maps.py | 273 | normalize, LinearMap, fit_op, ResidualMap, LowRankAffine, transform_global, fit_global_map, fit_la, save_map_state, load_map_state, choose_region_count, fit_regions, RegionalStatistics, map_documents, regional_validation_errors |
| src/mixindex/migration.py | 311 | MigrationState, bootstrap_migration, commit_backfill, maybe_refit_and_remap, emit_checkpoint, restore_migration, refresh_scheduling_snapshot, run_migration |
| src/mixindex/model_formats.py | 76 | convert_reviewed_checkpoint |
| src/mixindex/nomic_adapter.py | 216 | _sha256, verify_code_snapshot, _load_reviewed_modules, pool_nomic, NomicEncoderAdapter |
| src/mixindex/progress.py | 54 | mark_module_complete, update_checklist, remove_checklist |
| src/mixindex/queue.py | 387 | _requires_remote_sync, validate_jobs, load_jobs, enqueue_tasks, process_alive, reconcile_after_restart, probe_capacity, can_admit, launch_task, prepare_task, run_single, run_queue |
| src/mixindex/runtime.py | 318 | _read, _cpus, _reclaimable_file_bytes, effective_limits, probe_hardware, target_hardware_matches, require_target_hardware, probe_storage, probe_encoder, probe_threads, cost_scope |
| src/mixindex/scale_manifest.py | 145 | default_manifest_path, manifest_path, _parent_rows, freeze_common_manifest, load_common_manifest |
| src/mixindex/scheduling.py | 167 | build_candidate_sets, marginal_gain, select_random, select_greedy, select_degree, choose_batch_cap, SchedulingTraffic, select_on_read |
| src/mixindex/vectors.py | 369 | vector_cache_key, VectorStore, RowSubsetVectorStore, encode_corpus, encode_query_pool, PaidEmbeddingAccessor |
| tests/test_adaptive_schedulers.py | 79 | test_on_read_preserves_pending_order_across_capped_batches, test_all_primary_schedulers_resume_and_refresh_only_needed_queries, test_scheduler_traffic_rejects_wrong_role_or_nonfinite_weights, test_search_selection_needs_all_variants_and_never_calls_transfer_a_pass |
| tests/test_aol_prepare.py | 129 | _fixture_config, _write_fixture_source, test_aol_recovery_parser_publishes_capped_temporal_release, test_e6_primary_sensitivity_uses_user_blocks_and_days |
| tests/test_calibration_bootstrap.py | 119 | calibrated_fixture, test_primary_bootstrap_calibration_is_paid_disjoint_and_refreshed, test_calibration_off_has_same_paid_pools_and_identity_residual_radius, test_common_op_proposal_respects_actual_raw_ranks_and_pools |
| tests/test_contracts.py | 317 | test_config_rejects_unknown_or_inconsistent_settings, test_query_groups_and_priority_block_text_leakage, test_calibration_document_pools_are_disjoint_and_bounded, test_document_lookup_preserves_requested_rows_and_duplicate_policy, test_archive_rejects_traversal_and_truncation, test_accessor_checks_entire_request_before_source_and_unique_union, test_failed_accessor_keeps_granted_ids_on_restart, test_procrustes_known_isometry_and_roundtrip, test_learned_map_checkpoint_load_preserves_outputs, test_ |
| tests/test_dataset_publication.py | 79 | test_document_publication_preserves_rows_text_and_file_boundaries, test_scale_publication_payload_preserves_validated_release_and_source_hash, test_orcas_source_record_is_verified_from_manifest_metadata |
| tests/test_migration_evaluation.py | 83 | test_migration_resume_pending_stats_prefix_and_completion, test_checkpoint_detects_corrupted_state_before_serving, test_standard_ndcg_hit_nfr_zero_query_population, test_agreement_auc_and_paired_inference_units |
| tests/test_nomic_adapter.py | 22 | test_nomic_pooling_masks_padding_and_normalizes, test_nomic_code_revision_is_pinned_before_files_are_loaded |
| tests/test_presetup.py | 177 | test_bounded_lr_grid_selects_using_only_paid_validation, test_scope_profile_and_hardware_gates_and_immutable_merge, test_profile_content_tampering_fails_before_admission, test_presetup_dag_orders_inputs_correctness_runtime_and_freeze, test_forecast_preserves_unknown_costs_and_never_divides_by_concurrency, test_core_presetup_freezes_real_maps_and_restores_without_reading_test_labels |
| tests/test_progress.py | 30 | _read_checklist, test_checklist_keeps_only_compute_and_verified_rows |
| tests/test_query_cache_and_sources.py | 100 | test_query_cache_checks_identity_order_and_integrity, test_new_profiles_and_queued_jobs_do_not_change_closed_scientific_source, test_corpus_encoding_resumes_only_verified_contiguous_shards |
| tests/test_queue.py | 145 | job, capacity, test_dynamic_enqueue_preserves_live_jobs_and_checks_combined_graph, test_admission_uses_effective_limits_remaining_reservations_and_headroom, test_exclusive_jobs_dependencies_target_and_joint_probe_are_independent, test_validated_setup_dependency_does_not_require_artifact_upload, test_scientific_dependency_still_requires_verified_upload, test_pid_birth_time_and_compute_signal_prevent_duplicate_restarts, test_dead_worker_keeps_compute_and_marks_sync_pending, test_failed_dependency_ |
| tests/test_runtime_and_serving.py | 94 | test_token_bucketing_preserves_rows_and_reports_actual_padded_batches, test_runtime_probe_records_oom_and_restores_runtime_settings, test_readers_never_observe_new_vector_with_old_fidelity_or_calibration |
| tests/test_scale_data.py | 73 | _paths, test_scale_ingest_preserves_body_tabs_and_joins_qrels, test_orcas_groups_deduplicate_edges_and_respect_document_join |
| tests/test_static_experiments.py | 176 | test_evaluator_owns_reference_and_emits_only_a_technical_gate, _fixture, test_static_preflight_and_official_cell_keep_test_labels_out_until_preflight, test_static_matrix_has_all_declared_cells_and_concrete_dependencies |
| tests/test_sync_failures.py | 85 | test_account_quota_does_not_retry_or_allocate_repositories, test_failed_verification_has_no_completed_marker_and_retries_same_destination, test_source_snapshot_closes_before_run_and_is_never_overwritten, test_transient_connection_failures_have_bounded_retries, test_existing_project_repository_must_match_configured_visibility |
| scripts/advance_aol_pipeline.py | 173 | _now, _write_progress, _log, _recovery_status, _cli, _run, _verified_case_t0, _enqueue_and_run_e6, _main_locked, main |
| scripts/ci-tests.yml | 31 | configuration/job/profile |
| scripts/download_aol_http.py | 168 | _take_request_delay, _retry_after_seconds, _sleep_after_success, _sleep_after_error, _http_wayback_get, _run_pinned_downloader |
| scripts/log_aol_recovery.py | 76 | _snapshot, main |
| scripts/select_aol_recovery_candidates.py | 107 | _key, select_candidates, main |
| scripts/setup.sh | 13 | tài liệu/phương pháp |
| configs/base.yaml | 119 | configuration/job/profile |
| configs/datasets.yaml | 64 | configuration/job/profile |
| configs/experiments/core_smoke.yaml | 6 | configuration/job/profile |
| configs/experiments/e0.yaml | 2 | configuration/job/profile |
| configs/experiments/e1.yaml | 13 | configuration/job/profile |
| configs/experiments/e2.yaml | 19 | configuration/job/profile |
| configs/experiments/e3.yaml | 17 | configuration/job/profile |
| configs/experiments/e4.yaml | 24 | configuration/job/profile |
| configs/experiments/e5.yaml | 34 | configuration/job/profile |
| configs/experiments/e6.yaml | 33 | configuration/job/profile |
| configs/experiments/e7.yaml | 29 | configuration/job/profile |
| configs/experiments/t0.yaml | 4 | configuration/job/profile |
| configs/jobs-compact.yaml | 4137 | configuration/job/profile |
| configs/jobs-e3.yaml | 214 | configuration/job/profile |
| configs/jobs-e4-resume-20261023.yaml | 87 | configuration/job/profile |
| configs/jobs-e4-retry.yaml | 130 | configuration/job/profile |
| configs/jobs-e4-speed.yaml | 146 | configuration/job/profile |
| configs/jobs-e4-stream.yaml | 132 | configuration/job/profile |
| configs/jobs-e4-v3.yaml | 155 | configuration/job/profile |
| configs/jobs-e4.yaml | 146 | configuration/job/profile |
| configs/jobs-e6-retry.yaml | 161 | configuration/job/profile |
| configs/jobs-e6.yaml | 250 | configuration/job/profile |
| configs/jobs-e7.yaml | 1585 | configuration/job/profile |
| configs/locked/tuning.lock.yaml | 1775 | configuration/job/profile |
| configs/models.yaml | 72 | configuration/job/profile |
| codex/01_environment.md | 53 | tài liệu/phương pháp |
| codex/02_download_data.md | 48 | tài liệu/phương pháp |
| codex/03_preprocess_splits.md | 64 | tài liệu/phương pháp |
| codex/04_models_embeddings.md | 51 | tài liệu/phương pháp |
| codex/05_maps_calibration.md | 66 | tài liệu/phương pháp |
| codex/06_index_serving.md | 44 | tài liệu/phương pháp |
| codex/07_scheduler_migration.md | 82 | tài liệu/phương pháp |
| codex/08_evaluation_baselines.md | 69 | tài liệu/phương pháp |
| codex/09_experiments.md | 70 | tài liệu/phương pháp |
| codex/10_queue_resources_resume.md | 62 | tài liệu/phương pháp |
| codex/11_huggingface_sync.md | 77 | tài liệu/phương pháp |
| codex/12_tests_acceptance.md | 53 | tài liệu/phương pháp |
| codex/13_runbook.md | 127 | tài liệu/phương pháp |
| codex/14_presetup_tuning.md | 96 | tài liệu/phương pháp |
| codex/15_run_budget.md | 57 | tài liệu/phương pháp |
| codex/16_e567_downscale.md | 171 | tài liệu/phương pháp |
| codex/constraints.md | 60 | tài liệu/phương pháp |
| codex/contracts.md | 75 | tài liệu/phương pháp |
| codex/plan.md | 178 | tài liệu/phương pháp |
| codex/README.md | 41 | tài liệu/phương pháp |
| codex/structure.md | 119 | tài liệu/phương pháp |
| README.md | 140 | tài liệu/phương pháp |
| report.md | 763 | tài liệu/phương pháp |
| expect.md | 235 | tài liệu/phương pháp |
| checklist.md | 672 | tài liệu/phương pháp |
| pyproject.toml | 36 | tài liệu/phương pháp |
| requirements.lock.txt | 63 | tài liệu/phương pháp |
| LICENSE | 21 | tài liệu/phương pháp |
| .gitignore | 235 | tài liệu/phương pháp |
