#!/usr/bin/env python3
"""
Multi-Service Pricing Service
Handles pricing calculations for all service types with platform multipliers,
rush fees, and special offers
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Available service types"""
    LEVEL_BOOSTING = "level_boosting"
    BADGE_UNLOCK = "badge_unlock"
    VC_FARMING = "vc_farming"
    REPUTATION_GRINDING = "reputation_grinding"
    SQUAD_BUILDING = "squad_building"
    COACHING = "coaching"
    PC_MODS = "pc_mods"
    SECURITY_AUDIT = "security_audit"


class PlatformMultiplier(Enum):
    """Platform pricing multipliers"""
    PC = 1.0
    PS4 = 1.05
    PS5 = 1.1
    XBOX_ONE = 1.05
    XBOX_SERIES_X = 1.1
    SWITCH = 1.15


@dataclass
class PriceQuote:
    """Price quote response"""
    service_type: str
    base_price: float
    platform: str
    platform_multiplier: float
    platform_price: float
    rush_fee: float = 0.0
    additional_fees: float = 0.0
    discount: float = 0.0
    final_price: float = 0.0
    estimated_time: str = ""
    notes: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "service": self.service_type,
            "base_price": f"${self.base_price:.2f}",
            "platform": self.platform,
            "platform_multiplier": f"{self.platform_multiplier:.1%}",
            "platform_price": f"${self.platform_price:.2f}",
            "rush_fee": f"${self.rush_fee:.2f}" if self.rush_fee > 0 else "None",
            "additional_fees": f"${self.additional_fees:.2f}" if self.additional_fees > 0 else "None",
            "discount": f"-${self.discount:.2f}" if self.discount > 0 else "None",
            "final_price": f"${self.final_price:.2f}",
            "estimated_time": self.estimated_time,
            "notes": self.notes
        }


