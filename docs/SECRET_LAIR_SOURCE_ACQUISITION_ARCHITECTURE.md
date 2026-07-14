# Secret Lair Source Acquisition Architecture

Configured sources are loaded through connector adapters, normalized through
explicit JSON field maps, validated, and published to the warehouse. Acquisition
never writes directly to the registry. The 2.6.2 matching and guarded apply
workflow remains the only path that mutates local registry and price files.

Supported connector types: `csv`, `json`, and `directory`.
