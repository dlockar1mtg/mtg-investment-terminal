from terminal2.features.price_features import compute_price_features

def main():
    df = compute_price_features()
    print(f"Computed product features: {len(df)}")
    if len(df):
        print(df.head(30).to_string(index=False))

if __name__ == "__main__":
    main()
