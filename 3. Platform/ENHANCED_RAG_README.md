# Enhanced RAG System

A high-quality Retrieval-Augmented Generation (RAG) system using OpenAI's embeddings for government chatbot applications.

## Overview

This system replaces the previous sentence-transformers implementation with OpenAI's `text-embedding-3-small` model for superior semantic understanding and retrieval quality.

## Key Features

### 🎯 High-Quality Embeddings

- Uses OpenAI's `text-embedding-3-small` model (1536 dimensions)
- Superior semantic understanding compared to local models
- Normalized vectors for optimal cosine similarity

### 📚 Smart Document Processing

- Intelligent chunking with overlap for context preservation
- Automatic section title extraction from markdown headers
- Token-aware chunking (800 tokens per chunk, 100 token overlap)
- Metadata preservation for accurate source referencing

### 🔍 Advanced Retrieval

- FAISS-based vector search with cosine similarity
- Proper source attribution with file paths and sections
- Relevance scoring for result ranking

### ⚡ Performance Optimizations

- Intelligent caching system (documents hash-based)
- Batch processing for embedding creation
- Automatic cache invalidation when documents change

### 📝 Accurate Citations

- Automatic source citations in responses
- File path and section title preservation
- Multi-chunk document handling

## Usage

### Basic Usage

```python
from enhanced_rag import chat, initialize_rag_system

# Initialize the system (optional - happens automatically)
initialize_rag_system()

# Chat with the system
response = chat("Hoe kan ik een chatbot opzetten voor de overheid?")
print(response)
```

### Advanced Usage

```python
from enhanced_rag import EnhancedRAGSystem

# Create a custom RAG system
rag = EnhancedRAGSystem(documents_directory="path/to/docs")

# Retrieve relevant chunks
results = rag.retrieve_documents("your query", k=5)

# Get formatted context with sources
context, sources = rag.get_context_for_query("your query")
```

## Configuration

The system uses the following configuration (adjustable in `enhanced_rag.py`):

- **EMBEDDING_MODEL**: `text-embedding-3-small`
- **CHUNK_SIZE**: 800 tokens
- **CHUNK_OVERLAP**: 100 tokens
- **EMBEDDING_DIMENSIONS**: 1536

## System Architecture

### Document Processing Pipeline

1. **Document Loading**: Loads all `.md` files from the specified directory
2. **Chunking**: Intelligently splits documents into overlapping chunks
3. **Metadata Extraction**: Preserves file paths, section titles, and position information
4. **Embedding Creation**: Generates embeddings using OpenAI API
5. **Index Building**: Creates FAISS index for fast similarity search

### Retrieval Pipeline

1. **Query Embedding**: Converts user query to embedding vector
2. **Similarity Search**: Finds most relevant chunks using cosine similarity
3. **Context Assembly**: Combines retrieved chunks with source information
4. **Response Generation**: Uses GPT model with enhanced context and citations

## Data Structure

### DocumentChunk

```python
@dataclass
class DocumentChunk:
    content: str                    # Chunk text content
    file_path: str                 # Source file path
    chunk_index: int               # Position within document
    total_chunks: int              # Total chunks in document
    section_title: Optional[str]   # Extracted section title
    start_char: int                # Character position start
    end_char: int                  # Character position end
```

### RetrievalResult

```python
@dataclass
class RetrievalResult:
    chunk: DocumentChunk           # Retrieved chunk with metadata
    similarity_score: float        # Cosine similarity score
```

## Performance

- **Initial Processing**: ~2-3 minutes for 320 documents (2306 chunks)
- **Cache Loading**: ~1-2 seconds for subsequent runs
- **Query Response**: ~0.5-1 second per query
- **Storage**: ~50MB cache file for 320 documents

## Requirements

```
openai>=1.86.0
faiss-cpu>=1.11.0
numpy>=2.3.0
tiktoken>=0.9.0
python-dotenv>=1.1.0
```

## Environment Setup

Ensure your `.env` file contains:

```
GREENPT_API_KEY=sk--kufFCXhR9OHR-avU_TFF6mc9qDD8ktNjXhRbycSjJU
```

## Cache Management

The system automatically manages embeddings cache:

- **Location**: `./cache/embeddings_cache.pkl`
- **Validation**: Uses document hash for cache validation
- **Invalidation**: Automatic when documents change
- **Manual Clear**: Delete the cache directory to force re-processing

## Quality Improvements Over Previous System

1. **Better Embeddings**: OpenAI's models vs. local sentence-transformers
2. **Proper Chunking**: Token-aware with overlap vs. whole documents
3. **Source Attribution**: Detailed file and section references
4. **Caching**: Intelligent cache management for performance
5. **Error Handling**: Robust error handling and fallbacks
6. **Scalability**: Batch processing and optimized memory usage

## Testing

Run the test suite:

```bash
python test_enhanced_rag.py
```

## Migration from Previous System

The enhanced RAG system maintains the same API interface as the previous system while providing significant improvements in quality and performance. Simply replace imports from `Platform_rag` to `enhanced_rag`.

## Limitations

- Requires OpenAI API key and internet connection
- Processing time scales with document count
- Memory usage increases with corpus size
- API costs scale with document count and query frequency
