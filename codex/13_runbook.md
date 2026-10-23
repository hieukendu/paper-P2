# M13 — CLI runbook và wiring cuối

Các lệnh dưới là **giao diện phải implement**, chưa chạy được trong repo hiện tại. Agent phải nối `cli.py` với các module tương ứng rồi mới dùng. Chạy tại project root trên Linux server H10080, dùng `.venv`; không chạy training trên Windows.

## Command surface tối thiểu

```bash
python -m venv .venv
source .venv/bin/activate
# Ở first setup: cài compatible dependencies theo M01, smoke, sau đó lock.
# Ở rerun đã có lock:
python -m pip install -r requirements.lock.txt
python -m pip install -e . --no-deps
mixindex --help
mixindex probe --config configs/base.yaml
mixindex models prepare --pair minilm_mpnet
mixindex data prepare --dataset fiqa
mixindex sync self-test
pytest -q
mixindex run --experiment E0 --config configs/experiments/e0.yaml
mixindex run --experiment E1 --config configs/experiments/e1.yaml
mixindex run --experiment T0 --scope core --config configs/experiments/t0.yaml
```

First setup chưa có requirements lock thì M01 sinh lock sau smoke, không lặp lệnh install file chưa tồn tại. `.env` do user cung cấp trên server, không tạo token mẫu thật; không `cat .env` để kiểm. Lệnh sync self-test upload tiny bundle theo M11, được user yêu cầu trong setup flow.

`models prepare` pin/download và smoke adapter; `data prepare` bao gồm download, archive/digest validation, full ingest/count/schema/join checks, preprocessing và split validation theo M02/M03. Không có subcommand `prepare` chỉ tải vài file rồi đánh VALIDATED. Corpus inference/tuning chỉ sau các bước này. T0 --scope được CLI nối vào `build_presetup_tasks/run_presetup`, không tạo một runner khác. Chưa có core M05–M08/HNSW/tests thì code P3b trước lệnh T0.

## Chạy stage/matrix và chèn task

Official **execution** cần scoped T0 compute + local policy/profile validation; enqueue trước được phép để queue chờ dependencies. T0.sync có thể pending riêng, không được tick sync-complete. Xem M14 để phân biệt run hash với profile hash.

```bash
mixindex data prepare --dataset trec-covid
mixindex run --experiment T0 --scope case.trec-covid.minilm_mpnet --config configs/experiments/t0.yaml
mixindex enqueue --experiment E2 --config configs/experiments/e2.yaml
mixindex queue --jobs configs/jobs.yaml --max-compute-jobs 2
```

Ở terminal khác, có thể thêm task đủ dependency/resource khi queue còn chạy:

```bash
mixindex enqueue --experiment E4 --config configs/experiments/e4.yaml
mixindex status
```

`enqueue` mở rộng matrix theo M09 và ghi queue; nó không tự bỏ dependencies. `run --experiment E5` cũng dùng cùng builder/admission, không bypass resource gate. `--max-compute-jobs 2` là trần, không ép2 GPU jobs nếu thiếu RAM/VRAM/CPU. Benchmark exclusive sẽ đợi host yên, tạm dừng upload nặng.

Parent `run/queue` launch hidden `_worker --task-file <resolved_task.json>`; worker chỉ gọi `run_single`, không gọi lại public `run/queue` để tránh vòng spawn. `queue --jobs` merge job specs vào `state/tasks.json` hiện tại, không thay mất các task vừa enqueue.

## Chuẩn bị scale và case mới

Sau E2/E3 compute, chuẩn bị scope scale trước E4/E5:

```bash
mixindex models prepare --pair arctic
mixindex data prepare --dataset msmarco-docs-v1
mixindex data prepare --dataset orcas
mixindex run --experiment T0 --scope scale --config configs/experiments/t0.yaml
mixindex run --experiment E4 --config configs/experiments/e4.yaml
mixindex enqueue --experiment E5 --config configs/experiments/e5.yaml
```

Registry key `msmarco-docs-v1` phải ánh xạ document v1, `orcas` join đúng corpus đó; không BEIR passage msmarco. Base `compact_v1` dùng E4 subset probes và bootstrap stored graph gate; scale override `e4e567_scale_v3_50k` dùng common 50k/5k manifest và tạo parent E4 artifact mới. Sync worker upload từng completed checkpoint ngoài measurement window.

