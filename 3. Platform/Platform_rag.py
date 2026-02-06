import os
import requests
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import openai
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# Retrieve GreenPT API key (OpenAI-compatible)
openai.api_key = os.getenv('GREENPT_API_KEY')
client = OpenAI(api_key=os.getenv('GREENPT_API_KEY'), base_url=os.getenv('GREENPT_API_BASE', 'https://api.greenpt.ai/v1'))

# Load the sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Read documents from files in the directory
def read_documents_from_directory(directory):
    documents = []
    for filename in os.listdir(directory):
        if filename.endswith(".md"):  # Check for Markdown files
            file_path = os.path.join(directory, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    documents.append(file.read())  # Append document content if reading is successful
            except Exception as e:
                print(f"Failed to read {file_path}: {e}")  # Log the error and skip to the next file
    return documents

# Read the system prompt from a file
def read_system_prompt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read().strip()  # Return the content of the file
    except Exception as e:
        print(f"Failed to read system prompt file: {e}")
        return ""  # Return an empty string if there was an error

# Specify the directory containing your documents
directory_path = '../1. Datasets/Scrapen/scraped_content/content'
documents = read_documents_from_directory(directory_path)

# Check and create embeddings for documents
if documents:  # Ensure there are documents to encode
    embeddings = model.encode(documents)
    # Create a FAISS index
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(np.array(embeddings).astype('float32'))
else:
    index = None  # No documents, so no index

def retrieve_documents(query, k=2):
    if index is None:
        return []  # No documents indexed, return empty list
    query_embedding = model.encode([query])
    D, I = index.search(np.array(query_embedding).astype('float32'), k)

    # Check if any valid indices were returned
    if I.size == 0 or I[0][0] == -1:  # No results found
        return []  # Return an empty list if no documents are found

    # Retrieve documents using valid indices
    return [documents[i] for i in I[0] if i < len(documents) and i >= 0]  # Ensure index is in range

def generate_response(context, user_query):
    system_prompt = read_system_prompt('system_prompt.txt')
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ]

    try:
        response = client.chat.completions.create(
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
        return full_reply

    except Exception as e:
        print(f"\nError generating response: {e}")
        return "Ik kan hier geen antwoord op formuleren."

def is_relevant_query(query):
    system_prompt = (
        "Je bent een slimme filter die bepaalt of een gebruikersvraag gaat over chatbots voor de overheid. "
        "Beantwoord alleen met 'ja' of 'nee'."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Is deze vraag gerelateerd aan chatbots voor de overheid?\n\nVraag: {query}"}
    ]

    try:
        response = client.chat.completions.create(
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

def chat(user_query):
    if is_relevant_query(user_query):
        print("RELEVANT QUERY")
        retrieved_docs = retrieve_documents(user_query)
        context = ' '.join(retrieved_docs)

        if context:  # Only generate response if context is not empty
            response = generate_response(context, user_query)
        else:
            response = "Geen relevante documenten gevonden."
    else:
        print("IRRELEVANT QUERY")
        response = generate_response('system_prompt.txt', user_query)

    return response

if __name__ == "__main__":
    print("Welkom bij de eerste demo. Typ 'exit' om te stoppen.")
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() == 'exit':
            break
        response = chat(user_input)
