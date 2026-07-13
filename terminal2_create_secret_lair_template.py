from terminal2.secret_lair.registry import (
    REGISTRY_PATH,
    create_registry_template,
)


def main():
    path = create_registry_template(REGISTRY_PATH)
    print(f"Secret Lair registry template ready: {path}")
    print(
        "Populate this local file or use "
        "terminal2_import_secret_lair_registry.py."
    )


if __name__ == "__main__":
    main()
