from ..schemas import OptimizationMethod
from .base import BaseOptimizer, OptimizationContext
from .cod import ChainOfDensityOptimizer
from .dspy_opt import DspyOptimizer
from .fewshot import FewShotOptimizer
from .opro import OproOptimizer

OPTIMIZER_REGISTRY: dict[OptimizationMethod, type[BaseOptimizer]] = {
    OptimizationMethod.OPRO: OproOptimizer,
    OptimizationMethod.COD: ChainOfDensityOptimizer,
    OptimizationMethod.FEWSHOT: FewShotOptimizer,
    OptimizationMethod.DSPY: DspyOptimizer,
}

__all__ = [
    "BaseOptimizer",
    "OptimizationContext",
    "OproOptimizer",
    "ChainOfDensityOptimizer",
    "FewShotOptimizer",
    "DspyOptimizer",
    "OPTIMIZER_REGISTRY",
]
