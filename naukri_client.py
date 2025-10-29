from main import NaukriAPIClient
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Naukri.com Automation Client")

    parser.add_argument("--user", type=str, help="Naukri username (overrides .env)")
    parser.add_argument("--password", type=str, help="Naukri password (overrides .env)")
    parser.add_argument("--upload", type=str, help="Path to resume file to upload")
    parser.add_argument("--refresh", action="store_true", help="Refresh resume headline")

    args = parser.parse_args()

    # Initialize client (CLI flags override .env)
    client = NaukriAPIClient(username=args.user, password=args.password)

    # Login if cookies are expired
    if client._is_cookie_expired() or not client.session.cookies:
        client.login()

    # Perform requested action
    if args.upload:
        success = client.upload_resume(args.upload)
        print("✅ Upload successful" if success else "❌ Upload failed")
    elif args.refresh:
        client.refresh_resume_headline()
    else:
        print("ℹ️ No action provided. Use --upload or --refresh.")
