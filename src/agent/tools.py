"""
Agent Tools - ReAct Agent Operations
"""
import json
import os
import sys
from datetime import datetime
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.rag.knowledge_base import get_rag_engine
from src.orders.order_manager import get_order_manager, OrderStatus, ServiceType, Platform


# Import reputation calculator
try:
    from src.pricing.reputation_calculator import get_calculator
    REPUTATION_CALCULATOR_AVAILABLE = True
except ImportError:
    REPUTATION_CALCULATOR_AVAILABLE = False


class KnowledgeSearchInput(BaseModel):
    """Knowledge base search input"""
    query: str = Field(description="User question or search keywords")


class KnowledgeSearchTool(BaseTool):
    """Knowledge base search tool - RAG retrieval"""
    name: str = "knowledge_search"
    description: str = "Search NBA2k26 business knowledge base for services, pricing, FAQ, and more. Input: user question. Output: relevant knowledge content."
    args_schema: type[BaseModel] = KnowledgeSearchInput
    _rag_engine = None

    def _run(self, query: str) -> str:
        """Execute knowledge search"""
        try:
            if self._rag_engine is None:
                try:
                    self._rag_engine = get_rag_engine()
                except Exception as e:
                    return self._local_search(query)

            result = self._rag_engine.query(query)

            if result['confidence'] > 0.3:
                return f"[Knowledge Base]\n{result['answer']}\n\nConfidence: {result['confidence']:.2f}"
            else:
                return self._local_search(query)
        except Exception as e:
            return self._local_search(query)

    def _local_search(self, query: str) -> str:
        """Local knowledge search (no model dependency)"""
        query_lower = query.lower()

        # English knowledge base
        local_knowledge = {
            'price': '''【Pricing Information】
🏀 Player Upgrade: Level 1-70 $15 / 71-85 $20 / 86-95 $35 / 96-99 $50
🏅 Badge Unlock: Single $5 / 10 Pack $25 / 30 Pack $60
💰 VC Boosting:
   • 100K VC - $12.5 (15 min ETA, Manual)
   • 300K VC - $30 (24h ETA, Manual)
   • 500K VC - $27.5 (Instant) or $50 (Manual 24h)
   • 1M VC - $90 (24h ETA)
💻 PC Mod: Basic $15 / Pro $35 / Lifetime $60
🎮 Console Mod: PS/Xbox $45 / Switch $60 / All Platforms $100''',

            'pricing': '''【Pricing Information】
🏀 Player Upgrade: Level 1-70 $15 / 71-85 $20 / 86-95 $35 / 96-99 $50
🏅 Badge Unlock: Single $5 / 10 Pack $25 / 30 Pack $60
💰 VC Boosting:
   • 100K VC - $12.5 (15 min ETA, Manual)
   • 300K VC - $30 (24h ETA, Manual)
   • 500K VC - $27.5 (Instant) or $50 (Manual 24h)
   • 1M VC - $90 (24h ETA)
💻 PC Mod: Basic $15 / Pro $35 / Lifetime $60
🎮 Console Mod: PS/Xbox $45 / Switch $60 / All Platforms $100''',

            'cost': '''【Pricing Information】
🏀 Player Upgrade: Level 1-70 $15 / 71-85 $20 / 86-95 $35 / 96-99 $50
🏅 Badge Unlock: Single $5 / 10 Pack $25 / 30 Pack $60
💰 VC Boosting:
   • 100K VC - $12.5 (15 min ETA, Manual)
   • 300K VC - $30 (24h ETA, Manual)
   • 500K VC - $27.5 (Instant) or $50 (Manual 24h)
   • 1M VC - $90 (24h ETA)
💻 PC Mod: Basic $15 / Pro $35 / Lifetime $60
🎮 Console Mod: PS/Xbox $45 / Switch $60 / All Platforms $100''',

            'vc': '''【VC Boosting Service】
🚀 INSTANT VC:
• 500K VC - $27.5 (Instant delivery, requires 250 lifetime challenges)

🔧 MANUAL VC (50+ hrs safer, play during boost):
• 100K VC - $12.5 (15 min ETA)
• 300K VC - $30 (24h ETA)
• 500K VC - $50 (24h ETA)
• 1M VC - $90 (24h ETA)

💡 Instant VC is one-time only per Steam account. Use Manual VC after that.''',

            'service': '''【Available Services】
🎮 Boosting Services: Player Upgrade, Badge Unlock, VC Boosting, MyTeam Building
🔧 Mod Products: PC Version, Console Version (PS/Xbox/Switch)
📦 Supported Platforms: Steam, Epic, PlayStation, Xbox, Switch
💰 Special: Instant VC (500K for $27.5) available!''',

            'boost': '''【Boosting Services】
🎮 Boosting Services: Player Upgrade, Badge Unlock, VC Boosting, MyTeam Building
🔧 Mod Products: PC Version, Console Version (PS/Xbox/Switch)
📦 Supported Platforms: Steam, Epic, PlayStation, Xbox, Switch
💰 Special: Instant VC (500K for $27.5) available!''',

            'safe': '''【Safety Information】
✅ Boosting: Professional boosters, manual operation, minimized ban risk
⚠️ Mods: Latest anti-detection technology, recommended offline mode only
📝 Notes: Do not use in online matches, use with caution on important accounts''',

            'ban': '''【Safety Information】
✅ Boosting: Professional boosters, manual operation, minimized ban risk
⚠️ Mods: Latest anti-detection technology, recommended offline mode only
📝 Notes: Do not use in online matches, use with caution on important accounts''',

            'help': '''【Help Guide】
📋 Commands:
• !order - Create new order
• !status [order_id] - Check order status
• !pay <order_id> - Confirm payment
• !services - View all services
• !pricing - View prices
• !faq - Frequently asked questions
• !support - Contact support''',

            'mod': '''【Mod Information】
💻 PC Version: Supports Steam/Epic, features include unlimited VC, attribute editing, badge unlock
🎮 Console Version: Supports PS4/PS5/Xbox/Switch, cloud save management
⚠️ Safety: Recommended offline mode only, do not use in online matches''',

            'cheat': '''【Mod Information】
💻 PC Version: Supports Steam/Epic, features include unlimited VC, attribute editing, badge unlock
🎮 Console Version: Supports PS4/PS5/Xbox/Switch, cloud save management
⚠️ Safety: Recommended offline mode only, do not use in online matches''',

            'order': '''【Order Process】
1️⃣ Create Order: Use !order command or tell me your service type
2️⃣ Confirm Payment: Use !pay <order_id>
3️⃣ Auto Fulfillment: System automatically assigns and processes after payment
4️⃣ Check Status: Use !status <order_id>''',

            'faq': '''【Frequently Asked Questions】
Q: Is boosting safe?
A: Our boosting is done by professional players manually, using advanced security techniques.

Q: Will mods get me banned?
A: Any mod carries some risk. We use the latest anti-detection technology. Recommended offline only.

Q: How long does it take?
A: Depends on service type, usually 2-24 hours.

Q: Payment methods?
A: We support PayPal, Credit Card, Crypto, and more.''',

            'payment': '''【Payment Methods】
💳 PayPal - Fast and secure
💰 Credit Card - Visa, Mastercard, AMEX
🪙 Crypto - Bitcoin, Ethereum, USDT
📱 Discord members get special discounts!''',

            'time': '''【Processing Time】
🏀 Player Upgrade: 2-4 hours
🏅 Badge Unlock: 2-4 hours
💰 VC Farm: 1-2 hours
💻 PC Mod: Instant delivery
🎮 Console Mod: 30 mins setup''',

            'platform': '''【Supported Platforms】
💻 PC: Steam, Epic Games
🎮 Console: PlayStation 4/5, Xbox One/Series, Nintendo Switch
📱 All platforms fully supported!'''
        }

        # Match keywords
        for keyword, content in local_knowledge.items():
            if keyword in query_lower:
                return f"{content}\n\n💡 Need more help? Use specific commands or contact support."

        # Default return help
        return local_knowledge['help']


