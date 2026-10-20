"""Forward regression maps and float64 regional ridge sufficient statistics."""

from copy import deepcopy
import math

import numpy as np
from safetensors.torch import load_file, save_file
from sklearn.cluster import MiniBatchKMeans
import torch
from torch import nn


def normalize(values):
    values = np.asarray(values, dtype=np.float32)
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if not np.isfinite(values).all() or np.any(norms <= 0):
        raise ValueError("Cannot normalize zero/nonfinite mapped embedding")
    return values / norms


class LinearMap(nn.Module):
    def __init__(self, weight):
        super().__init__()
        self.weight = nn.Parameter(torch.as_tensor(weight, dtype=torch.float32), requires_grad=False)

    def forward(self, x):
        return x @ self.weight.T


def fit_op(X_train, Y_train):
    x, y = np.asarray(X_train, dtype=np.float64), np.asarray(Y_train, dtype=np.float64)
    if len(x) != len(y) or len(x) == 0 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Invalid Procrustes pairs")
    dimension = max(x.shape[1], y.shape[1])
    xp = np.pad(x, ((0, 0), (0, dimension - x.shape[1])))
    yp = np.pad(y, ((0, 0), (0, dimension - y.shape[1])))
    u, _, vt = np.linalg.svd(xp.T @ yp, full_matrices=False)
    return LinearMap((u @ vt).T[:y.shape[1], :x.shape[1]].copy())


class ResidualMap(nn.Module):
    def __init__(self, old_dim, new_dim, hidden=256, op=None):
        super().__init__()
        self.linear = nn.Linear(old_dim, new_dim)
        self.residual = nn.Sequential(nn.Linear(old_dim, hidden), nn.GELU(), nn.Linear(hidden, new_dim))
        with torch.no_grad():
            if op is not None:
                self.linear.weight.copy_(op.weight)
            self.linear.bias.zero_()
            self.residual[-1].weight.zero_()
            self.residual[-1].bias.zero_()

    def forward(self, x):
        return self.linear(x) + self.residual(x)


class LowRankAffine(nn.Module):
    def __init__(self, old_dim, new_dim, rank=64):
        super().__init__()
        self.U = nn.Parameter(torch.randn(new_dim, rank) * 0.01)
        self.V = nn.Parameter(torch.zeros(old_dim, rank))
        self.diagonal = nn.Parameter(torch.ones(min(old_dim, new_dim)))
        self.bias = nn.Parameter(torch.zeros(new_dim))
        self.old_dim, self.new_dim = old_dim, new_dim

    def forward(self, x):
        base = torch.zeros((len(x), self.new_dim), device=x.device, dtype=x.dtype)
        size = len(self.diagonal)
        base[:, :size] = x[:, :size] * self.diagonal
        return (x @ self.V) @ self.U.T + base + self.bias


def transform_global(model, X, normalize_output=False, **kwargs):
    # `normalize` is accepted for the module contract without shadowing normalize().
    normalize_output = kwargs.get("normalize", normalize_output)
    result = None
    with torch.inference_mode():
        for start in range(0, len(X), 16384):
            values = np.asarray(X[start:start + 16384], dtype=np.float32)
            if not values.flags.writeable:
                values = values.copy()  # Torch must not alias a read-only memory-map.
            output = model(torch.from_numpy(values)).cpu().numpy()
            if result is None:
                result = np.empty((len(X), output.shape[1]), dtype=np.float32)
            result[start:start + len(output)] = output
        if result is None:
            result = model(torch.empty((0, X.shape[1]), dtype=torch.float32)).cpu().numpy()
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite map output")
    return normalize(result) if normalize_output else result


def fit_global_map(kind, pairs, validation, cfg, seed=17):
    X, Y = pairs
    XV, YV = validation
    if len(XV) == 0:
        raise ValueError("Validation pairs are required for map selection")
    torch.manual_seed(seed)
    if kind == "op":
        model = fit_op(X, Y)
        output = transform_global(model, XV)
        normalize(output)
        loss = float(np.mean(np.sum((output - YV) ** 2, axis=1)))
        if not math.isfinite(loss):
            raise ValueError("Nonfinite OP validation loss")
        return model, {"validation_loss": loss, "epochs": 0, "kind": kind}
    if kind == "residual_mlp":
        model = ResidualMap(X.shape[1], Y.shape[1], cfg["hidden"], fit_op(X, Y))
    elif kind == "la":
        model = LowRankAffine(X.shape[1], Y.shape[1], cfg["rank"])
    else:
        raise ValueError("Unknown global map")
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg["lr"], weight_decay=0)
    x, y, xv, yv = [torch.as_tensor(np.asarray(a), dtype=torch.float32) for a in (X, Y, XV, YV)]
    best, significant, stale = math.inf, math.inf, 0
    history, best_state = [], None
    for epoch in range(cfg["max_epochs"]):
        model.train()
        order = torch.randperm(len(x))
        for indices in order.split(cfg["batch_size"]):
            optimizer.zero_grad(set_to_none=True)
            loss = ((model(x[indices]) - y[indices]) ** 2).sum(1).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite map fitting loss")
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            value = float(((model(xv) - yv) ** 2).sum(1).mean())
        if not math.isfinite(value):
            raise ValueError("Nonfinite validation loss")
        history.append(value)
        if value < best:
            best, best_state = value, deepcopy(model.state_dict())
        if value < significant - cfg["min_delta"]:
            significant, stale = value, 0
        else:
            stale += 1
        if stale >= cfg["patience"]:
            break
    if best_state is None:
        raise ValueError("Map grid produced no valid checkpoint")
    model.load_state_dict(best_state)
    model.eval().requires_grad_(False)
    normalize(transform_global(model, XV))  # Zero outputs invalidate a candidate too.
    return model, {"validation_loss": best, "epochs": len(history), "kind": kind,
                   "history": history, "lr": cfg["lr"]}


