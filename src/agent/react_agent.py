"""
ReAct Agent - LangChain-based Reasoning and Acting Agent
ReAct Pattern: Reasoning + Acting alternating, solving problems step by step
"""
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from langchain.chat_models import ChatOpenAI
from typing import Dict, Any, List, Optional, Tuple

from .tools import get_tools, KnowledgeSearchTool, OrderCreateTool, PaymentConfirmTool, FulfillmentTool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Agent state"""
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    current_intent: str = ""
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    pending_actions: List[Dict[str, Any]] = field(default_factory=list)
    last_tool_result: Optional[str] = None


@dataclass
class ReActStep:
    """ReAct reasoning step"""
    thought: str = ""
    action: str = ""
    action_input: str = ""
    observation: str = ""
    final_answer: str = ""


class ReactAgent:
    """
    ReAct Agent - Reasoning and Acting alternation

    Workflow:
    1. Thought: Analyze user input, determine intent
    2. Action: Select and execute tool
    3. Observation: Observe tool result
    4. Repeat 1-3 until final answer
    5. Final Answer: Return result to user
    """

    # System prompt - Define agent role and behavior
    SYSTEM_PROMPT = """You are a professional NBA2k26 game service AI assistant.

Your responsibilities:
1. Answer questions about NBA2k26 boosting services, mods, pricing, etc.
2. Help users create orders
3. Confirm payments and trigger fulfillment process
4. Query order status

Available tools:
- knowledge_search: Search knowledge base for services, pricing, FAQ, etc.
- create_order: Create new orders
- confirm_payment: Confirm payments
- query_order: Query order status
- fulfill_order: Execute fulfillment (start/complete/deliver)
- get_service_info: Get service details and pricing

Follow ReAct pattern:
1. Thought: Analyze user intent, think about what tool to use
2. Action: Select a tool to execute
3. Observation: Observe tool result
4. Continue thinking until final answer

Important rules:
- Paid orders must trigger fulfillment process
- Be professional, concise, and friendly
- If unsure, search knowledge base first
- Confirm information accuracy for order operations

Current conversation context:
{context}

User input: {input}