class OrderCreateInput(BaseModel):
    """Order creation input"""
    customer_id: str = Field(description="Customer Discord ID")
    service_type: str = Field(description="Service type: level_up/badges/vc_farm/pc_mod/console_mod")
    details: str = Field(description="Order details JSON string")


class OrderCreateTool(BaseTool):
    """Order creation tool"""
    name: str = "create_order"
    description: str = "Create a new order. Input customer ID, service type, and details. Returns order ID and price."
    args_schema: type[BaseModel] = OrderCreateInput

    def _run(self, customer_id: str, service_type: str, details: str) -> str:
        """Create order"""
        try:
            order_manager = get_order_manager()

            # Parse details
            details_dict = json.loads(details) if isinstance(details, str) else details

            # Service type mapping
            service_map = {
                'level_up': ServiceType.LEVEL_UP,
                'badges': ServiceType.BADGES,
                'vc_farm': ServiceType.VC_FARM,
                'pc_mod': ServiceType.PC_MOD,
                'console_mod': ServiceType.CONSOLE_MOD,
                'player upgrade': ServiceType.LEVEL_UP,
                'badge': ServiceType.BADGES,
                'vc': ServiceType.VC_FARM,
                'mod': ServiceType.PC_MOD,
                'console': ServiceType.CONSOLE_MOD
            }

            service = service_map.get(service_type.lower(), ServiceType.LEVEL_UP)

            # Create order
            order = order_manager.create_order(
                customer_id=customer_id,
                service_type=service,
                details=details_dict,
                platform=Platform.DISCORD
            )

            return json.dumps({
                "success": True,
                "order_id": order.id,
                "amount": order.amount,
                "status": order.status.value,
                "message": f"Order created successfully! Order ID: {order.id[:8]}..., Amount: ${order.amount}"
            })

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"Order creation failed: {str(e)}"
            })


