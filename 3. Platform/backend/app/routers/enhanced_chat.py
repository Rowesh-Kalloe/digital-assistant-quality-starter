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

@router.post("/chat/structured")
async def structured_chat_endpoint(
    request: Request,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
) -> Union[StructuredAIResponse, QuickAnswer, ComplianceAnalysis, TechnicalGuidance, ErrorResponse]:
    """
    Enhanced chat endpoint met structured outputs en knowledge base integratie
    """
    start_time = time.time()
    
    try:
        # Parse and validate request body manually for better error logging
        body = await request.json()
        logger.info(f"Received request body: {body}")
        
        try:
            chat_message = ChatMessage(**body)
        except ValidationError as ve:
            logger.error(f"Validation error: {ve}")
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {ve}"
            )
        
        logger.info(f"Processing structured chat message from {chat_message.context.role}: {chat_message.message[:100]}...")
        logger.info(f"User context: role={chat_message.context.role}, roleName={chat_message.context.roleName}, projectPhase={chat_message.context.projectPhase}")
        
        # Validate message length
        if len(chat_message.message) > 2000:
            raise HTTPException(
                status_code=400,
                detail="Bericht is te lang. Maximaal 2000 karakters toegestaan."
            )
        
        # Generate structured response
        structured_response = await openai_service.generate_structured_response(chat_message)
        
        processing_time = time.time() - start_time
        logger.info(f"Structured response generated in {processing_time:.2f}s, type: {type(structured_response).__name__}")
        
        return structured_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in structured chat endpoint: {e}")
        return ErrorResponse(
            error_type="api_error",
            error_message="Er ging iets mis bij het verwerken van je bericht. Probeer het opnieuw.",
            technical_details=str(e),
            suggested_action="Probeer je vraag opnieuw te formuleren of neem contact op met een expert.",
            needs_human_help=True
        )




@router.get("/knowledge/search")
async def search_knowledge_base(
    query: str,
    document_types: str = None,
    max_results: int = 5,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
):
    """
    Direct search in enhanced RAG system
    """
    try:
        doc_types = document_types.split(',') if document_types else None
        
        results = openai_service.enhanced_rag.search_documents(
            query=query,
            max_results=max_results,
            document_types=doc_types
        )
        
        return {
            "query": query,
            "results": results,
            "total_found": len(results),
            "enhanced_rag_stats": openai_service.enhanced_rag.get_statistics()
        }
        
    except Exception as e:
        logger.error(f"Error searching enhanced RAG system: {e}")
        raise HTTPException(
            status_code=500,
            detail="Er ging iets mis bij het doorzoeken van de enhanced RAG kennisbank."
        )

@router.get("/knowledge/role/{role}")
async def get_role_knowledge(
    role: str,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
):
    """
    Krijg rol-specifieke enhanced RAG documenten
    """
    try:
        documents = openai_service.enhanced_rag.get_role_specific_documents(role)
        
        return {
            "role": role,
            "documents": documents,
            "total_found": len(documents)
        }
        
    except Exception as e:
        logger.error(f"Error getting role knowledge for {role}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Er ging iets mis bij het ophalen van kennis voor rol {role}."
        )

@router.get("/knowledge/compliance/{regulation}")
async def get_compliance_knowledge(
    regulation: str,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
):
    """
    Krijg compliance-specifieke documenten
    """
    try:
        documents = openai_service.enhanced_rag.get_compliance_documents(regulation)
        
        return {
            "regulation": regulation,
            "documents": documents,
            "total_found": len(documents)
        }
        
    except Exception as e:
        logger.error(f"Error getting compliance knowledge for {regulation}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Er ging iets mis bij het ophalen van compliance informatie voor {regulation}."
        )

@router.get("/knowledge/stats")
async def get_knowledge_stats(
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
):
    """
    Krijg enhanced RAG statistieken
    """
    try:
        return openai_service.enhanced_rag.get_statistics()
    except Exception as e:
        logger.error(f"Error getting enhanced RAG stats: {e}")
        raise HTTPException(
            status_code=500,
            detail="Er ging iets mis bij het ophalen van enhanced RAG statistieken."
        )

@router.get("/knowledge/document/{document_id}")
async def view_document(
    document_id: str,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
):
    """
    Bekijk de volledige inhoud van een document uit de enhanced RAG
    """
    try:
        document = openai_service.enhanced_rag.get_document_by_id(document_id)
        
        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document niet gevonden in de enhanced RAG kennisbank."
            )
        
        return {
            "document_id": document_id,
            "title": document.get('title', 'Onbekend Document'),
            "content": document.get('content', ''),
            "summary": document.get('summary', ''),
            "type": document.get('type', 'unknown'),
            "domain": document.get('domain', 'unknown'),
            "source_url": document.get('source_url', ''),
            "file_path": document.get('file_path', ''),
            "section_title": document.get('section_title', ''),
            "chunk_index": document.get('chunk_index'),
            "total_chunks": document.get('total_chunks')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing document {document_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Er ging iets mis bij het ophalen van het document."
        )

@router.get("/enhanced-rag/document/{document_id}")
async def view_enhanced_rag_document(
    document_id: str,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
):
    """
    Bekijk enhanced RAG document met volledige metadata
    """
    try:
        document = openai_service.enhanced_rag.get_document_by_id(document_id)
        
        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document niet gevonden in de enhanced RAG systeem."
            )
        
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing enhanced RAG document {document_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Er ging iets mis bij het ophalen van het enhanced RAG document."
        )

@router.get("/enhanced-rag/context")
async def get_enhanced_rag_context(
    query: str,
    max_chunks: int = 3,
    openai_service: EnhancedOpenAIService = Depends(get_enhanced_openai_service)
):
    """
    Krijg geformatteerde context en bronnen voor een query
    """
    try:
        context, sources = openai_service.enhanced_rag.get_context_for_query(query, max_chunks)
        
        return {
            "query": query,
            "context": context,
            "sources": sources,
            "total_sources": len(sources)
        }
        
    except Exception as e:
        logger.error(f"Error getting enhanced RAG context: {e}")
        raise HTTPException(
            status_code=500,
            detail="Er ging iets mis bij het ophalen van de context."
        )