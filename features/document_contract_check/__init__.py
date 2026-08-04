"""文档合同核对功能公开入口。"""

from .check import ContractError, ContractReport, check_contract

__all__ = ["ContractError", "ContractReport", "check_contract"]