class PaymentConfirmInput(BaseModel):
    """Payment confirmation input"""
    order_id: str = Field(description="Order ID")
    payment_method: str = Field(description="Payment method: paypal/credit_card/crypto")


class PaymentConfirmTool(BaseTool):
    """Payment confirmation tool"""
    name: str = "confirm_payment"
    description: str = "Confirm order payment. Input order ID and payment method. After successful payment, order status becomes PAID and can trigger fulfillment."
    args_schema: type[BaseModel] = PaymentConfirmInput

    def _run(self, order_id: str, payment_method: str) -> str:
        """Confirm payment"""
        try:
            order_manager = get_order_manager()

            # Get order
            order = order_manager.db_manager.get_order(order_id)
            if not order:
                return json.dumps({
                    "success": False,
                    "message": f"Order {order_id} not found"
                })

            # Check order status
            if order.status != OrderStatus.PENDING:
                return json.dumps({
                    "success": False,
                    "message": f"Invalid order status, current: {order.status.value}"
                })

            # Simulate payment confirmation (should call payment API in production)
            # Update order status to paid
            order_manager.update_order_status(order_id, OrderStatus.PAID)

            return json.dumps({
                "success": True,
                "order_id": order_id,
                "amount": order.amount,
                "payment_method": payment_method,
                "status": "paid",
                "message": f"Payment confirmed! Order {order_id[:8]}... paid ${order.amount}, ready for fulfillment."
            })

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })


class OrderQueryInput(BaseModel):
    """Order query input"""
    order_id: Optional[str] = Field(None, description="Order ID (optional)")
    customer_id: Optional[str] = Field(None, description="Customer ID (optional)")


class OrderQueryTool(BaseTool):
    """Order query tool"""
    name: str = "query_order"
    description: str = "Query order status. Input order ID or customer ID. Returns order details and status."
    args_schema: type[BaseModel] = OrderQueryInput

    def _run(self, order_id: str = None, customer_id: str = None) -> str:
        """Query order"""
        try:
            order_manager = get_order_manager()

            if order_id:
                status = order_manager.get_order_status(order_id)
                if status:
                    return json.dumps({
                        "success": True,
                        "order": status,
                        "message": f"Order {order_id[:8]}... status: {status['status']}"
                    })
                else:
                    return json.dumps({
                        "success": False,
                        "message": f"Order {order_id} not found"
                    })

            elif customer_id:
                orders = order_manager.db_manager.get_orders_by_customer(customer_id)
                if orders:
                    order_list = [{
                        "id": o.id[:8],
                        "service": o.service_type.value,
                        "status": o.status.value,
                        "amount": o.amount
                    } for o in orders[:5]]

                    return json.dumps({
                        "success": True,
                        "orders": order_list,
                        "count": len(orders),
                        "message": f"Found {len(orders)} order(s)"
                    })
                else:
                    return json.dumps({
                        "success": False,
                        "message": "No orders found for this customer"
                    })

            else:
                return json.dumps({
                    "success": False,
                    "message": "Please provide order ID or customer ID"
                })

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })


class FulfillmentInput(BaseModel):
    """Fulfillment input"""
    order_id: str = Field(description="Order ID")
    action: str = Field(description="Fulfillment action: start/complete/deliver")


