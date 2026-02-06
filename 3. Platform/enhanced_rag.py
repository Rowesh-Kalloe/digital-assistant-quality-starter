import os
import json
import pickle
import hashlib
import numpy as np
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI
import faiss
import tiktoken

# Load environment variables
load_dotenv('backend/.env')  # Load from backend directory
load_dotenv()  # Also try current directory

# Initialize OpenAI client lazily
client = None

def get_openai_client():
    """Get OpenAI client, initializing if necessary (using GreenPT)"""
    global client
    if client is None:
        api_key = os.getenv('GREENPT_API_KEY')
        if not api_key:
            raise ValueError("GREENPT_API_KEY environment variable not set")
        base_url = os.getenv('GREENPT_API_BASE', 'https://api.greenpt.ai/v1')
        client = OpenAI(api_key=api_key, base_url=base_url)
    return client

# Configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536  # Default for text-embedding-3-small
CHUNK_SIZE = 800  # Tokens per chunk
CHUNK_OVERLAP = 100  # Token overlap between chunks
MAX_TOKENS_PER_DOCUMENT = 8000  # Stay within model limits

@dataclass
class DocumentChunk:
    """Represents a chunk of a document with metadata"""
    content: str
    file_path: str
    chunk_index: int
    total_chunks: int
    section_title: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    original_url: Optional[str] = None
    document_title: Optional[str] = None

@dataclass
class RetrievalResult:
    """Represents a retrieval result with metadata"""
    chunk: DocumentChunk
    similarity_score: float
    
