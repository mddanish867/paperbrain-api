RAG Chatbot Backend

🚀 A Retrieval-Augmented Generation (RAG) powered chatbot backend built with FastAPI, LangChain, OpenAI, Pinecone, and Upstash Redis.

It allows users to upload documents (PDFs, text, etc.), indexes them into a vector database, and provides conversational Q&A powered by LLMs with memory.

📌 Features

✅ User authentication & protected routes

✅ PDF ingestion & text chunking

✅ Embedding generation (OpenAI)

✅ Vector database (Pinecone + FAISS fallback)

✅ Conversation memory (Upstash Redis)

✅ RAG pipeline using LangChain

✅ REST API with FastAPI

✅ Ready for deployment on Render

⚙️ Tech Stack

Backend: FastAPI

AI / RAG: LangChain
, OpenAI

Vector Store: Pinecone
 / FAISS

Cache / Memory: Upstash Redis

File Parsing: PyPDF2

Infra: Render (backend), Upstash (Redis), Pinecone (vectors)

🏗️ Architecture
flowchart TD
    A[User] -->|Ask Question / Upload PDF| B[FastAPI Backend]
    B -->|Chunk & Embed| C[LangChain + OpenAI Embeddings]
    C --> D[Pinecone Vector DB]
    B --> E[Redis Memory (Upstash)]
    D --> F[LLM Response Generator]
    E --> F
    F --> A[Answer to User]

🚀 Setup & Installation
1️⃣ Clone the repo
git clone https://github.com/<your-username>/rag-chatbot-backend.git
cd rag-chatbot-backend

2️⃣ Create and activate a virtual environment
python -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows

3️⃣ Install dependencies
pip install -r requirements.txt

4️⃣ Create a .env file

⚠️ Never commit this file. Add to .gitignore.

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Pinecone
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=us-east1-gcp

# Redis (Upstash)
UPSTASH_REDIS_URL=your_upstash_redis_url

# AWS (for S3 / storage)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1

5️⃣ Run the app locally
uvicorn app.main:app --reload


API will be available at: http://localhost:8000

☁️ Deployment
🔹 Render

Push repo to GitHub (make sure .env is excluded).

Create a Render Web Service linked to your repo.

Add all .env values under Render → Environment → Environment Variables.

🔹 Upstash Redis

Free tier available

Copy UPSTASH_REDIS_URL from dashboard and add to .env

🔹 Pinecone

Create a project + index

Add PINECONE_API_KEY and PINECONE_ENVIRONMENT

📂 Project Structure
rag-chatbot-backend/
│── app/
│   ├── main.py             # FastAPI entrypoint
│   ├── routes/             # API routes
│   ├── services/           # RAG, Pinecone, Redis, etc.
│   ├── auth/               # Auth & protected routes
│   └── utils/              # Helpers
│── data/                   # Uploaded PDFs
│── .env                    # Environment variables (ignored in git)
│── .gitignore
│── requirements.txt
│── README.md

🔐 Security Notes

Never commit .env → add it to .gitignore.

If a secret gets leaked, rotate it immediately.

GitHub push protection will block API keys from being pushed.

🧪 Example API Endpoints

POST /upload → Upload a PDF

POST /chat → Ask a question

GET /health → Health check