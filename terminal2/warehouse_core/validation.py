from dataclasses import dataclass
import tempfile
@dataclass(frozen=True)
class ValidationResult:
    passed:bool; errors:tuple[str,...]; warnings:tuple[str,...]
def validate_warehouse(warehouse):
    errors=list(warehouse.validate()); warnings=[]
    for p in warehouse.config.all_required_paths():
        if p.exists():
            try:
                with tempfile.NamedTemporaryFile(dir=p,delete=True): pass
            except OSError as e: errors.append(f'Not writable: {p} ({e})')
    if not warehouse.registry.all(): warnings.append('No datasets are registered yet. This is expected in 2.5.1a.')
    return ValidationResult(not errors,tuple(errors),tuple(warnings))
