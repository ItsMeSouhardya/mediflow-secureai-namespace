"""Web3 adapter for the MediFlow integrity contract.

The adapter accepts only pre-hashed bytes32 payload fields. It has no access to
patient names, document metadata, consent purposes, or clinical content.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


class BlockchainUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ChainSubmission:
    transaction_hash: str
    chain_id: int
    contract_address: str


@dataclass(frozen=True)
class ChainReceipt:
    transaction_hash: str
    block_number: int
    success: bool


def _bytes32(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise ValueError("Contract payload values must be 32-byte hexadecimal hashes")
    return f"0x{value.lower()}"


class Web3IntegrityAdapter:
    def __init__(self, config: dict):
        if not config.get("BLOCKCHAIN_ENABLED"):
            raise BlockchainUnavailable("Blockchain integration is disabled")
        try:
            from web3 import Web3
        except ImportError as error:
            raise BlockchainUnavailable("web3.py is not installed") from error

        abi_path = Path(config["BLOCKCHAIN_ABI_PATH"])
        if not abi_path.exists():
            raise BlockchainUnavailable(f"Contract ABI artifact not found: {abi_path}")
        artifact = json.loads(abi_path.read_text(encoding="utf-8"))
        self.web3 = Web3(Web3.HTTPProvider(config["BLOCKCHAIN_RPC_URL"], request_kwargs={"timeout": 10}))
        if not self.web3.is_connected():
            raise BlockchainUnavailable("Blockchain RPC is unavailable")
        self.account = None
        self.account_address = None
        if config.get("BLOCKCHAIN_DEVELOPMENT_UNLOCKED_ACCOUNT"):
            if config.get("ENV_NAME") == "production":
                raise BlockchainUnavailable("Unlocked blockchain accounts are forbidden in production")
            accounts = self.web3.eth.accounts
            if not accounts:
                raise BlockchainUnavailable("Development blockchain exposes no unlocked account")
            self.account_address = accounts[0]
        else:
            private_key = config.get("BLOCKCHAIN_DEPLOYER_PRIVATE_KEY")
            if not private_key:
                raise BlockchainUnavailable("Blockchain signer key is not configured")
            self.account = self.web3.eth.account.from_key(private_key)
            self.account_address = self.account.address
        self.contract_address = self.web3.to_checksum_address(config["BLOCKCHAIN_CONTRACT_ADDRESS"])
        self.contract = self.web3.eth.contract(address=self.contract_address, abi=artifact["abi"])
        self.chain_id = int(config["BLOCKCHAIN_CHAIN_ID"])
        if int(self.web3.eth.chain_id) != self.chain_id:
            raise BlockchainUnavailable("Configured blockchain chain ID does not match the RPC network")
        self.confirmations = max(1, int(config.get("BLOCKCHAIN_CONFIRMATIONS", 1)))

    def _function_for(self, operation: str, payload: dict):
        if operation == "record_register":
            return self.contract.functions.registerRecord(
                _bytes32(payload["record_ref"]), _bytes32(payload["content_hash"])
            )
        if operation == "consent_grant":
            return self.contract.functions.grantConsent(
                _bytes32(payload["consent_ref"]),
                _bytes32(payload["patient_ref"]),
                _bytes32(payload["grantee_ref"]),
                _bytes32(payload["scope_hash"]),
                _bytes32(payload["period_ref"]),
            )
        if operation == "consent_revoke":
            return self.contract.functions.revokeConsent(
                _bytes32(payload["consent_ref"]), _bytes32(payload["revocation_hash"])
            )
        if operation == "audit_anchor":
            return self.contract.functions.anchorAuditRoot(
                _bytes32(payload["period_ref"]), _bytes32(payload["merkle_root"])
            )
        raise ValueError(f"Unsupported blockchain operation: {operation}")

    def submit(self, operation: str, payload: dict) -> ChainSubmission:
        function = self._function_for(operation, payload)
        if self.account is None:
            tx_hash = function.transact({"from": self.account_address})
            return ChainSubmission(tx_hash.hex(), self.chain_id, self.contract_address)
        nonce = self.web3.eth.get_transaction_count(self.account_address, "pending")
        transaction = function.build_transaction(
            {
                "from": self.account_address,
                "nonce": nonce,
                "chainId": self.chain_id,
                "gas": function.estimate_gas({"from": self.account_address}),
                "maxFeePerGas": self.web3.eth.gas_price * 2,
                "maxPriorityFeePerGas": self.web3.to_wei(1, "gwei"),
            }
        )
        signed = self.account.sign_transaction(transaction)
        tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction).hex()
        return ChainSubmission(tx_hash, self.chain_id, self.contract_address)

    def wait_for_receipt(self, transaction_hash: str) -> ChainReceipt:
        receipt = self.web3.eth.wait_for_transaction_receipt(transaction_hash, timeout=120)
        if self.confirmations > 1:
            target = receipt.blockNumber + self.confirmations - 1
            while self.web3.eth.block_number < target:
                time.sleep(1)
        return ChainReceipt(transaction_hash, int(receipt.blockNumber), int(receipt.status) == 1)

    def verify_record(self, record_ref: str, content_hash: str) -> bool:
        return bool(self.contract.functions.verifyRecord(_bytes32(record_ref), _bytes32(content_hash)).call())
