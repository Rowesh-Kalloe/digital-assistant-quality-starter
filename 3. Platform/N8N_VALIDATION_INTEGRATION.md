# N8N Validation Layer Integration Guide

## 🎯 Overview

This integration adds an **advanced security validation layer** to your chatbot using n8n workflows. Every AI response is validated through your n8n webhook **BEFORE** the user sees it, ensuring consistent and reliable output.

## 🔒 How It Works

```
User sends message
    ↓
AI generates response
    ↓
🔒 SECURITY LAYER: Send to n8n webhook
    ↓
n8n validates/modifies response
    ↓
User sees validated response
```

**During validation:** User sees a loading animation while n8n processes the response.

## 📁 Files Created

### 1. **Validation Service** 
`backend/app/services/n8n_validation_service.py`
- Handles communication with n8n webhook
- Manages validation timeouts and retries
- Processes validation results

### 2. **Validated Chat Endpoint**
`backend/app/routers/enhanced_chat_with_validation.py`
- New endpoint: `POST /api/chat/validated`
- Integrates n8n validation into chat flow
- Provides detailed logging of validation process

### 3. **Updated Main Application**
`backend/app/main_with_n8n.py`
- Initializes n8n validation service
- Registers validated chat router
- Enhanced startup logging

### 4. **Environment Configuration**
`backend/.env.n8n.example`
- Configuration template for n8n integration

## 🚀 Setup Instructions

### Step 1: Configure Environment Variables

Copy the example file and configure:

```bash
cd "3. Platform/backend"
cp .env.n8n.example .env
```

Edit `.env` and set:

```bash
# Enable n8n validation
N8N_VALIDATION_ENABLED=true

# Your n8n webhook URL (from your n8n workflow)
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/validate-chatbot-response

# Validation timeout (seconds)
N8N_VALIDATION_TIMEOUT=30
```

### Step 2: Update Your Startup Script

Modify `start.py` to use the new main file:

```python
# Change this line:
uvicorn.run("app.main:app", ...)

# To this:
uvicorn.run("app.main_with_n8n:app", ...)
```

Or run directly:

```bash
python -m uvicorn app.main_with_n8n:app --reload --host 0.0.0.0 --port 8000
```

### Step 3: Create Your n8n Validation Workflow

Your n8n workflow should:

1. **Receive webhook POST request** with this payload:
```json
{
  "response": {
    "main_answer": "...",
    "confidence_level": "high",
    "knowledge_sources": [...],
    ...
  },
  "user_context": {
    "role": "civil-servant",
    "roleName": "Beleidsadviseur",
    "projectPhase": "implementatie",
    "message": "User's original question"
  },
  "timestamp": "2026-02-05T16:30:00",
  "validation_request": true
}
```

2. **Validate the response** based on your criteria:
   - Check for sensitive information
   - Verify compliance with regulations
   - Ensure appropriate tone and language
   - Validate source citations
   - Check for hallucinations or errors

3. **Return validation result** in this format:

**✅ APPROVED (optionally modified):**
```json
{
  "approved": true,
  "modified_response": {
    "main_answer": "Modified answer if needed...",
    ...
  },
  "validation_notes": "Response approved with minor modifications",
  "security_flags": [],
  "confidence_score": 0.95
}
```

**❌ REJECTED:**
```json
{
  "approved": false,
  "rejection_reason": "Contains unverified legal advice",
  "security_flags": ["legal_advice", "high_risk"],
  "fallback_response": {
    "message": "Deze vraag vereist juridische expertise. Neem contact op met een expert.",
    "needsHumanHelp": true
  }
}
```

## 🔧 N8N Workflow Example

Here's a basic n8n workflow structure:

### Node 1: Webhook Trigger
- **Method:** POST
- **Path:** `/webhook/validate-chatbot-response`
- **Response Mode:** Wait for response

### Node 2: Validation Logic (Function/Code Node)
```javascript
// Example validation logic
const response = $input.item.json.response;
const userContext = $input.item.json.user_context;

// Check for sensitive keywords
const sensitiveKeywords = ['confidential', 'geheim', 'intern'];
const hasSensitiveContent = sensitiveKeywords.some(keyword => 
  response.main_answer.toLowerCase().includes(keyword)
);

// Check confidence level
const isLowConfidence = response.confidence_level === 'low';

// Validation decision
if (hasSensitiveContent) {
  return {
    approved: false,
    rejection_reason: "Response contains sensitive information",
    security_flags: ["sensitive_content"],
    fallback_response: {
      message: "Deze informatie vereist extra verificatie. Neem contact op met een expert.",
      needsHumanHelp: true
    }
  };
}

if (isLowConfidence) {
  // Modify response to add disclaimer
  response.main_answer += "\n\n⚠️ **Let op:** Dit antwoord heeft een lage betrouwbaarheid. Verifieer deze informatie met een expert.";
  
  return {
    approved: true,
    modified_response: response,
    validation_notes: "Added low confidence disclaimer",
    security_flags: ["low_confidence"],
    confidence_score: 0.6
  };
}

// Approve without changes
return {
  approved: true,
  validation_notes: "Response approved",
  security_flags: [],
  confidence_score: 0.95
};
```

### Node 3: Respond to Webhook
Return the validation result to the chatbot backend.

## 📡 API Usage

### Using the Validated Endpoint

**Frontend change required:**

