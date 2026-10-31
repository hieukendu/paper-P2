# Vị trí so với công trình gần nhất

Đây là focused literature scan, không phải systematic review hay chứng nhận không có prior art. Đã đọc toàn văn hai công trình sát nhất; các mục khác đã đối chiếu metadata/abstract từ nguồn gốc. Khi viết không dùng “first” từ phạm vi đọc này.

| Công trình và nguồn gốc | Điều đã có | Quan hệ với study này | Điều không được tuyên bố |
|---|---|---|---|
| [Drift-Adapter, EMNLP 2025](https://aclanthology.org/2025.emnlp-main.805/) | Query-side adaptation về old space; OP, LA, MLP; paired embeddings | Là đối chứng gần cho lựa chọn giữ index cũ khi chuyển query encoder | Không gọi forward document OP của repo là implementation đầy đủ của Drift-Adapter |
| [Embedding-Converter, ACL 2025](https://aclanthology.org/2025.acl-long.1237/) | Document embedding conversion; **Appendix D.3, Tables 13–14 đã thử 50% converted + 50% true embeddings** | Prior art trực tiếp của mixed representation; cần trích rõ ở introduction/method | Không coi mixed converted/true index là novelty mới; không đổi residual MLP hiện tại thành tên baseline này |
| [When Embedding Models Meet: Procrustes Bounds and Applications](https://arxiv.org/abs/2510.13406) | Phân tích hình học của Procrustes alignment | Nền cho alignment và giới hạn compatibility | Không nhận các bounds đó thành guarantee cho pipeline regional/calibrated hiện tại |
| [mini-vec2vec: Scaling Universal Geometry Alignment with Linear Transformations](https://arxiv.org/abs/2510.02348) | Geometry alignment bằng linear transformations | Nhắc ngắn bối cảnh alignment; khác giả thiết paired supervision | Không gọi alignment là mới hoặc so số khác benchmark trực tiếp |
| [Embedding Surgery](https://arxiv.org/abs/2609.05110) | Localized updates cho ranking correction | Phân biệt mục tiêu sửa ranking và thay frozen embedding model | Không đồng nhất với backfill policy đã chạy |
| [Residual Reachability for Cross-Model Graph-Index Migration](https://arxiv.org/abs/2609.23036) | Tái dùng cấu trúc graph để xây index khi model thay đổi | Có thể liên quan index migration, nhưng khác bài toán giới hạn target-vector access | Không dùng kết quả graph construction để suy encoder savings của study này |

Các bài nền dữ liệu: [BEIR](https://arxiv.org/abs/2104.08663), [ORCAS](https://microsoft.github.io/msmarco/ORCAS), [AOL-IA](https://ir-datasets.com/aol-ia.html). Cần cite HNSW và encoder/model cards đúng phiên bản trong draft.

## Gap có thể bảo vệ

Study khảo sát **đồng thời judged relevance, agreement và diễn biến budget của gradual replacement**, cùng các backfill policies, workload scopes và trường hợp thiếu selection signal. Đây là câu hỏi thực nghiệm hẹp hơn việc phát minh conversion hoặc mixed embeddings.

Khoảng cách relevance–agreement tự nó không phải nguyên lý mới: target encoder và relevance judgments vốn khác nhau. Phần có thể hữu ích là quy mô của sự khác biệt, policy ranking reversal dưới controls, mức degradation so với hệ cũ, và điều kiện mà một policy thực chất chỉ chạy fallback. Paper phải trả lời “người vận hành học được điều gì cụ thể?” bằng số đo, không chỉ nhắc lại hai metric khác định nghĩa.

## Baseline còn thiếu

Ưu tiên một query-side OP adapter trên FiQA từ các paired vectors sẵn có, so ở cùng total target-document access và cùng test queries. Đây chỉ là baseline thuộc họ query adaptation; muốn gọi là Drift-Adapter phải theo đúng orientation, preprocessing, train/validation, calibration và selection procedure của bài gốc, đồng thời nêu mọi budget adaptation.

Embedding-Converter đầy đủ là đối chứng tiếp theo nếu tài nguyên cho phép. Phân biệt faithful reproduction với budget-matched adaptation. Chi phí encoder training hoặc pretraining của công trình gốc không được cộng/trừ tùy ý để tạo lợi thế. Nếu chưa chạy thì ghi giới hạn, không đưa bảng “dự đoán kết quả”.

Không cần mở rộng literature thành một catalog dài. Hai công trình trực tiếp phải được giải thích rõ và công bằng; các công trình còn lại chỉ giữ khi giúp hiểu giả thiết hoặc phân biệt bài toán.
