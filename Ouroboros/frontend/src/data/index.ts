/**
 * Production pages must not import demo data through this barrel.
 *
 * Demo fixtures contain invented causal chains, end-of-day summaries,
 * liquidation state, and market tape content. Keep those fixtures behind the
 * explicit "./demoOnly" entrypoint so real Web API pages cannot pick them up
 * by accident.
 */
export {};
