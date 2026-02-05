from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.exceptions import RequestValidationError
from loguru import logger
import time
from datetime import datetime
from typing import Union
from pydantic import ValidationError

from app.models.chat import ChatMessage, FeedbackRequest, ExpertContact
from app.models.ai_responses import (
    StructuredAIResponse, QuickAnswer, ComplianceAnalysis, 
    TechnicalGuidance, ErrorResponse, AIResponseFormat
)
from app.services.enhanced_openai_service import EnhancedOpenAIService
from app.services.n8n_validation_service import N8NValidationService

router = APIRouter()

def get_enhanced_openai_service(request: Request) -> EnhancedOpenAIService:
    """Dependency to get Enhanced OpenAI service from app state"""
    return request.app.state.enhanced_openai_service

def get_n8n_validation_service(request: Request) -> N8NValidationService:
    """Dependency to get N8N validation service from app state"""
    return request.app.state.n8n_validation_service

@router.post("/chat/validated")
async def validated_chat_endpoint(
    request: Request,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service),
    n8n_service: N8NValidationService = Depends(get_n8n_validation_service)
) -> Union[StructuredAIResponse, QuickAnswer, ComplianceAnalysis, TechnicalGuidance, ErrorResponse]:
    """
    Enhanced chat endpoint with n8n validation layer
    AI responses are validated through n8n webhook before delivery to user
    """
    start_time = time.time()
    
    try:
        # Parse and validate request body
        body = await request.json()
        logger.info(f"Received validated chat request: {body.get('message', '')[:100]}...")
        
        try:
            chat_message = ChatMessage(**body)
        except ValidationError as ve:
            logger.error(f"Validation error: {ve}")
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {ve}"
            )
        
        logger.info(f"Processing chat message from {chat_message.context.role}: {chat_message.message[:100]}...")
        
        # Validate message length
        if len(chat_message.message) > 2000:
            raise HTTPException(
                status_code=400,
                detail="Bericht is te lang. Maximaal 2000 karakters toegestaan."
            )
        
        # STEP 1: Generate AI response
        logger.info("Generating AI response...")
        structured_response = await openai_service.generate_structured_response(chat_message)
        ai_generation_time = time.time() - start_time
        logger.info(f"AI response generated in {ai_generation_time:.2f}s")
        
        # STEP 2: SECURITY LAYER - Validate through n8n before user sees it
        logger.info("🔒 Sending response to n8n validation layer...")
        validation_start = time.time()
        
        # Convert response to dict for n8n
        response_dict = structured_response.dict() if hasattr(structured_response, 'dict') else structured_response.__dict__
        
        validation_result = await n8n_service.validate_response(
            response_data=response_dict,
            user_context={
                "role": chat_message.context.role.value if chat_message.context.role else None,
                "roleName": chat_message.context.roleName,
                "projectPhase": chat_message.context.projectPhase,
                "message": chat_message.message,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        validation_time = time.time() - validation_start
        logger.info(f"✅ Validation completed in {validation_time:.2f}s, status: {validation_result.get('validation_status')}")
        
        # STEP 3: Handle validation result
        if validation_result.get("validation_status") == "rejected":
            logger.warning(f"⚠️ Response REJECTED by n8n: {validation_result.get('rejection_reason')}")
            logger.warning(f"Security flags: {validation_result.get('security_flags', [])}")
            
            # Return safe fallback response
            return ErrorResponse(
                error_type="validation_error",
                error_message=validation_result["response"].get("message", "Deze vraag vereist extra verificatie door een expert."),
                technical_details=f"Rejected: {validation_result.get('rejection_reason')}",
                suggested_action="Neem contact op met een expert voor meer informatie over dit onderwerp.",
                needs_human_help=True
            )
        
        # STEP 4: Use validated/modified response
        final_response = validation_result.get("response", structured_response)
        was_modified = validation_result.get("was_modified", False)
        
        if was_modified:
            logger.info("📝 Response was modified by n8n validation layer")
        
        # Reconstruct proper response type if modified
        if was_modified and isinstance(final_response, dict):
            try:
                response_type = type(structured_response)
                final_response = response_type(**final_response)
                logger.info(f"Reconstructed {response_type.__name__} from modified response")
            except Exception as e:
                logger.warning(f"Could not reconstruct response type: {e}, returning dict")
        
        total_time = time.time() - start_time
        logger.info(f"✨ Total processing time: {total_time:.2f}s (AI: {ai_generation_time:.2f}s, Validation: {validation_time:.2f}s)")
        logger.info(f"Validation metadata: validated={validation_result.get('validated')}, modified={was_modified}")
        
        return final_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in validated chat endpoint: {e}", exc_info=True)
        return ErrorResponse(
            error_type="api_error",
            error_message="Er ging iets mis bij het verwerken van je bericht. Probeer het opnieuw.",
            technical_details=str(e),
            suggested_action="Probeer je vraag opnieuw te formuleren of neem contact op met een expert.",
            needs_human_help=True
        )