E4 admission kiểm T0.scale inputs/lr/runtime/subset profile và common v3 manifest hash; reduced E4 tạo reduced-pool search/restore evidence bằng readiness measurements. Với `e4e567_scale_v3_50k`, E5-E7 admission kiểm parent E4 profile/hash và cùng manifest hash. Mỗi comparison preflight các bootstrap seeds/variants trước khi mở test, không tune lại riêng một cell sau khi thấy kết quả.

### Đường chạy downscale E5-E7 đang hoạt động

Theo [16_e567_downscale.md](16_e567_downscale.md), freeze common v3 manifests trước official result, chạy E4 trên reduced pool, rồi chỉ mở E5-E7 sau khi run/profile/hash và sync được verified. Cấu hình `scale_variant: e4e567_scale_v3_50k` phải xuất hiện trong mọi summary; không trộn artifact v2/full-scale.

E5 dùng MS MARCO child manifest 50k và ORCAS manifest tối đa 5k groups; E6 dùng document cap 50k/event cap 50k mỗi tuần nếu AOL-IA recovered; E7 dùng cap 50k documents và 500 queries cho case lớn. Runner phải load subset view trước khi cấp resource, ghi manifest hash vào summary, và không trộn aggregate variant với full-scale output.

Ví dụ thêm case E7 sau khi đã có shared E3/resource gates:

```bash
mixindex models prepare --pair bge
mixindex data prepare --dataset fever
mixindex run --experiment T0 --scope case.fever.bge --config configs/experiments/t0.yaml
```

E7 builder lặp policy này cho các required cases, reuse đúng profile hash khi có. AOL tương tự scope `case.aol-ia.arctic` nhưng chỉ tạo sau actual recovery và dùng history tuần1. Không mặc định mọi dataset/model có thể dùng profile FiQA.

## Resume và sync

```bash
mixindex resume --run-id RUN_ID
mixindex sync --run-id RUN_ID
mixindex sync --pending
mixindex aggregate --experiment E5
mixindex restore --repo OWNER/mixindex-runs-001 --run-id RUN_ID --output restored/RUN_ID
```

CLI tự tìm complete checkpoint mới nhất tương thích; incomplete checkpoint bị bỏ với reason, không tự xóa. `sync` chỉ upload/reconcile, không rerun training. Restore đọc catalog để tìm parts trên repo002/003, pin commit và verify hashes trước load.

## Orchestrator pseudocode

```python
def run_single(task):
    try:
        cfg = load_config(task.config_path)
        validate_task_dependencies(task)     # worker kiểm lại, không chỉ parent
        if task.phase == "official":
            profiles = load_tuning_profiles(cfg["tuning"]["lock_path"])
            validate_tuning_profile(task, cfg, profiles)
        data = open_validated_data(cfg)      # M02/M03; không bypass manifest/splits
        models = open_pinned_models(cfg)     # M04
        inputs = prepare_vectors_and_accessors(data, models, cfg)
        if task.experiment == "T0":
            result = run_presetup(task, inputs, cfg)  # chỉ development roles
        else:
            evaluator = build_isolated_evaluator(inputs, cfg)
            result = run_stage_branch(task, inputs, evaluator, cfg)
    except Exception as exc:
        result = close_as_failed(task, sanitized_reason(exc))
    finally:
        release_run_resources(task)
    result = finalize_run(task.run_dir, result)
    # finalize_run: đóng outputs -> compute checklist -> enqueue auto-sync (một lần)
    return result
```

`try/finally` phải đóng file/encoder/CUDA resources trước trả reservation; không nuốt exception rồi báo done. Sync worker callback verify xong gọi update_checklist lần nữa. Standalone run phải flush sync queue hoặc ghi pending receipt trước exit. Không để thread background mất khi Python process kết thúc.

## Handoff tối thiểu khi agent dừng phiên

Root checklist cập nhật và state/tasks.json có task/process handle sống hoặc terminal thật. Agent phiên sau bắt đầu **codex/README.md**, đọc đầy đủ report + expect, constraints/structure/contracts/plan/M14; xem checklist/process state và scoped profiles trước launch. Không tạo thêm handoff journal/provenance report. Secret chỉ trong `.env`/memory runtime.
