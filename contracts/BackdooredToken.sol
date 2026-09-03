// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * BackdooredToken — ERC-20 with deliberately hidden fraud mechanisms.
 * ContractGuard Demo Contract B: should receive HIGH RISK verdict.
 * Deploy to Sepolia via Remix IDE, verify on Etherscan.
 *
 * INTENTIONALLY BAD PATTERNS (for demo/educational purposes only):
 *  1. emergencyWithdraw() — owner can drain ALL token balances to arbitrary address
 *  2. mint() — owner can mint unlimited tokens after deployment (inflation attack)
 *  3. setBlacklist() — owner can block any address from transferring
 *  4. setTransferFee() — owner can set transfer fee up to 100%
 *  5. Ownership NOT renounced — active owner throughout lifecycle
 *
 * DO NOT use this contract for any real purpose. Educational demo only.
 */

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract BackdooredToken is ERC20, Ownable {

    // ── Hidden state ──────────────────────────────────────────────────────────
    mapping(address => bool) private _blacklisted;
    uint256 public transferFeeBps = 0; // Basis points (100 = 1%). Owner can raise to 10000 (100%)
    address public feeRecipient;

    event Blacklisted(address indexed account, bool status);
    event FeeUpdated(uint256 newFeeBps);
    event EmergencyWithdraw(address indexed to, uint256 amount);

    constructor() ERC20("ContractGuard Backdoor Demo", "CGBAD") Ownable(msg.sender) {
        feeRecipient = msg.sender;
        // Mint initial supply — owner retains ability to mint more
        _mint(msg.sender, 1_000_000 * 10 ** 18);
        // NOTE: ownership is NOT renounced — this is intentional for the demo
    }

    // ── BACKDOOR 1: Owner-drain function ─────────────────────────────────────
    // Owner can transfer ALL tokens held by this contract to any address.
    // In a real rug: deployer calls this after users add liquidity to a DEX pair.
    function emergencyWithdraw(address to, uint256 amount) external onlyOwner {
        _transfer(address(this), to, amount);
        emit EmergencyWithdraw(to, amount);
    }

    // ── BACKDOOR 2: Unlimited mint ───────────────────────────────────────────
    // Owner can inflate supply at will, diluting all holders.
    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount); // No MAX_SUPPLY check — unlimited inflation possible
    }

    // ── BACKDOOR 3: Transfer blacklist ───────────────────────────────────────
    // Owner can prevent any address from sending or receiving tokens.
    function setBlacklist(address account, bool status) external onlyOwner {
        _blacklisted[account] = status;
        emit Blacklisted(account, status);
    }

    function isBlacklisted(address account) external view returns (bool) {
        return _blacklisted[account];
    }

    // ── BACKDOOR 4: Hidden transfer fee ─────────────────────────────────────
    // Owner can silently raise fee to 100%, making tokens unsellable.
    function setTransferFee(uint256 feeBps) external onlyOwner {
        require(feeBps <= 10000, "Fee cannot exceed 100%");
        transferFeeBps = feeBps;
        emit FeeUpdated(feeBps);
    }

    function setFeeRecipient(address recipient) external onlyOwner {
        feeRecipient = recipient;
    }

    // ── Override transfer to apply blacklist + fee ────────────────────────────
    function _update(
        address from,
        address to,
        uint256 amount
    ) internal virtual override {
        require(!_blacklisted[from], "Sender is blacklisted");
        require(!_blacklisted[to], "Recipient is blacklisted");

        if (transferFeeBps > 0 && from != owner() && to != owner()) {
            uint256 fee = (amount * transferFeeBps) / 10000;
            uint256 netAmount = amount - fee;
            super._update(from, feeRecipient, fee);
            super._update(from, to, netAmount);
        } else {
            super._update(from, to, amount);
        }
    }
}
