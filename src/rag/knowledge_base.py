"""
RAG Knowledge Base System
"""
import logging
import numpy as np
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Document:
    """Document class"""
    def __init__(self, path: str, title: str, content: str, category: str):
        self.path = path
        self.title = title
        self.content = content
        self.category = category
        self.embedding = None
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'path': self.path,
            'title': self.title,
            'content': self.content,
            'category': self.category
        }


class KnowledgeBase:
    """RAG Knowledge Base"""
    def __init__(self, knowledge_base_path: str):
        self.knowledge_base_path = Path(knowledge_base_path)
        self.documents: List[Document] = []
        self.embeddings = None
        self.model = None
        self._init_model()
        self.load_documents()
        
    def _init_model(self):
        """Initialize embedding model"""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("✅ SentenceTransformer model loaded")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load SentenceTransformer: {e}")
            logger.info("⚠️ Using keyword-based search fallback")
            self.model = None

    def load_documents(self):
        """Load knowledge base documents"""
        logger.info(f"Loading documents from {self.knowledge_base_path}")
        
        if not self.knowledge_base_path.exists():
            logger.warning(f"Knowledge base path does not exist: {self.knowledge_base_path}")
            return
        
        # Traverse knowledge base directory
        for md_file in self.knowledge_base_path.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract title
                title = self._extract_title(content)
                
                # Determine category
                category = self._get_category(md_file)
                
                # Create document object
                doc = Document(
                    path=str(md_file),
                    title=title,
                    content=content,
                    category=category
                )
                
                self.documents.append(doc)
                logger.info(f"Loaded document: {title}")
                
            except Exception as e:
                logger.error(f"Error loading document {md_file}: {e}")
        
        # Generate embeddings
        if self.documents and self.model:
            self._generate_embeddings()
            logger.info(f"Loaded {len(self.documents)} documents with embeddings")
        else:
            logger.info(f"Loaded {len(self.documents)} documents (keyword search mode)")
    
    def _extract_title(self, content: str) -> str:
        """Extract title from content"""
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
        
        return "Untitled"
    
    def _get_category(self, file_path: Path) -> str:
        """Determine category from file path"""
        parts = file_path.parts
        
        for part in parts:
            if part in ['services', 'mods', 'pricing', 'procedures', 'faq']:
                return part
        
        return 'general'
    
    def _generate_embeddings(self):
        """Generate document embeddings"""
        if not self.model:
            return

        logger.info("Generating document embeddings...")
        
        # Prepare texts
        texts = []
        for doc in self.documents:
            text = f"{doc.title}\n{doc.content[:500]}"
            texts.append(text)
        
        # Generate embeddings
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            self.embeddings = self.model.encode(texts)
        
            for i, doc in enumerate(self.documents):
                doc.embedding = self.embeddings[i]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            self.embeddings = None
    
    def search(self, query: str, top_k: int = 3, min_score: float = 0.4) -> List[Dict[str, Any]]:
        """Search relevant documents - returns top_k results (default 3)"""
        if not self.documents:
            return []
        
        # Use embedding search if available
        if self.embeddings is not None and self.model is not None:
            return self._semantic_search(query, top_k, min_score)
        else:
            return self._keyword_search(query, top_k, min_score)
        
    def _semantic_search(self, query: str, top_k: int, min_score: float) -> List[Dict[str, Any]]:
        """Semantic search using embeddings"""
        try:
            from sklearn.metrics.pairwise import cosine_similarity
        
            # Generate query embedding
            query_embedding = self.model.encode([query])
        
            # Calculate similarity
            similarities = cosine_similarity(query_embedding, self.embeddings)[0]

            # Get top_k results
            top_indices = np.argsort(similarities)[-top_k:][::-1]

            results = []
            for idx in top_indices:
                score = similarities[idx]
                if score >= min_score:
                    doc = self.documents[idx]
                    results.append({
                        'document': doc.to_dict(),
                        'similarity': float(score),
                        'relevant_content': self._extract_relevant_content(doc.content, query)
                    })

            return results
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return self._keyword_search(query, top_k, min_score)

    def _keyword_search(self, query: str, top_k: int, min_score: float) -> List[Dict[str, Any]]:
        """Keyword-based search fallback"""
        query_words = set(query.lower().split())

        results = []
        for doc in self.documents:
            content_lower = doc.content.lower()
            title_lower = doc.title.lower()

            # Calculate keyword match score
            matches = sum(1 for word in query_words if word in content_lower or word in title_lower)
            score = matches / len(query_words) if query_words else 0

            if score >= min_score:
                results.append({
                    'document': doc.to_dict(),
                    'similarity': score,
                    'relevant_content': self._extract_relevant_content(doc.content, query)
                })
        
        # Sort by score and return top_k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def _extract_relevant_content(self, content: str, query: str) -> str:
        """Extract content fragments relevant to query"""
        query_words = query.lower().split()
        lines = content.split('\n')
        
        relevant_lines = []
        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in query_words):
                relevant_lines.append(line.strip())
        
        return '\n'.join(relevant_lines[:5])
    
    def get_services(self) -> List[Dict[str, Any]]:
        """Get all services info"""
        services = []
        
        for doc in self.documents:
            if doc.category == 'services':
                services.append(doc.to_dict())
        
        return services
    
    def get_pricing(self) -> Dict[str, Any]:
        """Get pricing info"""
        pricing_info = {}
        
        for doc in self.documents:
            if doc.category == 'pricing':
                pricing_info[doc.title] = self._parse_pricing(doc.content)
        
        return pricing_info
    
    def _parse_pricing(self, content: str) -> Dict[str, Any]:
        """Parse pricing info"""
        prices = {}
        
        lines = content.split('\n')
        for line in lines:
            # Match $ pricing
            if '$' in line:
                match = re.search(r'([^-$]+)\s*[-:]?\s*\$?(\d+)', line)
                if match:
                    item = match.group(1).strip()
                    price = f"${match.group(2)}"
                    prices[item] = price
            # Match ¥ pricing
            elif '¥' in line:
                match = re.search(r'([^¥]+)¥(\d+)', line)
                if match:
                    item = match.group(1).strip()
                    price = f"${match.group(2)}"  # Convert to USD
                    prices[item] = price
        
        return prices
    
    def get_faq(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get FAQ info"""
        faqs = []
        
        for doc in self.documents:
            if doc.category == 'faq':
                if category is None or category in doc.path:
                    faqs.append(doc.to_dict())
        
        return faqs


class RAGEngine:
    """RAG Search Engine"""
    def __init__(self, knowledge_base_path: str):
        self.knowledge_base = KnowledgeBase(knowledge_base_path)
        
    def query(self, question: str) -> Dict[str, Any]:
        """Process user query"""
        # Search relevant documents
        results = self.knowledge_base.search(question)
        
        if not results:
            return {
                'answer': 'Sorry, I couldn\'t find relevant information. Please try a different question or contact support.',
                'sources': [],
                'confidence': 0.0
            }
        
        # Generate answer
        answer = self._generate_answer(question, results)
        
        return {
            'answer': answer,
            'sources': [r['document']['path'] for r in results],
            'confidence': max(r['similarity'] for r in results)
        }
    
    def _generate_answer(self, question: str, results: List[Dict[str, Any]]) -> str:
        """Generate answer based on search results - returns single best answer"""
        # Only use the best (first) result to avoid duplicate content
        best_result = results[0]
        content = best_result['relevant_content']
        
        # Return the most relevant content directly
        return content[:1500] if len(content) > 1500 else content
        
    def _generate_pricing_answer(self, question: str, results: List[Dict[str, Any]]) -> str:
        """Generate pricing-related answer from knowledge base"""
        best_result = results[0]
        return best_result['relevant_content'][:1500]
        
    def _generate_service_answer(self, question: str, results: List[Dict[str, Any]]) -> str:
        """Generate service-related answer from knowledge base"""
        best_result = results[0]
        return best_result['relevant_content'][:1500]
        
    def _generate_mod_answer(self, question: str, results: List[Dict[str, Any]]) -> str:
        """Generate mod-related answer from knowledge base"""
        best_result = results[0]
        return best_result['relevant_content'][:1500]
        
    def _generate_safety_answer(self, question: str, results: List[Dict[str, Any]]) -> str:
        """Generate safety-related answer from knowledge base"""
        best_result = results[0]
        return best_result['relevant_content'][:1500]
        

# Global RAG engine instance
rag_engine = None


def get_rag_engine(knowledge_base_path: str = None) -> RAGEngine:
    """Get RAG engine instance"""
    global rag_engine
    
    if rag_engine is None:
        if knowledge_base_path is None:
            from src.config import config
            knowledge_base_path = config.KNOWLEDGE_BASE_PATH
        
        rag_engine = RAGEngine(knowledge_base_path)
    
    return rag_engine