class FulfillmentTool(BaseTool):
    """Fulfillment tool - Pass paid orders to downstream systems"""
    name: str = "fulfill_order"
    description: str = "Execute order fulfillment. Input order ID and action (start/complete/deliver). Used to process paid orders and pass to downstream systems."
    args_schema: type[BaseModel] = FulfillmentInput

    def _run(self, order_id: str, action: str) -> str:
        """Execute fulfillment"""
        try:
            order_manager = get_order_manager()

            # Get order
            order = order_manager.db_manager.get_order(order_id)
            if not order:
                return json.dumps({
                    "success": False,
                    "message": f"Order {order_id} not found"
                })

            # Execute different actions
            if action == "start":
                # Start fulfillment - order must be PAID
                if order.status != OrderStatus.PAID:
                    return json.dumps({
                        "success": False,
                        "message": f"Order must be PAID, current: {order.status.value}"
                    })

                # Update status to in progress
                order_manager.update_order_status(order_id, OrderStatus.IN_PROGRESS)

                # Trigger downstream system
                downstream_result = self._trigger_downstream(order)

                return json.dumps({
                    "success": True,
                    "order_id": order_id,
                    "status": "in_progress",
                    "downstream": downstream_result,
                    "message": f"Order {order_id[:8]}... fulfillment started, downstream system notified"
                })

            elif action == "complete":
                # Complete fulfillment
                if order.status != OrderStatus.IN_PROGRESS:
                    return json.dumps({
                        "success": False,
                        "message": f"Order must be IN_PROGRESS, current: {order.status.value}"
                    })

                order_manager.update_order_status(order_id, OrderStatus.COMPLETED)

                return json.dumps({
                    "success": True,
                    "order_id": order_id,
                    "status": "completed",
                    "message": f"Order {order_id[:8]}... service completed"
                })

            elif action == "deliver":
                # Deliver
                if order.status != OrderStatus.COMPLETED:
                    return json.dumps({
                        "success": False,
                        "message": f"Order must be COMPLETED, current: {order.status.value}"
                    })

                order_manager.update_order_status(order_id, OrderStatus.DELIVERED)

                return json.dumps({
                    "success": True,
                    "order_id": order_id,
                    "status": "delivered",
                    "message": f"Order {order_id[:8]}... delivered, customer notified"
                })

            else:
                return json.dumps({
                    "success": False,
                    "message": f"Unknown action: {action}"
                })

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })

    def _trigger_downstream(self, order) -> Dict[str, Any]:
        """Trigger downstream system"""
        # Can integrate G2G, U7buy APIs here
        # Currently returns simulated result

        downstream_actions = []

        # Determine downstream action by service type
        if order.service_type == ServiceType.PC_MOD:
            downstream_actions.append({
                "system": "mod_delivery",
                "action": "send_license",
                "details": "Send mod license key and download link"
            })

        elif order.service_type == ServiceType.CONSOLE_MOD:
            downstream_actions.append({
                "system": "cloud_save",
                "action": "prepare_save",
                "details": "Prepare cloud save file"
            })

        elif order.service_type in [ServiceType.LEVEL_UP, ServiceType.BADGES, ServiceType.VC_FARM]:
            downstream_actions.append({
                "system": "worker_assignment",
                "action": "assign_booster",
                "details": "Assign booster to handle order"
            })

        # Log
        return {
            "triggered": True,
            "actions": downstream_actions,
            "timestamp": datetime.now().isoformat()
        }


class ServiceInfoInput(BaseModel):
    """Service info input"""
    service_type: Optional[str] = Field(None, description="Service type (optional)")


