from terminal2.secret_lair.calibration import validate_secret_lair_calibration
def main():
    r=validate_secret_lair_calibration()
    print("\nTerminal 2.9.9 Secret Lair Intelligence Calibration Validation")
    print("="*72)
    print(f"Datasets checked: {r.datasets_checked}")
    print(f"Products calibrated: {r.products}")
    print(f"Score spread: {r.score_spread:.2f}")
    print(f"Actionable buys: {r.actionable_buys}")
    for x in r.warnings:print(f"WARNING: {x}")
    for x in r.errors:print(f"ERROR: {x}")
    if not r.passed:raise SystemExit(1)
    print("PASS: Secret Lair intelligence calibration is valid.")
if __name__=="__main__":main()
