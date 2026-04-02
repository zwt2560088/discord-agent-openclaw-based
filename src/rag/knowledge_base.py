"""
RAG Knowledge Base System — 混合检索（BM25 + 向量语义检索）+ 重排
"""
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

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
        # BM25 相关：预分词
        self.tokens = self._tokenize(content)
        self.title_tokens = self._tokenize(title)
        
    def _tokenize(self, text: str) -> List[str]:
        """简单分词：小写 + 去标点 + 按空格/特殊字符分割"""
        text = text.lower()
        # 保留数字、字母、中文
        tokens = re.findall(r'[\w\u4e00-\u9fff]+', text)
        # 过滤停用词
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                    'would', 'could', 'should', 'may', 'might', 'can', 'shall',
                    'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
                    'as', 'into', 'through', 'during', 'before', 'after', 'and',
                    'but', 'or', 'not', 'no', 'if', 'then', 'that', 'this',
                    'it', 'its', 'my', 'your', 'his', 'her', 'our', 'their',
                    'what', 'which', 'who', 'when', 'where', 'how', 'why'}
        return [t for t in tokens if t not in stopwords and len(t) > 1]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'path': self.path,
            'title': self.title,
            'content': self.content,
            'category': self.category
        }


class BM25:
    """
    BM25 检索算法实现
    无需外部依赖，纯 Python 实现
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1  # 词频饱和参数
        self.b = b    # 文档长度归一化参数
        self.documents: List[Document] = []
        self.doc_count = 0
        self.avg_doc_len = 0
        self.idf: Dict[str, float] = {}  # 逆文档频率
        self.doc_freq: Dict[str, int] = {}  # 文档频率

    def index(self, documents: List[Document]):
        """建立 BM25 索引"""
        self.documents = documents
        self.doc_count = len(documents)
        if self.doc_count == 0:
            return

        # 计算平均文档长度
        total_len = sum(len(doc.tokens) for doc in documents)
        self.avg_doc_len = total_len / self.doc_count

        # 计算文档频率和逆文档频率
        df = Counter()
        for doc in documents:
            unique_tokens = set(doc.tokens)
            for token in unique_tokens:
                df[token] += 1
        self.doc_freq = dict(df)

        # IDF = log((N - df + 0.5) / (df + 0.5) + 1)
        self.idf = {}
        for token, freq in self.doc_freq.items():
            self.idf[token] = math.log((self.doc_count - freq + 0.5) / (freq + 0.5) + 1)

        logger.info(f"📊 BM25 索引建立完成: {self.doc_count} 篇文档, 平均长度 {self.avg_doc_len:.0f} tokens")

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        BM25 搜索，返回 [(doc_index, score), ...]
        """
        query_tokens = Document.__new__(Document)
        Document.__init__(query_tokens, "", "", query, "")

        scores = []
        for i, doc in enumerate(self.documents):
            score = self._score(query_tokens.tokens, doc)
            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _score(self, query_tokens: List[str], doc: Document) -> float:
        """计算单篇文档的 BM25 分数"""
        score = 0.0
        doc_len = len(doc.tokens)

        # 文档词频
        tf = Counter(doc.tokens)

        for token in query_tokens:
            if token not in self.idf:
                continue
            idf = self.idf[token]
            freq = tf.get(token, 0)

            # BM25 评分公式
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_doc_len, 1))
            score += idf * (numerator / denominator)

        return score


