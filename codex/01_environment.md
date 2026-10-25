# M01 — Environment, config và probes

Đọc [constraints.md](constraints.md) và [contracts.md](contracts.md). Output là môi trường Linux chạy được MiniLM/MPNet trên **H100 80GB**, chưa cần full corpus.

## File cần code

`pyproject.toml`, `.env.example`, `configs/base.yaml`, `src/mixindex/config.py`, `runtime.py`, `cli.py`. Cập nhật `.gitignore` để ignore `data/`, `cache/`, `runs/`, `state/`, `staging/`, `.env*` nhưng cho phép `.env.example`; không ignore configs, source, lock và checklist.

Python 3.11 là target ban đầu. Dependencies: numpy, scipy, torch, transformers, sentence-transformers, huggingface_hub, safetensors, scikit-learn, hnswlib, pyarrow, PyYAML, python-dotenv, psutil, nvidia-ml-py, pytest; thêm `ir_datasets` khi làm E6. Không cài vLLM hoặc training framework cho encoder. Chọn torch/CUDA phù hợp **driver của server H100 thật**, smoke rồi ghi exact versions vào `requirements.lock.txt`. Không copy CUDA12.4 từ inventory H100 khác. Không dùng lệnh upgrade tự do khi rerun.

HNSW target là tag `v0.9.0`; resolve commit từ upstream, build và pin. Nếu tag/build không khả dụng thì E0 báo lỗi dependency, không âm thầm dùng latest hoặc một phiên bản khác.

## Config và `.env`

Base config phải đủ các nhóm: `paths`, `dataset`, `models`, `splits`, `mapping`, `calibration`, `search`, `scheduler`, `budget`, `evaluation`, `execution`, `tuning`, `sync`. YAML `experiments/eN.yaml`/`t0.yaml` chỉ override giá trị khác base, resolve thành một `config.lock.json`/run. Tuning policy/profile hash được lưu cùng run config hash theo M14, không yêu cầu mọi experiment dùng cùng run hash.

`.env.example` chỉ chứa:

```dotenv
HF_TOKEN=
HF_NAMESPACE=
MIXINDEX_DATA_ROOT=
MIXINDEX_CACHE_ROOT=
MIXINDEX_RUNS_ROOT=
```

Namespace rỗng thì lấy `whoami().name` từ token lúc sync; path rỗng dùng các thư mục relative project. Repo prefix/private/cap đặt trong YAML, không coi credential là hyperparameter. Dùng `.env` project explicit; env hiện có ưu tiên. Không dump `os.environ`.

## Hàm cần implement

| Hàm | Việc phải làm | Hàm tiếp theo sử dụng |
|---|---|---|
| `project_root(start: Path) -> Path` | Tìm `pyproject.toml`/repo root; resolve CLI root override | config, progress, env loader |
| `load_runtime_env(root: Path) -> None` | Đọc đúng `.env`, không log secret; không dùng `find_dotenv` dò sang project khác | HF auth/path overrides |
| `load_config(path, overrides=None) -> dict` | Merge base rồi experiment, validate keys, resolve paths; unknown key fail | experiments/runner |
| `validate_config(cfg) -> None` | Cross-check dim, endpoint, mode, cap, split/data name; không sửa âm thầm | trước run |
| `redacted_config(cfg) -> dict` | Chỉ export keys được phép, bỏ token/secret/path credential | config.lock/upload |
| `probe_hardware() -> dict` | GPU nhìn thấy bởi process, tổng/free VRAM, full/MIG, driver, torch CUDA; RAM/CPU **effective cgroup**, disk mount free | environment/admission |
| `effective_limits() -> dict` | Linux cgroup v2 `memory.max`, `memory.current`, `cpu.max`, cpuset; v1 equivalents; lấy min hữu hạn của ancestors/host | queue |
| `probe_storage(work_dir, bytes_to_write) -> dict` | File tạm trong output dir, write+fsync+read, thời gian/bytes; xóa đúng file probe do hàm tạo | E4 gate |
| `probe_encoder(encoder, text_sample, batch_grid) -> dict` | Warmup rồi đo docs/tokens/s, padded/nonpad tokens, peak VRAM/RSS theo độ dài; OOM là probe record | batch sizing/resource requests |
| `cost_scope(name)` | Context manager time.monotonic + CPU time; CUDA synchronize/events trong measurement; aggregate theo component | tất cả module |
| `main(argv=None) -> int` | argparse subcommands theo runbook; gọi module, không chứa scientific code | entrypoint `mixindex` |

GPU model phải lấy từ device thực tế visible cho torch, không chỉ GPU vật lý do `nvidia-smi -L` in ra. Nếu chỉ thấy MIG80/40 slice thì ghi profile; không label full H10080. CPU quota tính `quota/period`; danh sách cpuset128 không có nghĩa job được128 cores. RAM availability lấy min(host available, cgroup headroom).

Probes lưu một lần `state/environment.json`, `state/throughput_probe.json`, `state/storage_manifest.json`, được update khi hardware/config inference thay đổi. Không tạo telemetry service; một bảng record/sample là đủ. Mức headroom và resource policy xem M10.

## Nối vào E0/E4

E0 khóa env/config và test primitive accessor; T0 dùng probes chọn runtime trước official, E4 bổ sung measurements full bootstrap để forecast scale. E0 không bắt phải tải cả AOL hay tám models. Config E0 ghi source/count expectations; manifest thực tế được hoàn tất khi dataset tương ứng chuẩn bị xong. M14 quy định bounded batch/thread grids và stop rule; chưa có joint-throughput probe thì concurrency1.

Nhận module khi CLI `--help`, config load/unknown-key check, CUDA smoke và cgroup probe có kết quả thật; sau đó tick M01 trong root checklist. Không tick E4 chỉ vì probe code tồn tại.
