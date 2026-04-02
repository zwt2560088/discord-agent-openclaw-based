f = 'src/discord_bot_final.py'
with open(f, 'r') as fh:
    content = fh.read()

# Fix 1: rules 13-15
old1 = '12. Admin sending crypto addresses'
idx = content.find(old1)
if idx > 0:
    end = content.find('\n', idx)
    line = content[idx:end]
    rep = line + '\n13. NEVER fabricate prices or time estimates. Always use get_price tool for pricing. If get_price returns no result, tell the customer to contact admin for a custom quote.\n14. If a customer mentions they already placed/paid for an order that you cannot find in the system, politely ask them to provide the order ID or transaction details so the admin can look it up. Do NOT assume the order does not exist.\n15. Keep answers SHORT - max 3-4 sentences unless the customer asks for detailed info.'
    content = content.replace(line, rep)
    print("OK: rules 13-15")
else:
    print("SKIP: rules not found")

# Fix 2: max_iterations
content = content.replace('max_iterations=5', 'max_iterations=8')
print("OK: max_iterations=8")

# Fix 3: max_execution_time
old3 = 'max_iterations=8\n            )'
new3 = 'max_iterations=8,\n                max_execution_time=60\n            )'
content = content.replace(old3, new3)
print("OK: max_execution_time=60")

# Fix 4: empty output fallback
old4 = 'reply = result.get("output", "").strip()\n\n            # \u68c0\u67e5\u662f\u5426\u5305\u542b\u8ba2\u5355\u786e\u8ba4\u4fe1\u606f'
new4 = 'reply = result.get("output", "").strip()\n\n            if not reply:\n                logger.warning("ReAct Agent returned empty output")\n                reply = "Sorry, I couldn\'t process that fully. Let me get the admin to help you!"\n                return reply, False\n\n            # \u68c0\u67e5\u662f\u5426\u5305\u542b\u8ba2\u5355\u786e\u8ba4\u4fe1\u606f'
if old4 in content:
    content = content.replace(old4, new4)
    print("OK: empty output fallback")
else:
    print("SKIP: empty fallback")

# Fix 5: admin ack
old5 = '# \u6ca1\u6709\u5ba2\u6237\u6d88\u606f\uff0c\u7ba1\u7406\u5458\u53ef\u80fd\u662f\u5728\u6d4b\u8bd5 Bot'
idx5 = content.find(old5)
if idx5 > 0:
    # Find the whole block from "else:" before it to "return"
    block_start = content.rfind('else:', 0, idx5)
    # Find the next "return" after block_start
    ret_idx = content.find('return', idx5)
    if ret_idx > 0:
        end_of_return = content.find('\n', ret_idx)
        old_block = content[block_start:end_of_return]
        new_block = '''else:
                        logger.info(f"\U0001f454 No customer message found, sending ack to admin")
                        try:
                            await message.channel.send("I'm here and ready! No pending customer messages in this channel.")
                        except Exception as e:
                            logger.warning(f"Admin ack failed: {e}")
                        return'''
        content = content.replace(old_block, new_block)
        print("OK: admin ack")
    else:
        print("SKIP: admin ack no return found")
else:
    print("SKIP: admin ack not found")

with open(f, 'w') as fh:
    fh.write(content)
print("DONE")

