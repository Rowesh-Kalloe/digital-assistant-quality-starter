import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 45000, // Longer timeout voor structured responses
  headers: {
    'Content-Type': 'application/json',
  },
})

// Enhanced API service voor structured outputs
export const enhancedAPI = {
  // Structured chat endpoint - returns StructuredAIResponse
  async sendStructuredMessage(message, userContext) {
    try {
      // Map new context structure to API expected format
      // Map choice to valid role enum
      const choiceToRole = {
        'waarom': 'project-manager',
        'wat': 'it-manager', 
        'hoe': 'project-manager',
        'general': 'other'
      }
      
      // Determine the correct role - prioritize valid enum values
      let mappedRole = 'other'
      if (userContext.role?.id && ['digital-guide', 'civil-servant', 'it-manager', 'project-manager', 'developer', 'other'].includes(userContext.role.id)) {
        mappedRole = userContext.role.id
      } else if (userContext.selectedChoice && choiceToRole[userContext.selectedChoice]) {
        mappedRole = choiceToRole[userContext.selectedChoice]
      }
      
      const mappedContext = {
        role: mappedRole,
        roleName: userContext.role?.name || `${userContext.selectedChoice?.toUpperCase()} gebruiker`,
        projectPhase: userContext.projectPhase || userContext.selectedChoice,
        focusAreas: userContext.focusAreas || [],
        specificNeeds: userContext.specificNeeds || [],
        customContext: userContext.selectedOrganization ? 
          `Organisatie niveau: ${userContext.selectedOrganization.name}. Interesse: ${userContext.selectedChoice}` :
          userContext.customContext
      }

      const response = await api.post('/api/chat/validated', {
        message: message.trim(),
        context: mappedContext,
        timestamp: new Date().toISOString()
      })

      console.log('Request data:', {
        message: message.trim(),
        context: mappedContext,
        timestamp: new Date().toISOString()
      })

      return response.data
    } catch (error) {
      console.error('Error in structured message:', error)
      throw error
    }
  },


  // Knowledge base search
  async searchKnowledgeBase(query, documentTypes = null, maxResults = 5) {
    try {
      const params = new URLSearchParams({
        query: query,
        max_results: maxResults
      })
      
      if (documentTypes && documentTypes.length > 0) {
        params.append('document_types', documentTypes.join(','))
      }

      const response = await api.get(`/api/knowledge/search?${params}`)
      return response.data
    } catch (error) {
      console.error('Error searching knowledge base:', error)
      throw error
    }
  },

  // Get role-specific knowledge
  async getRoleKnowledge(role) {
    try {
      const response = await api.get(`/api/knowledge/role/${role}`)
      return response.data
    } catch (error) {
      console.error('Error getting role knowledge:', error)
      throw error
    }
  },

  // Get compliance-specific documents
  async getComplianceKnowledge(regulation) {
    try {
      const response = await api.get(`/api/knowledge/compliance/${regulation}`)
      return response.data
    } catch (error) {
      console.error('Error getting compliance knowledge:', error)
      throw error
    }
  },

  // Get knowledge base statistics
  async getKnowledgeStats() {
    try {
      const response = await api.get('/api/knowledge/stats')
      return response.data
    } catch (error) {
      console.error('Error getting knowledge stats:', error)
      throw error
    }
  },

  // Get document by ID
  async getDocument(documentId) {
    try {
      const response = await api.get(`/api/knowledge/document/${documentId}`)
      return response.data
    } catch (error) {
      console.error('Error getting document:', error)
      throw error
    }
  },

  // Enhanced RAG specific methods
  async getEnhancedRAGDocument(documentId) {
    try {
      const response = await api.get(`/api/enhanced-rag/document/${documentId}`)
      return response.data
    } catch (error) {
      console.error('Error getting enhanced RAG document:', error)
      throw error
    }
  },

  // Get full markdown content for a document
  async getFullMarkdownDocument(documentId) {
    try {
      console.log('Requesting full markdown for document:', documentId)
      const response = await api.get(`/api/knowledge/document/${documentId}/full`)
      return response.data
    } catch (error) {
      console.error('Error getting full markdown document:', error)
      // Fallback to regular document endpoint
      return await this.getDocument(documentId)
    }
  },

  // Get enhanced RAG context for a query
  async getEnhancedRAGContext(query, maxChunks = 3) {
    try {
      const params = new URLSearchParams({
        query: query,
        max_chunks: maxChunks
      })
      const response = await api.get(`/api/enhanced-rag/context?${params}`)
      return response.data
    } catch (error) {
      console.error('Error getting enhanced RAG context:', error)
      throw error
    }
  },

  // Enhanced health check
  async getHealthStatus() {
    try {
      const response = await api.get('/api/health')
      return response.data
    } catch (error) {
      console.error('Error getting health status:', error)
      throw error
    }
  },

  // Always use structured message
  async sendSmartMessage(message, userContext) {
    return await this.sendStructuredMessage(message, userContext)
  }
}