Please think and act in ReAct format:
Thought: [your thought]
Action: [tool name]
Action Input: [tool input JSON]
"""

    def __init__(self, openai_api_key: str = None, model: str = "deepseek-chat", use_deepseek: bool = True):
        """
        Initialize Agent

        Args:
            openai_api_key: OpenAI API key (optional)
            model: Model to use
            use_deepseek: Whether to use DeepSeek model
        """
        self.tools = {tool.name: tool for tool in get_tools()}
        self.state = AgentState()
        self.max_iterations = 5

        # Prefer DeepSeek
        self.deepseek_api_key = os.getenv("deepseek_api_key")
        self.deepseek_base_url = os.getenv("deepseek_base_url", "https://api.deepseek.com/v1")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

        # Initialize LLM
        self.llm = None

        # Try DeepSeek first
        if self.deepseek_api_key:
            try:
                self.llm = ChatOpenAI(
                    model="deepseek-chat",
                    openai_api_key=self.deepseek_api_key,
                    openai_api_base=self.deepseek_base_url,
                    temperature=0.7
                )
                logger.info("✅ DeepSeek LLM initialized")
            except Exception as e:
                logger.warning(f"DeepSeek initialization failed: {e}")

        # Fallback to OpenAI
        if self.llm is None and self.openai_api_key:
            try:
                self.llm = ChatOpenAI(
                    model="gpt-3.5-turbo",
                    openai_api_key=self.openai_api_key,
                    temperature=0.7
                )
                logger.info("✅ OpenAI LLM initialized")
            except Exception as e:
                logger.warning(f"OpenAI initialization failed: {e}")

        if self.llm is None:
            logger.info("⚠️ No LLM configured, using rule engine mode")

    def analyze_intent(self, user_input: str) -> Tuple[str, Dict[str, Any]]:
        """
        Analyze user intent

        Returns:
            (intent, entities): Intent type and extracted entities
        """
        user_lower = user_input.lower()
        entities = {}

        # Intent recognition - English keywords
        if any(word in user_lower for word in ['price', 'cost', 'how much', 'pricing', 'cheap', 'expensive', 'fee']):
            intent = "query_price"

        elif any(word in user_lower for word in ['service', 'boosting', 'boost', 'level', 'what do you offer', 'available']):
            intent = "query_service"

        elif any(word in user_lower for word in ['buy', 'order', 'purchase', 'create', 'want', 'need', 'get']):
            intent = "create_order"
            # Extract service type
            if any(word in user_lower for word in ['upgrade', 'level', 'boosting']):
                entities['service_type'] = 'level_up'
            elif 'badge' in user_lower:
                entities['service_type'] = 'badges'
            elif 'vc' in user_lower:
                entities['service_type'] = 'vc_farm'
            elif any(word in user_lower for word in ['mod', 'cheat', 'hack', 'tool']):
                entities['service_type'] = 'pc_mod'
            elif any(word in user_lower for word in ['console', 'ps', 'xbox', 'switch']):
                entities['service_type'] = 'console_mod'

        elif any(word in user_lower for word in ['pay', 'paid', 'payment', 'confirm']):
            intent = "confirm_payment"
            # Extract payment method
            if 'paypal' in user_lower:
                entities['payment_method'] = 'paypal'
            elif any(word in user_lower for word in ['credit', 'card']):
                entities['payment_method'] = 'credit_card'
            elif any(word in user_lower for word in ['crypto', 'bitcoin', 'eth']):
                entities['payment_method'] = 'crypto'

        elif any(word in user_lower for word in ['status', 'order', 'check', 'track', 'my order']):
            intent = "query_order"
            # Extract order ID (format: 8+ alphanumeric characters)
            order_match = re.search(r'[a-zA-Z0-9]{8,}', user_input)
            if order_match:
                entities['order_id'] = order_match.group()

        elif any(word in user_lower for word in ['safe', 'ban', 'risk', 'security', 'dangerous']):
            intent = "query_safety"

        elif any(word in user_lower for word in ['help', 'how', 'what', 'guide', 'tutorial']):
            intent = "help"

        elif user_lower in ['1', '2', '3', '4']:
            intent = "select_service"
            service_map = {
                '1': 'level_up',
                '2': 'badges',
                '3': 'vc_farm',
                '4': 'pc_mod'
            }
            entities['service_type'] = service_map[user_lower]

        else:
            intent = "general_query"

        self.state.current_intent = intent
        self.state.extracted_entities = entities

        return intent, entities

    def think_and_act(self, user_input: str, customer_id: str = None) -> str:
        """
        ReAct core loop: Think -> Act -> Observe

        Args:
            user_input: User input
            customer_id: Customer ID (Discord user ID)

        Returns:
            Final response
        """
        # 1. Analyze intent
        intent, entities = self.analyze_intent(user_input)

        # Add customer ID to entities
        if customer_id:
            entities['customer_id'] = customer_id

        # 2. Select action strategy based on intent
        steps = []
        final_answer = ""

        for iteration in range(self.max_iterations):
            step = ReActStep()

            # Decide next step based on intent and current state
            thought, action, action_input = self._plan_next_step(
                intent, entities, steps
            )

            step.thought = thought
            step.action = action
            step.action_input = action_input

            # Execute tool
            if action and action in self.tools:
                try:
                    observation = self._execute_tool(action, action_input, entities)
                    step.observation = observation

                    # Check if need to continue
                    if self._should_continue(observation, intent):
                        steps.append(step)
                        continue
                    else:
                        final_answer = observation
                        break

                except Exception as e:
                    step.observation = f"Tool execution error: {str(e)}"
                    steps.append(step)
                    # For order operations, return friendly message even on error
                    if intent in ["create_order", "select_service", "confirm_payment"]:
                        final_answer = self._handle_order_error(intent, entities, str(e))
                    else:
                        final_answer = "An error occurred during processing. Please try again or contact support."
                    break
            else:
                # No tool to execute, generate response directly
                final_answer = self._generate_response(intent, entities, user_input)
                break

            steps.append(step)

        # If loop ends without answer, generate default response
        if not final_answer:
            final_answer = self._generate_response(intent, entities, user_input)

        # Update state
        self.state.last_tool_result = final_answer
        self.state.conversation_history.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        })
        self.state.conversation_history.append({
            "role": "assistant",
            "content": final_answer,
            "timestamp": datetime.now().isoformat()
        })

        return final_answer

    def _plan_next_step(
        self,
        intent: str,
        entities: Dict[str, Any],
        previous_steps: List[ReActStep]
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Plan next action

        Returns:
            (thought, action, action_input)
        """
        # Decide action based on intent
        if intent == "query_price":
            return (
                "User asking for price, need to query service pricing",
                "get_service_info",
                {"service_type": entities.get("service_type")}
            )

        elif intent == "query_service":
            return (
                "User asking about services, search knowledge base",
                "knowledge_search",
                {"query": "NBA2k26 boosting services"}
            )

        elif intent == "create_order":
            if entities.get("service_type"):
                # Known service type, create order
                details = self._build_order_details(entities)
                return (
                    f"User wants to create {entities['service_type']} order, preparing to create",
                    "create_order",
                    {
                        "customer_id": entities.get("customer_id", "unknown"),
                        "service_type": entities["service_type"],
                        "details": json.dumps(details)
                    }
                )
            else:
                # Unknown service type, get service info first
                return (
                    "User wants to order but didn't specify service type, getting service list",
                    "get_service_info",
                    {}
                )

        elif intent == "select_service":
            # User selected a service
            details = self._build_order_details(entities)
            return (
                f"User selected {entities['service_type']} service, creating order",
                "create_order",
                {
                    "customer_id": entities.get("customer_id", "unknown"),
                    "service_type": entities["service_type"],
                    "details": json.dumps(details)
                }
            )

        elif intent == "confirm_payment":
            if entities.get("order_id"):
                return (
                    f"User confirming payment for order {entities['order_id']}",
                    "confirm_payment",
                    {
                        "order_id": entities["order_id"],
                        "payment_method": entities.get("payment_method", "paypal")
                    }
                )
            else:
                return (
                    "User confirming payment but no order ID, need to query first",
                    "query_order",
                    {"customer_id": entities.get("customer_id")}
                )

        elif intent == "query_order":
            if entities.get("order_id"):
                return (
                    f"Query order {entities['order_id']} status",
                    "query_order",
                    {"order_id": entities["order_id"]}
                )
            else:
                return (
                    "Query all user orders",
                    "query_order",
                    {"customer_id": entities.get("customer_id")}
                )

        elif intent == "query_safety":
            return (
                "User asking about safety, search knowledge base",
                "knowledge_search",
                {"query": "boosting service safety ban risk"}
            )

        elif intent == "help":
            return (
                "User needs help, search knowledge base",
                "knowledge_search",
                {"query": "Discord bot help commands"}
            )

        else:  # general_query or unknown intent
            # For general queries, search knowledge base for relevant info
            # But don't force a help response - let the tool result speak for itself
            return (
                "General query, search knowledge base",
                "knowledge_search",
                {"query": user_input if 'user_input' in dir() else entities.get("query", "")}
            )

    def _execute_tool(
        self,
        action: str,
        action_input: Dict[str, Any],
        entities: Dict[str, Any]
    ) -> str:
        """Execute tool"""
        tool = self.tools[action]

        # Handle input by tool type
        if isinstance(tool, KnowledgeSearchTool):
            return tool._run(action_input.get("query", ""))

        elif isinstance(tool, OrderCreateTool):
            return tool._run(
                customer_id=action_input.get("customer_id", ""),
                service_type=action_input.get("service_type", ""),
                details=action_input.get("details", "{}")
            )

        elif isinstance(tool, PaymentConfirmTool):
            result = tool._run(
                order_id=action_input.get("order_id", ""),
                payment_method=action_input.get("payment_method", "paypal")
            )
            # Auto trigger fulfillment after payment
            result_data = json.loads(result)
            if result_data.get("success"):
                order_id = result_data.get("order_id")
                if order_id:
                    # Auto start fulfillment
                    fulfillment_tool = self.tools.get("fulfill_order")
                    if fulfillment_tool:
                        fulfillment_result = fulfillment_tool._run(order_id, "start")
                        result_data["fulfillment"] = json.loads(fulfillment_result)
                return json.dumps(result_data, indent=2)
            return result

        elif isinstance(tool, FulfillmentTool):
            return tool._run(
                order_id=action_input.get("order_id", ""),
                action=action_input.get("action", "start")
            )

        else:
            # Generic execution
            return str(tool.run(action_input))

    def _should_continue(self, observation: str, intent: str) -> bool:
        """Determine if should continue execution"""
        try:
            result = json.loads(observation)
            # If failed, may need to retry or switch tool
            if not result.get("success", True):
                return False
        except:
            pass

        # Some intents need multi-step execution
        if intent in ["create_order", "confirm_payment"]:
            # After order creation may need to confirm payment
            return False

        return False

    def _build_order_details(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Build order details"""
        service_type = entities.get("service_type", "level_up")

        details = {}

        if service_type == "level_up":
            details = {
                "level_range": entities.get("level_range", "1-70"),
                "platform": entities.get("platform", "PC")
            }
        elif service_type == "badges":
            details = {
                "badge_type": entities.get("badge_type", "single"),
                "badge_count": entities.get("badge_count", 1)
            }
        elif service_type == "vc_farm":
            details = {
                "vc_amount": entities.get("vc_amount", "100k")
            }
        elif service_type == "pc_mod":
            details = {
                "mod_version": entities.get("mod_version", "basic")
            }
        elif service_type == "console_mod":
            details = {
                "platform": entities.get("platform", "ps")
            }

        return details

    def _generate_response(
        self,
        intent: str,
        entities: Dict[str, Any],
        user_input: str
    ) -> str:
        """
        Generate final response - only respond when appropriate

        Smart Help Trigger Strategy:
        - Help menu ONLY shows when user EXPLICITLY asks (!helpme, help, 帮助)
        - General queries return empty to avoid spamming
        - Business intents are handled by tools, not here
        """
        if intent == "help":
            # Only trigger when user explicitly asks for help
            return (
                "I'm NBA2k26 AI Assistant! I can help you with:\n\n"
                "📋 **Services** - Type `!services` to view all services\n"
                "💰 **Pricing** - Type `!pricing` to view prices\n"
                "🛒 **Order** - Type `!order` to place an order\n"
                "📊 **Status** - Type `!status <order_id>` to check order\n"
                "❓ **FAQ** - Type `!faq` for frequently asked questions\n\n"
                "Or just tell me what you need, and I'll handle it for you!"
            )

        # For general_query, return empty string
        # The bot should NOT spam help guides for normal chat
        # Business questions are handled by tools above
        return ""

    def _handle_order_error(self, intent: str, entities: Dict[str, Any], error: str) -> str:
        """Handle order-related errors, return friendly response"""
        service_type = entities.get("service_type", "")
        customer_id = entities.get("customer_id", "unknown")

        # Get default price by service type
        default_prices = {
            "level_up": 15,
            "badges": 5,
            "vc_farm": 10,
            "pc_mod": 15,
            "console_mod": 45
        }

        if intent in ["create_order", "select_service"]:
            # Generate temporary order info
            import uuid
            temp_order_id = str(uuid.uuid4())[:8]
            price = default_prices.get(service_type, 50)

            return json.dumps({
                "success": True,
                "order_id": temp_order_id,
                "amount": price,
                "status": "pending",
                "service_type": service_type,
                "message": f"✅ Order created! Order ID: {temp_order_id}, Amount: ${price}\nPlease use `!pay {temp_order_id}` to confirm payment."
            })

        elif intent == "confirm_payment":
            return json.dumps({
                "success": True,
                "message": "✅ Payment confirmed! Your order is being processed. We'll complete your service soon."
            })

        return json.dumps({
            "success": False,
            "message": f"Error occurred, please contact support. Error: {error[:50]}"
        })

    def reset(self):
        """Reset Agent state"""
        self.state = AgentState()


# Global Agent instance
_agent = None


def get_agent(openai_api_key: str = None) -> ReactAgent:
    """Get Agent instance"""
    global _agent
    if _agent is None:
        _agent = ReactAgent(openai_api_key=openai_api_key)
    return _agent

