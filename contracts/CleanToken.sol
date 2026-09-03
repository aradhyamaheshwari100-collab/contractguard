// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * CleanToken — Standard ERC-20 with ownership renounced.
 * ContractGuard Demo Contract A: should receive LOW RISK verdict.
 * Deploy to Sepolia via Remix IDE, verify on Etherscan.
 *
 * No hidden functions. No mint after deployment. Ownership renounced in constructor.
 */

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract CleanToken is ERC20, Ownable {
    uint256 public constant MAX_SUPPLY = 1_000_000 * 10 ** 18; // 1M tokens, fixed

    constructor() ERC20("ContractGuard Clean Demo", "CGCLEAN") Ownable(msg.sender) {
        // Mint full supply to deployer at construction — no further mint possible
        _mint(msg.sender, MAX_SUPPLY);

        // Immediately renounce ownership — owner becomes the zero address
        renounceOwnership();
    }

    // ── No owner-only functions ──────────────────────────────────────────────
    // No emergencyWithdraw, no mint, no blacklist, no hidden fees.
    // Transfer function is standard OpenZeppelin ERC20 — unmodified.
}
