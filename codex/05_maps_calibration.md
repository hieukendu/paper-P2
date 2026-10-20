# M05 — Maps, regions, calibration

Code `maps.py`, `calibration.py`. Inputs chỉ gồm old vectors và paid train/validation/calibration pairs do accessor trả. Outputs M0, regional state, a/b/r, được migration dùng để map corpus và index rerank.

## Global map functions

| Hàm | Cần code |
|---|---|
| `fit_op(X_train, Y_train) -> GlobalMap` | Procrustes source→target bằng SVD; pad hai phía tới D=max(src_dim,target_dim), transform rồi crop về target_dim; hỗ trợ cả forward và query-side giảm chiều, có save/load |
| `fit_la(X_train, Y_train, X_val, Y_val, cfg)` | `(U V^T + D)x+b`, rank64, U(new,64), V(old,64), rectangular diagonal D(new,old); train/early-stop trên validation như learned-map config |
| `ResidualMap.forward(x)` | `W*x+b + Linear(256,new)(GELU(Linear(old,256)(x)))`; W init OP, b0, residual output layer0 |
| `fit_global_map(kind, pairs, validation, cfg)` | Dispatch OP/LA/residual MLP; không đổi train/val IDs giữa variants |
| `transform_global(model, X, normalize=False)` | Trả **pre-normalization** u=M0(x) cho regional fit; serving normalize sau correction |
| `save_map_state(model, path)` / `load_map_state(path)` | Config shapes + safetensors/NumPy state; model round-trip check |

Dùng convention vectors column cho công thức; implementation batch row `X @ W.T`. Với OP solve `X_padded.T @ Y = U S Vt`, row transform `X_padded @ (U @ Vt)`, nên column W là transpose tương ứng rồi lấy old columns. Test known rotation và384→768/768→1024, không gọi random padding là baseline published.

Tổng quát cho query-side: với D=max(src_dim,target_dim), pad cả X/Y lên D, tính `X_pad.T @ Y_pad = U S Vt`, rồi `transform(X) = (X_pad @ (U @ Vt))[:, :target_dim]`. Forward old_dim≤new_dim giữ nguyên công thức trên; khi fit chiều ngược768→384 hoặc1024→768, không pad một số chiều âm hoặc dùng inverse của forward MLP. Normalize sau transform khi serve theo cùng policy. Tests phải có cả giảm chiều và zero/nonfinite output.

MLP primary: Adam, default lr1e-3, batch256, max50 epochs, no dropout/weight decay; loss mean theo docs của tổng squared error **trước normalize**. Validation checkpoint tốt nhất, patience5, min improvement1e-5. Theo yêu cầu tối ưu trước official, T0 chọn lr trong `{1e-4,1e-3}` bằng **P_val** theo [M14](14_presetup_tuning.md), lưu selected lr/profile hash rồi giữ chung cho các seeds/schedulers của case; không khóa cứng lại1e-3 sau khi đã chọn. LA nhận cùng grid/early-stop effort. OP không có lr; encoder không nhận gradient. Primary map kind vẫn residual MLP, không chọn OP/LA vì test tốt hơn.

## Regional maps và sufficient statistics

```text
R = largest power of two <= min(256, max(1, floor(n_train/100)))
# FiQA8; TREC32; MS MARCO64 theo allocations chuẩn
M_R(x) = A_R * M0(x) + b_R
```

| Hàm | Cần code |
|---|---|
| `choose_region_count(n_train) -> int` | Công thức trên; không mặc định256 cho mọi corpus |
| `fit_regions(old_vectors, cfg) -> RegionState` | MiniBatchKMeans normalized old X, batch4096/max_iter100/n_init3; fit sample uniform≤100k nếu corpus lớn, assign toàn corpus; save centers/IDs/assignments |
| `init_regional_statistics(M0, train_pairs, assignments)` | u=M0(x) chưa normalize, float64; count/numerators per region |
| `add_regional_pairs(stats, rows, X, Y)` | Chỉ train/bootstrap và **new backfill** hợp lệ, không val/cal, không cộng pair đã xử lý lần2 |
| `fit_regional_maps(stats, lambda_=10, min_pairs=20)` | Full affine ridge quanh identity, bias regularized; thiếu20 pair dùng identity correction/global |
| `map_documents(rows, old_vectors, M0, regional, assignments)` | Apply correction→L2 normalize→float32; zero/nonfinite fail theo IDs |
| `regional_validation_errors(state, P_val) -> table` | RMS vector error + sample count/region, không heldout ghi N/A |
| `fit_diagonal_regional(stats, cfg)` | Control bắt buộc của E2: A diagonal + bias, cùng ridge10 quanh identity, counts/pairs/fallback; cùng serving normalize, không gọi đây là full affine primary |

Để code đúng ridge, với ubar=[u;1], C=[A b], C0=[I 0]:

```text
H_R = lambda*I + sum(ubar @ ubar.T)
B_R = lambda*C0 + sum(y @ ubar.T)
C_R = solve(H_R, B_R.T).T
```

Counts, H/B và solves float64; không inverse tường minh; iterate regions để giảm peak memory. Stats được lưu để refit incremental; test bằng fit lại từ đầu trên cùng pairs. Diagonal control giải độc lập ridge2×2 cho mỗi output coordinate trên `[u_j,1]`, prior `[1,0]`, cùng lambda/fallback; global-only dùng identity correction. Primary M0/assignment freeze sau bootstrap, nên cache u không stale. Global-refit chỉ là ablation phải rebuild toàn stats và remap mọi mapped doc.

## Calibration và radius

| Hàm | Cần code |
|---|---|
| `make_calibration_proposal(op_map, cal_queries, old_vectors, caps)` | Common OP raw ranks6–20,≤4 pairs/query,≤1000 pairs/pool, respect disjoint doc pools; orchestration/accessor ở bootstrap |
| `score_shadow_pairs(pair_ids, M0, regional, query_vectors, paid_targets)` | s=dot(h(q), shadow mapped z), t=dot(h(q), true y); phục vụ paid doc true không thay shadow diagnostic |
| `fit_score_calibration(s_fit, t_fit) -> Calibration` | OLS `a=max(1e-6,cov(s,t)/var(s))`, `b=mean(t)-a*mean(s)`; var<1e-12/nonfinite identity+reason |
| `compute_radius(s_check, t_check, a, b, quantile=.95)` | Sort abs(t-(a*s+b)), index ceil(.95*n)-1; không dùng vector RMS thay score radius |
| `calibrate_scores(raw, fidelity, cal)` | Mapped a*raw+b, true raw; không clip[-1,1] |
| `refresh_calibration(state, fixed_pair_ids)` | Chỉ sau regional refit epoch, reuse paid targets; publish cùng index epoch |

Mỗi pool tối thiểu200 pairs/50 query groups để bật calibration/radius chính. Thiếu cal-fit thì identity; nếu cal-check vẫn hợp lệ tính r với identity. Thiếu cal-check thì r=N/A và greedy off→random với nhãn rõ. r=0 thì rescue band rỗng, random fallback, không thêm epsilon giả. `r_vec_region` chỉ diagnostic.

P95 chỉ mô tả pool đã chọn, không là bảo đảm95% trên future corpus. P90/P99 là sensitivity, không tune test. Không chọn bỏ regional/calibration sau khi nhìn test; primary giữ config cố định, kết quả xấu là negative result.

Nhận M05 sau tests OP dimension, incremental/full stats, cal identity/slope bound/r quantile/disjoint pairs và round-trip learned weights. Gói learned states phải được hàm sync M11 nhìn thấy, không chỉ có metrics.