// Demo mode fallback responses
export const demoResponses = {
  gdpr: {
    main_answer: `## GDPR Vereisten voor Gemeente Chatbots

Voor een gemeente chatbot die burgerservice ondersteunt, gelden de volgende **GDPR verplichtingen**:

### 1. Rechtmatige Grondslag (Art. 6 GDPR)
- **Gerechtvaardigd belang** voor publieke dienstverlening
- **Wettelijke verplichting** voor overheidstaken
- Documenteer en communiceer de grondslag duidelijk

### 2. Transparantie & Informatieplicht (Art. 12-14)
- **Duidelijke privacy notice** vóór eerste gebruik
- Leg uit dat gebruikers met AI praten
- Vermeld doeleinden van gegevensverwerking
- Geef contactgegevens van DPO (Data Protection Officer)

### 3. Dataminimalisatie (Art. 5.1.c)
- Verzamel alleen **noodzakelijke** gegevens voor de service
- Geen persoonlijke data opslaan tenzij strikt nodig
- Gebruik geanonimiseerde chat logs waar mogelijk

### 4. Bewaartermijn (Art. 5.1.e)
- Stel duidelijke **bewaartermijnen** vast voor chat data
- Automatische verwijdering na afloop termijn
- Documenteer retentiebeleid in DPIA

### 5. Beveiliging (Art. 32)
- **Encryptie** van data in transit en at rest
- Toegangscontrole voor beheerders
- Regular security assessments`,
    
    response_type: "compliance_analysis",
    confidence_level: "high",
    complexity: "moderate",
    
    action_items: [
      {
        title: "DPIA uitvoeren",
        description: "Data Protection Impact Assessment opstellen voor de chatbot",
        priority: "high",
        timeline: "Voor go-live"
      },
      {
        title: "Privacy notice opstellen",
        description: "Duidelijke gebruikersinformatie over dataverwerking",
        priority: "high",
        timeline: "Voor go-live"
      }
    ],
    
    compliance_checks: [
      {
        regulation: "gdpr",
        status: "needs_review",
        requirements: ["DPIA", "Privacy notice", "Rechtmatige grondslag", "Bewaartermijn"],
        recommendations: ["Raadpleeg DPO", "Gebruik privacy by design", "Implementeer opt-out"],
        risk_level: "medium"
      }
    ],
    
    knowledge_sources: [
      {
        title: "GDPR Handreiking Overheid",
        url: "#gdpr-guidance",
        snippet: "Specifieke richtlijnen voor overheids-AI systemen",
        relevance_score: 0.95,
        document_type: "guideline"
      }
    ],
    
    follow_up_suggestions: [
      {
        question: "Hoe stel ik een DPIA op voor een chatbot?",
        category: "legal",
        relevance: 0.9
      },
      {
        question: "Welke bewaartermijnen zijn gebruikelijk voor chat logs?",
        category: "legal", 
        relevance: 0.8
      }
    ],
    
    needs_human_expert: false,
    relevant_regulations: ["gdpr"],
    processing_time_ms: 1500
  },

  technical: {
    main_answer: `## Technische Architectuur voor Gemeente Chatbot

### Aanbevolen Technologie Stack

**Frontend:**
- React/Vue.js voor gebruikersinterface
- TypeScript voor type safety
- Tailwind CSS voor styling

**Backend:**
- FastAPI (Python) of Express.js (Node.js)
- PostgreSQL voor structured data
- Redis voor session management

**AI & ML:**
- OpenAI GPT-4o voor language processing
- Vector database (Pinecone/Weaviate) voor RAG
- LangChain voor AI orchestration

### Security & Compliance
- HTTPS/TLS 1.3 encryption
- OAuth 2.0 / OIDC authentication
- API rate limiting
- Audit logging

### Deployment
- Docker containers
- Kubernetes orchestration
- Cloud-agnostic (Azure/AWS/GCP)`,
    
    solution_approach: "Cloud-native microservices architectuur",
    implementation_steps: [
      {
        title: "API Gateway opzetten",
        description: "Implementeer API gateway voor routing en security",
        priority: "high"
      }
    ],
    
    technology_stack: ["FastAPI", "React", "PostgreSQL", "Docker", "Kubernetes"],
    best_practices: ["API versioning", "Health checks", "Monitoring"],
    processing_time_ms: 1200
  }
}

export default api