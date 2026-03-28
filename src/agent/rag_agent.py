#!/usr/bin/env python3
"""
RAG Intelligent Customer Service Agent
Industrial-grade pricing system based on LangChain + GPT-4o-mini + ChromaDB
Compatible with existing simple_bot.py Agent interface
"""

import logging
import os
import uuid
from datetime import datetime
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class PriceQuery(BaseModel):
    """Price query tool parameters"""
    service: str = Field(
        description="Service type such as level boosting, badge unlock, VC farming, squad building, reputation grinding"
    )
    current_level: Optional[str] = Field(None, description="Current level (e.g., 'Rookie 1')")
    target_level: Optional[str] = Field(None, description="Target level (e.g., 'Starter 1')")
    quantity: Optional[str] = Field(None, description="Quantity or amount (e.g., '100K VC')")
    platform: Optional[str] = Field(None, description="Platform (PC, PS5, Xbox, Nintendo Switch, etc.)")
    details: Optional[str] = Field(None, description="Additional details or special requirements")


class OrderCreate(BaseModel):
    """Order creation tool parameters"""
    service: str = Field(description="Service type")
    quantity: str = Field(description="Quantity or duration")
    price: float = Field(description="Confirmed order amount in USD")
    details: Optional[str] = Field(None, description="Order details")
    customer_id: Optional[str] = Field(None, description="Customer ID")


