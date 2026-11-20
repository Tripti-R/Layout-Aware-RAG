
from app.core.config import settings


def main():
    print("=" * 55)
    print(settings.project_name)
    print("=" * 55)

    directories = [
        settings.originals_dir,
        settings.processed_dir,
        settings.page_images_dir,
        settings.assets_dir,
        settings.logs_dir,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"[OK] {directory}")

    print("\nEnvironment initialized successfully.")


if __name__ == "__main__":
    main()
