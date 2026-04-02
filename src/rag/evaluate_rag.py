#!/usr/bin/env python3
"""
RAG 系统自动化评测脚本

评测指标：
1. 命中率 (Hit Rate): 查询是否有相关文档被召回
2. MRR (Mean Reciprocal Rank): 正确答案在召回列表中的平均排名倒数
3. 平均检索耗时
4. 各策略对比（BM25 / 语义 / 混合）
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==================== 评测数据集 ====================
EVAL_DATASET = [
    # 价格相关
    {
        "query": "What's the price for Rep Sleeves?",
        "expected_doc_keywords": ["rep", "sleeve", "price"],
        "expected_category": "pricing",
        "difficulty": "easy"
    },
    {
        "query": "How much does 99 overall cost?",
        "expected_doc_keywords": ["99", "overall", "price"],
        "expected_category": "pricing",
        "difficulty": "easy"
    },
    {
        "query": "VC prices",
        "expected_doc_keywords": ["vc", "price"],
        "expected_category": "pricing",
        "difficulty": "medium"
    },
    {
        "query": "MT服务价格",
        "expected_doc_keywords": ["mt", "price"],
        "expected_category": "pricing",
        "difficulty": "medium"
    },
    # 服务相关
    {
        "query": "What services do you offer?",
        "expected_doc_keywords": ["service", "rep", "boost"],
        "expected_category": "services",
        "difficulty": "easy"
    },
    {
        "query": "Can you help with badge grinding?",
        "expected_doc_keywords": ["badge", "grind"],
        "expected_category": "services",
        "difficulty": "medium"
    },
    {
        "query": "I need help with leveling",
        "expected_doc_keywords": ["level", "boost"],
        "expected_category": "services",
        "difficulty": "medium"
    },
    # 流程相关
    {
        "query": "How do I place an order?",
        "expected_doc_keywords": ["order", "process", "step"],
        "expected_category": "procedures",
        "difficulty": "easy"
    },
    {
        "query": "What payment methods do you accept?",
        "expected_doc_keywords": ["payment", "method", "paypal", "crypto"],
        "expected_category": "procedures",
        "difficulty": "medium"
    },
    {
        "query": "How long does delivery take?",
        "expected_doc_keywords": ["delivery", "time", "hour"],
        "expected_category": "procedures",
        "difficulty": "medium"
    },
    # FAQ 相关
    {
        "query": "Is it safe to buy from you?",
        "expected_doc_keywords": ["safe", "risk", "ban"],
        "expected_category": "faq",
        "difficulty": "easy"
    },
    {
        "query": "Will I get banned?",
        "expected_doc_keywords": ["ban", "safe"],
        "expected_category": "faq",
        "difficulty": "easy"
    },
    {
        "query": "Do you offer refunds?",
        "expected_doc_keywords": ["refund", "satisfaction"],
        "expected_category": "faq",
        "difficulty": "medium"
    },
    # 组合/复杂查询
    {
        "query": "I want to buy Rep Sleeves and Level 40 boost, how much total?",
        "expected_doc_keywords": ["rep", "sleeve", "level", "price"],
        "expected_category": "pricing",
        "difficulty": "hard"
    },
    {
        "query": "What's the difference between 99 overall and max overall service?",
        "expected_doc_keywords": ["99", "overall", "max"],
        "expected_category": "services",
        "difficulty": "hard"
    },
    # 边界 case
    {
        "query": "xcvbnmasdfghjkl",  # 无意义查询
        "expected_doc_keywords": [],
        "expected_category": None,
        "expected_no_results": True,  # 期望返回空结果或低相关
        "difficulty": "edge"
    },
    {
        "query": "ping",  # 简单测试
        "expected_doc_keywords": [],
        "expected_category": None,
        "expected_no_results": True,
        "difficulty": "edge"
    },
    # 英文/中文混合
    {
        "query": "rep sleeve多少钱",
        "expected_doc_keywords": ["rep", "sleeve"],
        "expected_category": "pricing",
        "difficulty": "medium"
    },
    {
        "query": "99 overall服务介绍",
        "expected_doc_keywords": ["99", "overall"],
        "expected_category": "services",
        "difficulty": "medium"
    },
]


class RAGEvaluator:
    """RAG 系统评测器"""

    def __init__(self, knowledge_base_path: str):
        from rag.knowledge_base import KnowledgeBase
        self.kb = KnowledgeBase(knowledge_base_path)
        self.results = []

    def evaluate_single(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """评测单个查询"""
        query = test_case["query"]
        expected_keywords = test_case.get("expected_doc_keywords", [])
        expected_category = test_case.get("expected_category")
        difficulty = test_case.get("difficulty", "medium")

        start_time = time.time()
        results = self.kb.search(query, top_k=5, use_hybrid=True, min_score=0.0)
        latency_ms = (time.time() - start_time) * 1000

        # 计算命中：先检查 relevant_content，再检查完整文档内容
        hit = False
        rank = 0
        if test_case.get("expected_no_results"):
            # Edge case: 期望无结果或所有结果低相关度
            hit = all(r['similarity'] < 0.1 for r in results) if results else True
        elif expected_keywords:
            for i, r in enumerate(results):
                # 优先检查 relevant_content
                content_lower = r['relevant_content'].lower()
                full_lower = r['document']['content'].lower()
                if any(kw.lower() in content_lower or kw.lower() in full_lower for kw in expected_keywords):
                    hit = True
                    rank = i + 1
                    break

        # 类别匹配
        category_match = False
        if expected_category and results:
            category_match = results[0]['document'].get('category') == expected_category

        return {
            "query": query,
            "difficulty": difficulty,
            "hit": hit,
            "rank": rank,
            "reciprocal_rank": 1.0 / rank if rank > 0 else 0,
            "latency_ms": round(latency_ms, 2),
            "category_match": category_match,
            "num_results": len(results),
            "expected_category": expected_category,
            "actual_category": results[0]['document'].get('category') if results else None
        }

    def evaluate_all(self, dataset: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """评测整个数据集"""
        if dataset is None:
            dataset = EVAL_DATASET

        self.results = []
        for test_case in dataset:
            result = self.evaluate_single(test_case)
            self.results.append(result)

        # 汇总指标
        total = len(self.results)
        hits = sum(1 for r in self.results if r["hit"])
        mrr = sum(r["reciprocal_rank"] for r in self.results) / max(total, 1)
        avg_latency = sum(r["latency_ms"] for r in self.results) / max(total, 1)
        category_accuracy = sum(1 for r in self.results if r["category_match"]) / max(
            sum(1 for r in self.results if r["expected_category"]), 1)

        # 按难度分组统计
        by_difficulty = {}
        for r in self.results:
            diff = r["difficulty"]
            if diff not in by_difficulty:
                by_difficulty[diff] = {"total": 0, "hits": 0, "mrr_sum": 0, "latency_sum": 0}
            by_difficulty[diff]["total"] += 1
            by_difficulty[diff]["hits"] += 1 if r["hit"] else 0
            by_difficulty[diff]["mrr_sum"] += r["reciprocal_rank"]
            by_difficulty[diff]["latency_sum"] += r["latency_ms"]

        for diff, stats in by_difficulty.items():
            stats["hit_rate"] = stats["hits"] / max(stats["total"], 1)
            stats["mrr"] = stats["mrr_sum"] / max(stats["total"], 1)
            stats["avg_latency_ms"] = stats["latency_sum"] / max(stats["total"], 1)

        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_queries": total,
                "hit_rate": hits / max(total, 1),
                "mrr": round(mrr, 4),
                "avg_latency_ms": round(avg_latency, 2),
                "category_accuracy": round(category_accuracy, 4),
            },
            "by_difficulty": {k: {
                "total": v["total"],
                "hit_rate": round(v["hit_rate"], 4),
                "mrr": round(v["mrr"], 4),
                "avg_latency_ms": round(v["avg_latency_ms"], 2)
            } for k, v in by_difficulty.items()},
            "details": self.results
        }

    def compare_strategies(self, query: str) -> Dict[str, Any]:
        """对比不同检索策略的效果"""
        results = {}

        # BM25 only
        start = time.time()
        bm25_results = self.kb.search(query, top_k=5, use_hybrid=False)
        results["bm25"] = {
            "latency_ms": round((time.time() - start) * 1000, 2),
            "results": [{"title": r['document']['title'], "score": r['similarity']} for r in bm25_results]
        }

        # 混合检索
        start = time.time()
        hybrid_results = self.kb.search(query, top_k=5, use_hybrid=True)
        results["hybrid"] = {
            "latency_ms": round((time.time() - start) * 1000, 2),
            "results": [{
                "title": r['document']['title'],
                "bm25_score": r.get('bm25_score', 0),
                "semantic_score": r.get('semantic_score', 0),
                "final_score": r['similarity']
            } for r in hybrid_results]
        }

        return results

    def save_report(self, output_path: str = None):
        """保存评测报告"""
        if output_path is None:
            output_path = os.path.join(
                Path(__file__).parent,
                f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

        report = self.evaluate_all()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"📊 评测报告已保存: {output_path}")
        return report


def print_report(report: Dict[str, Any]):
    """打印评测报告"""
    print("\n" + "=" * 60)
    print("📊 RAG 系统评测报告")
    print("=" * 60)

    summary = report["summary"]
    print(f"\n【总体指标】")
    print(f"  总查询数: {summary['total_queries']}")
    print(f"  命中率 (Hit Rate): {summary['hit_rate']:.2%}")
    print(f"  MRR (Mean Reciprocal Rank): {summary['mrr']:.4f}")
    print(f"  平均延迟: {summary['avg_latency_ms']:.2f} ms")
    print(f"  类别准确率: {summary['category_accuracy']:.2%}")

    print(f"\n【按难度统计】")
    for diff, stats in report.get("by_difficulty", {}).items():
        print(f"  {diff}: 命中率 {stats['hit_rate']:.2%}, MRR {stats['mrr']:.4f}, 延迟 {stats['avg_latency_ms']:.2f}ms")

    print(f"\n【详细结果（失败案例）】")
    failures = [r for r in report["details"] if not r["hit"] and r["difficulty"] != "edge"]
    for f in failures[:5]:
        print(f"  ❌ '{f['query'][:40]}...' → 未命中 (期望: {f['expected_category']})")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    # 获取知识库路径
    kb_path = os.path.join(Path(__file__).parent.parent.parent, "knowledge")

    if not os.path.exists(kb_path):
        logger.error(f"知识库路径不存在: {kb_path}")
        sys.exit(1)

    # 运行评测
    evaluator = RAGEvaluator(kb_path)
    report = evaluator.save_report()
    print_report(report)

    # 策略对比示例
    print("\n【策略对比示例】")
    comparison = evaluator.compare_strategies("What's the price for Rep Sleeves?")
    print(f"BM25 延迟: {comparison['bm25']['latency_ms']}ms")
    print(f"混合检索延迟: {comparison['hybrid']['latency_ms']}ms")
    print(f"BM25 Top1: {comparison['bm25']['results'][0] if comparison['bm25']['results'] else 'N/A'}")
    print(f"混合 Top1: {comparison['hybrid']['results'][0] if comparison['hybrid']['results'] else 'N/A'}")

