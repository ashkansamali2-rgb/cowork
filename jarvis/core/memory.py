import sys, os
sys.path.insert(0, os.path.expanduser("~/jarvis"))
import chromadb
from chromadb.utils import embedding_functions

MEMORY_DIR = os.path.expanduser("~/jarvis/memory")
os.makedirs(MEMORY_DIR, exist_ok=True)

# use local sentence transformers for embeddings — no API key needed
ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

client = chromadb.PersistentClient(path=MEMORY_DIR)

def get_collection(name: str):
    return client.get_or_create_collection(name=name, embedding_function=ef)

def remember(text: str, metadata: dict = {}, collection: str = "coding") -> str:
    """Store a memory."""
    col = get_collection(collection)
    import hashlib, time
    doc_id = hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()
    col.add(documents=[text], metadatas=[metadata], ids=[doc_id])
    return doc_id

def recall(query: str, collection: str = "coding", n: int = 5) -> str:
    """Retrieve relevant memories for a query."""
    try:
        col = get_collection(collection)
        count = col.count()
        if count == 0:
            return ""
        results = col.query(query_texts=[query], n_results=min(n, count))
        docs = results["documents"][0]
        if docs:
            return "\n---\n".join(docs)
        return ""
    except Exception as e:
        return f"Memory recall error: {e}"

def remember_project(project_name: str, content: str, kind: str = "code"):
    """Store project-specific memory."""
    remember(
        content,
        metadata={"project": project_name, "kind": kind},
        collection=f"project_{project_name}"
    )

def recall_project(project_name: str, query: str, n: int = 5) -> str:
    """Recall memories for a specific project."""
    return recall(query, collection=f"project_{project_name}", n=n)

if __name__ == "__main__":
    remember("The vision project uses FastAPI and React", {"project": "vision"})
    remember("Vision project database is PostgreSQL", {"project": "vision"})
    result = recall("what database does vision use")
    print("Recalled:", result)
