#!/usr/bin/env python3
f = 'src/discord_bot_final.py'
with open(f, 'r') as h:
    c = h.read()

# Fix 1: Empty output fallback
old1 = 'reply = result.get("output", "").strip()\n\n            # \u68c0\u67e5\u662f\u5426\u5305\u542b\u8ba2\u5355\u786e\u8ba4\u4fe1\u606f'
new1 = 'reply = result.get("output", "").strip()\n\n            if not reply:\n                logger.warning("Agent returned empty output (iteration limit)")\n                reply = "Sorry, I couldn\'t process that fully. Let me get the admin to help you!"\n                return reply, False\n\n            # \u68c0\u67e5\u662f\u5426\u5305\u542b\u8ba2\u5355\u786e\u8ba4\u4fe1\u606f'
if old1 in c:
    c = c.replace(old1, new1)
    print('OK: empty output fallback')
else:
    print('SKIP: empty output fallback')

# Fix 2: Rules 13-15
old2 = '12. Admin sending crypto addresses (Bitcoin, Ethereum, etc.), PayPal info, or payment instructions = WAITING for payment, NOT confirmed. Never treat this as payment received.'
new2 = '12. Admin sending crypto addresses (Bitcoin, Ethereum, etc.), PayPal info, or payment instructions = WAITING for payment, NOT confirmed. Never treat this as payment received.\n13. NEVER fabricate prices or time estimates. Always use get_price tool. If get_price returns no result, tell the customer to contact admin for a custom quote.\n14. If a customer mentions they already placed/paid for an order that you cannot find in the system, politely ask for their order ID or transaction details so the admin can look it up. Do NOT assume the order does not exist.\n15. Keep answers SHORT - max 3-4 sentences unless the customer asks for detailed info.'
if old2 in c:
    c = c.replace(old2, new2)
    print('OK: rules 13-15')
else:
    print('SKIP: rules 13-15')

# Fix 3: Admin @Bot ack
old3 = '                        # \u6ca1\u6709\u5ba2\u6237\u6d88\u606f\uff0c\u7ba1\u7406\u5458\u53ef\u80fd\u662f\u5728\u6d4b\u8bd5 Bot\uff0c\u7528\u7ba1\u7406\u5458\u81ea\u5df1\u7684\u6d88\u606f\u5904\u7406\n                        logger.info(f"\U0001f454 No customer message found, processing admin message as test")\n                        # \u7ee7\u7eed\u8d70\u4e0b\u9762\u7684\u5ba2\u6237\u6d88\u606f\u5904\u7406\u6d41\u7a0b'
new3 = '                        logger.info(f"\U0001f454 No customer message found, sending ack")\n                        try:\n                            await message.channel.send("\u2705 I\'m here and ready! No pending customer messages in this channel.")\n                        except Exception:\n                            pass\n                        return'
if old3 in c:
    c = c.replace(old3, new3)
    print('OK: admin ack')
else:
    print('SKIP: admin ack')

with open(f, 'w') as h:
    h.write(c)
print('DONE')

