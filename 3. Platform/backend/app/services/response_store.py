"""
In-memory store for pending AI responses awaiting n8n validation callback.
Used to bridge the async gap between sending to n8n and receiving the validated result.
"""
import asyncio
import time
from typing import Dict, Any, Optional
from loguru import logger


class ResponseStore:
    """Thread-safe in-memory store for pending chat responses"""
    
    def __init__(self, ttl_seconds: int = 120):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds
    
    def create_pending(self, request_id: str, ai_response: Dict[str, Any], user_context: Dict[str, Any]) -> None:
        """Store a pending response that was sent to n8n for validation"""
        self._store[request_id] = {
            "status": "pending",
            "ai_response": ai_response,
            "user_context": user_context,
            "validated_response": None,
            "created_at": time.time(),
            "completed_at": None,
        }
        logger.info(f"Stored pending response: {request_id}")
        self._cleanup_expired()
    
    def complete(self, request_id: str, validated_response: Dict[str, Any]) -> bool:
        """Mark a pending response as completed with the validated result from n8n"""
        if request_id not in self._store:
            logger.warning(f"Request ID not found in store: {request_id}")
            return False
        
        self._store[request_id]["status"] = "completed"
        self._store[request_id]["validated_response"] = validated_response
        self._store[request_id]["completed_at"] = time.time()
        logger.info(f"Completed response: {request_id}")
        return True
    
    def reject(self, request_id: str, reason: str = None) -> bool:
        """Mark a pending response as rejected"""
        if request_id not in self._store:
            return False
        
        self._store[request_id]["status"] = "rejected"
        self._store[request_id]["rejection_reason"] = reason
        self._store[request_id]["completed_at"] = time.time()
        logger.info(f"Rejected response: {request_id}, reason: {reason}")
        return True
    
    def get(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get the current state of a response"""
        entry = self._store.get(request_id)
        if not entry:
            return None
        
        # Check if expired
        if time.time() - entry["created_at"] > self._ttl:
            del self._store[request_id]
            return {"status": "expired"}
        
        return entry
    
    def _cleanup_expired(self) -> None:
        """Remove expired entries"""
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v["created_at"] > self._ttl]
        for k in expired:
            del self._store[k]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired response entries")


# Singleton instance
response_store = ResponseStore(ttl_seconds=120)