class RAGAgent:
    """RAG Intelligent Customer Service Agent - supports pricing, orders, and order channel creation"""

    def __init__(
        self,
        openai_api_key: str = None,
        vectorstore_path: str = "./knowledge_db",
        order_manager=None,
        reputation_calculator=None,
        pricing_service=None,
    ):
        """
        Initialize RAG Agent

        Args:
            openai_api_key: OpenAI API Key
            vectorstore_path: Path to the vector database (use './knowledge_db' for comprehensive knowledge)
            order_manager: Order manager instance (order_communication)
            reputation_calculator: Reputation level calculator instance
            pricing_service: Pricing service instance for multi-service quotes
        """
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set. Please set it in environment or pass it directly.")

        # Dependency injection
        self.order_manager = order_manager
        self.reputation_calculator = reputation_calculator

        # Initialize pricing service
        if pricing_service:
            self.pricing_service = pricing_service
        else:
            try:
                from src.pricing.pricing_service import PricingService
                self.pricing_service = PricingService(reputation_calculator=reputation_calculator)
            except Exception as e:
                logger.warning(f"Failed to initialize pricing service: {e}")
                self.pricing_service = None

        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=self.openai_api_key,
        )

        # Initialize embedding model
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=self.openai_api_key,
        )

        # Load vector database
        self.vectorstore_path = vectorstore_path
        try:
            self.vectorstore = Chroma(
                persist_directory=vectorstore_path,
                embedding_function=self.embeddings,
            )
            self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})
            logger.info(f"✅ Vector database loaded: {vectorstore_path}")
        except Exception as e:
            logger.warning(f"⚠️ Vector database load failed: {e}, continuing with limited functionality")
            self.retriever = None

        # Bind tools
        self.tools = self._get_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Session management
        self.user_histories: Dict[str, List[Dict]] = {}

    def _get_tools(self) -> List:
        """Define tool list"""

        @tool(args_schema=PriceQuery)
        def get_price(
            service: str,
            current_level: Optional[str] = None,
            target_level: Optional[str] = None,
            quantity: Optional[str] = None,
            platform: Optional[str] = None,
            details: Optional[str] = None,
        ) -> str:
            """
            Query service pricing and calculate quotes using pricing service
            """
            platform = platform or "PC"
            service_lower = service.lower()

            try:
                # 1. Handle Reputation/Tier Grinding
                if any(term in service_lower for term in ["reputation", "tier", "grade", "pro am", "rec"]):
                    if current_level and target_level and self.pricing_service:
                        quote = self.pricing_service.calculate_reputation_grinding_price(
                            current_level=current_level,
                            target_level=target_level,
                            platform=platform
                        )
                        return self._format_price_response(quote, details)
                    else:
                        return "❓ **Reputation Grinding Quote**\nPlease provide: current tier, target tier, and platform.\nExample: 'Rookie 1 to Starter 1 on PS5'"

                # 2. Handle VC Farming
                elif any(term in service_lower for term in ["vc", "virtual currency", "vc farming"]):
                    vc_amount = 0
                    if quantity:
                        # Extract VC amount from quantity
                        import re
                        match = re.search(r'(\d+)\s*[KkMm]', quantity)
                        if match:
                            num = int(match.group(1))
                            vc_amount = num * 1000 if 'M' in quantity.upper() else num * 1000

                    if vc_amount > 0 and self.pricing_service:
                        new_player = "new" in (details or "").lower()
                        quote = self.pricing_service.calculate_vc_farming_price(
                            vc_amount=vc_amount,
                            platform=platform,
                            new_player=new_player
                        )
                        return self._format_price_response(quote, details)
                    else:
                        return "❓ **VC Farming Quote**\nPlease specify the amount (e.g., '100K VC', '500K VC', '2M VC')"

                # 3. Handle Level Boosting
                elif any(term in service_lower for term in ["level", "leveling", "level boost", "level up"]):
                    if current_level and target_level and self.pricing_service:
                        try:
                            current_int = int(current_level.split()[0])
                            target_int = int(target_level.split()[0])
                            quote = self.pricing_service.calculate_level_boost_price(
                                current_level=current_int,
                                target_level=target_int,
                                platform=platform
                            )
                            return self._format_price_response(quote, details)
                        except Exception as e:
                            logger.warning(f"Level parsing failed: {e}")

                    return "❓ **Level Boosting Quote**\nPlease provide: current level (0-99) and target level.\nExample: 'Level 0 to 99' or '45 to 99'"

                # 4. Handle Badge Unlock
                elif any(term in service_lower for term in ["badge", "badges"]):
                    rarity = "common"
                    if "rare" in (details or "").lower() or "gold" in (details or "").lower():
                        rarity = "rare"
                    elif "elite" in (details or "").lower() or "hof" in (details or "").lower():
                        rarity = "elite"

                    badge_count = 1
                    if "set" in (details or "").lower() or "all" in (details or "").lower():
                        badge_count = 15

                    if self.pricing_service:
                        quote = self.pricing_service.calculate_badge_unlock_price(
                            badge_count=badge_count,
                            rarity=rarity,
                            platform=platform
                        )
                        return self._format_price_response(quote, details)

                # 5. Handle Squad Building
                elif any(term in service_lower for term in ["squad", "myteam", "team"]):
                    tier = "beginner"
                    if "competitive" in (details or "").lower():
                        tier = "competitive"
                    elif "professional" in (details or "").lower() or "pro" in (details or "").lower():
                        tier = "professional"
                    elif "elite" in (details or "").lower():
                        tier = "elite"

                    if self.pricing_service:
                        quote = self.pricing_service.calculate_squad_building_price(
                            tier=tier,
                            platform=platform
                        )
                        return self._format_price_response(quote, details)

                # 6. Handle Coaching
                elif any(term in service_lower for term in ["coach", "coaching", "training", "lesson"]):
                    hours = 1
                    if quantity and "hour" in quantity.lower():
                        import re
                        match = re.search(r'(\d+)', quantity)
                        if match:
                            hours = int(match.group(1))

                    if self.pricing_service:
                        quote = self.pricing_service.calculate_coaching_price(
                            hours=hours,
                            specialization=details or ""
                        )
                        return self._format_price_response(quote, details)

                # 7. Fallback: Search knowledge base
                else:
                    if self.retriever:
                        docs = self.retriever.invoke(f"{service} price quote")
                        if docs:
                            return f"**{service}** Pricing Information:\n\n{docs[0].page_content[:500]}...\n\nFor exact pricing, please provide more details."

                    return f"❓ I can help with pricing for:\n• Level Boosting\n• Badge Unlock\n• VC Farming\n• Reputation Grinding\n• Squad Building\n• Coaching\n\nWhat service are you interested in?"

            except Exception as e:
                logger.error(f"Price calculation error: {e}", exc_info=True)
                return f"❌ I encountered an error calculating the quote. Please try again or contact support."

        # Store reference to self for use in nested function
        agent_self = self

        def _format_price_response(quote, details):
            """Format price quote for display"""
            response = f"**{quote.service_type}** 💰\n\n"
            response += f"**Quote Breakdown:**\n"
            response += f"• Base Price: ${quote.base_price:.2f}\n"
            response += f"• Platform ({quote.platform}): ${quote.platform_price:.2f}\n"

            if quote.rush_fee > 0:
                response += f"• Rush Fee (+20%): ${quote.rush_fee:.2f}\n"
            if quote.additional_fees > 0:
                response += f"• Additional Fees: ${quote.additional_fees:.2f}\n"
            if quote.discount > 0:
                response += f"• Discount: -${quote.discount:.2f}\n"

            response += f"\n**Final Price: ${quote.final_price:.2f}**\n"
            response += f"⏱️  Estimated Time: {quote.estimated_time}\n"

            if quote.notes:
                response += f"📝 Notes: {quote.notes}\n"

            response += f"\n✅ Reply with 'order' to place this order"
            return response

        @tool(args_schema=OrderCreate)
        def create_order(
            service: str,
            quantity: str,
            price: float,
            details: Optional[str] = None,
            customer_id: Optional[str] = None,
        ) -> str:
            """
            Create order and create order channel through order_manager
            """
            order_id = str(uuid.uuid4())[:8].upper()

            # Create order channel using order_manager if available
            channel_id = None
            if self.order_manager:
                try:
                    channel_id = self.order_manager.create_order(
                        order_id=order_id,
                        customer_id=customer_id,
                        service=service,
                        quantity=quantity,
                        price=price,
                    )
                    logger.info(f"Order channel created: {channel_id}")
                except Exception as e:
                    logger.warning(f"Order channel creation failed: {e}")

            order_info = {
                "success": True,
                "order_id": order_id,
                "service": service,
                "quantity": quantity,
                "price": price,
                "currency": "USD",
                "details": details,
                "channel_id": channel_id,
                "created_at": datetime.now().isoformat(),
                "status": "PENDING",
            }

            response = f"""
✅ **Order Created Successfully!**

📋 **Order Details:**
• Order ID: `{order_id}`
• Service: {service}
• Quantity: {quantity}
• Price: **${price:.2f}**
• Status: Pending

{'📌 Check your order channel for updates' if channel_id else '⏳ Our team will contact you shortly'}
"""
            return response

        return [get_price, create_order]

    def think_and_act(
        self, query: str, customer_id: str = None, **kwargs
    ) -> str:
        """
        Main entry point for processing user queries
        Compatible with existing Agent interface, returns plain text

        Args:
            query: User message
            customer_id: Customer ID
            **kwargs: Additional parameters

        Returns:
            Agent response text
        """
        try:
            # Retrieve context from knowledge base
            context = ""
            if self.retriever:
                try:
                    docs = self.retriever.invoke(query)
                    context = "\n\n".join(doc.page_content for doc in docs)
                except Exception as e:
                    logger.warning(f"Retrieval failed: {e}")

            # Build prompt
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a professional NBA 2K26 gaming service customer support assistant. You have access to the following knowledge base:

