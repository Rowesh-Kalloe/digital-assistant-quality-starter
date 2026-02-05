# Quick Start: N8N Validation Integration

## ✅ What You Need

1. **Your n8n instance** with a webhook workflow
2. **5 minutes** to configure

## 🚀 3-Step Setup

### Step 1: Get Your n8n Webhook URL

In your n8n workflow:
1. Add a **Webhook** node (trigger)
2. Set method to **POST**
3. Copy the **Production URL** (looks like: `https://your-n8n.com/webhook/abc123`)

### Step 2: Configure Environment

Edit `3. Platform/backend/.env`:

```bash
# Enable n8n validation
N8N_VALIDATION_ENABLED=true

# Paste your webhook URL here
N8N_WEBHOOK_URL=https://your-n8n.com/webhook/abc123

# Optional: adjust timeout (default 30 seconds)
N8N_VALIDATION_TIMEOUT=30
```

### Step 3: Update Your Startup

**Option A: Modify start.py**

Edit `3. Platform/backend/start.py`, change:
```python
uvicorn.run("app.main:app", ...)
```
to:
```python
uvicorn.run("app.main_with_n8n:app", ...)
```

**Option B: Run directly**
```bash
cd "3. Platform/backend"
python -m uvicorn app.main_with_n8n:app --reload --host 0.0.0.0 --port 8000
```

## 🎯 Update Your Frontend

Change the API endpoint in your frontend code:

```javascript
// OLD
const response = await axios.post('/api/chat/structured', {...});

// NEW (with validation)
const response = await axios.post('/api/chat/validated', {...});
```

## ✨ That's It!

Your chatbot now validates every response through n8n before showing it to users.

**Test it:**
1. Start backend: `python start.py`
2. Send a message through the chat
3. Watch your n8n workflow receive the validation request
4. User sees the validated response

## 📋 N8N Workflow Template

Your n8n workflow receives:
```json
{
  "response": {
    "main_answer": "AI generated answer...",
    "confidence_level": "high",
    ...
  },
  "user_context": {
    "role": "civil-servant",
    "message": "User's question"
  }
}
```

Your workflow must return:
```json
{
  "approved": true,
  "validation_notes": "Looks good",
  "security_flags": [],
  "confidence_score": 0.95
}
```

Or to reject:
```json
{
  "approved": false,
  "rejection_reason": "Contains sensitive info",
  "fallback_response": {
    "message": "Please contact an expert",
    "needsHumanHelp": true
  }
}
```

## 🔧 Troubleshooting

**Validation not working?**
- Check `N8N_VALIDATION_ENABLED=true` in `.env`
- Verify webhook URL is correct
- Check n8n workflow is active
- Look at backend logs for errors

**Timeout errors?**
- Increase `N8N_VALIDATION_TIMEOUT` in `.env`
- Optimize your n8n workflow
- Check n8n instance performance

**Want to disable temporarily?**
```bash
# In .env
N8N_VALIDATION_ENABLED=false
```

## 📚 Full Documentation

See `N8N_VALIDATION_INTEGRATION.md` for complete details, advanced configuration, and examples.

---

**Ready to validate!** 🎉
