import os
import json
from typing import Dict, List, Tuple, Optional
from openai import AsyncOpenAI
from loguru import logger
import tiktoken
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.chat import ChatMessage, ChatResponse, Source, UserContext, UserRole

class OpenAIService:
    def __init__(self):
        api_key = os.getenv("GREENPT_API_KEY")
        if not api_key:
            raise ValueError("GREENPT_API_KEY environment variable is required")
        
        base_url = os.getenv("GREENPT_API_BASE", "https://api.greenpt.ai/v1")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = os.getenv("GREENPT_MODEL", "gpt-4-1106-preview")
        self.max_tokens = int(os.getenv("GREENPT_MAX_TOKENS", "1500"))
        self.temperature = float(os.getenv("GREENPT_TEMPERATURE", "0.7"))
        
        # Initialize tokenizer for token counting
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        logger.info(f"OpenAI service initialized with model: {self.model}")

    def _build_system_prompt(self, context: UserContext) -> str:
        """Build context-aware system prompt based on user role and needs"""
        
        base_prompt = """Je bent een AI assistant voor Nederlandse gemeentes, gespecialiseerd in digitale transformatie en AI implementatie. Je helpt ambtenaren, projectleiders en IT managers met:

- Regelgeving en compliance (GDPR, AI Act, Woo)
- Technische implementatie en architectuur
- Best practices voor digitale gemeenschapsgoederen
- Common Ground principes
- Privacy by design
- Transparantie en ethische AI

BELANGRIJKE RICHTLIJNEN:
1. Wees ALTIJD transparant dat je een AI bent
2. Voor complexe juridische of technische zaken, verwijs door naar menselijke experts
3. Geef praktische, actionable advice
4. Citeer relevante bronnen en wet- en regelgeving
5. Houd rekening met de Nederlandse context en overheidsstructuur
6. Wees voorzichtig met juridische interpretaties - adviseer altijd professionele juridische bijstand voor complexe zaken

"""

        # Role-specific context
        role_contexts = {
            UserRole.DIGITAL_GUIDE: """
SPECIALISATIE: Digitale Bouwplaatsbegeleiding
- Focus op projectmanagement en stakeholder management
- Draagvlakvorming en change management
- Risicomanagement bij digitale transformatie
- Communicatie tussen techniek en beleid
""",
            UserRole.CIVIL_SERVANT: """
SPECIALISATIE: Beleid en Compliance
- GDPR, AI Act en andere relevante regelgeving
- Beleidsimplementatie en uitvoering
- Transparantie en verantwoording
- Burgerparticipatie en inclusie
""",
            UserRole.IT_MANAGER: """
SPECIALISATIE: Technische Architectuur en Implementatie
- Systeemarchitectuur en integratie
- Security en privacy by design
- Vendor management en lock-in preventie
- Legacy systeem migratie
""",
            UserRole.PROJECT_MANAGER: """
SPECIALISATIE: Projectmanagement Digitale Transformatie
- Agile en iteratieve ontwikkeling
- Stakeholder management
- Risk management en quality assurance
- Budget en resource planning
""",
            UserRole.DEVELOPER: """
SPECIALISATIE: Technische Ontwikkeling
- Open standaarden en APIs
- Common Ground implementatie
- Code kwaliteit en testing
- DevOps en deployment
""",
            UserRole.OTHER: """
SPECIALISATIE: Algemene Digitalisering Support
- Oriëntatie en kennisoverdracht
- Best practices identificatie
- Doorverwijzing naar specialisten
"""
        }

        system_prompt = base_prompt
        
        if context.role:
            system_prompt += role_contexts.get(context.role, role_contexts[UserRole.OTHER])
        
        if context.projectPhase:
            system_prompt += f"\nHUIDIGE PROJECTFASE: {context.projectPhase}"
        
        if context.focusAreas:
            focus_areas = ", ".join([area.value for area in context.focusAreas])
            system_prompt += f"\nFOCUSGEBIEDEN: {focus_areas}"
        
        if context.customContext:
            system_prompt += f"\nSPECIFIEKE CONTEXT: {context.customContext}"

        system_prompt += """

Reageer in het Nederlands met concrete, praktische adviezen. Structureer je antwoord duidelijk met headers waar mogelijk."""

        return system_prompt

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))

    def _assess_complexity(self, message: str, context: UserContext) -> Tuple[bool, float]:
        """Assess if query is complex and needs human help"""
        complexity_indicators = [
            "juridisch advies",
            "contract",
            "aanbesteding", 
            "rechtszaak",
            "boete",
            "sanctie",
            "specifieke implementatie",
            "budget",
            "personeel",
            "organisatiestructuur"
        ]
        
        message_lower = message.lower()
        complexity_score = sum(1 for indicator in complexity_indicators if indicator in message_lower)
        
        # Higher complexity for certain roles and contexts
        if context.role in [UserRole.IT_MANAGER, UserRole.PROJECT_MANAGER]:
            complexity_score *= 1.2
        
        needs_human = complexity_score > 2 or len(message.split()) > 100
        confidence = max(0.3, 1.0 - (complexity_score * 0.15))
        
        return needs_human, confidence

    def _extract_sources(self, response_text: str) -> List[Source]:
        """Extract and format sources from response"""
        # In a real implementation, this would integrate with your knowledge base
        # For now, return mock sources based on content
        sources = []
        
        if "gdpr" in response_text.lower() or "privacy" in response_text.lower():
            sources.append(Source(
                title="GDPR Handreiking voor Overheid",
                url="https://autoriteitpersoonsgegevens.nl/gdpr",
                snippet="Praktische gids voor GDPR compliance in overheidssystemen"
            ))
        
        if "ai act" in response_text.lower() or "ai-act" in response_text.lower():
            sources.append(Source(
                title="AI Act Implementatie Nederlandse Overheid",
                url="https://minbzk.github.io/Algoritmekader/",
                snippet="Officiële richtlijnen voor AI Act compliance"
            ))
        
        if "common ground" in response_text.lower():
            sources.append(Source(
                title="Common Ground Documentatie",
                url="https://commonground.nl/",
                snippet="Architectuurprincipes en implementatierichtlijnen"
            ))
        
        return sources

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def generate_response(self, chat_message: ChatMessage) -> ChatResponse:
        """Generate AI response to user message"""
        try:
            system_prompt = self._build_system_prompt(chat_message.context)
            needs_human, confidence = self._assess_complexity(chat_message.message, chat_message.context)
            
            # Check token limits
            system_tokens = self._count_tokens(system_prompt)
            message_tokens = self._count_tokens(chat_message.message)
            
            if system_tokens + message_tokens > 3000:
                logger.warning("Token limit approached, truncating context")
                system_prompt = system_prompt[:2000]
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": chat_message.message}
            ]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                presence_penalty=0.1,
                frequency_penalty=0.1
            )
            
            response_text = response.choices[0].message.content
            sources = self._extract_sources(response_text)
            
            # Generate contextual suggestions
            suggestions = self._generate_suggestions(chat_message.context, chat_message.message)
            
            return ChatResponse(
                message=response_text,
                confidence=confidence,
                sources=sources,
                needsHumanHelp=needs_human,
                suggestions=suggestions,
                responseTime=response.usage.total_tokens if response.usage else None
            )
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return ChatResponse(
                message="Sorry, ik kon geen antwoord genereren. Probeer het opnieuw of neem contact op met een expert.",
                confidence=0.0,
                needsHumanHelp=True,
                sources=[],
                suggestions=[]
            )

    def _generate_suggestions(self, context: UserContext, message: str) -> List[str]:
        """Generate contextual follow-up suggestions"""
        base_suggestions = {
            UserRole.DIGITAL_GUIDE: [
                "Hoe zorg ik voor draagvlak bij stakeholders?",
                "Welke risico's moet ik monitoren?",
                "Hoe communiceer ik met technische teams?"
            ],
            UserRole.CIVIL_SERVANT: [
                "Welke andere regelgeving is relevant?", 
                "Hoe implementeer ik dit in de praktijk?",
                "Wat zijn de compliance deadlines?"
            ],
            UserRole.IT_MANAGER: [
                "Welke technische standaarden moet ik volgen?",
                "Hoe zorg ik voor scalabiliteit?", 
                "Wat zijn security best practices?"
            ],
            UserRole.PROJECT_MANAGER: [
                "Hoe plan ik de volgende projectfase?",
                "Welke resources heb ik nodig?",
                "Hoe meet ik project succes?"
            ],
            UserRole.DEVELOPER: [
                "Welke APIs kan ik gebruiken?",
                "Hoe test ik deze implementatie?",
                "Waar vind ik code voorbeelden?"
            ]
        }
        
        return base_suggestions.get(context.role, [
            "Waar kan ik meer informatie vinden?",
            "Wie kan me verder helpen?", 
            "Wat zijn de volgende stappen?"
        ])

    async def health_check(self) -> Dict[str, any]:
        """Check if OpenAI service is healthy"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )
            return {
                "status": "healthy",
                "model": self.model,
                "usage": response.usage.dict() if response.usage else None
            }
        except Exception as e:
            logger.error(f"OpenAI health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }