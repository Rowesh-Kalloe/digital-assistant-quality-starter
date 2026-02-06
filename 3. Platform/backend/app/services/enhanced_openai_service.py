import os
import json
import time
from typing import Dict, List, Optional, Union, Type
from openai import AsyncOpenAI
from loguru import logger
import tiktoken
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.chat import ChatMessage, UserContext, UserRole
from app.models.ai_responses import (
    StructuredAIResponse, QuickAnswer, ComplianceAnalysis, TechnicalGuidance, 
    ErrorResponse, KnowledgeSource, ActionItem, ComplianceCheck, FollowUpSuggestion,
    ResponseType, ConfidenceLevel, ComplexityLevel, RegulationType
)
from app.services.enhanced_rag_service import EnhancedRAGServiceWrapper

class EnhancedOpenAIService:
    """
    Enhanced OpenAI service met structured outputs en knowledge base integratie
    """
    
    def __init__(self):
        api_key = os.getenv("GREENPT_API_KEY")
        demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
        
        if not api_key or api_key == "your_greenpt_api_key_here":
            if not demo_mode:
                raise ValueError("GREENPT_API_KEY environment variable is required. Set DEMO_MODE=true voor demo functionaliteit.")
            else:
                logger.info("Running in DEMO MODE - using mock responses")
                api_key = "demo-key-for-demo-mode"  # Dummy key voor demo
        
        base_url = os.getenv("GREENPT_API_BASE", "https://api.greenpt.ai/v1")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.demo_mode = demo_mode
        self.model = os.getenv("GREENPT_MODEL", "gpt-4o-2024-08-06")  # Updated voor structured outputs
        self.max_tokens = int(os.getenv("GREENPT_MAX_TOKENS", "2000"))
        self.temperature = float(os.getenv("GREENPT_TEMPERATURE", "0.3"))  # Lower voor consistentie
        
        # Initialize tokenizer
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4")
        except:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # Initialize enhanced RAG system
        self.enhanced_rag = EnhancedRAGServiceWrapper()
        
        logger.info(f"Enhanced OpenAI service initialized with model: {self.model}")
        logger.info(f"API Base URL: {base_url}")
        logger.info(f"Enhanced RAG statistics: {self.enhanced_rag.get_statistics()}")

    def _determine_response_type(self, message: str, context: UserContext) -> Type:
        """Bepaal welk response type het beste past bij de vraag"""
        message_lower = message.lower()
        
        # Check voor compliance gerelateerde termen (ook gerelateerde concepten)
        compliance_terms = ['gdpr', 'ai act', 'woo', 'compliance', 'regelgeving', 'wet', 'dpia', 
                           'privacy', 'gegevensbescherming', 'avg', 'archiefwet', 'transparantie',
                           'rechtmatige grondslag', 'bewaartermijn', 'toestemming']
        
        if any(term in message_lower for term in compliance_terms):
            return ComplianceAnalysis
        
        # Check voor technische termen
        technical_terms = ['architectuur', 'implementeer', 'api', 'technical', 'code', 'systeem',
                          'database', 'server', 'cloud', 'security', 'integratie', 'deployment',
                          'microservices', 'container', 'kubernetes', 'docker']
        
        if any(term in message_lower for term in technical_terms):
            return TechnicalGuidance
        
        # Voor zeer korte vragen (minder dan 5 woorden) -> QuickAnswer
        if len(message.split()) < 5 and '?' in message and not any(term in message_lower for term in compliance_terms + technical_terms):
            return QuickAnswer
            
        # Default naar structured response voor uitgebreide antwoorden
        return StructuredAIResponse

    def _build_context_prompt(self, context: UserContext, relevant_docs: List[Dict]) -> str:
        """Build enhanced context prompt met knowledge base informatie"""
        
        base_prompt = f"""Je bent een AI assistant voor Nederlandse gemeentes, gespecialiseerd in digitale transformatie en AI implementatie.

GEBRUIKER CONTEXT:
- Rol: {context.roleName or context.role}
- Projectfase: {context.projectPhase or 'Niet gespecificeerd'}
- Focusgebieden: {', '.join([area.value for area in context.focusAreas]) if context.focusAreas else 'Algemeen'}
- Specifieke context: {context.customContext or 'Geen extra context'}

RELEVANTE KENNISBANK INFORMATIE:
"""
        
        # Voeg relevante documenten toe
        for i, doc in enumerate(relevant_docs[:3], 1):  # Max 3 docs voor context
            base_prompt += f"""
{i}. {doc['title']} ({doc['type']})
   {doc['summary']}
   Relevantie: {doc['score']}
"""
        
        base_prompt += """

INSTRUCTIES:
1. Gebruik de kennisbank informatie om accurate, brongestuurde antwoorden te geven
2. Wees specifiek over regelgeving en compliance requirements
3. Geef praktische, uitvoerbare adviezen
4. Verwijs naar menselijke experts voor complexe juridische interpretaties
5. Houd altijd rekening met de Nederlandse overheidscontext
6. Wees transparant over beperkingen van je kennis

RESPONSE FORMAT:
Geef een duidelijke hoofdrespons die de vraag volledig beantwoordt.
Voeg GEEN bronverwijzingen, vervolgvragen of escalatie-informatie toe - deze worden automatisch toegevoegd door het systeem.
"""
        
        return base_prompt

    def _extract_knowledge_sources(self, relevant_docs: List[Dict]) -> List[KnowledgeSource]:
        """Convert relevante documenten naar KnowledgeSource objecten"""
        sources = []
        
        for doc in relevant_docs:
            source = KnowledgeSource(
                title=doc['title'],
                url=doc.get('url', ''),
                snippet=doc.get('content_snippet', doc['summary']),
                relevance_score=doc.get('relevance_score', min(doc['score'] / 10.0, 1.0)),  # Use provided relevance_score or normalize
                document_type=self._map_doc_type_to_enum(doc['type']),
                document_id=doc['document_id'],
                # Enhanced RAG specific fields
                file_path=doc.get('file_path'),
                section_title=doc.get('section_title'),
                chunk_index=doc.get('chunk_index'),
                total_chunks=doc.get('total_chunks'),
                original_url=doc.get('original_url'),
                document_title=doc.get('document_title')
            )
            sources.append(source)
            
        return sources

    def _map_doc_type_to_enum(self, doc_type: str) -> str:
        """Map document types naar enum values"""
        mapping = {
            'privacy_law': 'law',
            'ai_regulation': 'law', 
            'transparency_law': 'law',
            'technical_standard': 'guideline',
            'municipal_guidance': 'best_practice',
            'official_guidance': 'guideline'
        }
        return mapping.get(doc_type, 'guideline')

    def _assess_complexity_and_confidence(self, message: str, context: UserContext, relevant_docs: List[Dict]) -> tuple:
        """Assess complexity level en confidence gebaseerd op verschillende factoren"""
        
        complexity_indicators = {
            'expert_required': ['juridisch advies', 'contract', 'aanbesteding', 'rechtszaak', 'boete'],
            'complex': ['implementatie strategie', 'architectuur design', 'compliance framework'],
            'moderate': ['best practices', 'richtlijnen', 'standaarden'],
            'simple': ['wat is', 'hoe werkt', 'definitie', 'uitleg']
        }
        
        message_lower = message.lower()
        complexity = ComplexityLevel.MODERATE  # Default
        
        for level, indicators in complexity_indicators.items():
            if any(indicator in message_lower for indicator in indicators):
                complexity = ComplexityLevel(level)
                break
        
        # Confidence gebaseerd op knowledge base matches
        confidence = ConfidenceLevel.MEDIUM  # Default
        if relevant_docs:
            avg_score = sum(doc['score'] for doc in relevant_docs) / len(relevant_docs)
            if avg_score > 7:
                confidence = ConfidenceLevel.HIGH
            elif avg_score < 3:
                confidence = ConfidenceLevel.LOW
        
        return complexity, confidence

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def generate_structured_response(self, chat_message: ChatMessage, force_response_type: Type = None) -> Union[StructuredAIResponse, QuickAnswer, ComplianceAnalysis, TechnicalGuidance, ErrorResponse]:
        """Generate structured AI response met knowledge base integratie"""
        
        start_time = time.time()
        
        try:
            # Search enhanced RAG system voor relevante documenten
            relevant_docs = self.enhanced_rag.search_documents(
                chat_message.message,
                max_results=5
            )
            
            # Voeg role-specific documenten toe
            role_docs = self.enhanced_rag.get_role_specific_documents(
                chat_message.context.role.value if chat_message.context.role else 'other'
            )
            
            # Combine en deduplicate
            all_docs = {doc['document_id']: doc for doc in relevant_docs + role_docs[:3]}
            final_docs = list(all_docs.values())[:5]
            
            # Always use StructuredAIResponse
            response_type_class = StructuredAIResponse
            
            # Build context prompt
            system_prompt = self._build_context_prompt(chat_message.context, final_docs)
            
            # Assess complexity en confidence
            complexity, confidence = self._assess_complexity_and_confidence(
                chat_message.message, chat_message.context, final_docs
            )
            
            # Check token limits
            prompt_tokens = self._count_tokens(system_prompt + chat_message.message)
            if prompt_tokens > 6000:  # Leave room for response
                logger.warning("Token limit approached, truncating context")
                system_prompt = system_prompt[:4000]
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": chat_message.message}
            ]
            
            # Voor demo doeleinden: gebruik mock structured response
            # In productie: gebruik echte GreenPT structured outputs API
            use_demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
            
            completion = None
            if use_demo_mode or os.getenv("GREENPT_API_KEY", "").startswith("demo"):
                # Demo structured response
                logger.info("Using demo structured response")
                structured_response = self._create_demo_structured_response(
                    chat_message.message, response_type_class, final_docs, complexity, confidence
                )
            else:
                try:
                    # Real OpenAI completion (niet structured outputs voor nu)
                    logger.info(f"Using real OpenAI API with {response_type_class.__name__}")
                    
                    # Enhanced system prompt voor structured response
                    enhanced_prompt = system_prompt + f"""

VERY IMPORTANT: Je MOET een {response_type_class.__name__} response geven. 

Antwoord altijd in het Nederlands en geef concrete, actionable informatie.
Focus op gemeente-specifieke context en Nederlandse regelgeving.

BELANGRIJK: Voeg GEEN bronverwijzingen, vervolgvragen of escalatie-secties toe aan je antwoord.
Deze worden automatisch door het systeem toegevoegd.

Voor ComplianceAnalysis: Focus op GDPR, AI Act, Woo, en andere relevante wetgeving
Voor TechnicalGuidance: Focus op Common Ground, open standaarden, en overheids-architectuur
Voor StructuredAIResponse: Geef uitgebreide, gestructureerde antwoorden met concrete actiepunten
"""
                    
                    completion = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": enhanced_prompt},
                            {"role": "user", "content": chat_message.message}
                        ],
                        max_tokens=self.max_tokens,
                        temperature=self.temperature
                    )
                    
                    response_text = completion.choices[0].message.content
                    print(response_text)
                    
                    # Voor nu: converteer text response naar structured format
                    structured_response = await self._convert_text_to_structured(
                        response_text, response_type_class, final_docs, complexity, confidence
                    )
                    
                except Exception as e:
                    logger.warning(f"OpenAI API failed: {e}")
                    # Fallback to demo response
                    structured_response = self._create_demo_structured_response(
                        chat_message.message, response_type_class, final_docs, complexity, confidence
                    )
            
            # Post-process response met additional metadata
            if isinstance(structured_response, StructuredAIResponse):
                # Add knowledge sources
                structured_response.knowledge_sources = self._extract_knowledge_sources(final_docs)
                
                # Add processing metadata
                structured_response.processing_time_ms = int((time.time() - start_time) * 1000)
                structured_response.token_usage = completion.usage.total_tokens if completion and completion.usage else None
                
                # Set confidence en complexity
                structured_response.confidence_level = confidence
                structured_response.complexity = complexity
                
                # Generate follow-up suggestions
                structured_response.follow_up_suggestions = await self._generate_follow_up_suggestions(
                    chat_message.context, chat_message.message
                )
            
            logger.info(f"Generated {type(structured_response).__name__} in {time.time() - start_time:.2f}s")
            return structured_response
            
        except Exception as e:
            logger.error(f"Error in structured response generation: {e}")
            return ErrorResponse(
                error_type="api_error",
                error_message="Er ging iets mis bij het genereren van het antwoord. Probeer het opnieuw.",
                technical_details=str(e),
                suggested_action="Probeer je vraag opnieuw te stellen of neem contact op met een expert.",
                needs_human_help=True
            )

    async def _generate_follow_up_suggestions(self, context: UserContext, message: str) -> List[FollowUpSuggestion]:
        """Generate dynamic, context-aware follow-up suggestions using AI"""
        
        try:
            # Create a simple prompt for generating relevant follow-up questions
            follow_up_prompt = f"""
Gebaseerd op gebruikersrol '{context.role.value if context.role else 'Algemene gebruiker'}' en mijn antwoord: "{message[:200]}..."

Genereer 3 logische vervolgvragen die deze gebruiker waarschijnlijk zou willen stellen na mijn antwoord. 
Denk na over:
- Wat zou hij/zij als volgende willen weten?
- Welke praktische vragen zouden opkomen?
- Welke verdieping zou relevant zijn voor hun rol?

Maak de vragen alsof de gebruiker ze zou stellen (dus vanuit hun perspectief).

Formaat per vraag (één vraag per regel):
1. [vraag tekst]
2. [vraag tekst] 
3. [vraag tekst]

Geen JSON, alleen de vragen zelf.
"""
            
            # Use the AI service to generate dynamic suggestions
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Je bent een expert die logische vervolgvragen genereert die een gebruiker zou kunnen stellen na het ontvangen van een antwoord. Bedenk wat de gebruiker als volgende zou willen weten. Geef alleen de vragen terug, geen extra tekst."},
                    {"role": "user", "content": follow_up_prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )
            
            ai_response = completion.choices[0].message.content.strip()
            
            # Parse the response and extract questions
            lines = [line.strip() for line in ai_response.split('\n') if line.strip()]
            valid_suggestions = []
            
            for i, line in enumerate(lines[:3]):
                # Remove numbering if present
                question = line
                if question.startswith(('1.', '2.', '3.', '-', '•')):
                    question = question.split('.', 1)[-1].strip() if '.' in question else question[1:].strip()
                
                if len(question) > 10:  # Basic validation
                    # Determine category based on content
                    category = "process"  # default
                    if any(word in question.lower() for word in ['wet', 'regel', 'compliance', 'gdpr', 'juridisch']):
                        category = "legal"
                    elif any(word in question.lower() for word in ['technisch', 'api', 'systeem', 'software', 'code']):
                        category = "technical"
                    elif any(word in question.lower() for word in ['beleid', 'policy', 'strategie']):
                        category = "policy"
                    
                    valid_suggestions.append(FollowUpSuggestion(
                        question=question,
                        category=category,
                        relevance=0.9 - (i * 0.1)  # Decreasing relevance
                    ))
            
            if valid_suggestions:
                return valid_suggestions
                
        except Exception as e:
            logger.error(f"Error generating AI follow-up suggestions: {e}")
            
        # Fallback to simple, role-based suggestions in Dutch
        role_fallbacks = {
            UserRole.DIGITAL_GUIDE: [
                ("Hoe zorg ik voor draagvlak bij stakeholders voor dit project?", "process", 0.8),
                ("Welke implementatierisico's moet ik monitoren?", "process", 0.7),
                ("Wie zijn de belangrijkste stakeholders om te betrekken?", "process", 0.7)
            ],
            UserRole.CIVIL_SERVANT: [
                ("Welke andere regelgeving is relevant voor mijn situatie?", "legal", 0.8),
                ("Hoe documenteer ik compliance voor audits?", "legal", 0.7),
                ("Wat zijn de sancties bij non-compliance?", "legal", 0.6)
            ],
            UserRole.IT_MANAGER: [
                ("Welke technische standaarden moet ik volgen?", "technical", 0.8),
                ("Hoe zorg ik voor schaalbaarheid van dit systeem?", "technical", 0.7),
                ("Wat zijn de security best practices?", "technical", 0.7)
            ],
            UserRole.PROJECT_MANAGER: [
                ("Hoe plan ik de volgende fase van dit project?", "process", 0.8),
                ("Welke resources heb ik nodig voor implementatie?", "process", 0.7),
                ("Hoe meet ik het succes van dit project?", "process", 0.6)
            ],
            UserRole.DEVELOPER: [
                ("Waar vind ik documentatie voor deze APIs?", "technical", 0.8),
                ("Welke testing strategie moet ik hanteren?", "technical", 0.7),
                ("Hoe zorg ik voor code kwaliteit?", "technical", 0.6)
            ]
        }
        
        role = context.role or UserRole.OTHER
        suggestions_data = role_fallbacks.get(role, [
            ("Waar kan ik meer informatie vinden over dit onderwerp?", "process", 0.6),
            ("Wie kan me verder helpen met specifieke vragen?", "process", 0.5)
        ])
        
        return [FollowUpSuggestion(question=q, category=cat, relevance=rel) 
               for q, cat, rel in suggestions_data[:3]]

    def _extract_action_items(self, response_text: str) -> List[ActionItem]:
        """Extract action items from response text using AI-generated suggestions"""
        # Generate dynamic, context-aware action items based on the response content
        action_items = []
        
        # Use AI to generate relevant follow-up actions based on response content
        try:
            action_prompt = f"""
            Based on this response: "{response_text[:500]}..."
            
            Generate 1-2 specific, actionable follow-up items that would be most relevant and helpful for the user. 
            Focus on practical next steps that directly relate to the content discussed.
            
            Format as JSON array with objects containing: title, description, priority (high/medium/low), timeline
            Keep descriptions concise and actionable.
            """
            
            # This would integrate with your AI service to generate dynamic actions
            # For now, return empty to remove the hardcoded Dutch content
            
        except Exception as e:
            logger.error(f"Error generating action items: {e}")
        
        return action_items

    def _identify_regulations(self, response_text: str) -> List[RegulationType]:
        """Identify relevant regulations mentioned in response"""
        regulations = []
        text_lower = response_text.lower()
        
        if any(term in text_lower for term in ['gdpr', 'avg', 'privacy']):
            regulations.append(RegulationType.GDPR)
        if any(term in text_lower for term in ['ai act', 'kunstmatige intelligentie']):
            regulations.append(RegulationType.AI_ACT)
        if any(term in text_lower for term in ['woo', 'openbaarheid']):
            regulations.append(RegulationType.WOO)
        if any(term in text_lower for term in ['toegankelijkheid', 'wcag']):
            regulations.append(RegulationType.TOEGANKELIJKHEID)
        if any(term in text_lower for term in ['archief', 'archiefwet']):
            regulations.append(RegulationType.ARCHIEFWET)
        
        # Default to general if no specific regulation found
        if not regulations:
            regulations.append(RegulationType.GENERAL)
        
        return regulations

    async def _convert_text_to_structured(self, response_text: str, response_type_class: Type, docs: List[Dict], complexity: ComplexityLevel, confidence: ConfidenceLevel):
        """Convert text response to structured format"""
        
        # Always return StructuredAIResponse
        return StructuredAIResponse(
            main_answer=response_text,
            response_type=ResponseType.DIRECT_ANSWER,
            confidence_level=confidence,
            complexity=complexity,
            knowledge_sources=self._extract_knowledge_sources(docs),
            action_items=self._extract_action_items(response_text),
            compliance_checks=[],
            follow_up_suggestions=[],  # Will be filled later
            needs_human_expert=complexity == "high" or confidence == "low",
            expert_reason="Complex onderwerp vereist expert beoordeling" if complexity == "high" or confidence == "low" else None,
            expert_type="legal" if complexity == "high" or confidence == "low" else None,
            relevant_regulations=self._identify_regulations(response_text),
            stakeholders=[],
            processing_time_ms=0,  # Will be set later
            token_usage=None
        )
        
        # Old complex logic - keeping for reference but not used
        if False and response_type_class == ComplianceAnalysis:
            # Determine regulation type from response content
            regulation_type = RegulationType.AI_ACT if 'ai act' in response_text.lower() else RegulationType.GDPR
            
            return ComplianceAnalysis(
                regulation_type=regulation_type,
                compliance_status="needs_assessment",
                requirements=[
                    "Data Protection Impact Assessment (DPIA) uitvoeren",
                    "Privacy notice opstellen en publiceren",
                    "Rechtmatige grondslag vastleggen en documenteren",
                    "Beveiligingsmaatregelen implementeren"
                ],
                gaps=[
                    "DPIA nog niet uitgevoerd",
                    "Privacy notice ontbreekt", 
                    "Compliance review nodig"
                ],
                immediate_actions=[
                    ActionItem(
                        title="Review AI Analyse",
                        description=f"Review de gegenereerde analyse: {response_text}",
                        priority="high",
                        timeline="Voor go-live",
                        resources=["DPO", "Legal team"]
                    ),
                    ActionItem(
                        title="DPIA opstarten",
                        description="Data Protection Impact Assessment uitvoeren voor het AI systeem",
                        priority="high",
                        timeline="Voor go-live",
                        resources=["DPO", "Legal team"]
                    )
                ],
                risk_assessment="Medium risico: AI systeem verwerkt mogelijk persoonlijke gegevens van burgers. Compliance verificatie is verplicht.",
                timeline="6-8 weken voor volledige compliance",
                budget_implications="Circa €15.000-25.000 voor compliance consultancy en implementatie"
            )
        elif response_type_class == TechnicalGuidance:
            return TechnicalGuidance(
                solution_approach=response_text,
                architecture_recommendations=[
                    "Gebruik API-first design principes",
                    "Implementeer microservices architectuur", 
                    "Volg Common Ground standaarden",
                    "Zet cloud-native oplossing op"
                ],
                implementation_steps=[
                    ActionItem(
                        title="Analyseer technische vereisten",
                        description="Review de volledige AI guidance en identificeer specifieke technische behoeften",
                        priority="high",
                        timeline="Deze week",
                        resources=["IT Architect", "Development team"]
                    )
                ],
                technology_stack=[
                    "FastAPI/Node.js voor backend",
                    "React/Vue.js voor frontend",
                    "PostgreSQL voor database",
                    "Docker voor containerization",
                    "Kubernetes voor orchestration"
                ],
                common_pitfalls=[
                    "Onvoldoende security maatregelen",
                    "Geen backup en disaster recovery plan",
                    "Inadequate monitoring en logging",
                    "Verkeerde API versioning strategie"
                ],
                best_practices=[
                    "Implementeer comprehensive testing",
                    "Gebruik Infrastructure as Code",
                    "Zet proper monitoring op",
                    "Documenteer alle API endpoints",
                    "Volg security best practices"
                ],
                testing_strategy="Unit tests, integration tests, end-to-end tests en security testing",
                monitoring_requirements=[
                    "Application performance monitoring",
                    "Infrastructure monitoring",
                    "Security monitoring en alerting",
                    "User experience tracking"
                ]
            )
        else:
            # StructuredAIResponse
            knowledge_sources = self._extract_knowledge_sources(docs) if docs else []
            
            return StructuredAIResponse(
                main_answer=response_text,
                response_type=ResponseType.DIRECT_ANSWER,
                confidence_level=confidence,
                complexity=complexity,
                action_items=[],
                compliance_checks=[],
                knowledge_sources=knowledge_sources,
                follow_up_suggestions=await self._generate_follow_up_suggestions(
                    UserContext(role=UserRole.OTHER), response_text
                ),
                needs_human_expert=complexity == ComplexityLevel.EXPERT_REQUIRED,
                expert_reason="Complex onderwerp vereist expert beoordeling" if complexity == ComplexityLevel.EXPERT_REQUIRED else None,
                expert_type="legal" if complexity == ComplexityLevel.EXPERT_REQUIRED else None,
                relevant_regulations=[RegulationType.GENERAL],
                stakeholders=[],
                processing_time_ms=1000,
                token_usage=None
            )

    def _create_demo_structured_response(self, message: str, response_type_class: Type, docs: List[Dict], complexity: ComplexityLevel, confidence: ConfidenceLevel):
        """Create demo structured response voor development/testing"""
        message_lower = message.lower()
        
        # Create response text based on message content
        response_text = ""
        
        # GDPR/Compliance specific demo - check for any compliance terms
        compliance_terms = ['gdpr', 'dpia', 'privacy', 'compliance', 'avg', 'gegevensbescherming', 'wet', 'regelgeving']
        if any(term in message_lower for term in compliance_terms):
            response_text = f"""## GDPR Compliance voor Gemeente AI Systeem

Voor de implementatie van een AI systeem binnen de gemeente zijn de volgende GDPR maatregelen essentieel:

### 🔒 Rechtmatige Grondslag
- **Gerechtvaardigd belang** voor publieke dienstverlening
- **Wettelijke verplichting** voor overheidstaken
- Documenteer en communiceer de grondslag duidelijk aan gebruikers

### 📋 Transparantie & Informatieplicht
- Stel een duidelijke **privacy notice** op voor gebruik
- Leg uit dat gebruikers met een AI systeem interacteren
- Vermeld doeleinden van gegevensverwerking
- Geef contactgegevens van de DPO (Data Protection Officer)

### 🛡️ Dataminimalisatie & Beveiliging
- Verzamel alleen **noodzakelijke** gegevens voor de service
- Gebruik **encryptie** voor data in transit en at rest
- Implementeer toegangscontrole voor beheerders
- Voer regelmatige security assessments uit

### ⏰ Bewaartermijnen
- Stel duidelijke bewaartermijnen vast voor chat data
- Implementeer automatische verwijdering na afloop termijn
- Documenteer retentiebeleid in DPIA"""

        elif any(term in message_lower for term in ['architectuur', 'technisch', 'implementatie', 'api', 'system']):
            response_text = f"""## Technische Architectuur voor Gemeente AI Systeem

Voor een robuuste en schaalbare AI implementatie adviseer ik de volgende technische aanpak:

### 🏗️ Aanbevolen Architectuur
- **Microservices** architectuur voor schaalbaarheid
- **API Gateway** voor centraal beheer en security
- **Container orchestration** met Docker/Kubernetes
- **Cloud-agnostic** deployment voor vendor onafhankelijkheid

### 💻 Technology Stack
- **Frontend**: React/Vue.js met TypeScript
- **Backend**: FastAPI (Python) of Express.js (Node.js)
- **Database**: PostgreSQL voor structured data
- **Caching**: Redis voor session management
- **AI Integration**: OpenAI API met LangChain orchestration

### 🔐 Security & Compliance
- HTTPS/TLS 1.3 encryptie verplicht
- OAuth 2.0 / OIDC authenticatie
- API rate limiting en monitoring
- Comprehensive audit logging
- Regular security assessments

### 📊 Monitoring & Observability
- Application Performance Monitoring (APM)
- Infrastructure monitoring met alerts
- API response times en error rate tracking
- User behavior analytics voor optimalisatie"""

        else:
            response_text = f"""## Gemeente AI Assistant Response

Bedankt voor je vraag: "{message}"

Als gemeente professional help ik je graag met digitale transformatie vraagstukken. Gebaseerd op de beschikbare knowledge base met {len(docs)} relevante documenten, kan ik je ondersteunen bij:

### 🎯 Algemene Aanbevelingen
- Raadpleeg de relevante gemeente richtlijnen
- Volg best practices voor digitale dienstverlening
- Zorg voor adequate stakeholder betrokkenheid
- Implementeer iteratieve aanpak met feedback loops

### 📚 Knowledge Base Informatie
Er zijn {len(docs)} relevante documenten gevonden die aansluiten bij je vraag. Deze bevatten specifieke richtlijnen en best practices voor gemeente digitalisering.

### 🔍 Vervolgstappen
1. Review de aangeleverde bronnen uit de knowledge base
2. Bepaal welke aspecten specifiek van toepassing zijn op jouw situatie
3. Overleg met relevante stakeholders en experts
4. Stel een implementatieplan op met concrete mijlpalen"""

        # Always return StructuredAIResponse
        return StructuredAIResponse(
            main_answer=response_text,
            response_type=ResponseType.DIRECT_ANSWER,
            confidence_level=confidence,
            complexity=complexity,
            knowledge_sources=self._extract_knowledge_sources(docs),
            action_items=self._extract_action_items(response_text),
            compliance_checks=[],
            follow_up_suggestions=[],  # Will be filled later
            needs_human_expert=complexity == "high" or confidence == "low",
            expert_reason="Complex onderwerp vereist expert beoordeling" if complexity == "high" or confidence == "low" else None,
            expert_type="legal" if complexity == "high" or confidence == "low" else None,
            relevant_regulations=self._identify_regulations(response_text),
            stakeholders=[],
            processing_time_ms=1000,
            token_usage=None
        )

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        try:
            return len(self.encoding.encode(text))
        except:
            return len(text.split())  # Fallback

    async def health_check(self) -> Dict[str, any]:
        """Enhanced health check met enhanced RAG status"""
        try:
            # Enhanced RAG statistics
            rag_stats = self.enhanced_rag.get_statistics()
            
            health_data = {
                "status": "healthy",
                "model": self.model,
                "demo_mode": self.demo_mode,
                "enhanced_rag": {
                    "status": rag_stats.get('status', 'unknown'),
                    "documents": rag_stats.get('total_documents', 0),
                    "chunks": rag_stats.get('total_chunks', 0),
                    "document_types": rag_stats.get('document_types', {}),
                    "embedding_model": rag_stats.get('embedding_model', 'unknown'),
                    "cache_available": rag_stats.get('cache_available', False)
                }
            }
            
            if not self.demo_mode:
                # Test echte OpenAI API alleen als niet in demo mode
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "Test"}],
                    max_tokens=10
                )
                health_data["api_usage"] = response.usage.dict() if response.usage else None
            else:
                health_data["api_usage"] = "demo_mode_active"
            
            return health_data
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy" if not self.demo_mode else "demo_mode",
                "demo_mode": self.demo_mode,
                "error": str(e),
                "enhanced_rag": {"status": "unknown"}
            }
