# Deterministic risk model

| Rule | Control | Failure action |
|---|---|---|
| R001 | Explicit paper-only mode | Reject |
| R002 | Minimum consensus confidence | Reject |
| R003 | Minimum agreeing agents | Reject |
| R004 | New and total symbol exposure | Modify or reject |
| R005 | Buying power | Modify or reject |
| R006 | Market-data freshness | Reject |
| R007 | Duplicate active intent | Reject |
| R008 | Daily execution count | Reject |
| R009 | Daily loss | Reject |
| R010 | Drawdown / kill switch | Reject |
| R011 | Regular market hours | Reject |
| R012 | Semantic risk review | Escalate |
| R013 | Annualized volatility | Reject |
| R014 | Prohibited short exposure | Reject |

The engine is fail-closed. A hard-check failure sets approved exposure to zero. A semantic rejection escalates only if every hard rule passes. Position and buying-power constraints can reduce size, producing `MODIFY`.

The engine runs twice: once after consensus and again immediately before approval/execution.

## Protective-put controls

| Rule | Control | Failure action |
|---|---|---|
| H001 | Explicit paper-only mode | Reject |
| H002 | Existing protectable 100-share lot | Reject |
| H003 | Minimum portfolio-risk activation score | Reject |
| H004 | Active, tradable put contract | Reject |
| H005 | Configured days-to-expiration window | Reject |
| H006 | Maximum out-of-the-money strike distance | Reject |
| H007 | Hedge ratio and contract-count caps | Reject |
| H008 | Premium budget and buying power | Reject |
| H009 | Maximum relative bid/ask spread | Reject |
| H010 | Option quote freshness | Reject |
| H011 | Duplicate option intent | Reject |
| H012 | Daily execution count | Reject |
| H013 | Market-hours policy | Reject |
| H014 | Independent semantic review | Escalate |
| H015 | Execution kill switch | Reject |
| H016 | Alpaca CLI or explicit replay interface | Reject |
| H017 | Alpaca options approval/trading level ≥ 2 | Reject |

Elevated volatility and drawdown contribute to hedge activation; they are not treated as reasons to reject a risk-reducing proposal. The kill switch still blocks every broker mutation. Hedge decisions are re-evaluated at approval time, including quote freshness and duplicate intent.
