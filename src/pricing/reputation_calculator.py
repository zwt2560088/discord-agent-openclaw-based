"""
Reputation Leveling Price Calculator
Calculates prices for NBA2K reputation boosting service
"""
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class LevelInfo:
    """Level information"""
    id: int
    name: str
    name_zh: str
    next_level: Optional[str]
    required_value: float
    reward: str
    reward_zh: str


@dataclass
class PriceBreakdown:
    """Price breakdown details"""
    total_reputation: float
    base_price: float
    urgent_fee: float
    live_stream_fee: float
    platform_multiplier: float
    bulk_discount: float
    final_price: float
    level_breakdown: List[Dict]


class ReputationCalculator:
    """Reputation leveling price calculator"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "level_config.json"
            )

        self.config = self._load_config(config_path)
        self.levels = self._parse_levels()
        self.level_order = [lv.name for lv in self.levels]

    def _load_config(self, path: str) -> Dict:
        """Load configuration from JSON file"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _parse_levels(self) -> List[LevelInfo]:
        """Parse levels from config"""
        levels = []
        for lv in self.config['levels']:
            levels.append(LevelInfo(
                id=lv['id'],
                name=lv['name'],
                name_zh=lv['name_zh'],
                next_level=lv.get('next_level'),
                required_value=lv['required_value'],
                reward=lv.get('reward', 'None'),
                reward_zh=lv.get('reward_zh', '无')
            ))
        return levels

    def get_level_by_name(self, name: str) -> Optional[LevelInfo]:
        """Get level info by name (supports both EN and CN)"""
        for lv in self.levels:
            if lv.name == name or lv.name_zh == name:
                return lv
        return None

    def get_all_levels(self) -> List[Dict]:
        """Get all levels as dict list"""
        return [
            {
                "id": lv.id,
                "name": lv.name,
                "name_zh": lv.name_zh,
                "required_value": lv.required_value,
                "reward": lv.reward,
                "reward_zh": lv.reward_zh
            }
            for lv in self.levels
        ]

    def calculate_price(
        self,
        current_level: str,
        current_percent: float,
        target_level: str,
        target_percent: float,
        platform: str = "PC",
        urgent: bool = False,
        live_stream: bool = False,
        bulk_count: int = 1
    ) -> PriceBreakdown:
        """
        Calculate reputation boosting price

        Args:
            current_level: Current level name (e.g., "Rookie 1" or "新秀1")
            current_percent: Current progress (e.g., -4 means -4%, need to fill 4%)
            target_level: Target level name
            target_percent: Target progress (e.g., -3 means stop at 97%)
            platform: Platform type (PC, PS5, Xbox, etc.)
            urgent: Urgent order ( +10%)
            live_stream: Live stream service (+10%)
            bulk_count: Number of orders for bulk discount

        Returns:
            PriceBreakdown object with detailed pricing
        """
        # Get level info
        current_lv = self.get_level_by_name(current_level)
        target_lv = self.get_level_by_name(target_level)

        if not current_lv or not target_lv:
            raise ValueError(f"Invalid level name: {current_level} or {target_level}")

        current_idx = self.level_order.index(current_lv.name)
        target_idx = self.level_order.index(target_lv.name)

        if current_idx > target_idx:
            raise ValueError("Target level cannot be lower than current level")

        # Calculate total reputation needed
        total_rep = 0.0
        level_breakdown = []

        # Same level case
        if current_idx == target_idx:
            # Just fill the difference
            diff_percent = abs(target_percent - current_percent)
            rep_needed = current_lv.required_value * (diff_percent / 100)
            total_rep += rep_needed
            level_breakdown.append({
                "level": current_lv.name,
                "level_zh": current_lv.name_zh,
                "action": f"Fill {diff_percent:.1f}%",
                "reputation": rep_needed
            })
        else:
            # Different levels
            # 1. Fill current level remaining
            fill_percent = abs(current_percent) if current_percent < 0 else 0
            if fill_percent > 0:
                rep_needed = current_lv.required_value * (fill_percent / 100)
                total_rep += rep_needed
                level_breakdown.append({
                    "level": current_lv.name,
                    "level_zh": current_lv.name_zh,
                    "action": f"Fill remaining {fill_percent:.1f}%",
                    "reputation": rep_needed
                })

            # 2. Add full levels in between
            for i in range(current_idx, target_idx):
                from_lv = self.levels[i]
                if i + 1 < len(self.levels):
                    to_lv = self.levels[i + 1]
                    total_rep += from_lv.required_value
                    level_breakdown.append({
                        "level": from_lv.name,
                        "level_zh": from_lv.name_zh,
                        "action": f"Complete level → {to_lv.name}",
                        "reputation": from_lv.required_value
                    })

            # 3. Add target level progress
            if target_percent < 0:
                # Partial target level
                target_progress = 100 - abs(target_percent)
                rep_needed = target_lv.required_value * (target_progress / 100)
                total_rep += rep_needed
                level_breakdown.append({
                    "level": target_lv.name,
                    "level_zh": target_lv.name_zh,
                    "action": f"Reach {target_progress:.1f}%",
                    "reputation": rep_needed
                })

        # Get pricing rules
        pricing_rules = self.config['pricing_rules']
        unit_price = self.config['meta']['unit_price']

        # Base price
        base_price = total_rep * unit_price

        # Platform multiplier
        platform_mult = pricing_rules['platform_multiplier'].get(platform, 1.0)
        base_price *= platform_mult

        # Extra fees
        urgent_fee = 0.0
        live_fee = 0.0

        if urgent:
            urgent_fee = base_price * (pricing_rules['urgent_fee_percent'] / 100)
        if live_stream:
            live_fee = base_price * (pricing_rules['live_stream_fee_percent'] / 100)

        # Bulk discount
        bulk_discount = 0.0
        for threshold, discount in sorted(pricing_rules['bulk_discount'].items(), reverse=True):
            if bulk_count >= int(threshold.replace('+', '')):
                bulk_discount = discount
                break

        # Final price
        final_price = base_price + urgent_fee + live_fee
        if bulk_discount > 0:
            final_price *= bulk_discount

        return PriceBreakdown(
            total_reputation=round(total_rep, 2),
            base_price=round(base_price, 2),
            urgent_fee=round(urgent_fee, 2),
            live_stream_fee=round(live_fee, 2),
            platform_multiplier=platform_mult,
            bulk_discount=bulk_discount,
            final_price=round(final_price, 2),
            level_breakdown=level_breakdown
        )

    def update_config(self, updates: Dict) -> bool:
        """Update configuration (for admin interface)"""
        try:
            # Deep merge updates
            def deep_merge(base: dict, update: dict) -> dict:
                for key, value in update.items():
                    if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                        deep_merge(base[key], value)
                    else:
                        base[key] = value
                return base

            deep_merge(self.config, updates)

            # Save to file
            config_path = os.path.join(
                os.path.dirname(__file__), "level_config.json"
            )
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)

            # Reload
            self.config = self._load_config(config_path)
            self.levels = self._parse_levels()

            return True
        except Exception as e:
            print(f"Failed to update config: {e}")
            return False

    def add_level(self, level_data: Dict) -> bool:
        """Add a new level"""
        try:
            self.config['levels'].append(level_data)
            self.update_config({})
            return True
        except Exception as e:
            print(f"Failed to add level: {e}")
            return False

    def update_level(self, level_id: int, updates: Dict) -> bool:
        """Update an existing level"""
        try:
            for i, lv in enumerate(self.config['levels']):
                if lv['id'] == level_id:
                    self.config['levels'][i].update(updates)
                    self.update_config({})
                    return True
            return False
        except Exception as e:
            print(f"Failed to update level: {e}")
            return False

    def delete_level(self, level_id: int) -> bool:
        """Delete a level"""
        try:
            self.config['levels'] = [
                lv for lv in self.config['levels'] if lv['id'] != level_id
            ]
            self.update_config({})
            return True
        except Exception as e:
            print(f"Failed to delete level: {e}")
            return False


# Global calculator instance
_calculator = None


def get_calculator() -> ReputationCalculator:
    """Get global calculator instance"""
    global _calculator
    if _calculator is None:
        _calculator = ReputationCalculator()
    return _calculator


# CLI test
if __name__ == "__main__":
    calc = get_calculator()

    # Test case from screenshot
    result = calc.calculate_price(
        current_level="Rookie 1",
        current_percent=-4,
        target_level="Starter 1",
        target_percent=-3,
        platform="PC",
        urgent=False,
        live_stream=False
    )

    print("=" * 50)
    print("Price Calculation Result")
    print("=" * 50)
    print(f"Total Reputation: {result.total_reputation}")
    print(f"Base Price: ${result.base_price}")
    print(f"Urgent Fee: ${result.urgent_fee}")
    print(f"Live Stream Fee: ${result.live_stream_fee}")
    print(f"Final Price: ${result.final_price}")
    print("\nLevel Breakdown:")
    for item in result.level_breakdown:
        print(f"  {item['level']}: {item['action']} = {item['reputation']} rep")

