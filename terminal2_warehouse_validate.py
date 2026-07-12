from terminal2.warehouse_core import Warehouse
from terminal2.warehouse_core.validation import validate_warehouse
def main():
    w=Warehouse(); w.initialize(); r=validate_warehouse(w)
    for x in r.warnings: print('WARNING:',x)
    for x in r.errors: print('ERROR:',x)
    if not r.passed: raise SystemExit(1)
    print('PASS: Warehouse core is initialized and writable.')
if __name__=='__main__': main()
