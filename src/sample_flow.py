from web3 import Web3
import json

w3 = Web3(Web3.HTTPProvider("https://eth.drpc.org"))

vault = "0x277C6A642564A91ff78b008022D65683cEE5CCC5"

fe_oracle = "0x5250Ae8A29A19DF1A591cB1295ea9bF2B0232453"
fe_oracle_abi = [
    {
        "inputs": [{"internalType": "address", "name": "vault", "type": "address"}],
        "name": "tvl",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


oracle_helper = "0x000000005F543c38d5ea6D0bF10A50974Eb55E35"

oracle_helper_abi = [
    {
        "inputs": [
            {"internalType": "contract Vault", "name": "vault", "type": "address"},
            {"internalType": "uint256", "name": "totalAssets", "type": "uint256"},
            {
                "components": [
                    {"internalType": "address", "name": "asset", "type": "address"},
                    {"internalType": "uint256", "name": "priceD18", "type": "uint256"},
                ],
                "internalType": "struct OracleHelper.AssetPrice[]",
                "name": "assetPrices",
                "type": "tuple[]",
            },
        ],
        "name": "getPricesD18",
        "outputs": [
            {"internalType": "uint256[]", "name": "pricesD18", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


fe_oracle = w3.eth.contract(
    address=Web3.to_checksum_address(fe_oracle), abi=fe_oracle_abi
)


block_number = w3.eth.block_number
total_assets = fe_oracle.functions.tvl(vault).call(block_identifier=block_number)

oracle_helper = w3.eth.contract(
    address=Web3.to_checksum_address(oracle_helper), abi=oracle_helper_abi
)

wsteth = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"
wsteth_abi = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "_wstETHAmount", "type": "uint256"}
        ],
        "name": "getStETHByWstETH",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


wsteth = w3.eth.contract(address=Web3.to_checksum_address(wsteth), abi=wsteth_abi)

asset_prices = [
    [
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
        wsteth.functions.getStETHByWstETH(10**18).call(block_identifier=block_number),
    ],
    ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 10**18],
    ["0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", 0],
]

prices = oracle_helper.functions.getPricesD18(vault, total_assets, asset_prices).call(
    block_identifier=block_number
)

response = []
for x, y in zip(
    [
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
    ],
    prices,
):
    response.append({"asset": x, "priceD18": y})

print(json.dumps({"reports": response}, indent=2))

# construct OracleReport based on Oracle SC

# prepare transaction for sending to destination safe

# send

# print stats
