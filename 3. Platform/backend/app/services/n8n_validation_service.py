"""
N8N Validation Service
Sends chatbot outputs to n8n webhook for validation before delivering to users
"""

import os
import httpx
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

class EmptyN8NResponseError(Exception):
    """Raised when n8n returns empty body, triggers retry"""
    pass


class N8NValidationService:
    """
    Service to validate chatbot outputs through n8n webhook
    """
    
    def __init__(self):
        self.webhook_url = os.getenv("N8N_WEBHOOK_URL")
        self.validation_timeout = int(os.getenv("N8N_VALIDATION_TIMEOUT", "30"))  # seconds
        self.enabled = os.getenv("N8N_VALIDATION_ENABLED", "false").lower() == "true"
        
        if self.enabled and not self.webhook_url:
            logger.warning("N8N validation enabled but N8N_WEBHOOK_URL not set!")
            self.enabled = False
        
        if self.enabled:
            logger.info(f"N8N validation service initialized: {self.webhook_url}")
        else:
            logger.info("N8N validation service disabled")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=3, max=10),
        retry=lambda retry_state: isinstance(retry_state.outcome.exception(), EmptyN8NResponseError) if retry_state.outcome and retry_state.outcome.exception() else False
    )
    async def validate_response(
        self, 
        response_data: Dict[str, Any],
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send response to n8n webhook for validation
        
        Args:
            response_data: The AI response to validate
            user_context: Optional user context for validation rules
            
        Returns:
            Validated response data (may be modified by n8n)
        """
        
        # If validation is disabled, return original response
        if not self.enabled:
            logger.debug("N8N validation disabled, returning original response")
            return {
                "validated": False,
                "response": response_data,
                "validation_status": "skipped"
            }
        
        try:
            logger.info("Sending response to n8n webhook for validation")
            
            # Prepare payload for n8n
            payload = {
                "response": response_data,
                "user_context": user_context or {},
                "timestamp": asyncio.get_event_loop().time(),
                "validation_request": True
            }
            
            # Send to n8n webhook with timeout
            async with httpx.AsyncClient(timeout=self.validation_timeout) as client:
                webhook_response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Validation-Source": "gemeente-chatbot"
                    }
                )
                
                webhook_response.raise_for_status()
                
                # === DETAILED LOGGING OF N8N RESPONSE ===
                response_text = webhook_response.text.strip()
                logger.info(f"📥 N8N response status: {webhook_response.status_code}")
                logger.info(f"📥 N8N response headers: {dict(webhook_response.headers)}")
                logger.info(f"📥 N8N response body (raw): '{response_text[:500]}'")
                
                if not response_text:
                    logger.warning("📥 N8N returned EMPTY body — will retry to wait for n8n...")
                    raise EmptyN8NResponseError("N8N returned empty body")
                
                try:
                    validation_result = webhook_response.json()
                    logger.info(f"📥 N8N response parsed JSON keys: {list(validation_result.keys()) if isinstance(validation_result, dict) else type(validation_result)}")
                    logger.info(f"📥 N8N response parsed JSON: {str(validation_result)[:500]}")
                except Exception:
                    # n8n returned plain text — this IS the validated response text
                    logger.info(f"📥 N8N returned plain text, using as validated main_answer")
                    validation_result = {"approved": True, "modified_response": {**response_data, "main_answer": response_text}}
            
            # Parse n8n response
            return self._parse_validation_result(validation_result, response_data)
            
        except httpx.TimeoutException:
            logger.error(f"N8N validation timeout after {self.validation_timeout}s")
            return {
                "validated": False,
                "response": response_data,
                "validation_status": "timeout",
                "error": "Validation timeout - returning original response"
            }
            
        except httpx.HTTPError as e:
            logger.error(f"N8N webhook HTTP error: {e}")
            return {
                "validated": False,
                "response": response_data,
                "validation_status": "error",
                "error": str(e)
            }
            
        except EmptyN8NResponseError:
            # Let @retry handle this
            raise
            
        except Exception as e:
            logger.error(f"N8N validation error: {e}")
            return {
                "validated": False,
                "response": response_data,
                "validation_status": "error",
                "error": str(e)
            }
    
    def _parse_validation_result(
        self, 
        validation_result: Dict[str, Any],
        original_response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Parse the validation result from n8n
        
        Expected n8n response format:
        {
            "approved": true/false,
            "modified_response": {...},  # Optional: modified response
            "validation_notes": "...",
            "security_flags": [...],
            "confidence_score": 0.95
        }
        """
        
        # Default to approved=True when n8n responds (Respond to Webhook node)
        # Only reject if explicitly set to approved=false
        approved = validation_result.get("approved", True)
        
        if approved:
            # Use modified response if provided, otherwise original
            final_response = validation_result.get("modified_response", original_response)
            
            return {
                "validated": True,
                "response": final_response,
                "validation_status": "approved",
                "validation_notes": validation_result.get("validation_notes"),
                "security_flags": validation_result.get("security_flags", []),
                "confidence_score": validation_result.get("confidence_score"),
                "was_modified": "modified_response" in validation_result
            }
        else:
            # Response rejected by n8n
            logger.warning("Response rejected by n8n validation")
            
            # Return fallback response or error
            fallback_response = validation_result.get("fallback_response", {
                "message": "Deze vraag vereist extra verificatie. Neem contact op met een expert voor meer informatie.",
                "needsHumanHelp": True,
                "confidence": 0.0
            })
            
            return {
                "validated": True,
                "response": fallback_response,
                "validation_status": "rejected",
                "rejection_reason": validation_result.get("rejection_reason"),
                "security_flags": validation_result.get("security_flags", []),
                "original_response_blocked": True
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if n8n webhook is reachable"""
        if not self.enabled:
            return {
                "status": "disabled",
                "webhook_url": None
            }
        
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Send a test ping
                response = await client.post(
                    self.webhook_url,
                    json={"health_check": True},
                    headers={"X-Health-Check": "true"}
                )
                
                return {
                    "status": "healthy",
                    "webhook_url": self.webhook_url,
                    "response_code": response.status_code
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "webhook_url": self.webhook_url,
                "error": str(e)
            }
