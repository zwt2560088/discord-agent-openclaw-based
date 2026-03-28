"""
响应缓存系统
用于缓存热门问题和答案，优化响应速度
"""
import json
import time
import hashlib
from typing import Dict, Any, Optional, List
import pickle
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResponseCache:
    """响应缓存类"""
    
    def __init__(self, cache_dir: str = "cache", max_size: int = 1000, ttl: int = 3600):
        """
        初始化缓存系统
        
        Args:
            cache_dir: 缓存目录
            max_size: 最大缓存条目数
            ttl: 缓存生存时间（秒）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.max_size = max_size
        self.ttl = ttl
        
        # 内存缓存（快速访问）
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # 磁盘缓存文件
        self.cache_file = self.cache_dir / "response_cache.pkl"
        
        # 热门问题统计
        self.popular_questions: Dict[str, int] = {}
        
        # 加载现有缓存
        self._load_cache()
        
    def _load_cache(self):
        """从磁盘加载缓存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'rb') as f:
                    data = pickle.load(f)
                    self.memory_cache = data.get('cache', {})
                    self.popular_questions = data.get('popular', {})
                logger.info(f"Loaded cache with {len(self.memory_cache)} entries")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self.memory_cache = {}
            self.popular_questions = {}
    
    def _save_cache(self):
        """保存缓存到磁盘"""
        try:
            data = {
                'cache': self.memory_cache,
                'popular': self.popular_questions
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _generate_key(self, question: str, context: Optional[str] = None) -> str:
        """生成缓存键"""
        text = question.lower().strip()
        if context:
            text += f"|{context.lower().strip()}"
        
        # 使用MD5生成短键
        return hashlib.md5(text.encode()).hexdigest()[:16]
    
    def get(self, question: str, context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        从缓存获取响应
        
        Args:
            question: 问题文本
            context: 上下文信息
            
        Returns:
            缓存响应或None
        """
        key = self._generate_key(question, context)
        
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            
            # 检查是否过期
            if time.time() - entry['timestamp'] < self.ttl:
                # 更新访问计数
                self.popular_questions[key] = self.popular_questions.get(key, 0) + 1
                entry['access_count'] = entry.get('access_count', 0) + 1
                entry['last_access'] = time.time()
                
                logger.debug(f"Cache hit for key: {key}")
                return entry['response']
            else:
                # 删除过期条目
                del self.memory_cache[key]
                logger.debug(f"Cache expired for key: {key}")
        
        return None
    
    def set(self, question: str, response: Dict[str, Any], 
            context: Optional[str] = None, category: str = "general"):
        """
        设置缓存响应
        
        Args:
            question: 问题文本
            response: 响应数据
            context: 上下文信息
            category: 问题类别
        """
        key = self._generate_key(question, context)
        
        # 如果缓存已满，删除最不常用的条目
        if len(self.memory_cache) >= self.max_size:
            self._evict_oldest()
        
        # 创建缓存条目
        entry = {
            'question': question,
            'response': response,
            'context': context,
            'category': category,
            'timestamp': time.time(),
            'access_count': 1,
            'last_access': time.time()
        }
        
        self.memory_cache[key] = entry
        
        # 更新热门问题统计
        self.popular_questions[key] = self.popular_questions.get(key, 0) + 1
        
        logger.debug(f"Cached response for key: {key}")
        
        # 定期保存到磁盘
        if len(self.memory_cache) % 10 == 0:
            self._save_cache()
    
    def _evict_oldest(self):
        """删除最旧的缓存条目"""
        if not self.memory_cache:
            return
        
        # 找到访问次数最少且最久未访问的条目
        oldest_key = None
        oldest_score = float('inf')
        
        for key, entry in self.memory_cache.items():
            # 计算分数：访问次数越少、越久未访问，分数越高
            access_count = entry.get('access_count', 1)
            last_access = entry.get('last_access', entry['timestamp'])
            time_since_access = time.time() - last_access
            
            # 分数公式：时间权重 * (1/访问次数)
            score = time_since_access * (1.0 / max(access_count, 1))
            
            if score > oldest_score:
                oldest_score = score
                oldest_key = key
        
        if oldest_key:
            del self.memory_cache[oldest_key]
            logger.debug(f"Evicted cache entry: {oldest_key}")
    
    def get_popular_questions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取热门问题列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            热门问题列表
        """
        # 按访问次数排序
        sorted_items = sorted(
            self.popular_questions.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        result = []
        for key, count in sorted_items:
            if key in self.memory_cache:
                entry = self.memory_cache[key]
                result.append({
                    'question': entry['question'],
                    'category': entry['category'],
                    'access_count': count,
                    'last_access': entry.get('last_access', entry['timestamp'])
                })
        
        return result
    
    def clear_expired(self):
        """清理过期缓存"""
        expired_keys = []
        current_time = time.time()
        
        for key, entry in self.memory_cache.items():
            if current_time - entry['timestamp'] >= self.ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.memory_cache[key]
        
        if expired_keys:
            logger.info(f"Cleared {len(expired_keys)} expired cache entries")
            self._save_cache()
    
    def clear_all(self):
        """清除所有缓存"""
        self.memory_cache.clear()
        self.popular_questions.clear()
        self._save_cache()
        logger.info("Cleared all cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_entries = len(self.memory_cache)
        
        # 按类别统计
        categories = {}
        for entry in self.memory_cache.values():
            cat = entry['category']
            categories[cat] = categories.get(cat, 0) + 1
        
        # 计算命中率（需要在实际使用中跟踪）
        hit_rate = 0
        if hasattr(self, 'total_requests') and self.total_requests > 0:
            hit_rate = self.hit_count / self.total_requests
        
        return {
            'total_entries': total_entries,
            'max_size': self.max_size,
            'ttl': self.ttl,
            'categories': categories,
            'popular_count': len(self.popular_questions),
            'cache_dir': str(self.cache_dir)
        }


# 全局缓存实例
_cache_instance: Optional[ResponseCache] = None

def get_cache() -> ResponseCache:
    """获取全局缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ResponseCache()
    return _cache_instance


# 预加载的热门问题和答案
PRELOADED_CACHE = {
    # 价格相关
    "价格": {
        "response": {
            "answer": "我们的价格根据服务类型和难度而定：\n\n🏀 代练服务：\n• 球员升级：¥80-350\n• 徽章获取：¥20-400\n• VC农场：¥50-1500\n• MyTeam服务：¥30起\n\n🔧 修改器产品：\n• PC版：¥99-399\n• 主机版：¥299-699\n\n使用 `!pricing` 查看详细价格表。",
            "sources": ["pricing/g2g-pricing.md"],
            "confidence": 0.95
        },
        "category": "pricing"
    },
    
    # 服务相关
    "服务": {
        "response": {
            "answer": "我们提供以下NBA2k26服务：\n\n1. 🏀 代练服务\n   • 球员升级和属性提升\n   • 徽章获取和升级\n   • VC货币农场\n   • MyTeam阵容优化\n\n2. 🔧 修改器产品\n   • PC版多功能修改器\n   • 主机版硬件修改器\n   • 属性修改和无限VC\n\n3. 📊 专业服务\n   • 账号托管和优化\n   • 比赛代打和排名提升\n   • 定制化解决方案\n\n使用 `!services` 查看所有服务详情。",
            "sources": ["services/overview.md"],
            "confidence": 0.95
        },
        "category": "services"
    },
    
    # 订单相关
    "订单": {
        "response": {
            "answer": "创建订单流程：\n\n1. 使用 `!order` 命令开始创建\n2. 选择服务类型和具体项目\n3. 填写账户信息和具体要求\n4. 确认价格和支付方式\n5. 等待代练员接单开始服务\n\n订单状态查询：\n• 使用 `!status <订单号>` 查询进度\n• 系统每小时自动更新进度\n• 完成后会收到通知\n\n有问题随时联系客服 `!support`。",
            "sources": ["procedures/order-process.md"],
            "confidence": 0.90
        },
        "category": "orders"
    },
    
    # 帮助相关
    "帮助": {
        "response": {
            "answer": "可用命令列表：\n\n📋 **订单命令**\n• `!order` - 创建新订单\n• `!status [订单号]` - 查询订单状态\n• `!pay <订单号>` - 确认支付\n\n💰 **价格和服务**\n• `!services` - 查看所有服务\n• `!pricing` - 查看价格表\n• `!mods` - 修改器信息\n\n❓ **帮助和支持**\n• `!helpme` - 查看帮助（当前命令）\n• `!faq` - 常见问题\n• `!support` - 联系客服\n\n💬 **智能客服**\n• 直接提问任何问题\n• 系统会自动从知识库寻找答案\n• 支持中文和英文提问",
            "sources": [],
            "confidence": 1.0
        },
        "category": "help"
    },
    
    # 修改器相关
    "修改器": {
        "response": {
            "answer": "修改器产品信息：\n\n🔧 **PC版修改器**\n• 价格：¥99-399\n• 功能：属性修改、无限VC、徽章解锁\n• 安全：内存注入，不会被检测\n• 支持：Windows 10/11，Steam/Epic\n\n🎮 **主机版修改器**\n• 价格：¥299-699\n• 平台：PS4/PS5, Xbox One/Series X|S\n• 类型：硬件修改器，物理安全\n• 安装：需要技术指导\n\n⚠️ **注意事项**\n• 所有修改器都有3个月免费更新\n• 使用前请备份存档\n• 遵守游戏平台规则\n\n使用 `!mods` 查看详细信息和购买。",
            "sources": ["mods/pc-mods.md"],
            "confidence": 0.95
        },
        "category": "mods"
    }
}


def preload_cache():
    """预加载热门问题和答案到缓存"""
    cache = get_cache()
    
    for question, data in PRELOADED_CACHE.items():
        cache.set(
            question=question,
            response=data["response"],
            category=data["category"]
        )
    
    logger.info(f"Preloaded {len(PRELOADED_CACHE)} cache entries")


if __name__ == "__main__":
    # 测试缓存系统
    cache = ResponseCache()
    preload_cache()
    
    # 测试获取
    response = cache.get("价格")
    if response:
        print("缓存命中:", response["answer"][:100])
    
    # 获取统计信息
    stats = cache.get_stats()
    print("缓存统计:", json.dumps(stats, indent=2, ensure_ascii=False))