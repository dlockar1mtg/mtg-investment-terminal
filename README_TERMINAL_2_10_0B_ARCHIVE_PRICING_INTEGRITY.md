# Terminal 2.10.0b — Archive Pricing Integrity

Apply this patch after Terminal 2.10.0a, rerun archive preview, then rerun
`--apply`. The apply command creates a backup and removes historical price rows
whose Secret Lair IDs are not present in the production registry.
