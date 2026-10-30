"""
Observability and Telemetry Tracer for Multi-Agent Orchestration.
Tracks run IDs, agent execution steps, input/output contracts, token usage, and latency.
"""

import json
import uuid
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from config.settings import settings

logger = logging.getLogger("observability.tracer")


class AgentStepTrace(dict):
    """Dictionary representation of a single agent step trace."""
    pass


class ExecutionTracer:
    """Collector for multi-agent run traces."""

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or str(uuid.uuid4())
        self.start_time = time.time()
        self.steps: List[Dict[str, Any]] = []
        self.total_tokens: int = 0
        self.estimated_cost_usd: float = 0.0

    def record_step(
        self,
        agent_name: str,
        action: str,
        inputs: Any,
        outputs: Any,
        tokens_used: int = 0,
        latency_ms: float = 0.0,
        notes: Optional[str] = None
    ):
        """Records an execution step within the agent workflow."""
        step = {
            "step_index": len(self.steps) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": agent_name,
            "action": action,
            "inputs": inputs,
            "outputs": outputs,
            "tokens_used": tokens_used,
            "latency_ms": round(latency_ms, 2),
            "notes": notes
        }
        self.steps.append(step)
        self.total_tokens += tokens_used
        # Rough estimate: $0.15 per 1M tokens for typical flash models
        self.estimated_cost_usd += (tokens_used / 1_000_000.0) * 0.15

        logger.info(f"[{self.run_id[:8]}] Agent '{agent_name}' completed '{action}' in {latency_ms:.1f}ms")

    def export_trace(self) -> Dict[str, Any]:
        """Returns the full execution trace record."""
        total_latency_ms = round((time.time() - self.start_time) * 1000.0, 2)
        return {
            "run_id": self.run_id,
            "started_at": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "total_steps": len(self.steps),
            "total_latency_ms": total_latency_ms,
            "total_tokens_used": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "steps": self.steps
        }

    def save_to_disk(self, out_path: Optional[Path] = None) -> Path:
        """Saves execution trace to disk in logs directory."""
        path = out_path or (settings.LOGS_DIR / f"{self.run_id}_trace.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.export_trace(), f, indent=2)
        return path
