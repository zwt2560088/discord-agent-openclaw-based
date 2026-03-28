import aiohttp
import glob
import hashlib
import os
import time
import warnings
from typing import List, Dict

# Configure HuggingFace to use cache and not download during init
os.environ["HF_HUB_OFFLINE"] = "0"  # Allow online mode but with proper caching
os.environ["HF_DATASETS_OFFLINE"] = "0"

# Suppress LangChain and Transformers warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Use new LangChain packages (0.2+)
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

try:
    from langchain_community.document_loaders import TextLoader, UnstructuredMarkdownLoader
except ImportError:
    from langchain.document_loaders import TextLoader, UnstructuredMarkdownLoader

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError:
        from langchain.embeddings import HuggingFaceEmbeddings

try:
    from langchain_chroma import Chroma
except ImportError:
    try:
        from langchain_community.vectorstores import Chroma
    except ImportError:
        from langchain.vectorstores import Chroma


class RAGAgent:
    def __init__(self, api_key: str, knowledge_dir: str = "knowledge_en"):
        self.api_key = api_key
        self.knowledge_dir = knowledge_dir
        self.embeddings = self._init_embeddings()
        self.vectorstore = None
        self.retriever = None
        self.query_cache = {}
        self.cache_ttl = 3600
        self._init_vectorstore()

    def _init_embeddings(self):
        """Initialize embeddings with retry logic and offline support"""
        print("⏳ Initializing embeddings...")
        try:
            embeddings = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True, "clean_up_tokenization_spaces": True}
            )
            print("✅ Embeddings initialized successfully")
            return embeddings
        except Exception as e:
            print(f"⚠️ Failed to initialize embeddings: {e}")
            print("🔄 Retrying with offline mode...")
            try:
                # Try with offline mode using cached model
                os.environ["HF_HUB_OFFLINE"] = "1"
                embeddings = HuggingFaceEmbeddings(
                    model_name="all-MiniLM-L6-v2",
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True, "clean_up_tokenization_spaces": True}
                )
                print("✅ Embeddings initialized in offline mode")
                return embeddings
            except Exception as e2:
                print(f"❌ Failed to initialize embeddings in offline mode: {e2}")
                raise RuntimeError(f"Could not initialize embeddings: {e2}")

    def _init_vectorstore(self):
        persist_dir = "./knowledge_db"
        if os.path.exists(persist_dir):
            print("📚 Loading existing vector store...")
            try:
                self.vectorstore = Chroma(persist_directory=persist_dir, embedding_function=self.embeddings)
                # 测试检索以验证有效性
                _ = self.vectorstore.similarity_search("test")
                print("✅ Vector store loaded successfully")
            except Exception as e:
                print(f"⚠️ Failed to load vector store: {e}")
                print("🔄 Rebuilding vector store...")
                self._build_vectorstore(persist_dir)
        else:
            print(f"🔨 Building vector store from {self.knowledge_dir}...")
            self._build_vectorstore(persist_dir)

        if self.vectorstore:
            self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})
        else:
            raise RuntimeError("Failed to initialize vector store")
    def _build_vectorstore(self, persist_dir):
        # Try primary knowledge directory
        if not os.path.exists(self.knowledge_dir):
            print(f"⚠️  {self.knowledge_dir} not found, trying fallback directories...")
            # Try fallback directories
            fallback_dirs = ["knowledge", "knowledge/en", "knowledge_en"]
            for fallback in fallback_dirs:
                if os.path.exists(fallback):
                    print(f"   Using {fallback} instead")
                    self.knowledge_dir = fallback
                    break

        # Recursive search for knowledge files
        file_paths = glob.glob(os.path.join(self.knowledge_dir, "*.md")) + \
                     glob.glob(os.path.join(self.knowledge_dir, "**/*.md"), recursive=True) + \
                     glob.glob(os.path.join(self.knowledge_dir, "*.txt")) + \
                     glob.glob(os.path.join(self.knowledge_dir, "**/*.txt"), recursive=True)

        # Deduplicate
        file_paths = list(set(file_paths))

        if not file_paths:
            raise FileNotFoundError(f"No knowledge files found in {self.knowledge_dir}")

        docs = []
        for fp in file_paths:
            try:
                if fp.endswith(".md"):
                    try:
                        loader = UnstructuredMarkdownLoader(fp)
                    except:
                        loader = TextLoader(fp, encoding="utf-8")
                else:
                    loader = TextLoader(fp, encoding="utf-8")
                docs.extend(loader.load())
                print(f"  ✅ Loaded: {os.path.basename(fp)}")
            except Exception as e:
                print(f"  ⚠️ Failed to load {fp}: {e}")

        if not docs:
            raise ValueError("No documents loaded from knowledge files")

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200,
                                                  separators=["\n## ", "\n### ", "\n\n", "\n", " "])
        chunks = splitter.split_documents(docs)
        print(f"✅ Created {len(chunks)} chunks from {len(file_paths)} files")

        self.vectorstore = Chroma.from_documents(chunks, self.embeddings, persist_directory=persist_dir)
        # Note: Chroma 0.4+ automatically persists documents, explicit persist() is no longer needed
        print(f"✅ Vector store persisted to {persist_dir}")

    async def rebuild_knowledge_base(self):
        """热更新知识库"""
        print("🔄 Rebuilding knowledge base...")
        import shutil
        if os.path.exists("./knowledge_db"):
            shutil.rmtree("./knowledge_db")
        self._build_vectorstore("./knowledge_db")
        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})
        self.query_cache.clear()
        print("✅ Knowledge base rebuilt.")

    async def call_deepseek(self, messages: List[Dict[str, str]]) -> str:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": messages, "temperature": 0.3, "max_tokens": 1000}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"DeepSeek API error: {resp.status} - {text}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def think_and_act(self, query: str, customer_id: str = None) -> str:
        # 缓存检查
        cache_key = hashlib.md5(query.encode()).hexdigest()
        if cache_key in self.query_cache:
            cached = self.query_cache[cache_key]
            if time.time() - cached["timestamp"] < self.cache_ttl:
                return cached["result"]

        # 检索
        docs = self.retriever.invoke(query)
        context = "\n\n".join([doc.page_content for doc in docs[:3]])

        system = f"""You are a professional NBA2k26 game service assistant. Your knowledge base:

{context}

User: {query}

**Strict Rules:**
1. **Only call `create_order` tool if the user explicitly says they want to place an order** (e.g., "I want to order", "Please create order", "I'll take it").
2. **For price inquiries**, answer directly with the price from the knowledge base.
3. **Do NOT create orders automatically** just because the user mentions a service.
4. **Answer concisely in English** without unnecessary greetings.

Now respond to the user:
"""
        try:
            response = await self.call_deepseek([{"role": "system", "content": system}, {"role": "user", "content": query}])
        except Exception as e:
            response = f"❌ Error: {e}"

        # 缓存
        self.query_cache[cache_key] = {"result": response, "timestamp": time.time()}
        return response