class EnhancedRAGSystem:
    def __init__(self, documents_directory: str, cache_dir: str = "./cache"):
        self.documents_directory = documents_directory
        self.cache_dir = cache_dir
        self.chunks: List[DocumentChunk] = []
        self.embeddings: Optional[np.ndarray] = None
        self.index: Optional[faiss.IndexFlatIP] = None  # Using Inner Product for cosine similarity
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        # Initialize the system
        self._initialize_system()
    
    def _extract_frontmatter_and_url(self, content: str) -> Tuple[Optional[str], Optional[str], str]:
        """Extract URL and title from frontmatter and clean content"""
        url = None
        title = None
        clean_content = content
        
        # Check for YAML frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                clean_content = parts[2].strip()
                
                # Extract URL from frontmatter
                url_match = re.search(r'^url:\s*(.+)$', frontmatter, re.MULTILINE)
                if url_match:
                    url = url_match.group(1).strip()
                
                # Extract title from frontmatter
                title_match = re.search(r'^title:\s*(.+)$', frontmatter, re.MULTILINE)
                if title_match:
                    title = title_match.group(1).strip()
        
        # Also look for Source: lines in content as backup
        if not url:
            source_match = re.search(r'^Source:\s*(https?://[^\s]+)', clean_content, re.MULTILINE)
            if source_match:
                url = source_match.group(1)
        
        return url, title, clean_content
    
    def _initialize_system(self):
        """Initialize the RAG system by loading or creating embeddings"""
        print("Initializing Enhanced RAG System...")
        
        # Check if we have cached embeddings
        cache_path = os.path.join(self.cache_dir, "embeddings_cache_v2.pkl")  # v2 to force regeneration with URLs
        documents_hash = self._get_documents_hash()
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    cache_data = pickle.load(f)
                
                if cache_data.get('documents_hash') == documents_hash:
                    print("Loading cached embeddings...")
                    self.chunks = cache_data['chunks']
                    self.embeddings = cache_data['embeddings']
                    self._build_index()
                    print(f"Loaded {len(self.chunks)} chunks from cache")
                    return
            except Exception as e:
                print(f"Error loading cache: {e}")
        
        # Process documents and create embeddings
        print("Processing documents and creating embeddings...")
        self._process_documents()
        self._create_embeddings()
        self._build_index()
        
        # Save to cache
        self._save_cache(documents_hash)
        print(f"Processed {len(self.chunks)} chunks and saved to cache")
    
    def _get_documents_hash(self) -> str:
        """Create a hash of all documents for cache validation"""
        file_hashes = []
        
        if not os.path.exists(self.documents_directory):
            return ""
        
        for filename in sorted(os.listdir(self.documents_directory)):
            if filename.endswith(".md"):
                file_path = os.path.join(self.documents_directory, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    file_hash = hashlib.md5(content.encode()).hexdigest()
                    file_hashes.append(f"{filename}:{file_hash}")
                except Exception as e:
                    print(f"Error hashing {filename}: {e}")
        
        return hashlib.md5("|".join(file_hashes).encode()).hexdigest()
    
    def _process_documents(self):
        """Process all documents and create chunks"""
        self.chunks = []
        
        if not os.path.exists(self.documents_directory):
            print(f"Documents directory not found: {self.documents_directory}")
            return
        
        for filename in os.listdir(self.documents_directory):
            if filename.endswith(".md"):
                file_path = os.path.join(self.documents_directory, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Extract URL and title from frontmatter
                    original_url, document_title, clean_content = self._extract_frontmatter_and_url(content)
                    
                    # Create chunks for this document
                    document_chunks = self._chunk_document(clean_content, file_path, original_url, document_title)
                    self.chunks.extend(document_chunks)
                    
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
    
    def _chunk_document(self, content: str, file_path: str, original_url: Optional[str] = None, document_title: Optional[str] = None) -> List[DocumentChunk]:
        """Split a document into chunks while preserving context"""
        chunks = []
        
        # Tokenize the content
        tokens = self.tokenizer.encode(content)
        
        # If document is small enough, treat as single chunk
        if len(tokens) <= CHUNK_SIZE:
            chunk = DocumentChunk(
                content=content,
                file_path=file_path,
                chunk_index=0,
                total_chunks=1,
                start_char=0,
                end_char=len(content),
                original_url=original_url,
                document_title=document_title
            )
            return [chunk]
        
        # Split into overlapping chunks
        chunk_index = 0
        start_token = 0
        
        while start_token < len(tokens):
            # Calculate chunk boundaries
            end_token = min(start_token + CHUNK_SIZE, len(tokens))
            
            # Convert tokens back to text
            chunk_tokens = tokens[start_token:end_token]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            # Find character positions (approximate)
            start_char = len(self.tokenizer.decode(tokens[:start_token]))
            end_char = len(self.tokenizer.decode(tokens[:end_token]))
            
            # Try to extract section title from the beginning of the chunk
            section_title = self._extract_section_title(chunk_text)
            
            chunk = DocumentChunk(
                content=chunk_text,
                file_path=file_path,
                chunk_index=chunk_index,
                total_chunks=0,  # Will be updated later
                section_title=section_title,
                start_char=start_char,
                end_char=end_char,
                original_url=original_url,
                document_title=document_title
            )
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start_token += CHUNK_SIZE - CHUNK_OVERLAP
            chunk_index += 1
        
        # Update total_chunks for all chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)
        
        return chunks
    
    def _extract_section_title(self, text: str) -> Optional[str]:
        """Extract section title from text (looks for markdown headers)"""
        lines = text.strip().split('\n')
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line.startswith('#'):
                # Remove markdown header symbols and return title
                return line.lstrip('#').strip()
        return None
    
    def _create_embeddings(self):
        """Create embeddings for all chunks using OpenAI API"""
        if not self.chunks:
            self.embeddings = np.array([])
            return
        
        print(f"Creating embeddings for {len(self.chunks)} chunks...")
        embeddings_list = []
        
        # Process chunks in batches to avoid rate limits
        batch_size = 100
        for i in range(0, len(self.chunks), batch_size):
            batch_chunks = self.chunks[i:i + batch_size]
            batch_texts = [chunk.content for chunk in batch_chunks]
            
            try:
                response = get_openai_client().embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=batch_texts,
                    encoding_format="float"
                )
                
                batch_embeddings = [data.embedding for data in response.data]
                embeddings_list.extend(batch_embeddings)
                
                print(f"Processed batch {i//batch_size + 1}/{(len(self.chunks) + batch_size - 1)//batch_size}")
                
            except Exception as e:
                print(f"Error creating embeddings for batch {i//batch_size + 1}: {e}")
                # Create zero embeddings as fallback
                batch_embeddings = [[0.0] * EMBEDDING_DIMENSIONS] * len(batch_chunks)
                embeddings_list.extend(batch_embeddings)
        
        self.embeddings = np.array(embeddings_list, dtype=np.float32)
    
    def _build_index(self):
        """Build FAISS index for similarity search"""
        if self.embeddings is None or len(self.embeddings) == 0:
            self.index = None
            return
        
        # Normalize embeddings for cosine similarity
        embeddings_normalized = self.embeddings / np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        
        # Create FAISS index (Inner Product for normalized vectors = cosine similarity)
        self.index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
        self.index.add(embeddings_normalized)
    
    def _save_cache(self, documents_hash: str):
        """Save embeddings and chunks to cache"""
        cache_data = {
            'documents_hash': documents_hash,
            'chunks': self.chunks,
            'embeddings': self.embeddings
        }
        
        cache_path = os.path.join(self.cache_dir, "embeddings_cache_v2.pkl")
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def retrieve_documents(self, query: str, k: int = 5) -> List[RetrievalResult]:
        """Retrieve the most relevant document chunks for a query"""
        if not self.index or not self.chunks:
            return []
        
        try:
            # Create query embedding
            response = get_openai_client().embeddings.create(
                model=EMBEDDING_MODEL,
                input=[query],
                encoding_format="float"
            )
            query_embedding = np.array([response.data[0].embedding], dtype=np.float32)
            
            # Normalize query embedding
            query_embedding = query_embedding / np.linalg.norm(query_embedding, axis=1, keepdims=True)
            
            # Search for similar chunks
            similarities, indices = self.index.search(query_embedding, k)
            
            results = []
            for i, (similarity, idx) in enumerate(zip(similarities[0], indices[0])):
                if idx < len(self.chunks) and similarity > 0:  # Valid index and positive similarity
                    result = RetrievalResult(
                        chunk=self.chunks[idx],
                        similarity_score=float(similarity)
                    )
                    results.append(result)
            
            return results
            
        except Exception as e:
            print(f"Error during retrieval: {e}")
            return []
    
    def get_context_for_query(self, query: str, max_chunks: int = 3) -> Tuple[str, List[str]]:
        """Get formatted context and sources for a query"""
        results = self.retrieve_documents(query, k=max_chunks)
        
        if not results:
            return "", []
        
        # Build context string
        context_parts = []
        sources = []
        
        for i, result in enumerate(results):
            chunk = result.chunk
            filename = os.path.basename(chunk.file_path)
            
            # Create a context entry with source information
            context_part = f"[Source {i+1}: {filename}"
            if chunk.section_title:
                context_part += f" - {chunk.section_title}"
            if chunk.total_chunks > 1:
                context_part += f" (Part {chunk.chunk_index + 1}/{chunk.total_chunks})"
            context_part += f"]\n{chunk.content}\n"
            
            context_parts.append(context_part)
            
            # Create source reference
            source_ref = f"{filename}"
            if chunk.section_title:
                source_ref += f" - {chunk.section_title}"
            sources.append(source_ref)
        
        context = "\n---\n".join(context_parts)
        return context, sources


# Initialize the global RAG system
rag_system = None

def initialize_rag_system(documents_directory: str = '../1. Datasets/Scrapen/scraped_content/content'):
    """Initialize the global RAG system"""
    global rag_system
    rag_system = EnhancedRAGSystem(documents_directory)

def read_system_prompt(file_path: str) -> str:
    """Read the system prompt from a file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except Exception as e:
        print(f"Failed to read system prompt file: {e}")
        return ""

def is_relevant_query(query: str) -> bool:
    """Check if a query is relevant to government chatbots"""
    system_prompt = (
        "Je bent een slimme filter die bepaalt of een gebruikersvraag gaat over chatbots voor de overheid. "
        "Beantwoord alleen met 'ja' of 'nee'."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Is deze vraag gerelateerd aan chatbots voor de overheid?\n\nVraag: {query}"}
    ]

    try:
        response = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=3,
            temperature=0
        )
        answer = response.choices[0].message.content.strip().lower()
        return "ja" in answer
    except Exception as e:
        print(f"Error checking query relevance: {e}")
        return False

def generate_response(context: str, user_query: str, sources: List[str]) -> str:
    """Generate a response using the enhanced context and sources"""
    system_prompt = read_system_prompt('system_prompt.txt')
    
    # Enhanced system prompt that includes source information
    enhanced_system_prompt = f"""{system_prompt}

Wanneer je antwoord op basis van de verstrekte context, vermeld dan altijd de relevante bronnen aan het einde van je antwoord.
Gebruik de volgende format voor bronvermelding:

**Bronnen:**
- [Bron naam]
- [Bron naam]

De context bevat informatie uit verschillende documenten met bronvermelding. Gebruik deze informatie om een accuraat en nuttig antwoord te geven."""

    messages = [
        {"role": "system", "content": enhanced_system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nVraag: {user_query}"}
    ]

    try:
        response = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            stream=True
        )

        full_reply = ""
        print("Model: ", end="", flush=True)

        for chunk in response:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                print(content, end="", flush=True)
                full_reply += content

        print()  # Newline after response
        
        # Add sources if not already included
        if sources and "**Bronnen:**" not in full_reply:
            full_reply += f"\n\n**Bronnen:**\n" + "\n".join(f"- {source}" for source in sources)
        
        return full_reply

    except Exception as e:
        print(f"\nError generating response: {e}")
        return "Ik kan hier geen antwoord op formuleren."

def chat(user_query: str) -> str:
    """Main chat function using the enhanced RAG system"""
    global rag_system
    
    if rag_system is None:
        initialize_rag_system()
    
    if is_relevant_query(user_query):
        print("RELEVANT QUERY")
        context, sources = rag_system.get_context_for_query(user_query)
        
        if context:
            response = generate_response(context, user_query, sources)
        else:
            response = "Geen relevante documenten gevonden."
    else:
        print("IRRELEVANT QUERY")
        response = generate_response('', user_query, [])

    return response

if __name__ == "__main__":
    print("Welkom bij de Enhanced RAG Demo. Typ 'exit' om te stoppen.")
    initialize_rag_system()
    
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() == 'exit':
            break
        response = chat(user_input)