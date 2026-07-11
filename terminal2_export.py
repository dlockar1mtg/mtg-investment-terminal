from terminal2.exports.export_reports import export_all

def main():
    outputs = export_all()
    print("Exports created:")
    for name, path in outputs.items():
        print(f"{name}: {path}")

if __name__ == "__main__":
    main()
