#!/usr/bin/env python3
"""
🔍 Discord Bot 诊断脚本
检查所有关键配置和 API 连接
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def check_env_vars():
    """检查环境变量"""
    print("=" * 60)
    print("📋 Environment Variables Check")
    print("=" * 60)

    vars_to_check = [
        ("discord_token", "Discord Token"),
        ("deepseek_api_key", "DeepSeek API Key"),
        ("openai_api_key", "OpenAI API Key"),
    ]

    results = {}
    for env_var, display_name in vars_to_check:
        value = os.getenv(env_var)
        if value:
            display_val = f"{value[:20]}..." if len(value) > 20 else value
            print(f"✅ {display_name}: {display_val}")
            results[env_var] = True
        else:
            print(f"❌ {display_name}: NOT CONFIGURED")
            results[env_var] = False

    return results

async def test_deepseek_api():
    """测试 DeepSeek API 连接"""
    print("\n" + "=" * 60)
    print("🌐 DeepSeek API Connection Test")
    print("=" * 60)

    api_key = os.getenv("deepseek_api_key")
    if not api_key:
        print("❌ DeepSeek API key not configured, skipping test")
        return False

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.3,
                "max_tokens": 50
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "choices" in data and data["choices"]:
                        reply = data["choices"][0]["message"]["content"]
                        print(f"✅ DeepSeek API working!")
                        print(f"   Reply: {reply[:50]}...")
                        return True
                else:
                    text = await resp.text()
                    print(f"❌ DeepSeek API error: {resp.status}")
                    print(f"   Response: {text[:200]}")
                    return False
    except asyncio.TimeoutError:
        print("❌ DeepSeek API timeout (>10s)")
        return False
    except Exception as e:
        print(f"❌ DeepSeek API error: {e}")
        return False

async def test_openai_api():
    """测试 OpenAI API 连接"""
    print("\n" + "=" * 60)
    print("🌐 OpenAI API Connection Test")
    print("=" * 60)

    api_key = os.getenv("openai_api_key")
    if not api_key:
        print("⊘ OpenAI API key not configured, skipping test")
        return None

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.3,
                "max_tokens": 50
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "choices" in data and data["choices"]:
                        reply = data["choices"][0]["message"]["content"]
                        print(f"✅ OpenAI API working!")
                        print(f"   Reply: {reply[:50]}...")
                        return True
                else:
                    text = await resp.text()
                    print(f"❌ OpenAI API error: {resp.status}")
                    print(f"   Response: {text[:200]}")
                    return False
    except asyncio.TimeoutError:
        print("❌ OpenAI API timeout (>10s)")
        return False
    except Exception as e:
        print(f"❌ OpenAI API error: {e}")
        return False

async def check_quick_reply():
    """检查快速回复关键词"""
    print("\n" + "=" * 60)
    print("⚡ Quick Reply Keywords Check")
    print("=" * 60)

    from discord_bot_final import QUICK_REPLY_KEYWORDS

    print(f"✅ Found {len(QUICK_REPLY_KEYWORDS)} quick reply keywords:")
    for keyword in list(QUICK_REPLY_KEYWORDS.keys())[:5]:
        print(f"   • {keyword}")
    if len(QUICK_REPLY_KEYWORDS) > 5:
        print(f"   ... and {len(QUICK_REPLY_KEYWORDS) - 5} more")

async def main():
    print("\n🔍 Discord Bot Diagnostic Report")
    print("=" * 60)

    # 1. 检查环境变量
    env_results = check_env_vars()

    # 2. 测试 API 连接
    deepseek_ok = await test_deepseek_api()
    openai_ok = await test_openai_api()

    # 3. 检查快速回复
    try:
        await check_quick_reply()
    except Exception as e:
        print(f"\n⚠️ Quick reply check failed: {e}")

    # 总结
    print("\n" + "=" * 60)
    print("📊 Diagnostic Summary")
    print("=" * 60)

    if env_results.get("discord_token"):
        print("✅ Discord Token: Configured")
    else:
        print("❌ Discord Token: MISSING - Bot cannot start")

    if deepseek_ok or openai_ok:
        print("✅ AI API: At least one API is working")
        if deepseek_ok:
            print("   ✅ DeepSeek: OK")
        if openai_ok:
            print("   ✅ OpenAI: OK")
    else:
        print("❌ AI API: Neither API is working - Bot won't respond to queries")

    print("\n" + "=" * 60)
    print("💡 Next Steps:")
    print("=" * 60)
    print("1. Start the bot: python3 discord_bot_final.py")
    print("2. In Discord, send: 'rep' or 'price' (should get quick reply)")
    print("3. Send: '@Bot what's the 99 overall price?' (AI response)")
    print("4. Check console logs for any errors")
    print("\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {e}")
        sys.exit(1)

