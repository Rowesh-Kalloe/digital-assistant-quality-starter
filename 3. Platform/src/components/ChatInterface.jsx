import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Send, 
  Bot, 
  User, 
  RotateCcw, 
  HelpCircle, 
  Download,
  ExternalLink,
  AlertCircle,
  CheckCircle,
  Clock,
  ThumbsUp,
  ThumbsDown,
  Shield,
  Search,
  FileCheck
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { sendMessage } from '../services/api'

const QUICK_SUGGESTIONS = {
  'digital-guide': [
    'Welke stakeholders moet ik betrekken bij een AI implementatie?',
    'Hoe zorg ik voor draagvlak in de organisatie?',
    'Wat zijn de belangrijkste risico\'s die ik moet managen?'
  ],
  'civil-servant': [
    'Welke GDPR maatregelen zijn nodig voor een chatbot?',
    'Hoe ga ik om met de AI Act verplichtingen?',
    'Wat zijn best practices voor transparantie?'
  ],
  'it-manager': [
    'Welke architectuur principes moet ik volgen?',
    'Hoe voorkom ik vendor lock-in?',
    'Welke security maatregelen zijn essentieel?'
  ],
  'project-manager': [
    'Hoe plan ik een AI implementatie stap voor stap?',
    'Welke success metrics moet ik definiëren?',
    'Hoe manage ik risico\'s bij AI projecten?'
  ],
  'developer': [
    'Welke open standaarden moet ik gebruiken?',
    'Hoe implementeer ik Common Ground principes?',
    'Welke APIs zijn beschikbaar voor gemeentes?'
  ],
  'other': [
    'Waar moet ik beginnen met digitale transformatie?',
    'Welke regelgeving is relevant voor mijn project?',
    'Wie kan me verder helpen?'
  ]
}

