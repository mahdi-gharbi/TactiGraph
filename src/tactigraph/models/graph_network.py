"""Small CPU GINE and the four prespecified ablations."""

import hashlib
import random
from copy import deepcopy

import numpy as np
import torch
from torch import nn
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GINEConv, global_mean_pool

from tactigraph.models.graph_features import EDGE_DIM, GLOBAL_NAMES, NODE_DIM


def seed_everything(seed, threads=2):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)


def graph_data(row, variant="gine", seed=2026):
    x = torch.tensor(row["nodes"], dtype=torch.float32)
    edges = torch.tensor(row["edges"], dtype=torch.long).reshape(-1, 2).t().contiguous()
    attributes = torch.tensor(row["edge_attributes"], dtype=torch.float32).reshape(-1, EDGE_DIM)
    if variant == "episode_edges":
        mask = attributes[:, 8] == 1
        edges, attributes = edges[:, mask], attributes[mask]
    elif variant == "no_edge_time_space":
        attributes[:, :6] = 0
        attributes[:, 9:11] = 0
    elif variant == "random_connectivity":
        sample_seed = int.from_bytes(
            hashlib.sha256(f"{row['sample_id']}:{seed}".encode()).digest()[:8]
        )
        rng = np.random.default_rng(sample_seed)
        a = rng.integers(len(x), size=edges.shape[1])
        b = (a + rng.integers(1, len(x), size=edges.shape[1])) % len(x)
        edges = torch.tensor(np.stack([a, b]), dtype=torch.long)
    return Data(
        x=x,
        edge_index=edges,
        edge_attr=attributes,
        global_features=torch.tensor([row["globals"]], dtype=torch.float32),
        holder_mask=x[:, -1].bool(),
        y=torch.tensor([float(row["label"])], dtype=torch.float32),
    )


class ShotAfterThirdPass(nn.Module):
    def __init__(self, variant="gine", width=32, dropout=0.2):
        super().__init__()
        self.variant = variant
        self.project = nn.Linear(NODE_DIM, width)
        self.layers = nn.ModuleList(
            [
                GINEConv(
                    nn.Sequential(nn.Linear(width, width), nn.ReLU(), nn.Linear(width, width)),
                    edge_dim=EDGE_DIM,
                )
                if variant != "no_message"
                else nn.Sequential(nn.Linear(width, width), nn.ReLU(), nn.Linear(width, width))
                for _ in range(2)
            ]
        )
        self.dropout = nn.Dropout(dropout)
        self.output = nn.Sequential(
            nn.Linear(width * 2 + len(GLOBAL_NAMES), width),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(width, 1),
        )

    def forward(self, batch):
        x = torch.relu(self.project(batch.x))
        for layer in self.layers:
            x = (
                layer(x)
                if self.variant == "no_message"
                else layer(x, batch.edge_index, batch.edge_attr)
            )
            x = self.dropout(torch.relu(x))
        pooled = global_mean_pool(x, batch.batch)
        holder = x[batch.holder_mask]
        return self.output(torch.cat([pooled, holder, batch.global_features], dim=1)).flatten()


@torch.no_grad()
def predict(model, dataset, batch_size=128):
    model.eval()
    values = [
        torch.sigmoid(model(batch)).numpy() for batch in DataLoader(dataset, batch_size=batch_size)
    ]
    return np.concatenate(values) if values else np.array([])


def train(rows, tuning, variant, seed, protocol, epochs=None):
    from sklearn.metrics import log_loss

    seed_everything(seed, protocol["torch_threads"])
    dataset = [graph_data(r, variant, seed) for r in rows]
    development = [graph_data(r, variant, seed) for r in tuning] if tuning else []
    model = ShotAfterThirdPass(variant, protocol["hidden_width"], protocol["dropout"])
    optimizer = torch.optim.Adam(
        model.parameters(), lr=protocol["learning_rate"], weight_decay=protocol["weight_decay"]
    )
    loader = DataLoader(
        dataset,
        batch_size=protocol["batch_size"],
        shuffle=True,
        generator=torch.Generator().manual_seed(seed),
        num_workers=0,
    )
    best, best_epoch, best_state, stale = float("inf"), 0, None, 0
    history = []
    for epoch in range(1, (epochs or protocol["max_epochs"]) + 1):
        model.train()
        for batch in loader:
            optimizer.zero_grad()
            loss = nn.functional.binary_cross_entropy_with_logits(model(batch), batch.y)
            loss.backward()
            optimizer.step()
        if development:
            probabilities = predict(model, development, protocol["batch_size"])
            score = float(log_loss([r["label"] for r in tuning], probabilities, labels=[0, 1]))
            history.append(score)
            if score < best:
                best, best_epoch, best_state, stale = score, epoch, deepcopy(model.state_dict()), 0
            else:
                stale += 1
            if stale >= protocol["patience"]:
                break
        else:
            best_epoch = epoch
        if epoch % 5 == 0:
            print(
                f"{variant} seed={seed} epoch={epoch} "
                f"tuning_loss={history[-1] if history else 'refit'}",
                flush=True,
            )
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, {
        "selected_epoch": best_epoch,
        "tuning_history": history,
        "parameters": sum(p.numel() for p in model.parameters()),
    }
