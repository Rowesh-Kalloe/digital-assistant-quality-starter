# 🔑 GreenPT API Key Setup

## Voor Volledige Functionaliteit

De Gemeente AI Assistant gebruikt GreenPT - een privacy-vriendelijke en duurzame OpenAI-compatibele API. Om alle features te gebruiken heb je een GreenPT API key nodig.

### 1. Verkrijg een GreenPT API Key

Je GreenPT API key wordt verstrekt door de hackathon organisatie. Vraag deze aan of activeer hem na de uitleg.

### 2. Configureer de API Key

1. Kopieer de `.env.example` file naar `.env`:

```bash
cd backend
cp .env.example .env
```

2. Open `backend/.env` en vul je GreenPT key in:

```bash
GREENPT_API_KEY=sk--kufFCXhR9OHR-avU_TFF6mc9qDD8ktNjXhRbycSjJU
```

### 3. Zet Demo Mode Uit

In dezelfde `.env` file, verander:

```bash
DEMO_MODE=false
```

### 4. Herstart de Backend

```bash
cd backend
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## 🎮 Demo Mode (Zonder API Key)

Voor demonstratie en development kun je de app gebruiken zonder echte GreenPT API:

```bash
# In .env file:
DEMO_MODE=true
GREENPT_API_KEY=sk--kufFCXhR9OHR-avU_TFF6mc9qDD8ktNjXhRbycSjJU  # Mag placeholder blijven
```

**Demo Features:**

- ✅ Volledig werkende UI/UX
- ✅ Knowledge base zoeken (189 documenten)
- ✅ Structured response templates
- ✅ Compliance en technical guidance demos
- ❌ Geen echte AI responses
- ❌ Geen context-aware antwoorden

## 🧪 Test de Setup

Na configuratie test je de setup:

```bash
# Test health endpoint
curl http://localhost:8000/api/health

# Test structured chat
curl -X POST http://localhost:8000/api/chat/structured \
  -H "Content-Type: application/json" \
  -d '{"message": "Test", "context": {"role": "other"}, "timestamp": "2025-06-11T15:00:00Z"}'
```

## 🔒 Security Best Practices

1. **Nooit API keys committen** naar git
2. **Gebruik environment variables** voor productie
3. **Deel je API key niet** met anderen

## 🆘 Troubleshooting

### "Invalid API key" Error

- Check of je key correct is gekopieerd
- Zorg dat er geen extra spaties zijn
- Vraag de hackathon organisatie om een nieuwe key

### "Model not found" Error

- Controleer of het model beschikbaar is via GreenPT
- Pas `GREENPT_MODEL` aan in je `.env` file

### Verbindingsproblemen

- Controleer je internetverbinding
- Vraag de hackathon organisatie of de GreenPT service actief is

---

**Ready to go!** 🚀 Je Gemeente AI Assistant is nu volledig operationeel met GreenPT.