const ChatInterface = ({ userContext, onRestart }) => {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [validationPhase, setValidationPhase] = useState(0)
  const [showSuggestions, setShowSuggestions] = useState(true)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const validationTimerRef = useRef(null)

  const VALIDATION_PHASES = [
    { icon: 'search', text: 'Bronnen doorzoeken...', color: 'text-blue-500' },
    { icon: 'bot', text: 'AI genereert antwoord...', color: 'text-gemeente-primary' },
    { icon: 'shield', text: 'Je antwoord wordt gevalideerd...', color: 'text-amber-500' },
    { icon: 'filecheck', text: 'Kwaliteitscontrole uitvoeren...', color: 'text-purple-500' },
    { icon: 'check', text: 'Bijna klaar...', color: 'text-green-500' },
  ]

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    // Welcome message based on user context
    const welcomeMessage = {
      id: Date.now(),
      type: 'ai',
      content: generateWelcomeMessage(userContext),
      timestamp: new Date(),
      suggestions: QUICK_SUGGESTIONS[userContext.role?.id] || QUICK_SUGGESTIONS.other
    }
    setMessages([welcomeMessage])
  }, [userContext])

  const generateWelcomeMessage = (context) => {
    const { role, projectPhase, focusAreas, customContext } = context
    
    let message = `Hoi! Ik ben je AI assistant en help je graag verder als **${role.name}**.`
    
    if (projectPhase) {
      message += ` Ik zie dat je je bevindt in de fase: **${projectPhase}**.`
    }
    
    if (focusAreas && focusAreas.length > 0) {
      message += ` Je focus ligt op: **${focusAreas.map(area => area.name).join(', ')}**.`
    }
    
    if (customContext) {
      message += `\n\nJe specifieke situatie: *${customContext}*`
    }
    
    message += `\n\n**Belangrijk:** Je praat met een AI systeem. Voor complexe juridische of technische zaken kan ik je doorverwijzen naar een menselijke expert.`
    
    message += `\n\nWaarmee kan ik je helpen? Hieronder zie je enkele suggesties, of stel gewoon je eigen vraag.`
    
    return message
  }

  const handleSendMessage = async (message = inputValue.trim()) => {
    if (!message || isLoading) return

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: message,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)
    setValidationPhase(0)
    setShowSuggestions(false)

    // Cycle through validation phases while waiting
    validationTimerRef.current = setInterval(() => {
      setValidationPhase(prev => {
        if (prev < 4) return prev + 1
        return prev
      })
    }, 3000)

    try {
      const response = await sendMessage(message, userContext)
      
      const aiMessage = {
        id: Date.now() + 1,
        type: 'ai',
        content: response.message,
        timestamp: new Date(),
        sources: response.sources,
        confidence: response.confidence,
        needsHumanHelp: response.needsHumanHelp
      }

      setMessages(prev => [...prev, aiMessage])
    } catch (error) {
      const errorMessage = {
        id: Date.now() + 1,
        type: 'ai',
        content: 'Sorry, er ging iets mis. Probeer het opnieuw of neem contact op met een expert.',
        timestamp: new Date(),
        isError: true,
        needsHumanHelp: true
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      if (validationTimerRef.current) {
        clearInterval(validationTimerRef.current)
        validationTimerRef.current = null
      }
      setIsLoading(false)
      setValidationPhase(0)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleSuggestionClick = (suggestion) => {
    handleSendMessage(suggestion)
  }

  const handleFeedback = (messageId, isPositive) => {
    // In a real app, send feedback to backend
    console.log(`Feedback for message ${messageId}: ${isPositive ? 'positive' : 'negative'}`)
  }

  return (
    <div className="h-screen flex flex-col bg-white">
      {/* Header */}
      <div className="border-b border-gemeente-neutral-200 p-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <Bot className="w-6 h-6 text-gemeente-primary" />
              <h1 className="text-xl font-semibold text-gemeente-neutral-800">
                Gemeente AI Assistant
              </h1>
            </div>
            <div className="hidden md:flex items-center space-x-2 text-sm text-gemeente-neutral-600">
              <span>•</span>
              <span>{userContext.role?.name}</span>
              {userContext.projectPhase && (
                <>
                  <span>•</span>
                  <span>{userContext.projectPhase}</span>
                </>
              )}
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <button className="btn-secondary text-sm px-4 py-2 flex items-center space-x-2">
              <HelpCircle className="w-4 h-4" />
              <span>Menselijke Hulp</span>
            </button>
            
            <button 
              onClick={onRestart}
              className="btn-secondary text-sm px-4 py-2 flex items-center space-x-2"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Opnieuw</span>
            </button>
          </div>
        </div>
      </div>

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-4 pb-20">
        <div className="max-w-4xl mx-auto space-y-6">
          <AnimatePresence>
            {messages.map((message) => (
              <motion.div
                key={message.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`max-w-3xl ${message.type === 'user' ? 'ml-12' : 'mr-12'}`}>
                  {/* Message Header */}
                  <div className={`flex items-center space-x-2 mb-2 ${
                    message.type === 'user' ? 'justify-end' : 'justify-start'
                  }`}>
                    {message.type === 'ai' && <Bot className="w-4 h-4 text-gemeente-primary" />}
                    <span className="text-xs text-gemeente-neutral-500">
                      {message.type === 'ai' ? 'AI Assistant' : 'Je'}
                    </span>
                    <span className="text-xs text-gemeente-neutral-400">
                      {message.timestamp.toLocaleTimeString('nl-NL', { 
                        hour: '2-digit', 
                        minute: '2-digit' 
                      })}
                    </span>
                    {message.type === 'user' && <User className="w-4 h-4 text-gemeente-neutral-600" />}
                  </div>

                  {/* Message Content */}
                  <div className={`${
                    message.type === 'user' 
                      ? 'chat-bubble-user' 
                      : `chat-bubble-ai ${message.isError ? 'border-gemeente-error bg-red-50' : ''}`
                  }`}>
                    {message.type === 'ai' ? (
                      <ReactMarkdown className="prose prose-sm max-w-none">
                        {message.content}
                      </ReactMarkdown>
                    ) : (
                      <p>{message.content}</p>
                    )}
                  </div>

                  {/* Message Metadata */}
                  {message.type === 'ai' && (
                    <div className="mt-3 space-y-2">
                      {/* Confidence Indicator */}
                      {message.confidence && (
                        <div className="flex items-center space-x-2 text-xs">
                          {message.confidence > 0.8 ? (
                            <CheckCircle className="w-3 h-3 text-green-600" />
                          ) : message.confidence > 0.6 ? (
                            <Clock className="w-3 h-3 text-yellow-600" />
                          ) : (
                            <AlertCircle className="w-3 h-3 text-red-600" />
                          )}
                          <span className="text-gemeente-neutral-500">
                            Betrouwbaarheid: {Math.round(message.confidence * 100)}%
                          </span>
                        </div>
                      )}

                      {/* Sources */}
                      {message.sources && message.sources.length > 0 && (
                        <div className="border-t border-gemeente-neutral-200 pt-2">
                          <p className="text-xs text-gemeente-neutral-500 mb-1">Bronnen:</p>
                          <div className="space-y-1">
                            {message.sources.map((source, index) => (
                              <a
                                key={index}
                                href={source.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center space-x-1 text-xs text-gemeente-primary hover:underline"
                              >
                                <ExternalLink className="w-3 h-3" />
                                <span>{source.title}</span>
                              </a>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Need Human Help */}
                      {message.needsHumanHelp && (
                        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                          <div className="flex items-start space-x-2">
                            <AlertCircle className="w-4 h-4 text-yellow-600 flex-shrink-0 mt-0.5" />
                            <div>
                              <p className="text-sm text-yellow-800 font-medium mb-1">
                                Complex onderwerp gedetecteerd
                              </p>
                              <p className="text-xs text-yellow-700 mb-2">
                                Voor dit onderwerp raad ik aan om contact op te nemen met een expert.
                              </p>
                              <button className="btn-primary text-xs px-3 py-1">
                                Contact Expert
                              </button>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Feedback */}
                      <div className="flex items-center space-x-2">
                        <span className="text-xs text-gemeente-neutral-500">Was dit helpvol?</span>
                        <button
                          onClick={() => handleFeedback(message.id, true)}
                          className="p-1 hover:bg-gemeente-neutral-100 rounded"
                        >
                          <ThumbsUp className="w-3 h-3 text-gemeente-neutral-400 hover:text-green-600" />
                        </button>
                        <button
                          onClick={() => handleFeedback(message.id, false)}
                          className="p-1 hover:bg-gemeente-neutral-100 rounded"
                        >
                          <ThumbsDown className="w-3 h-3 text-gemeente-neutral-400 hover:text-red-600" />
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Suggestions */}
                  {message.suggestions && showSuggestions && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="mt-4 space-y-2"
                    >
                      <p className="text-sm text-gemeente-neutral-600 font-medium">
                        Veelgestelde vragen:
                      </p>
                      {message.suggestions.map((suggestion, index) => (
                        <button
                          key={index}
                          onClick={() => handleSuggestionClick(suggestion)}
                          className="block w-full text-left text-sm bg-gemeente-neutral-50 hover:bg-gemeente-neutral-100 border border-gemeente-neutral-200 rounded-lg p-3 transition-colors duration-200"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Validation Loading Indicator */}
          {isLoading && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex justify-start"
            >
              <div className="chat-bubble-ai max-w-md">
                <div className="space-y-3">
                  {VALIDATION_PHASES.map((phase, index) => (
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ 
                        opacity: index <= validationPhase ? 1 : 0.3,
                        x: 0
                      }}
                      transition={{ duration: 0.3, delay: index * 0.1 }}
                      className={`flex items-center space-x-3 ${index <= validationPhase ? '' : 'opacity-30'}`}
                    >
                      <div className={`flex-shrink-0 ${phase.color}`}>
                        {index < validationPhase ? (
                          <CheckCircle className="w-4 h-4 text-green-500" />
                        ) : index === validationPhase ? (
                          <div className="w-4 h-4 relative">
                            {phase.icon === 'search' && <Search className={`w-4 h-4 ${phase.color} animate-pulse`} />}
                            {phase.icon === 'bot' && <Bot className={`w-4 h-4 ${phase.color} animate-pulse`} />}
                            {phase.icon === 'shield' && <Shield className={`w-4 h-4 ${phase.color} animate-pulse`} />}
                            {phase.icon === 'filecheck' && <FileCheck className={`w-4 h-4 ${phase.color} animate-pulse`} />}
                            {phase.icon === 'check' && <CheckCircle className={`w-4 h-4 ${phase.color} animate-pulse`} />}
                          </div>
                        ) : (
                          <div className="w-4 h-4 rounded-full border-2 border-gemeente-neutral-300" />
                        )}
                      </div>
                      <span className={`text-sm ${
                        index < validationPhase ? 'text-green-600 line-through' :
                        index === validationPhase ? 'text-gemeente-neutral-800 font-medium' :
                        'text-gemeente-neutral-400'
                      }`}>
                        {phase.text}
                      </span>
                    </motion.div>
                  ))}
                  <div className="flex items-center space-x-2 pt-2 border-t border-gemeente-neutral-100">
                    <div className="flex space-x-1">
                      <div className="w-1.5 h-1.5 bg-gemeente-primary rounded-full animate-bounce" />
                      <div className="w-1.5 h-1.5 bg-gemeente-primary rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                      <div className="w-1.5 h-1.5 bg-gemeente-primary rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                    </div>
                    <span className="text-xs text-gemeente-neutral-500">Even geduld alsjeblieft...</span>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="border-t border-gemeente-neutral-200 p-4 bg-white">
        <div className="max-w-4xl mx-auto">
          <div className="flex space-x-4">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type je vraag hier... (Enter om te verzenden, Shift+Enter voor nieuwe regel)"
                className="w-full p-4 pr-12 border border-gemeente-neutral-300 rounded-lg focus:border-gemeente-primary focus:ring-2 focus:ring-gemeente-primary focus:ring-opacity-20 resize-none"
                rows={1}
                style={{ minHeight: '52px', maxHeight: '120px' }}
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={!inputValue.trim() || isLoading}
                className="absolute right-3 bottom-3 p-2 text-gemeente-primary hover:bg-gemeente-primary hover:text-white rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </div>
          
          <div className="mt-2 flex justify-between items-center text-xs text-gemeente-neutral-500">
            <span>💡 Tip: Wees specifiek in je vraag voor het beste antwoord</span>
            <span>{inputValue.length}/500</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ChatInterface