{context}

Based on the user's message, you should:
1. Determine the user's intent (price inquiry, order placement, consultation, etc.)
2. If user asks about pricing, call the `get_price` tool with all relevant parameters
3. If user wants to place an order or says "confirm", "yes", or "order", call the `create_order` tool
4. For other cases, provide helpful suggestions

**Important Guidelines:**
- For reputation tier system: Always extract current_level and target_level if mentioned (e.g., "Rookie 1 to Starter 1")
- For VC farming: Include VC amount in quantity field (e.g., "100K VC")
- Always include platform information (PC, PS5, Xbox, etc.), default to PC
- Keep responses concise, friendly, and professional
- Use emojis and **bold text** for readability
- Always include $ symbol and decimal point for prices
- If unclear, ask for more details before providing a quote"""),
                ("human", "{input}")
            ])

            messages = prompt.invoke({
                "context": context,
                "input": query
            })

            # Call LLM with tool binding
            response = self.llm_with_tools.invoke(messages)

            # Handle tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_call = response.tool_calls[0]
                tool_name = tool_call["name"]
                args = tool_call["args"]

                logger.info(f"🔧 Tool called: {tool_name} with args: {args}")

                if tool_name == "get_price":
                    return self._call_get_price(**args)
                elif tool_name == "create_order":
                    # Inject customer_id when creating order
                    if "customer_id" not in args or not args["customer_id"]:
                        args["customer_id"] = customer_id
                    return self._call_create_order(**args)

            # No tool call, return LLM response directly
            return response.content if hasattr(response, "content") else str(response)

        except Exception as e:
            logger.error(f"❌ Agent processing failed: {e}", exc_info=True)
            return "❌ Sorry, an error occurred while processing your request. Please try again or contact our support team."

    def _call_get_price(self, service: str, **kwargs) -> str:
        """Internal method: call get_price tool"""
        for tool_obj in self.tools:
            if tool_obj.name == "get_price":
                return tool_obj.func(service=service, **kwargs)
        return "Price query tool failed"

    def _call_create_order(self, service: str, quantity: str, price: float, **kwargs) -> str:
        """Internal method: call create_order tool"""
        for tool_obj in self.tools:
            if tool_obj.name == "create_order":
                return tool_obj.func(
                    service=service,
                    quantity=quantity,
                    price=price,
                    **kwargs
                )
        return "Order creation tool failed"

    def add_history(self, customer_id: str, role: str, content: str):
        """Add conversation history"""
        if customer_id not in self.user_histories:
            self.user_histories[customer_id] = []
        self.user_histories[customer_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_history(self, customer_id: str, limit: int = 10) -> List[Dict]:
        """Get conversation history"""
        if customer_id not in self.user_histories:
            return []
        return self.user_histories[customer_id][-limit:]

    def clear_history(self, customer_id: str):
        """Clear conversation history"""
        if customer_id in self.user_histories:
            del self.user_histories[customer_id]

