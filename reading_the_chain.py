import random
import json
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers.rpc import HTTPProvider
import os


# If you use one of the suggested infrastructure providers, the url will be of the form
# now_url  = f"https://eth.nownodes.io/{now_token}"
# alchemy_url = f"https://eth-mainnet.alchemyapi.io/v2/{alchemy_token}"
# infura_url = f"https://mainnet.infura.io/v3/{infura_token}"

def connect_to_eth():
    url = "https://mainnet.infura.io/v3/fdbce84670d0495b943692aec38c7785"
    w3 = Web3(HTTPProvider(url))
    assert w3.is_connected(), f"Failed to connect to provider at {url}"
    return w3


def connect_with_middleware(contract_json):
	# read contract details
  with open(contract_json, "r") as f:
      d = json.load(f)
      d = d["bsc"]
      address = d["address"]
      abi = d["abi"]

  # connect to BSC testnet
  bsc_testnet_url = os.environ.get("BSC_TESTNET_RPC", "https://bsc-testnet.publicnode.com")
  w3 = Web3(HTTPProvider(bsc_testnet_url, request_kwargs={"timeout": 30}))
  assert w3.is_connected(), f"Failed to connect to provider at {bsc_testnet_url}"

  # inject POA middleware (required for BSC/other POA chains)
  w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

  # create contract object
  contract = w3.eth.contract(
      address=Web3.to_checksum_address(address),
      abi=abi
  )

  return w3, contract

def _tx_priority_fee(tx, base_fee):
    """
    Compute the *priority* fee used for greedy ordering.
    - Pre-1559 (no base_fee): return gasPrice (we'll handle separately).
    - Post-1559:
        * Type 2 (EIP-1559): min(maxPriorityFeePerGas, maxFeePerGas - base_fee)
        * Type 0: gasPrice - base_fee
    """
    # Defensive helpers
    def get(field, default=None):
        return tx[field] if field in tx and tx[field] is not None else default

    # If EIP-1559 fields present, treat as type 2
    max_prio = get('maxPriorityFeePerGas')
    max_fee = get('maxFeePerGas')
    gas_price = get('gasPrice')

    if base_fee is None:
        # Pre-1559 comparison uses total gasPrice
        return gas_price

    if max_prio is not None and max_fee is not None:
        # Type 2: priority = min(maxPriorityFeePerGas, maxFeePerGas - base_fee)
        eff = max_fee - base_fee
        if eff < 0:
            eff = 0
        return min(max_prio, eff)
    else:
        # Legacy tx in post-1559 block: priority = gasPrice - base_fee
        if gas_price is None:
            return 0
        prio = gas_price - base_fee
        return prio if prio > 0 else 0


def is_ordered_block(w3, block_num):
    """
    Takes a block number
    Returns a boolean that tells whether all the transactions in the block are ordered by priority fee

    Before EIP-1559, a block is ordered if and only if all transactions are sorted in decreasing order of the gasPrice field

    After EIP-1559, there are two types of transactions
        *Type 0* The priority fee is tx.gasPrice - block.baseFeePerGas
        *Type 2* The priority fee is min( tx.maxPriorityFeePerGas, tx.maxFeePerGas - block.baseFeePerGas )

    Conveniently, most type 2 transactions set the gasPrice field to be min( tx.maxPriorityFeePerGas + block.baseFeePerGas, tx.maxFeePerGas )
    """
    block = w3.eth.get_block(block_num, full_transactions=True)
    base_fee = block.get('baseFeePerGas', None)

    txs = block.get('transactions', [])
    if not txs or len(txs) <= 1:
        return True  # trivially ordered

    # Build the sequence to compare
    if base_fee is None:
        # Pre-1559: compare gasPrice directly
        keys = [tx['gasPrice'] for tx in txs]
    else:
        # Post-1559: compare priority fees
        keys = [_tx_priority_fee(tx, base_fee) for tx in txs]

    # Check non-increasing ordering
    for i in range(1, len(keys)):
        if keys[i] > keys[i - 1]:
            return False
    return True


def get_contract_values(contract, admin_address, owner_address):
    """
    Takes a contract object, and two addresses (as strings) to be used for calling
    the contract to check current on chain values.
    The provided "default_admin_role" is the correctly formatted solidity default
    admin value to use when checking with the contract
    To complete this method you need to make three calls to the contract to get:
        onchain_root: Get and return the merkleRoot from the provided contract
        has_role: Verify that the address "admin_address" has the role "default_admin_role" return True/False
        prime: Call the contract to get and return the prime owned by "owner_address"

    check on available contract functions and transactions on the block explorer at
    https://testnet.bscscan.com/address/0xaA7CAaDA823300D18D3c43f65569a47e78220073
    """
    default_admin_role = int.to_bytes(0, 32, byteorder="big")

    # TODO complete the following lines by performing contract calls
    onchain_root = contract.functions.merkleRoot().call()
    has_role = contract.functions.hasRole(default_admin_role, Web3.to_checksum_address(admin_address)).call()
    prime = contract.functions.getPrimeByOwner(Web3.to_checksum_address(owner_address)).call()

    return onchain_root, has_role, prime


"""
	This might be useful for testing (main is not run by the grader feel free to change 
	this code anyway that is helpful)
"""
if __name__ == "__main__":
	# These are addresses associated with the Merkle contract (check on contract
	# functions and transactions on the block explorer at
	# https://testnet.bscscan.com/address/0xaA7CAaDA823300D18D3c43f65569a47e78220073
	admin_address = "0xAC55e7d73A792fE1A9e051BDF4A010c33962809A"
	owner_address = "0x793A37a85964D96ACD6368777c7C7050F05b11dE"
	contract_file = "contract_info.json"

	eth_w3 = connect_to_eth()
	cont_w3, contract = connect_with_middleware(contract_file)

	latest_block = eth_w3.eth.get_block_number()
	london_hard_fork_block_num = 12965000
	assert latest_block > london_hard_fork_block_num, f"Error: the chain never got past the London Hard Fork"

	n = 5
	for _ in range(n):
		block_num = random.randint(1, latest_block)
		ordered = is_ordered_block(block_num)
		if ordered:
			print(f"Block {block_num} is ordered")
		else:
			print(f"Block {block_num} is not ordered")