```javascript
// OLD endpoint (no validation)
const response = await axios.post('/api/chat/structured', {
  message: userMessage,
  context: userContext,
  timestamp: new Date().toISOString()
});

// NEW endpoint (with n8n validation)
const response = await axios.post('/api/chat/validated', {
  message: userMessage,
  context: userContext,
  timestamp: new Date().toISOString()
});
```

The validated endpoint will:
1. Generate AI response (user sees loading)
2. Send to n8n for validation (user still sees loading)
3. Return validated response (user sees result)

**Total time:** AI generation time + n8n validation time

## 🎨 Frontend Integration

Update your chat interface to use the validated endpoint:

```javascript
// In src/services/enhanced_api.js or similar
export const sendValidatedMessage = async (message, context) => {
  try {
    const response = await axios.post(
      `${API_BASE_URL}/api/chat/validated`,
      {
        message,
        context,
        timestamp: new Date().toISOString()
      }
    );
    
    return response.data;
  } catch (error) {
    console.error('Validated chat error:', error);
    throw error;
  }
};
```

The loading animation will automatically show during the entire validation process.

## ⚙️ Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `N8N_VALIDATION_ENABLED` | `false` | Enable/disable validation layer |
| `N8N_WEBHOOK_URL` | - | Your n8n webhook URL (required if enabled) |
| `N8N_VALIDATION_TIMEOUT` | `30` | Timeout in seconds for validation |

### Validation Behavior

**When enabled:**
- All responses go through n8n validation
- User sees loading during validation
- Rejected responses show safe fallback
- Modified responses are used instead of originals

**When disabled:**
- Responses go directly to user
- No validation delay
- Original behavior maintained

**On timeout/error:**
- Original response is returned
- Error is logged
- User experience is not blocked

## 🔍 Monitoring & Logging

The service provides detailed logging:

```
✓ N8N validation service initialized and ENABLED
  Webhook URL: https://your-n8n.com/webhook/...
  Timeout: 30s

🔒 Sending response to n8n validation layer...
✅ Validation completed in 1.2s, status: approved
📝 Response was modified by n8n validation layer
✨ Total processing time: 3.5s (AI: 2.3s, Validation: 1.2s)
```

**Warning logs:**
```
⚠️ Response REJECTED by n8n: Contains unverified legal advice
Security flags: ['legal_advice', 'high_risk']
```

## 🧪 Testing

### Test with Validation Disabled

```bash
# In .env
N8N_VALIDATION_ENABLED=false

# Start server
python start.py

# Response goes directly to user (no n8n call)
```

### Test with Validation Enabled

```bash
# In .env
N8N_VALIDATION_ENABLED=true
N8N_WEBHOOK_URL=https://your-n8n.com/webhook/validate

# Start server
python start.py

# Every response is validated through n8n
```

### Test n8n Webhook Health

```bash
# Check if n8n service is reachable
curl http://localhost:8000/api/health

# Response includes n8n validation status
```

## 🚨 Error Handling

### Timeout Scenario
```
User sends message → AI generates → n8n times out (30s)
→ Original AI response returned to user
→ Warning logged
```

### n8n Unreachable
```
User sends message → AI generates → n8n webhook fails
→ Original AI response returned to user
→ Error logged
```

### Rejected Response
```
User sends message → AI generates → n8n rejects
→ Safe fallback message shown to user
→ Original response blocked
```

## 📊 Validation Criteria Examples

### Security Checks
- ✅ No personal data (names, addresses, BSN)
- ✅ No internal/confidential information
- ✅ No unverified legal advice
- ✅ Appropriate language and tone

### Quality Checks
- ✅ Sources are cited correctly
- ✅ Confidence level is appropriate
- ✅ Answer is relevant to question
- ✅ No hallucinations or false information

### Compliance Checks
- ✅ GDPR compliant
- ✅ Follows government communication guidelines
- ✅ Appropriate disclaimers present
- ✅ Escalation to human when needed

## 🎯 Benefits

1. **Consistent Quality:** Every response is validated before delivery
2. **Security Layer:** Catch sensitive information before users see it
3. **Compliance:** Ensure all responses meet regulatory requirements
4. **Flexibility:** Modify responses on-the-fly through n8n
5. **Auditability:** All validations logged for review
6. **Graceful Degradation:** System works even if n8n is down

## 🔄 Migration Path

### Phase 1: Testing (Current)
- Use `/api/chat/validated` endpoint for testing
- Keep original `/api/chat/structured` endpoint active
- Validate n8n workflow works correctly

### Phase 2: Gradual Rollout
- Update frontend to use validated endpoint
- Monitor performance and validation results
- Adjust n8n validation rules as needed

### Phase 3: Full Production
- Make validated endpoint the default
- Deprecate old endpoint
- Enable for all users

## 📞 Support

If you encounter issues:

1. Check logs for validation errors
2. Verify n8n webhook URL is correct
3. Test n8n workflow independently
4. Check timeout settings
5. Verify environment variables are set

## 🎉 You're Ready!

Your chatbot now has an advanced security validation layer powered by n8n. Every response is checked before users see it, ensuring consistent, reliable, and safe output.

**Next steps:**
1. Configure your `.env` file
2. Create your n8n validation workflow
3. Test with the `/api/chat/validated` endpoint
4. Update your frontend to use the validated endpoint
5. Monitor and refine your validation rules