def fit_la(X_train, Y_train, X_val, Y_val, cfg):
    return fit_global_map("la", (X_train, Y_train), (X_val, Y_val), cfg)


def save_map_state(model, path):
    import json
    if isinstance(model, LinearMap):
        spec = {"kind": "op", "old_dim": model.weight.shape[1], "new_dim": model.weight.shape[0]}
    elif isinstance(model, ResidualMap):
        spec = {"kind": "residual_mlp", "old_dim": model.linear.in_features,
                "new_dim": model.linear.out_features, "hidden": model.residual[0].out_features}
    else:
        spec = {"kind": "la", "old_dim": model.old_dim, "new_dim": model.new_dim, "rank": model.U.shape[1]}
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}, str(path),
              metadata={"architecture": json.dumps(spec)})


def load_map_state(path):
    import json
    from safetensors import safe_open
    with safe_open(str(path), framework="pt") as file:
        spec = json.loads(file.metadata()["architecture"])
    kind = spec.pop("kind")
    if kind == "op":
        model = LinearMap(np.zeros((spec["new_dim"], spec["old_dim"]), dtype=np.float32))
    elif kind == "residual_mlp":
        model = ResidualMap(**spec)
    else:
        model = LowRankAffine(**spec)
    model.load_state_dict(load_file(str(path)))
    return model.eval().requires_grad_(False)


def choose_region_count(n_train):
    size = min(256, max(1, n_train // 100))
    return 1 << (size.bit_length() - 1)


def fit_regions(old_vectors, n_train, seed=17):
    n = len(old_vectors)
    rng = np.random.default_rng(seed)
    rows = np.sort(rng.choice(n, min(n, 100000), replace=False))
    model = MiniBatchKMeans(n_clusters=choose_region_count(n_train), batch_size=4096,
                            max_iter=100, n_init=3, random_state=seed)
    model.fit(old_vectors[rows])
    assignments = np.empty(n, dtype=np.int64)
    for start in range(0, n, 16384):
        assignments[start:start + 16384] = model.predict(old_vectors[start:start + 16384])
    return {"centers": model.cluster_centers_, "sample_rows": rows, "assignments": assignments}


class RegionalStatistics:
    def __init__(self, dimension, n_regions, ridge=10.0):
        self.dimension, self.n_regions, self.ridge = dimension, n_regions, ridge
        self.H = np.repeat((np.eye(dimension + 1) * ridge)[None], n_regions, axis=0)
        prior = np.column_stack([np.eye(dimension), np.zeros(dimension)])
        self.B = np.repeat((ridge * prior)[None], n_regions, axis=0)
        self.counts = np.zeros(n_regions, dtype=np.int64)
        self.seen = set()
        self.dirty = set()

    def add_pairs(self, rows, U, Y, assignments, excluded=()):
        rows = np.asarray(rows, dtype=np.int64)
        if set(map(int, rows)) & set(map(int, excluded)):
            raise PermissionError("Held-out pairs cannot enter regional fitting")
        if len(set(rows)) != len(rows) or self.seen & set(rows):
            raise ValueError("Regional pair would be counted twice")
        for region in np.unique(assignments[rows]):
            mask = assignments[rows] == region
            ubar = np.column_stack([U[mask], np.ones(mask.sum())]).astype(np.float64)
            y = Y[mask].astype(np.float64)
            self.H[region] += ubar.T @ ubar
            self.B[region] += y.T @ ubar
            self.counts[region] += int(mask.sum())
            self.dirty.add(int(region))
        self.seen.update(map(int, rows))

    def fit(self, min_pairs=20, mode="full", regions=None, current=None):
        d = self.dimension
        result = (np.repeat(np.column_stack([np.eye(d), np.zeros(d)])[None], self.n_regions, axis=0)
                  if current is None else np.array(current, copy=True))
        for region in (range(self.n_regions) if regions is None else regions):
            if self.counts[region] < min_pairs or mode == "none":
                continue
            if mode == "full":
                result[region] = np.linalg.solve(self.H[region], self.B[region].T).T
            elif mode == "diagonal":
                result[region] = 0
                for j in range(d):
                    indices = [j, d]
                    solution = np.linalg.solve(self.H[region][np.ix_(indices, indices)],
                                                self.B[region][j, indices])
                    result[region, j, j], result[region, j, d] = solution
            else:
                raise ValueError("Unknown regional mode")
        return result


def map_documents(rows, old_vectors, M0, regional, assignments):
    rows = np.asarray(rows, dtype=np.int64)
    u = transform_global(M0, old_vectors[rows])
    result = np.empty_like(u)
    for region in np.unique(assignments[rows]):
        mask = assignments[rows] == region
        correction = regional[region]
        result[mask] = u[mask] @ correction[:, :-1].T + correction[:, -1]
    return normalize(result)


def regional_validation_errors(state, validation_rows):
    rows = np.asarray(validation_rows, dtype=np.int64)
    if any(int(row) not in state.accessor.roles["validation"] for row in rows):
        raise PermissionError("Regional validation requires validation-role rows")
    vectors = map_documents(rows, state.old_vectors, state.M0, state.regional,
                            state.regions["assignments"])
    target = np.stack([state.accessor.cache[int(row)] for row in rows])
    error = np.sum((vectors - target) ** 2, axis=1)
    result = []
    for region in range(len(state.regions["centers"])):
        mask = state.regions["assignments"][rows] == region
        result.append({"region": region, "validation_pairs": int(mask.sum()),
                       "training_pairs": int(state.statistics.counts[region]),
                       "r_vec_region": float(np.sqrt(error[mask].mean())) if mask.any() else None})
    return result
