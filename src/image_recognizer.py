#!/usr/bin/env python3
"""
🖼️ NBA 2K26 游戏截图智能识别工具
识别游戏内：等级、Rep、徽章、金额等关键业务信息
基于 Tesseract OCR + 关键词匹配的轻量方案
"""

import aiohttp
import asyncio
import io
import json
import logging
import os
import pytesseract
import re
from PIL import Image
from aiohttp_socks import ProxyConnector
from typing import Optional, Dict

logger = logging.getLogger("DiscordBot.ImageRecognizer")

# 游戏内关键信息识别规则（贴合 NBA 2K26 场景）
RECOGNITION_RULES = {
    "level": ["rookie", "starter", "veteran", "legend", "level", "lvl"],
    "rep": ["rep", "rep grind", "rep sleeve"],
    "badge": ["badge", "gym rat", "legendary", "gold", "hof"],
    "99_overall": ["99", "overall", "max overall"],
    "payment": ["paid", "payment", "$", "usd", "crypto", "paypal"]
}


class ImageRecognizer:
    """NBA 2K26 游戏截图识别器"""

    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=60)
        self._session = None
        self._proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        logger.info(f"✅ ImageRecognizer initialized (proxy: {self._proxy})")

    def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session（复用连接池）"""
        if self._session is None or self._session.closed:
            if self._proxy:
                connector = ProxyConnector.from_url(self._proxy)
                logger.info(f"🖼️ Using proxy for image download: {self._proxy}")
            else:
                connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
                trust_env=False
            )
        return self._session

    async def download_image(self, image_url: str, retries: int = 2) -> Optional[Image.Image]:
        """异步下载 Discord 图片（带重试）"""
        for attempt in range(retries + 1):
            try:
                session = self._get_session()
                logger.info(f"🖼️ Downloading image (attempt {attempt+1}): {image_url[:80]}...")
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        logger.warning(f"❌ Image download failed: HTTP {resp.status}")
                        if attempt < retries:
                            await asyncio.sleep(1)
                            continue
                        return None
                    image_data = await resp.read()
                    img = Image.open(io.BytesIO(image_data))
                    logger.info(f"✅ Image downloaded successfully: {img.size}")
                    return img
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Image download timeout (attempt {attempt+1}): {image_url[:80]}")
                if attempt < retries:
                    await asyncio.sleep(1)
                else:
                    logger.error(f"❌ Image download timeout after {retries+1} attempts")
                    return None
            except Exception as e:
                logger.error(f"❌ Image download exception: {e}")
                return None
        return None

    async def close(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()

    def ocr_extract_text(self, image: Image.Image) -> str:
        """
        OCR 识别图片文字（针对游戏字体优化）
        预处理：灰度化 + 二值化，提升游戏文字识别准确率
        """
        try:
            # 转换为灰度图
            image = image.convert("L")

            # 二值化处理（强化游戏内文字对比度）
            threshold = 127
            image = image.point(lambda p: p > threshold and 255)

            # Tesseract OCR 识别（英文优先）
            text = pytesseract.image_to_string(image, lang="eng").lower()

            logger.info(f"📝 OCR 识别结果: {text[:100]}...")
            return text
        except Exception as e:
            logger.error(f"❌ OCR 识别失败: {e}")
            return ""

    def extract_business_info(self, text: str) -> Dict[str, str]:
        """从识别文本中提取业务关键信息"""
        info = {}

        # 匹配等级/Rep/徽章等核心业务字段
        for key, keywords in RECOGNITION_RULES.items():
            if any(kw in text for kw in keywords):
                # 提取具体数值
                if key == "level":
                    level_match = re.search(r"(rookie|starter|veteran|legend)\s*(\d+)", text)
                    if level_match:
                        info["level"] = f"{level_match.group(1)}_{level_match.group(2)}"
                        logger.info(f"🎮 识别到等级: {info['level']}")
                elif key == "rep":
                    rep_match = re.search(r"(rep grind|rep sleeve)", text)
                    if rep_match:
                        info["rep_type"] = rep_match.group(1)
                        logger.info(f"🎯 识别到 Rep 类型: {info['rep_type']}")
                elif key == "99_overall":
                    info["99_overall"] = "true"
                    logger.info(f"💎 识别到 99 Overall")
                elif key == "badge":
                    badge_match = re.search(r"(gym rat|legendary|gold|hof)", text)
                    if badge_match:
                        info["badge"] = badge_match.group(1)
                        logger.info(f"🌟 识别到徽章: {info['badge']}")
                elif key == "payment":
                    price_match = re.search(r"\$(\d+(\.\d+)?)", text)
                    if price_match:
                        info["payment_amount"] = price_match.group(1)
                        logger.info(f"💰 识别到金额: ${info['payment_amount']}")

        return info

    async def recognize(self, image_url: str) -> Optional[Dict[str, str]]:
        """
        统一识图入口: 下载 → OCR → 提取业务信息
        返回: {"level": "rookie_3"} 或 None
        """
        try:
            # 下载图片
            image = await self.download_image(image_url)
            if not image:
                return None

            # OCR 识别
            text = self.ocr_extract_text(image)
            if not text or len(text.strip()) < 3:
                logger.warning(f"⚠️ 图片未识别到有效文字")
                return None

            # 提取业务信息
            info = self.extract_business_info(text)

            if info:
                logger.info(f"✅ 识图完成: {json.dumps(info)}")
                return info
            else:
                logger.warning(f"⚠️ 图片未识别到业务信息")
                return None

        except Exception as e:
            logger.error(f"❌ 识图异常: {e}", exc_info=True)
            return None


# 全局识图工具实例
image_recognizer = None


def init_image_recognizer():
    """初始化识图工具（在 Bot 启动时调用）"""
    global image_recognizer
    try:
        image_recognizer = ImageRecognizer()
        logger.info("🖼️ Image recognizer initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize image recognizer: {e}")
        return False

