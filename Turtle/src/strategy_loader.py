import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Any, Optional


@dataclass
class StrategyConfig:
    name: str
    description: str
    config: Dict[str, Any]
    file_path: str


class StrategyLoader:
    """Loads and parses trading strategy files from the strategies directory"""
    
    def __init__(self, strategies_dir: str = "../strategies"):
        self.strategies_dir = Path(strategies_dir)
    
    def load_all_strategies(self) -> List[StrategyConfig]:
        """Load all strategy files from the strategies directory"""
        strategies = []
        
        if not self.strategies_dir.exists():
            return strategies
        
        for file_path in self.strategies_dir.glob("*.md"):
            try:
                strategy = self.load_strategy(file_path)
                if strategy:
                    strategies.append(strategy)
            except Exception as e:
                print(f"Error loading strategy {file_path}: {e}")
        
        return strategies
    
    def load_strategy(self, file_path: Path) -> Optional[StrategyConfig]:
        """Load a single strategy file and parse its configuration"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract strategy name from filename or first header
        name = file_path.stem.replace('_', ' ').title()
        
        # Extract description from the first few lines
        description = self._extract_description(content)
        
        # Extract YAML configuration
        config = self._extract_yaml_config(content)
        
        return StrategyConfig(
            name=name,
            description=description,
            config=config,
            file_path=str(file_path)
        )
    
    def _extract_description(self, content: str) -> str:
        """Extract strategy description from markdown content"""
        lines = content.split('\n')
        description_lines = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                # Skip headers
                continue
            elif line.startswith('>'):
                # Quote block - likely description
                description_lines.append(line[1:].strip())
            elif line and not line.startswith('---') and description_lines:
                # Stop at first non-quote content after quotes
                break
            elif line and not description_lines:
                # First non-header line if no quotes found
                description_lines.append(line)
                break
        
        return ' '.join(description_lines) if description_lines else "Trading strategy"
    
    def _extract_yaml_config(self, content: str) -> Dict[str, Any]:
        """Extract YAML configuration from markdown code blocks"""
        # Look for YAML code blocks
        yaml_pattern = r'```yaml\s*\n(.*?)\n```'
        matches = re.findall(yaml_pattern, content, re.DOTALL)
        
        if matches:
            try:
                return yaml.safe_load(matches[0])
            except yaml.YAMLError as e:
                print(f"Error parsing YAML config: {e}")
                return self._create_default_config()
        
        # If no YAML found, create default config based on content
        return self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default turtle strategy configuration"""
        return {
            'risk': {
                'unit_pct': 0.01,
                'max_heat_pct': 0.25,
                'class_var_pct': 0.06
            },
            'entries': {
                'sys1_breakout_days': 20,
                'sys2_breakout_days': 55,
                'confirm_on_close': True,
                'vol_gate_atr_mult': 1.2
            },
            'exits': {
                'stop_init_atr_mult': 2.0,
                'breakeven_trigger_atr': 1.0,
                'trail_sys1_days': 10,
                'trail_sys2_days': 20,
                'time_stop_days': 80
            },
            'pyramiding': {
                'max_addons': 4,
                'addon_step_atr': 0.5,
                'whipsaw_brake_losses': 2
            },
            'portfolio': {
                'min_markets': 30,
                'corr_cap': 0.6,
                'liquidity_adv_usd': 5000000
            },
            'execution': {
                'vwap_slice_hours': 2,
                'roll_days_before_fnd': 5
            },
            'monitoring': {
                'slippage_factor_limit': 1.5
            }
        }
    
    def get_strategy_names(self) -> List[str]:
        """Get list of available strategy names"""
        strategies = self.load_all_strategies()
        return [strategy.name for strategy in strategies]
    
    def get_strategy_by_name(self, name: str) -> Optional[StrategyConfig]:
        """Get strategy configuration by name"""
        strategies = self.load_all_strategies()
        for strategy in strategies:
            if strategy.name == name:
                return strategy
        return None