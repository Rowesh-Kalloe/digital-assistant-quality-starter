from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from loguru import logger
import json
import time
import uuid
from datetime import datetime
from typing import Union, Dict, Any
from pydantic import ValidationError

from app.models.chat import ChatMessage
from app.models.ai_responses import StructuredAIResponse
from app.services.enhanced_openai_service import EnhancedOpenAIService
from app.services.n8n_validation_service import N8NValidationService

router = APIRouter()


def get_enhanced_openai_service(request: Request) -> EnhancedOpenAIService:
    return request.app.state.enhanced_openai_service

def get_n8n_validation_service(request: Request) -> N8NValidationService:
    return request.app.state.n8n_validation_service


def _serialize_response(structured_response) -> dict:
    """Convert a Pydantic model to a JSON-safe dict (handles enums)"""
    if hasattr(structured_response, 'model_dump'):
        return structured_response.model_dump(mode='json')
    elif hasattr(structured_response, 'dict'):
        raw = structured_response.dict()
    else:
        raw = structured_response.__dict__

    def _convert(obj):
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_convert(v) for v in obj]
        elif hasattr(obj, 'value'):
            return obj.value
        return obj

    return _convert(raw)


@router.post("/chat/validated")
async def validated_chat_endpoint(
    request: Request,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service),
    n8n_service: N8NValidationService = Depends(get_n8n_validation_service)
):
    """
    Synchronous chat endpoint with n8n validation.
    1. Generate AI response
    2. Send to n8n webhook (fire-and-forget)
    3. Return the AI response directly to the frontend
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())

    try:
        body = await request.json()
        logger.info(f"[{request_id}] Received: {body.get('message', '')[:100]}")

        try:
            chat_message = ChatMessage(**body)
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=str(ve))

        if len(chat_message.message) > 2000:
            raise HTTPException(status_code=400, detail="Bericht is te lang (max 2000).")

        # STEP 1: Generate AI response
        logger.info(f"[{request_id}] Generating AI response...")
        structured_response = await openai_service.generate_structured_response(chat_message)
        elapsed = time.time() - start_time
        logger.info(f"[{request_id}] AI response generated in {elapsed:.2f}s")

        # STEP 2: Serialize to JSON-safe dict
        response_dict = _serialize_response(structured_response)
        logger.info(f"[{request_id}] main_answer[:80]: {str(response_dict.get('main_answer', 'MISSING'))[:80]}")

        # STEP 3: Send to n8n and WAIT for response
        final_response = response_dict  # default: use original AI response

        if n8n_service.enabled:
            try:
                user_context = {
                    "role": chat_message.context.role.value if chat_message.context.role else None,
                    "message": chat_message.message,
                    "timestamp": datetime.now().isoformat()
                }
                logger.info(f"[{request_id}] Sending to n8n and waiting for response...")
                n8n_result = await n8n_service.validate_response(
                    response_data={**response_dict, "request_id": request_id},
                    user_context=user_context
                )
                
                validation_status = n8n_result.get("validation_status", "unknown")
                logger.info(f"[{request_id}] n8n validation_status: {validation_status}")
                logger.info(f"[{request_id}] n8n full result keys: {list(n8n_result.keys())}")
                
                if validation_status == "approved" and "response" in n8n_result:
                    # n8n sent back a validated/modified response — USE IT
                    final_response = n8n_result["response"]
                    logger.info(f"[{request_id}] ✅ Using n8n validated response")
                elif validation_status == "rejected":
                    final_response = {
                        "main_answer": n8n_result.get("rejection_reason", "Dit antwoord is afgekeurd door validatie."),
                        "confidence_level": "low",
                        "knowledge_sources": [],
                        "follow_up_suggestions": [],
                        "needs_human_expert": True
                    }
                    logger.warning(f"[{request_id}] ⚠️ Response rejected by n8n")
                else:
                    # sent/error/timeout/unknown — use original AI response
                    logger.info(f"[{request_id}] Using original AI response (n8n status: {validation_status})")
                    
            except Exception as e:
                logger.error(f"[{request_id}] n8n failed: {e} — using original AI response")

        # STEP 4: Return the final response to frontend
        logger.info(f"[{request_id}] Returning to frontend. main_answer[:80]: {str(final_response.get('main_answer', 'MISSING'))[:80]}")

        # Safety check: ensure JSON-serializable
        try:
            json.dumps(final_response)
        except (TypeError, ValueError) as e:
            logger.error(f"[{request_id}] Not JSON-serializable: {e}")
            final_response = {
                "main_answer": str(final_response.get("main_answer", "Er ging iets mis.")),
                "confidence_level": "medium",
                "knowledge_sources": [],
                "follow_up_suggestions": [],
                "needs_human_expert": False
            }

        return JSONResponse(content=final_response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Er ging iets mis bij het verwerken van je bericht.")
