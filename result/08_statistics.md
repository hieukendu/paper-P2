# Thống kê tính lại từ dữ liệu đã có

Phân tích ngày 30/10/2026; không training hay inference mới. Dùng đúng công thức trong `evaluation.py`: mean mỗi query qua ba map seeds trước, paired query-group bootstrap 10.000 draws, seed 20261020; paired sign-flip hai phía; Holm trong ba contrast greedy−random/degree/read của từng endpoint FiQA. Bootstrap là bất định query **có điều kiện trên seed design và corpus đã chọn**, không phải CI qua corpus/model/population.

Các contrast scheduler nDCG ở 10% theo family đã đặt trong protocol cũ; ARR scheduler là endpoint hỗ trợ. OP−MLP, partial−old, Nomic new−old và Read−Random temporal là tái phân tích bổ sung **exploratory**, không giả thành các giả thuyết chính đã preregister. Không chọn ngưỡng tương đương sau khi xem kết quả; CI cắt 0 không chứng minh bằng nhau.

| Stage | Contrast | Metric | Accessed fraction | Mean effect | CI95% low | CI95% high | p raw | p Holm | Family |
|---|---|---|---|---|---|---|---|---|---|
| E2 | greedy - random | ndcg_at_10 | 0.100000 | -0.002111 | -0.012561 | 0.008154 | 0.693731 | 1.000000 | E2 scheduler ndcg_at_10 |
| E2 | greedy - degree | ndcg_at_10 | 0.100000 | 0.044691 | 0.036279 | 0.053394 | 0.000100 | 0.000300 | E2 scheduler ndcg_at_10 |
| E2 | greedy - read | ndcg_at_10 | 0.100000 | -0.002697 | -0.016090 | 0.010452 | 0.688931 | 1.000000 | E2 scheduler ndcg_at_10 |
| E2 | greedy - random | arr_at_10 | 0.100000 | -0.000463 | -0.006224 | 0.005248 | 0.865713 | 0.865713 | E2 scheduler arr_at_10 |
| E2 | greedy - degree | arr_at_10 | 0.100000 | -0.019599 | -0.027572 | -0.011934 | 0.000100 | 0.000300 | E2 scheduler arr_at_10 |
| E2 | greedy - read | arr_at_10 | 0.100000 | -0.030864 | -0.039199 | -0.022479 | 0.000100 | 0.000300 | E2 scheduler arr_at_10 |
| E2 | OP - MLP | ndcg_at_10 | 0.100000 | 0.012778 | 0.005341 | 0.020484 | 0.001000 | N/A | exploratory |
| E2 | OP - MLP | arr_at_10 | 0.100000 | 0.008745 | 0.003292 | 0.014095 | 0.001400 | N/A | exploratory |
| E2 | MLP random - old | ndcg_at_10 | 0.100000 | -0.088668 | -0.109429 | -0.068681 | 0.000100 | N/A | exploratory |
| E2 | MLP random - old | ndcg_at_10 | 0.500000 | -0.002979 | -0.025749 | 0.018941 | 0.803820 | N/A | exploratory |
| E7 | Nomic full new - old | ndcg_at_10 | 1.000000 | -0.003736 | -0.014315 | 0.006829 | 0.479652 | N/A | exploratory |


Không viết p=0. Giá trị Monte Carlo nhỏ nhất ở đây là 1/10001; precision số lẻ trong bảng không hàm ý precision thực nghiệm tương ứng. Các CI95% là marginal percentile bootstrap, không phải simultaneous confidence bands sau multiple testing.

**Kết luận được hỗ trợ:** không có lợi thế nDCG rõ của greedy so random/read trên FiQA ở 10%; greedy có nDCG cao hơn degree nhưng ARR thấp hơn degree. OP-based pipeline có nDCG cao hơn MLP-based pipeline trong FiQA exact study; kết quả này là mô tả/phân tích bổ sung, không chứng minh tất cả OP tốt hơn MLP.

**E5:** không có per-query output, do đó không tính paired-query CI/significance. Chỉ ba map-seed values/ranges. Không coi seed×query hoặc checkpoint×query là iid.

**E6:** tính lại weekly record-weighted ARR từ toàn bộ bảng per-group và weights, khớp summaries trong sai số float. Paired user-block Read−Random tuần 8 có effect 0,009418, CI95% [0,006696; 0,012306], 4.563 blocks và 10.000 draws, seed 1101; giới hạn một chronology. Không dùng CI marginal từng method để suy paired significance.

Kiểm tra cấu trúc tất cả 99 bảng metrics (1.074.908 dòng): finite, giá trị trong [0,1], không duplicate query/checkpoint ở schema áp dụng. Các exact completion hiện hành E2/E7 khớp reference. Tính lại riêng 24 E2 rankings + qrels cho 110.064 dòng, cả nDCG/Hit/NFR/ARR đều khớp; không coi đó là tái chạy toàn pipeline trên GPU.
