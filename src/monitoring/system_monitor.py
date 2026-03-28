    def _count_alerts_by_severity(self) -> Dict[str, int]:
        """按严重程度统计告警"""
        counts = {'info': 0, 'warning': 0, 'critical': 0}
        for alert in self.alert_manager.alerts:
            severity = alert.get('severity', 'info')
            counts[severity] = counts.get(severity, 0) + 1
        return counts
    
    def stop(self):
        """停止监控"""
        self.monitor_task.stop()
        self.status_report_task.stop()


# Discord命令扩展
class MonitorCommands(commands.Cog):
    """监控相关命令"""
    
    def __init__(self, bot: commands.Bot, monitor: BotMonitor):
        self.bot = bot
        self.monitor = monitor
    
    @commands.command(name='status')
    @commands.has_permissions(administrator=True)
    async def system_status(self, ctx):
        """查看系统状态"""
        stats = self.monitor.get_detailed_stats()
        
        embed = discord.Embed(
            title="📊 系统状态监控",
            description="NBA2k26业务系统实时状态",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # 机器人状态
        bot_stats = stats['bot']
        embed.add_field(
            name="🤖 机器人状态",
            value=f"运行时间: {bot_stats['uptime_hours']:.1f}h\n"
                  f"服务器: {bot_stats['guilds_count']}个\n"
                  f"用户: {bot_stats['users_count']}人\n"
                  f"命令处理: {bot_stats['commands_processed']}次",
            inline=False
        )
        
        # 系统指标
        metrics = stats['metrics']
        embed.add_field(
            name="💻 系统资源",
            value=f"CPU使用: {metrics.get('process_cpu_avg', 0):.1f}%\n"
                  f"内存使用: {metrics.get('process_memory_avg', 0):.1f}%\n"
                  f"系统CPU: {metrics.get('system_cpu_avg', 0):.1f}%\n"
                  f"系统内存: {metrics.get('system_memory_avg', 0):.1f}%",
            inline=True
        )
        
        # 告警状态
        alerts = stats['alerts']
        embed.add_field(
            name="🚨 告警状态",
            value=f"总告警: {alerts['total']}\n"
                  f"24小时内: {alerts['recent_24h']}\n"
                  f"严重告警: {alerts['by_severity'].get('critical', 0)}",
            inline=True
        )
        
        # 错误统计
        embed.add_field(
            name="⚠️ 错误统计",
            value=f"消息处理: {bot_stats['messages_processed']}\n"
                  f"错误次数: {bot_stats['errors_count']}\n"
                  f"错误率: {(bot_stats['errors_count'] / max(bot_stats['messages_processed'], 1) * 100):.1f}%",
            inline=True
        )
        
        # 状态指示器
        status_emoji = "🟢"  # 绿色
        if alerts['by_severity'].get('critical', 0) > 0:
            status_emoji = "🔴"  # 红色
        elif alerts['by_severity'].get('warning', 0) > 0:
            status_emoji = "🟡"  # 黄色
        
        embed.add_field(
            name="📈 整体状态",
            value=f"{status_emoji} 系统运行正常" if status_emoji == "🟢" else f"{status_emoji} 需要注意",
            inline=False
        )
        
        embed.set_footer(text=f"监控指标数: {metrics.get('metrics_count', 0)}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='alerts')
    @commands.has_permissions(administrator=True)
    async def show_alerts(self, ctx, hours: int = 24):
        """查看告警历史"""
        alerts = self.monitor.alert_manager.get_recent_alerts(hours=hours)
        
        if not alerts:
            await ctx.send(f"✅ 过去{hours}小时内没有告警")
            return
        
        # 按严重程度分组
        critical_alerts = [a for a in alerts if a['severity'] == 'critical']
        warning_alerts = [a for a in alerts if a['severity'] == 'warning']
        info_alerts = [a for a in alerts if a['severity'] == 'info']
        
        embed = discord.Embed(
            title=f"🚨 告警历史 ({hours}小时)",
            description=f"共 {len(alerts)} 条告警记录",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        # 严重告警
        if critical_alerts:
            critical_text = "\n".join([
                f"• {a['name']}: {a['message']} ({datetime.fromtimestamp(a['timestamp']).strftime('%H:%M')})"
                for a in critical_alerts[:5]  # 只显示最近5条
            ])
            if len(critical_alerts) > 5:
                critical_text += f"\n... 还有 {len(critical_alerts) - 5} 条"
            embed.add_field(name="🔴 严重告警", value=critical_text, inline=False)
        
        # 警告
        if warning_alerts:
            warning_text = "\n".join([
                f"• {a['name']}: {a['message']} ({datetime.fromtimestamp(a['timestamp']).strftime('%H:%M')})"
                for a in warning_alerts[:5]
            ])
            if len(warning_alerts) > 5:
                warning_text += f"\n... 还有 {len(warning_alerts) - 5} 条"
            embed.add_field(name="🟡 警告", value=warning_text, inline=False)
        
        # 信息
        if info_alerts:
            info_count = len(info_alerts)
            embed.add_field(name="🔵 信息通知", value=f"{info_count} 条信息通知", inline=False)
        
        embed.set_footer(text=f"显示最近 {len(alerts)} 条告警中的部分")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='metrics')
    @commands.has_permissions(administrator=True)
    async def show_metrics(self, ctx, minutes: int = 30):
        """查看系统指标"""
        metrics_history = self.monitor.metrics.get_history(minutes=minutes)
        
        if not metrics_history:
            await ctx.send(f"❌ 没有找到过去{minutes}分钟的指标数据")
            return
        
        # 计算统计信息
        cpu_values = [m['process']['cpu_percent'] for m in metrics_history]
        memory_values = [m['process']['memory_percent'] for m in metrics_history]
        
        embed = discord.Embed(
            title=f"📈 系统指标 ({minutes}分钟)",
            description=f"共 {len(metrics_history)} 条记录",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="💻 CPU使用率",
            value=f"平均: {sum(cpu_values)/len(cpu_values):.1f}%\n"
                  f"最高: {max(cpu_values):.1f}%\n"
                  f"最低: {min(cpu_values):.1f}%",
            inline=True
        )
        
        embed.add_field(
            name="🧠 内存使用率",
            value=f"平均: {sum(memory_values)/len(memory_values):.1f}%\n"
                  f"最高: {max(memory_values):.1f}%\n"
                  f"最低: {min(memory_values):.1f}%",
            inline=True
        )
        
        # 最新指标
        latest = metrics_history[-1]
        embed.add_field(
            name="⏱️ 最新数据",
            value=f"时间: {datetime.fromisoformat(latest['datetime']).strftime('%H:%M:%S')}\n"
                  f"CPU: {latest['process']['cpu_percent']:.1f}%\n"
                  f"内存: {latest['process']['memory_percent']:.1f}%",
            inline=True
        )
        
        # 系统信息
        embed.add_field(
            name="🖥️ 系统资源",
            value=f"系统CPU: {latest['system']['cpu_percent']:.1f}%\n"
                  f"系统内存: {latest['system']['memory_percent']:.1f}%\n"
                  f"磁盘使用: {latest['system']['disk_percent']:.1f}%",
            inline=True
        )
        
        # 趋势指示
        if len(metrics_history) >= 2:
            recent_avg = sum(cpu_values[-5:]) / min(5, len(cpu_values))
            older_avg = sum(cpu_values[-10:-5]) / min(5, len(cpu_values)-5)
            trend = "↗️ 上升" if recent_avg > older_avg else "↘️ 下降" if recent_avg < older_avg else "➡️ 稳定"
            embed.add_field(name="📊 趋势", value=trend, inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='clearcache')
    @commands.has_permissions(administrator=True)
    async def clear_cache(self, ctx):
        """清理监控缓存"""
        self.monitor.metrics.metrics_history = []
        self.monitor.alert_manager.alerts = []
        await ctx.send("✅ 监控缓存已清理")


def setup_monitoring(bot: commands.Bot, alert_channel_id: Optional[int] = None) -> BotMonitor:
    """
    设置监控系统
    
    Args:
        bot: Discord机器人实例
        alert_channel_id: 告警频道ID（可选）
    
    Returns:
        BotMonitor实例
    """
    monitor = BotMonitor(bot, alert_channel_id)
    bot.add_cog(MonitorCommands(bot, monitor))
    
    # 添加事件监听
    @bot.event
    async def on_command_completion(ctx):
        monitor.increment_command_count()
    
    @bot.event
    async def on_message(message):
        if not message.author.bot:
            monitor.increment_message_count()
    
    @bot.event
    async def on_command_error(ctx, error):
        monitor.increment_error_count()
        logger.error(f"Command error: {error}")
    
    logger.info("监控系统已启动")
    return monitor


if __name__ == "__main__":
    # 测试代码
    import asyncio
    
    class MockBot:
        def __init__(self):
            self.guilds = []
            self.is_ready_flag = True
        
        @property
        def is_ready(self):
            return lambda: self.is_ready_flag
        
        async def wait_until_ready(self):
            await asyncio.sleep(0.1)
    
    async def test():
        bot = MockBot()
        monitor = BotMonitor(bot)
        
        # 模拟一些指标
        for _ in range(5):
            metrics = monitor.metrics.collect()
            print(f"CPU: {metrics['process']['cpu_percent']}%, Memory: {metrics['process']['memory_percent']}%")
            await asyncio.sleep(1)
        
        # 获取统计信息
        stats = monitor.get_detailed_stats()
        print("\n系统统计:")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        monitor.stop()
    
    asyncio.run(test())