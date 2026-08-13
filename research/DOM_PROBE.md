# Market-data API entitlement: every plumbing explanation is now eliminated

Six probe rounds, 2026-08-11 → 2026-08-13. Each round removed one candidate
explanation for why the API market-data socket refuses every CME contract.
What remains is not fixable from code.

## What was tested and eliminated, in order

| # | hypothesis | test | result |
|---|---|---|---|
| 1 | wrong symbol / expired contract | all 12 REST-known contracts (NQ, MNQ, ES, MES, CL, GC), by name AND numeric id | all refused equally |
| 2 | no L1 subscription | user subscribed CME Group L1 (portal shows SUBSCRIBED), re-probed 90 s later | still all refused |
| 3 | demo host never gets paid data | probed live | live blocked by 2FA new-machine gate |
| 4 | 2FA | user approved device `dom-recorder-001` (fixed deviceId, approval persists) | live auth now s:200 |
| 5 | wrong endpoint spelling | live 404'd `md/subscribeQuote`; switched to lowercase | live STILL 404'd — wrong host, not case |
| 6 | wrong host | `md-live.tradovateapi.com` owns no md/* routes; production md is `md.tradovateapi.com` | endpoints resolve, authorize s:200 — and **"Symbol is inaccessible"**, same as demo |

Final state, both environments, correct hosts, correct endpoints, authorized
sessions, `hasMarketData=True hasLive=True hasFunded=True` on the token reply,
CME Group L1 + CME L2 paid in the dealer portal:

```
md-demo.tradovateapi.com  authorize s:200  → all 28 requests: Symbol is inaccessible
md.tradovateapi.com       authorize s:200  → all 28 requests: Symbol is inaccessible
```

(28 = quote by name + quote by id for 12 contracts, plus subscribeDom on the
four index front months.)

## Conclusion

The dealer-portal market-data subscription is not propagating to API
market-data entitlement. That is a Tradovate account-configuration issue —
possibly the API-access add-on not carrying md entitlement, possibly the
subscription being scoped to the Trader UI only (the portal's monthly total
shows $0, i.e. dealer-covered, which may exclude third-party API access).
No further code change can move this.

## The support ticket to raise

> My account (user kyewells…, demo 46293485) is subscribed to CME Group
> Top of Book (L1) and CME Depth of Market (L2) in the dealer portal, and my
> access-token reply shows hasMarketData=true. But the market-data WebSocket
> (both md-demo.tradovateapi.com and md.tradovateapi.com, after a successful
> authorize) returns `errorText: "Symbol is inaccessible", errorCode:
> "UnknownSymbol"` for every CME contract (NQU6, ESU6, MNQU6, …) on both
> md/subscribequote and md/subscribedom, by symbol name and by contract id.
> API key auth succeeds; the 2FA device is approved. What is missing for the
> market-data subscription to apply to API access?

## Two bugs this hunt fixed in our own tooling

- probe parser treated router errors (`d` as string) as unparseable and
  printed "(no reply)" — masked the 404s for a full round.
- the recorder targeted `md-live.tradovateapi.com` for live, which accepts
  the socket and the authorize but owns no md routes. Production market data
  is `md.tradovateapi.com`. `dom_record.py` must use the same mapping when
  entitlement arrives.