class ServiceInfoTool(BaseTool):
    """Service info tool"""
    name: str = "get_service_info"
    description: str = "Get service information and pricing. Input service type for detailed pricing, or no input for all services list."
    args_schema: type[BaseModel] = ServiceInfoInput

    def _run(self, service_type: str = None) -> str:
        """Get service info"""
        services = {
            "level_up": {
                "name": "🏀 Player Upgrade",
                "description": "Fast player level boost",
                "prices": {
                    "Level 1-70": "$15",
                    "Level 71-85": "$20",
                    "Level 86-95": "$35",
                    "Level 96-99": "$50"
                },
                "time": "2-4 hours"
            },
            "badges": {
                "name": "🏅 Badge Unlock",
                "description": "Unlock player badges",
                "prices": {
                    "Single": "$5",
                    "10 Pack": "$25",
                    "30 Pack": "$60"
                },
                "time": "2-4 hours"
            },
            "vc_farm": {
                "name": "💰 VC Boosting",
                "description": "Fast VC with Instant & Manual options",
                "prices": {
                    "100K (Manual)": "$12.5 - 15 min ETA",
                    "300K (Manual)": "$30 - 24h ETA",
                    "500K (Instant)": "$27.5 - Instant!",
                    "500K (Manual)": "$50 - 24h ETA",
                    "1M (Manual)": "$90 - 24h ETA"
                },
                "features": ["Instant delivery available", "Play while boosting", "Safe method"],
                "notes": "Instant VC requires 250 lifetime challenges, one-time only"
            },
            "pc_mod": {
                "name": "💻 PC Mod",
                "description": "Safe and stable PC tools",
                "prices": {
                    "Basic": "$15",
                    "Pro": "$35",
                    "Lifetime": "$60"
                },
                "features": ["Unlimited VC", "Attribute Edit", "Badge Unlock"]
            },
            "console_mod": {
                "name": "🎮 Console Mod",
                "description": "Compatible with PS/Xbox/Switch",
                "prices": {
                    "PS": "$45",
                    "Xbox": "$45",
                    "Switch": "$60",
                    "All Platforms": "$100"
                }
            }
        }

        if service_type and service_type.lower() in services:
            return json.dumps({
                "success": True,
                "service": services[service_type.lower()]
            }, indent=2)
        else:
            return json.dumps({
                "success": True,
                "services": {k: v["name"] for k, v in services.items()},
                "message": "Available services: " + ", ".join([v["name"] for v in services.values()])
            })


class ReputationPriceInput(BaseModel):
    """Reputation price calculation input"""
    current_level: str = Field(description="Current level name (e.g., 'Rookie 1' or '新秀1')")
    current_percent: float = Field(description="Current progress percent (e.g., -4 means -4%)")
    target_level: str = Field(description="Target level name")
    target_percent: float = Field(description="Target progress percent (e.g., -3 means stop at 97%)")
    platform: str = Field(default="PC", description="Platform: PC/PS5/PS4/Xbox Series/Xbox One/Switch")
    urgent: bool = Field(default=False, description="Urgent order (+10%)")
    live_stream: bool = Field(default=False, description="Live stream service (+10%)")
    bulk_count: int = Field(default=1, description="Number of orders for bulk discount")


class ReputationPriceTool(BaseTool):
    """Reputation boosting price calculator tool"""
    name: str = "calculate_reputation_price"
    description: str = "Calculate NBA2K reputation leveling price. Input current/target level and progress. Returns detailed price breakdown."
    args_schema: type[BaseModel] = ReputationPriceInput

    def _run(
        self,
        current_level: str,
        current_percent: float,
        target_level: str,
        target_percent: float,
        platform: str = "PC",
        urgent: bool = False,
        live_stream: bool = False,
        bulk_count: int = 1
    ) -> str:
        """Calculate reputation boosting price"""
        if not REPUTATION_CALCULATOR_AVAILABLE:
            return json.dumps({
                "success": False,
                "message": "Reputation calculator not available"
            })

        try:
            calc = get_calculator()
            result = calc.calculate_price(
                current_level=current_level,
                current_percent=current_percent,
                target_level=target_level,
                target_percent=target_percent,
                platform=platform,
                urgent=urgent,
                live_stream=live_stream,
                bulk_count=bulk_count
            )

            return json.dumps({
                "success": True,
                "total_reputation": result.total_reputation,
                "base_price": result.base_price,
                "urgent_fee": result.urgent_fee,
                "live_stream_fee": result.live_stream_fee,
                "platform_multiplier": result.platform_multiplier,
                "bulk_discount": result.bulk_discount,
                "final_price": result.final_price,
                "level_breakdown": result.level_breakdown,
                "message": f"Price: ${result.final_price} ({result.total_reputation} reputation needed)"
            })
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"Calculation failed: {str(e)}"
            })


# Tool registry
AVAILABLE_TOOLS = [
    KnowledgeSearchTool(),
    OrderCreateTool(),
    PaymentConfirmTool(),
    OrderQueryTool(),
    FulfillmentTool(),
    ServiceInfoTool(),
    ReputationPriceTool()  # New reputation calculator tool
]


def get_tools() -> List[BaseTool]:
    """Get all available tools"""
    return AVAILABLE_TOOLS

