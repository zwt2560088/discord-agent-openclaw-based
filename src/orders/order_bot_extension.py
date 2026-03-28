"""
Discord Order Communication Extension
Anonymous Chinese-English communication bridge for orders
"""
import discord
import os
import sys
from discord.ext import commands

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.orders.order_bridge import get_order_manager, OrderStatus, MessageType


class OrderCommunicationCog(commands.Cog):
    """Order communication extension for Discord bot"""

    def __init__(self, bot):
        self.bot = bot
        self.order_manager = get_order_manager()
        self.category_name = "📦 Orders"

    @commands.Cog.listener()
    async def on_ready(self):
        """Setup on ready"""
        print(f"📦 Order Communication System loaded")

    async def get_or_create_category(self, guild: discord.Guild, name: str) -> discord.CategoryChannel:
        """Get or create category"""
        category = discord.utils.get(guild.categories, name=name)
        if not category:
            category = await guild.create_category(name)
        return category

    @commands.command(name='neworder')
    async def create_order_cmd(self, ctx, service_type: str = "reputation",
                                current_level: str = "", target_level: str = "",
                                price: float = 0.0):
        """
        Create a new order with anonymous communication channel

        Usage: !neworder reputation "Rookie 1" "Starter 1" 50
        """
        customer_id = str(ctx.author.id)
        customer_name = str(ctx.author.display_name)

        # Create order in database
        order = self.order_manager.create_order(
            customer_id=customer_id,
            customer_name=customer_name,
            service_type=service_type,
            current_level=current_level,
            target_level=target_level,
            price=price
        )

        # Create customer channel (English - visible to customer)
        guild = ctx.guild
        orders_category = await self.get_or_create_category(guild, self.category_name)

        # Customer channel (English interface)
        customer_channel = await guild.create_text_channel(
            name=f"order-{order.id}",
            category=orders_category,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
            },
            topic=f"Order #{order.id} - Customer Support Channel"
        )

        # Worker channel (Chinese interface - not visible to customer)
        worker_channel = await guild.create_text_channel(
            name=f"履约-{order.id}",
            category=orders_category,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
            },
            topic=f"订单 #{order.id} - 打手沟通频道"
        )

        # Save channel IDs
        self.order_manager.set_channels(
            order.id,
            str(customer_channel.id),
            str(worker_channel.id)
        )

        # Send welcome message to customer (English)
        embed = discord.Embed(
            title="✅ Order Created",
            description=f"Order ID: `{order.id}`",
            color=discord.Color.green()
        )
        embed.add_field(name="Service", value=service_type, inline=True)
        embed.add_field(name="Price", value=f"${price}", inline=True)
        embed.add_field(name="Status", value="⏳ Awaiting Assignment", inline=True)
        embed.add_field(
            name="💬 Communication",
            value="This is your private chat channel. You can talk to our booster here. All messages will be automatically translated!",
            inline=False
        )
        embed.set_footer(text="We'll notify you when a booster is assigned")

        await customer_channel.send(embed=embed)

        # Send welcome message to worker channel (Chinese)
        worker_embed = discord.Embed(
            title="🔔 新订单",
            description=f"订单号: `{order.id}`",
            color=discord.Color.blue()
        )
        worker_embed.add_field(name="服务类型", value=service_type, inline=True)
        worker_embed.add_field(name="价格", value=f"${price}", inline=True)
        worker_embed.add_field(name="状态", value="⏳ 等待接单", inline=True)
        worker_embed.add_field(
            name="📝 说明",
            value="接单后请在此频道沟通。消息会自动翻译给客户（中文→英文）",
            inline=False
        )
        worker_embed.set_footer(text="使用 !accept 命令接单")

        await worker_channel.send(embed=worker_embed)

        # Notify user
        await ctx.send(f"✅ Order created! Your private chat: {customer_channel.mention}")

    @commands.command(name='accept')
    @commands.has_role("Booster")  # Only boosters can accept
    async def accept_order(self, ctx, order_id: str):
        """
        Accept an order (Booster only)

        Usage: !accept abc123
        """
        order = self.order_manager.get_order(order_id)
        if not order:
            await ctx.send(f"❌ Order `{order_id}` not found")
            return

        if order.status != OrderStatus.PENDING and order.status != OrderStatus.PAID:
            await ctx.send(f"❌ Order status is `{order.status.value}`, cannot accept")
            return

        worker_id = str(ctx.author.id)
        worker_name = str(ctx.author.display_name)

        # Assign worker
        self.order_manager.assign_worker(order_id, worker_id, worker_name)
        self.order_manager.update_status(order_id, OrderStatus.IN_PROGRESS)

        # Get channels
        worker_channel = self.bot.get_channel(int(order.worker_channel_id)) if order.worker_channel_id else None
        customer_channel = self.bot.get_channel(int(order.customer_channel_id)) if order.customer_channel_id else None

        # Give worker access to both channels
        if worker_channel:
            await worker_channel.set_permissions(ctx.author, view_channel=True, send_messages=True)
            await worker_channel.send(f"✅ **{ctx.author.display_name}** 已接单，开始履约！")

        # Notify customer (in English)
        if customer_channel:
            embed = discord.Embed(
                title="🎮 Booster Assigned",
                description=f"A booster has been assigned to your order!",
                color=discord.Color.green()
            )
            embed.add_field(name="Status", value="🔄 In Progress", inline=True)
            embed.add_field(
                name="💬 Chat",
                value="You can now chat with your booster here. All messages are automatically translated!",
                inline=False
            )
            await customer_channel.send(embed=embed)

        await ctx.send(f"✅ You accepted order `{order_id}`")

    @commands.command(name='complete')
    @commands.has_role("Booster")
    async def complete_order(self, ctx, order_id: str):
        """Mark order as completed"""
        order = self.order_manager.get_order(order_id)
        if not order:
            await ctx.send(f"❌ Order `{order_id}` not found")
            return

        self.order_manager.update_status(order_id, OrderStatus.COMPLETED)

        # Notify customer
        customer_channel = self.bot.get_channel(int(order.customer_channel_id)) if order.customer_channel_id else None
        if customer_channel:
            embed = discord.Embed(
                title="🎉 Order Completed",
                description="Your order has been completed!",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="📋 What's Next?",
                value="• Please verify the service\n• Use `!confirm` to confirm delivery\n• Contact support if any issues",
                inline=False
            )
            await customer_channel.send(embed=embed)

        await ctx.send(f"✅ Order `{order_id}` marked as completed")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle message translation"""
        if message.author.bot:
            return

        # Check if message is in an order channel
        if not message.channel.name.startswith(("order-", "履约-")):
            return

        # Find order by channel
        order = self._find_order_by_channel(str(message.channel.id))
        if not order:
            return

        # Determine message type and translate
        if message.channel.id == int(order.customer_channel_id) if order.customer_channel_id else None:
            # Customer message (English) → Translate to Chinese for worker
            msg_type = MessageType.CUSTOMER
            worker_channel = self.bot.get_channel(int(order.worker_channel_id)) if order.worker_channel_id else None

            if worker_channel:
                # Process translation
                processed = await self.order_manager.process_message(
                    order.id, msg_type, message.content, str(message.author.id)
                )

                # Send to worker channel
                await worker_channel.send(f"👤 **[Customer]** {processed.translated_text}")

        elif message.channel.id == int(order.worker_channel_id) if order.worker_channel_id else None:
            # Worker message (Chinese) → Translate to English for customer
            msg_type = MessageType.WORKER
            customer_channel = self.bot.get_channel(int(order.customer_channel_id)) if order.customer_channel_id else None

            if customer_channel:
                # Process translation
                processed = await self.order_manager.process_message(
                    order.id, msg_type, message.content, str(message.author.id)
                )

                # Send to customer channel (anonymous - show as Support)
                await customer_channel.send(f"🎮 **[Support]** {processed.translated_text}")

    def _find_order_by_channel(self, channel_id: str) -> any:
        """Find order by channel ID"""
        orders = self.order_manager.get_all_orders()
        for order in orders:
            if order.customer_channel_id == channel_id or order.worker_channel_id == channel_id:
                return order
        return None

    @commands.command(name='orderstats')
    async def order_stats(self, ctx):
        """Show order statistics"""
        stats = self.order_manager.get_stats()

        embed = discord.Embed(
            title="📊 Order Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="Total Orders", value=stats.get('total', 0), inline=True)
        embed.add_field(name="Today", value=stats.get('today', 0), inline=True)
        embed.add_field(name="Pending", value=stats.get('pending', 0), inline=True)
        embed.add_field(name="In Progress", value=stats.get('in_progress', 0), inline=True)
        embed.add_field(name="Completed", value=stats.get('completed', 0), inline=True)

        await ctx.send(embed=embed)

    @commands.command(name='myorders')
    async def my_orders(self, ctx):
        """Show user's orders"""
        customer_id = str(ctx.author.id)
        orders = self.order_manager.get_orders_by_customer(customer_id)

        if not orders:
            await ctx.send("You have no orders yet.")
            return

        embed = discord.Embed(
            title="📋 Your Orders",
            color=discord.Color.blue()
        )

        for order in orders[:5]:  # Show last 5 orders
            status_emoji = {
                OrderStatus.PENDING: "⏳",
                OrderStatus.PAID: "💰",
                OrderStatus.ASSIGNED: "👤",
                OrderStatus.IN_PROGRESS: "🔄",
                OrderStatus.COMPLETED: "✅",
                OrderStatus.DELIVERED: "📦"
            }.get(order.status, "❓")

            embed.add_field(
                name=f"{status_emoji} Order #{order.id}",
                value=f"Service: {order.service_type}\nPrice: ${order.price}\nStatus: {order.status.value}",
                inline=False
            )

        await ctx.send(embed=embed)


async def setup(bot):
    """Setup the cog"""
    await bot.add_cog(OrderCommunicationCog(bot))


# Function to add cog to existing bot
def add_order_communication(bot):
    """Add order communication to existing bot"""
    bot.add_cog(OrderCommunicationCog(bot))
    return bot