class KnowledgeBase:
    """RAG Knowledge Base — 混合检索"""

    def __init__(self, knowledge_base_path: str):
        self.knowledge_base_path = Path(knowledge_base_path)
        self.documents: List[Document] = []
        self.embeddings = None
        self.model = None
        self.bm25 = BM25()
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
            logger.info("⚠️ Using BM25-only search fallback")
            self.model = None

    def load_documents(self):
        """Load knowledge base documents"""
        logger.info(f"Loading documents from {self.knowledge_base_path}")
        
        if not self.knowledge_base_path.exists():
            logger.warning(f"Knowledge base path does not exist: {self.knowledge_base_path}")
            return
        
        for md_file in self.knowledge_base_path.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                title = self._extract_title(content)
                category = self._get_category(md_file)
                
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
        
        # 建立 BM25 索引
        self.bm25.index(self.documents)

        # 生成向量嵌入
        if self.documents and self.model:
            self._generate_embeddings()
            logger.info(f"Loaded {len(self.documents)} documents (BM25 + Semantic)")
        else:
            logger.info(f"Loaded {len(self.documents)} documents (BM25 only)")
    
    def _extract_title(self, content: str) -> str:
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
        return "Untitled"
    
    # 类别关键词映射：用于根目录文件的智能分类
    _CATEGORY_KEYWORDS = {
        'pricing': ['price', 'pricing', 'cost', 'fee', 'standard', 'g2g'],
        'services': ['service', 'boost', 'overview', 'level-up', 'reputation'],
        'procedures': ['order', 'process', 'procedure', 'payment'],
        'faq': ['faq', 'question', 'answer', 'technical'],
        'mods': ['mod', 'pc-mod'],
    }

    def _get_category(self, file_path: Path) -> str:
        parts = file_path.parts
        # 优先根据子目录名判断（跳过 'en'）
        for part in parts:
            if part in ['services', 'mods', 'pricing', 'procedures', 'faq']:
                return part

        # 根目录文件：根据文件名和内容智能分类
        filename = file_path.stem.lower()
        for category, keywords in self._CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in filename:
                    return category

        # 回退：尝试读文件首行判断
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_lines = ''.join([next(f, '') for _ in range(10)])
            for category, keywords in self._CATEGORY_KEYWORDS.items():
                for kw in keywords:
                    if kw in first_lines.lower():
                        return category
        except Exception:
            pass

        return 'general'
    
    def _generate_embeddings(self):
        if not self.model:
            return
        logger.info("Generating document embeddings...")
        texts = []
        for doc in self.documents:
            text = f"{doc.title}\n{doc.content[:500]}"
            texts.append(text)
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            self.embeddings = self.model.encode(texts)
            for i, doc in enumerate(self.documents):
                doc.embedding = self.embeddings[i]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            self.embeddings = None
    
    def search(self, query: str, top_k: int = 3, min_score: float = 0.3,
               use_hybrid: bool = True) -> List[Dict[str, Any]]:
        """
        混合检索：BM25 + 向量语义检索 + 分数融合

        Args:
            query: 查询文本
            top_k: 返回结果数量
            min_score: 最低分数阈值
            use_hybrid: 是否使用混合检索（False 则仅 BM25）
        """
        if not self.documents:
            return []
        
        # ========== 第一阶段：BM25 召回 ==========
        bm25_results = self.bm25.search(query, top_k=top_k * 2)
        bm25_scores = {idx: score for idx, score in bm25_results}
        
        # ========== 第二阶段：向量语义召回 ==========
        semantic_scores = {}
        if use_hybrid and self.embeddings is not None and self.model is not None:
            try:
                from sklearn.metrics.pairwise import cosine_similarity
                query_embedding = self.model.encode([query])
                similarities = cosine_similarity(query_embedding, self.embeddings)[0]
                for i, sim in enumerate(similarities):
                    semantic_scores[i] = float(sim)
            except Exception as e:
                logger.error(f"Semantic search failed: {e}")
        
        # ========== 第三阶段：分数融合（Reciprocal Rank Fusion） ==========
        # RRF: score = Σ 1/(k + rank_i), k=60
        k = 60
        
        # BM25 排名
        bm25_ranked = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)
        # 语义排名
        semantic_ranked = sorted(semantic_scores.items(), key=lambda x: x[1], reverse=True)

        rrf_scores = Counter()
        for rank, (idx, _) in enumerate(bm25_ranked):
            rrf_scores[idx] += 1 / (k + rank + 1)
        for rank, (idx, _) in enumerate(semantic_ranked):
            rrf_scores[idx] += 1 / (k + rank + 1)

        # ========== 第四阶段：组装结果 ==========
        fused_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for idx, rrf_score in fused_results[:top_k]:
            doc = self.documents[idx]
            bm25_s = bm25_scores.get(idx, 0)
            semantic_s = semantic_scores.get(idx, 0)

            # 归一化分数用于展示
            display_score = rrf_score * 10  # 放大显示

            if display_score >= min_score:
                results.append({
                    'document': doc.to_dict(),
                    'similarity': display_score,
                    'bm25_score': bm25_s,
                    'semantic_score': semantic_s,
                    'relevant_content': self._extract_relevant_content(doc.content, query)
                })
        
        if not results:
            # 回退到纯 BM25
            logger.debug("Hybrid search returned no results, falling back to BM25")
            for idx, score in bm25_ranked[:top_k]:
                if score >= min_score:
                    doc = self.documents[idx]
                    results.append({
                        'document': doc.to_dict(),
                        'similarity': score,
                        'bm25_score': score,
                        'semantic_score': 0,
                        'relevant_content': self._extract_relevant_content(doc.content, query)
                    })
    
        return results

    # 同义词扩展映射，提升召回
    _SYNONYMS = {
        'refund': ['refund', 'money', 'back', 'return', 'satisfaction', 'guarantee'],
        'price': ['price', 'pricing', 'cost', 'fee', '$', 'dollar', 'usd'],
        'ban': ['ban', 'safe', 'risk', 'safety', 'banned', 'security'],
        'buy': ['buy', 'order', 'purchase', 'get', 'place'],
        'service': ['service', 'services', 'boost', 'boosting'],
        'delivery': ['delivery', 'deliver', 'time', ' ETA ', 'fast', 'slow', 'speed'],
        'mt': ['mt', 'coin', 'coins', 'currency'],
        'badge': ['badge', 'badges'],
        'level': ['level', 'leveling', 'lvl'],
    }

    def _expand_query_tokens(self, query_tokens: set) -> set:
        """基于同义词表扩展查询 token"""
        expanded = set(query_tokens)
        for token in query_tokens:
            for syn_group in self._SYNONYMS.values():
                if token in syn_group:
                    expanded.update(syn_group)
        return expanded

    def _extract_relevant_content(self, content: str, query: str) -> str:
        """Extract content fragments relevant to query"""
        # 复用 Document 的分词逻辑
        _dummy = Document("", "", query, "")
        query_tokens = set(_dummy.tokens)
        if not query_tokens:
            query_tokens = set(query.lower().split())
        
        # 同义词扩展
        expanded_tokens = self._expand_query_tokens(query_tokens)

        lines = content.split('\n')
        scored_lines = []
        for line in lines:
            line_lower = line.lower()
            # 原始 token 匹配权重高
            exact_hits = sum(1 for t in query_tokens if t in line_lower)
            # 扩展 token 匹配权重低
            expand_hits = sum(0.5 for t in expanded_tokens - query_tokens if t in line_lower)
            total_hits = exact_hits + expand_hits
            if total_hits > 0:
                scored_lines.append((total_hits, line.strip()))
        
        scored_lines.sort(key=lambda x: x[0], reverse=True)
        return '\n'.join(line for _, line in scored_lines[:8])
    
    def get_services(self) -> List[Dict[str, Any]]:
        services = []
        for doc in self.documents:
            if doc.category == 'services':
                services.append(doc.to_dict())
        return services
    
    def get_pricing(self) -> Dict[str, Any]:
        pricing_info = {}
        for doc in self.documents:
            if doc.category == 'pricing':
                pricing_info[doc.title] = self._parse_pricing(doc.content)
        return pricing_info
    
    def _parse_pricing(self, content: str) -> Dict[str, Any]:
        prices = {}
        lines = content.split('\n')
        for line in lines:
            if '$' in line:
                match = re.search(r'([^-$]+)\s*[-:]?\s*\$?(\d+)', line)
                if match:
                    item = match.group(1).strip()
                    price = f"${match.group(2)}"
                    prices[item] = price
            elif '¥' in line:
                match = re.search(r'([^¥]+)¥(\d+)', line)
                if match:
                    item = match.group(1).strip()
                    price = f"${match.group(2)}"
                    prices[item] = price
        return prices
    
    def get_faq(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        faqs = []
        for doc in self.documents:
            if doc.category == 'faq':
                if category is None or category in doc.path:
                    faqs.append(doc.to_dict())
        return faqs


class RAGEngine:
    """RAG Search Engine — 混合检索"""
    def __init__(self, knowledge_base_path: str):
        self.knowledge_base = KnowledgeBase(knowledge_base_path)
        
    def query(self, question: str) -> Dict[str, Any]:
        """Process user query"""
        results = self.knowledge_base.search(question)
        
        if not results:
            return {
                'answer': "Sorry, I couldn't find relevant information.",
                'sources': [],
                'confidence': 0.0
            }
        
        answer = self._generate_answer(question, results)
        return {
            'answer': answer,
            'sources': [r['document']['path'] for r in results],
            'confidence': max(r['similarity'] for r in results)
        }
    
    def _generate_answer(self, question: str, results: List[Dict[str, Any]]) -> str:
        best_result = results[0]
        content = best_result['relevant_content']
        return content[:1500] if len(content) > 1500 else content
        
        
# Global RAG engine instance
rag_engine = None


def get_rag_engine(knowledge_base_path: str = None) -> RAGEngine:
    global rag_engine
    if rag_engine is None:
        if knowledge_base_path is None:
            from src.config import config
            knowledge_base_path = config.KNOWLEDGE_BASE_PATH
        rag_engine = RAGEngine(knowledge_base_path)
    return rag_engine