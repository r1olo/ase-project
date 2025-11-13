"""Matchmaking HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from flask import Blueprint, current_app, jsonify, request


bp = Blueprint("matchmaking", __name__)


@dataclass
class QueueState:
    queue_id: str
    players: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"queue_id": self.queue_id, "size": len(self.players), "players": self.players}


class QueueRegistry:
    def __init__(self):
        self._queues: Dict[str, QueueState] = {}

    def get(self, queue_id: str) -> QueueState:
        if queue_id not in self._queues:
            self._queues[queue_id] = QueueState(queue_id=queue_id)
        return self._queues[queue_id]


def _registry() -> QueueRegistry:
    registry = current_app.config.get("QUEUE_REGISTRY")
    if not registry:
        registry = QueueRegistry()
        current_app.config["QUEUE_REGISTRY"] = registry
    return registry


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.post("/queues/<queue_id>/join")
def join_queue(queue_id: str):
    registry = _registry()
    player_id = (request.get_json(silent=True) or {}).get("player_id")
    if not player_id:
        return jsonify({"msg": "player_id is required"}), 400

    queue = registry.get(queue_id)
    if player_id in queue.players:
        return jsonify(queue.to_dict()), 200

    max_size = current_app.config.get("MAX_QUEUE_SIZE", 500)
    if len(queue.players) >= max_size:
        return jsonify({"msg": "queue is full"}), 409

    queue.players.append(player_id)
    return jsonify(queue.to_dict()), 202


@bp.delete("/queues/<queue_id>/leave")
def leave_queue(queue_id: str):
    registry = _registry()
    player_id = request.args.get("player_id")
    if not player_id:
        return jsonify({"msg": "player_id query param is required"}), 400

    queue = registry.get(queue_id)
    if player_id in queue.players:
        queue.players.remove(player_id)
    return jsonify(queue.to_dict())


@bp.get("/queues/<queue_id>")
def queue_status(queue_id: str):
    queue = _registry().get(queue_id)
    return jsonify(queue.to_dict())
