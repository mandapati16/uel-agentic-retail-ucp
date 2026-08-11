import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("ucp_audit_logger")
logger.setLevel(logging.INFO)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

def log_audit_event(
    event_type: str,
    agent_id: str,
    action: str,
    status: str,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None,
    error: Optional[str] = None
) -> Dict[str, Any]:
    """Generates and logs a standardized UCP Audit Event."""
    audit_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "agent_id": agent_id,
        "action": action,
        "status": status,
        "correlation_id": correlation_id or "N/A",
        "payload": payload,
        "error": error
    }
    
    logger.info(f"[AUDIT_EVENT] {json.dumps(audit_entry)}")
    return audit_entry