class PricingService:
    """Comprehensive pricing service for all NBA 2K26 services"""

    # Base prices for each service type
    BASE_PRICES = {
        "level_0_to_25": 15,
        "level_0_to_50": 25,
        "level_0_to_75": 35,
        "level_0_to_99": 50,
        "level_per_10": 8,

        "badge_common": 5,
        "badge_rare": 15,
        "badge_elite": 30,
        "badge_set_common": 55,
        "badge_set_rare": 125,
        "badge_set_elite": 300,

        "vc_100k": 12.50,
        "vc_300k": 30.00,
        "vc_500k": 45.00,
        "vc_750k": 60.00,
        "vc_1m": 75.00,
        "vc_2m": 140.00,

        "tier_per_level": 12,
        "tier_rush_base": 20,

        "squad_beginner": 25,
        "squad_competitive": 50,
        "squad_professional": 100,
        "squad_elite": 200,

        "coaching_1hour": 20,
        "coaching_boot_camp": 80,

        "pc_mod_basic": 5,
        "pc_mod_bundle": 50,

        "security_audit": 30,
    }

    # Estimated completion times
    COMPLETION_TIMES = {
        "level_0_to_25": "8-12 hours",
        "level_0_to_50": "16-20 hours",
        "level_0_to_75": "24-30 hours",
        "level_0_to_99": "40-50 hours",

        "badge_common": "2-4 hours",
        "badge_set": "6-12 hours",

        "vc_farming": "24-48 hours",

        "tier_1": "2-3 days",
        "tier_2_3": "3-5 days",
        "tier_4_plus": "5-7 days",

        "squad_build": "2-4 hours",
        "coaching_session": "1 hour (scheduled)",
    }

    def __init__(self, reputation_calculator=None):
        """Initialize pricing service with optional reputation calculator"""
        self.reputation_calculator = reputation_calculator

    def get_platform_multiplier(self, platform: str) -> float:
        """Get platform pricing multiplier"""
        platform = platform.upper().replace(" ", "_")

        multiplier_map = {
            "PC": PlatformMultiplier.PC.value,
            "PS4": PlatformMultiplier.PS4.value,
            "PS5": PlatformMultiplier.PS5.value,
            "PLAYSTATION_4": PlatformMultiplier.PS4.value,
            "PLAYSTATION_5": PlatformMultiplier.PS5.value,
            "XBOX_ONE": PlatformMultiplier.XBOX_ONE.value,
            "XBOX_SERIES_X": PlatformMultiplier.XBOX_SERIES_X.value,
            "XBOX_SERIES_X_S": PlatformMultiplier.XBOX_SERIES_X.value,
            "SWITCH": PlatformMultiplier.SWITCH.value,
            "NINTENDO_SWITCH": PlatformMultiplier.SWITCH.value,
        }

        return multiplier_map.get(platform, 1.0)

    def calculate_level_boost_price(
        self,
        current_level: int,
        target_level: int,
        platform: str = "PC",
        rush: bool = False,
        live_stream: bool = False
    ) -> PriceQuote:
        """Calculate level boosting price"""

        # Determine base price
        level_diff = target_level - current_level

        if current_level == 0:
            if target_level <= 25:
                base_price = self.BASE_PRICES["level_0_to_25"]
            elif target_level <= 50:
                base_price = self.BASE_PRICES["level_0_to_50"]
            elif target_level <= 75:
                base_price = self.BASE_PRICES["level_0_to_75"]
            else:
                base_price = self.BASE_PRICES["level_0_to_99"]
        else:
            base_price = (level_diff / 10) * self.BASE_PRICES["level_per_10"]

        return self._apply_modifiers(
            service_type="Level Boosting",
            base_price=base_price,
            platform=platform,
            rush=rush,
            live_stream=live_stream,
            estimated_time=f"{level_diff * 0.5:.0f}-{level_diff * 0.75:.0f} hours"
        )

    def calculate_badge_unlock_price(
        self,
        badge_count: int = 1,
        rarity: str = "common",
        platform: str = "PC",
        rush: bool = False
    ) -> PriceQuote:
        """Calculate badge unlock price"""

        # Determine base price
        if badge_count == 1:
            if rarity.lower() == "common":
                base_price = self.BASE_PRICES["badge_common"]
            elif rarity.lower() == "rare":
                base_price = self.BASE_PRICES["badge_rare"]
            else:
                base_price = self.BASE_PRICES["badge_elite"]
        else:
            if rarity.lower() == "common":
                base_price = self.BASE_PRICES["badge_set_common"]
            elif rarity.lower() == "rare":
                base_price = self.BASE_PRICES["badge_set_rare"]
            else:
                base_price = self.BASE_PRICES["badge_set_elite"]

        return self._apply_modifiers(
            service_type="Badge Unlock",
            base_price=base_price,
            platform=platform,
            rush=rush,
            estimated_time=self.COMPLETION_TIMES.get("badge_common", "6-12 hours")
        )

    def calculate_vc_farming_price(
        self,
        vc_amount: int,
        platform: str = "PC",
        rush: bool = False,
        new_player: bool = False
    ) -> PriceQuote:
        """Calculate VC farming price"""

        # Find matching base price
        base_price = 0
        if vc_amount >= 2000:
            base_price = self.BASE_PRICES["vc_2m"]
        elif vc_amount >= 1000:
            base_price = self.BASE_PRICES["vc_1m"]
        elif vc_amount >= 750:
            base_price = self.BASE_PRICES["vc_750k"]
        elif vc_amount >= 500:
            base_price = self.BASE_PRICES["vc_500k"]
        elif vc_amount >= 300:
            base_price = self.BASE_PRICES["vc_300k"]
        elif vc_amount >= 100:
            base_price = self.BASE_PRICES["vc_100k"]
        else:
            base_price = (vc_amount / 100) * self.BASE_PRICES["vc_100k"]

        quote = self._apply_modifiers(
            service_type="VC Farming",
            base_price=base_price,
            platform=platform,
            rush=rush,
            estimated_time=self.COMPLETION_TIMES.get("vc_farming", "24-48 hours")
        )

        # Apply new player discount if eligible
        if new_player:
            discount = quote.final_price * 0.15  # 15% off
            quote.discount = discount
            quote.final_price -= discount
            quote.notes = "New Player Bonus (15% off applied)"

        return quote

    def calculate_reputation_grinding_price(
        self,
        current_tier: str,
        target_tier: str,
        platform: str = "PC",
        rush: bool = False,
        live_stream: bool = False
    ) -> PriceQuote:
        """Calculate reputation tier grinding price"""

        # If reputation calculator is available, use it
        if self.reputation_calculator:
            try:
                result = self.reputation_calculator.calculate_price(
                    current_level=current_tier,
                    target_level=target_tier,
                    platform=platform
                )
                return PriceQuote(
                    service_type="Reputation Grinding",
                    base_price=result.get("base_price", 0),
                    platform=platform,
                    platform_multiplier=self.get_platform_multiplier(platform),
                    platform_price=result.get("final_price", 0),
                    final_price=result.get("final_price", 0),
                    estimated_time=result.get("estimated_time", "3-7 days"),
                    notes="Using integrated reputation calculator"
                )
            except Exception as e:
                logger.warning(f"Reputation calculator failed: {e}, using fallback pricing")

        # Fallback pricing
        tier_map = {
            "rookie": 1, "pro": 2, "star": 3, "elite": 4,
            "rookie_1": 1, "pro_1": 2, "star_1": 3, "elite_1": 4
        }

        current_num = tier_map.get(current_tier.lower().replace(" ", "_"), 1)
        target_num = tier_map.get(target_tier.lower().replace(" ", "_"), 4)
        tier_diff = max(target_num - current_num, 1)

        base_price = tier_diff * self.BASE_PRICES["tier_per_level"]

        return self._apply_modifiers(
            service_type="Reputation Grinding",
            base_price=base_price,
            platform=platform,
            rush=rush,
            live_stream=live_stream,
            estimated_time=f"{tier_diff * 2}-{tier_diff * 3} days"
        )

    def calculate_squad_building_price(
        self,
        tier: str = "beginner",
        platform: str = "PC"
    ) -> PriceQuote:
        """Calculate squad building price"""

        tier_price_map = {
            "beginner": self.BASE_PRICES["squad_beginner"],
            "competitive": self.BASE_PRICES["squad_competitive"],
            "professional": self.BASE_PRICES["squad_professional"],
            "elite": self.BASE_PRICES["squad_elite"],
        }

        base_price = tier_price_map.get(tier.lower(), self.BASE_PRICES["squad_beginner"])

        return self._apply_modifiers(
            service_type="Squad Building",
            base_price=base_price,
            platform=platform,
            estimated_time=self.COMPLETION_TIMES.get("squad_build", "2-4 hours")
        )

    def calculate_coaching_price(
        self,
        hours: int = 1,
        specialization: str = ""
    ) -> PriceQuote:
        """Calculate coaching session price"""

        base_price = self.BASE_PRICES["coaching_1hour"] * hours
        additional_fees = 0

        if specialization.lower() in ["shooting", "ball_handling", "defense"]:
            additional_fees = 5
        elif specialization.lower() == "pro_level":
            additional_fees = 10

        return PriceQuote(
            service_type="Coaching Session",
            base_price=base_price,
            platform="All",
            platform_multiplier=1.0,
            platform_price=base_price,
            additional_fees=additional_fees,
            final_price=base_price + additional_fees,
            estimated_time=f"{hours} hour(s) (scheduled)",
            notes=f"Specialization: {specialization}" if specialization else ""
        )

    def _apply_modifiers(
        self,
        service_type: str,
        base_price: float,
        platform: str = "PC",
        rush: bool = False,
        live_stream: bool = False,
        estimated_time: str = ""
    ) -> PriceQuote:
        """Apply modifiers (platform, rush, live stream) to base price"""

        # Platform multiplier
        platform_mult = self.get_platform_multiplier(platform)
        platform_price = base_price * platform_mult

        # Rush fee (20% additional)
        rush_fee = platform_price * 0.20 if rush else 0

        # Live stream fee ($5-10)
        live_stream_fee = 10 if live_stream else 0

        # Final price
        final_price = platform_price + rush_fee + live_stream_fee

        notes = []
        if rush:
            notes.append("Rush service (+20%)")
        if live_stream:
            notes.append("Live stream coverage (+$10)")

        return PriceQuote(
            service_type=service_type,
            base_price=base_price,
            platform=platform,
            platform_multiplier=platform_mult,
            platform_price=round(platform_price, 2),
            rush_fee=round(rush_fee, 2),
            additional_fees=round(live_stream_fee, 2),
            final_price=round(final_price, 2),
            estimated_time=estimated_time,
            notes=" | ".join(notes) if notes else ""
        )

    def apply_discount(self, quote: PriceQuote, discount_percent: float = 0) -> PriceQuote:
        """Apply discount to quote"""
        if discount_percent > 0:
            discount_amount = quote.final_price * (discount_percent / 100)
            quote.discount = round(discount_amount, 2)
            quote.final_price = round(quote.final_price - discount_amount, 2)
        return quote


# Example usage
if __name__ == "__main__":
    service = PricingService()

    # Test level boosting
    quote = service.calculate_level_boost_price(0, 99, "PS5", rush=True)
    print(f"Level 0-99 on PS5 with rush: ${quote.final_price:.2f}")
    print(f"Details: {quote.to_dict()}\n")

    # Test VC farming
    quote = service.calculate_vc_farming_price(500, "PC", new_player=True)
    print(f"500K VC with new player discount: ${quote.final_price:.2f}")
    print(f"Details: {quote.to_dict()}\n")

    # Test badge unlock
    quote = service.calculate_badge_unlock_price(15, "common", "Xbox Series X", rush=True)
    print(f"15 common badges on Xbox with rush: ${quote.final_price:.2f}")
    print(f"Details: {quote.to_dict()}\n")

