# MTG V1 -> UIP Export Interface

## Status

MTG_V1_TO_UIP_EXPORT_CONTRACT_CERTIFIED

## Source authority

Unified MTG V1 production authority is certified.

Source commit:

94c2bd3273eaba4d05ee8f7f5c3d6c4dcc283768

Source normalized authority:

docs/phase_9/unified_mtg/unified_mtg_v1_normalized_product_authority.csv

Source SHA-256:

006ba3951565437291284d8e86e93a40208d2c0e783f43d3652e9f8f510914e1

## Export payload

docs/phase_9/uip_export/mtg_v1_uip_export_payload.csv

Payload SHA-256:

006ba3951565437291284d8e86e93a40208d2c0e783f43d3652e9f8f510914e1

The payload is byte-for-byte identical to the certified Unified MTG
normalized product authority.

No filtering, imputation, renaming, rescoring, reranking, or other
transformation occurs at the MTG -> UIP boundary.

## Current snapshot

Collector: 50

Pre-Collector: 131

Secret Lair V1.1: 787

Total: 968

968 is a current snapshot count, not a permanent MTG universe constant.

## Native analytical semantics

Native MTG ranks remain lane-specific.

They are not a global MTG rank and are not a cross-asset UIP rank.

Native purchase states remain lane-specific.

Secret Lair BUY_CANDIDATE_NOW means:

MODEL_QUALIFIED_ENTRY_CANDIDATE

It does not mean execution-ready purchase.

## Missing authority

Missing price does not mean zero.

Missing forecast does not mean zero.

Missing rank does not mean worst rank.

Missing purchase state does not mean WAIT.

## Execution

Execution-ready purchase authority:

FALSE

Automatic purchase execution:

FALSE

## Refresh responsibility

UIP may request MTG refresh activity.

MTG remains responsible for executing refreshes through governed MTG
refresh routes.

Price refresh is not automatically retraining.

New-product discovery is not automatically model redesign.

Historical append is not automatically retraining.

Retraining and recertification remain separately governed.

Secret Lair discovery remains dynamic.

## UIP acceptance

UIP-side semantic-preservation acceptance is authorized.

UIP integration is not yet certified.

## Next gate

UIP_MTG_A1_EXPORT_ACCEPTANCE_AND_SEMANTIC_PRESERVATION