import { ToolResult } from "../types.js";

export async function checkLiquidityLock(contractAddress: string, chain: string = "sepolia"): Promise<ToolResult> {
  const isTestnet = chain === "sepolia" || chain === "polygon_amoy";
  if (isTestnet) {
    return {
      tool: "check_liquidity_lock",
      success: false,
      insufficient_data: true,
      data: null,
      error: `Liquidity lock check not available on ${chain} testnet — no DEX liquidity exists on testnets. On mainnet, this would query DexScreener/Uniswap subgraph.`,
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }

  try {
    const url = `https://api.dexscreener.com/latest/dex/tokens/${contractAddress}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    
    if (!res.ok) {
      throw new Error(`DexScreener API returned status: ${res.status}`);
    }

    const json = await res.json();
    
    if (!json.pairs || json.pairs.length === 0) {
      return {
        tool: "check_liquidity_lock",
        success: true,
        insufficient_data: false,
        data: {
          has_pairs: false,
          total_liquidity_usd: 0,
          pairs: [],
          message: "No pairs found on DexScreener. Liquidity might not be established yet.",
        },
        error: null,
        cached: false,
        fetched_at: new Date().toISOString(),
      };
    }

    const pairs = json.pairs;
    let totalLiquidity = 0;
    
    const formattedPairs = pairs.map((p: any) => {
      const liqUsd = p.liquidity?.usd || 0;
      totalLiquidity += liqUsd;
      return {
        dexId: p.dexId,
        url: p.url,
        pairAddress: p.pairAddress,
        liquidity_usd: liqUsd,
      };
    });

    return {
      tool: "check_liquidity_lock",
      success: true,
      insufficient_data: false,
      data: {
        has_pairs: true,
        total_liquidity_usd: totalLiquidity,
        pairs: formattedPairs,
        message: "Liquidity data fetched. Note: DexScreener does not natively verify LP token lock status (e.g. via Team Finance). Check total liquidity to gauge if liquidity is suspiciously low.",
      },
      error: null,
      cached: false,
      fetched_at: new Date().toISOString(),
    };

  } catch (err: any) {
    return {
      tool: "check_liquidity_lock",
      success: false,
      insufficient_data: true,
      data: null,
      error: err.message || "Failed to fetch DexScreener data",
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }
}
