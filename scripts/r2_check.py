"""One-shot Cloudflare R2 connectivity check for AI-Teaching-Assistant.

Zero-dependency on purpose: reads the four R2_* values straight from
backend/.env (no pydantic / app imports needed), then talks to the R2 S3
API: authenticate -> confirm the bucket -> upload/read/delete a tiny test
object (a few bytes, auto-cleaned).

Run from the repo root:
    python scripts/r2_check.py

Only requirement when values are filled in: boto3
(pip install boto3   - or run this inside the backend container).

Exit codes: 0 = R2 works, 1 = configured but the API call failed,
2 = R2 not (fully) configured yet.
"""
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "backend" / ".env"

FIELDS = [
    ("R2_ACCOUNT_ID", "your Cloudflare account id"),
    ("R2_ACCESS_KEY_ID", "Access Key ID of the R2 API token"),
    ("R2_SECRET_ACCESS_KEY", "Secret Access Key of the R2 API token"),
    ("R2_BUCKET", "the R2 bucket name"),
]

CLICK_PATH = (
    "1. Create the bucket: R2 Object Storage -> 'Create bucket' (any name).\n"
    "2. Create the token:  R2 Object Storage -> 'Manage R2 API Tokens' ->\n"
    "   'Create API Token' -> Permissions: Object Read & Write -> Create.\n"
    "3. Paste Access Key ID / Secret Access Key / bucket name into backend/.env\n"
    "   (the R2_ACCOUNT_ID block at the bottom) and re-run this script."
)


def read_env_values(path: Path) -> dict:
    """Minimal KEY=VALUE parser for .env (quotes stripped, comments ignored)."""
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def main() -> int:
    print("Cloudflare R2 check")
    print("-" * 60)

    env = read_env_values(ENV_FILE)
    os.environ.update({k: v for k, v in env.items() if k.startswith("R2_")})

    missing = [name for name, _ in FIELDS if not env.get(name)]
    if missing:
        print(f"backend/.env: {'found' if ENV_FILE.exists() else 'NOT FOUND'}")
        print("NOT CONFIGURED - these values are still empty:")
        for name in missing:
            print(f"  {name}   ({dict(FIELDS)[name]})")
        print("\nWhere to get them:\n" + CLICK_PATH)
        return 2

    account_id = env["R2_ACCOUNT_ID"]
    bucket = env["R2_BUCKET"]
    key_id = env["R2_ACCESS_KEY_ID"]
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    print(f" backend/.env : {ENV_FILE}")
    print(f" endpoint     : {endpoint}")
    print(f" bucket       : {bucket}")
    shown = f"{key_id[:6]}...{key_id[-4:]}" if len(key_id) > 10 else "***"
    print(f" key id       : {shown}")

    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("\nValues are set, but boto3 is not installed on THIS machine.")
        print("Install it with:  pip install boto3")
        print("(inside the app it is already in backend/requirements.txt, so")
        print(" uploads will work in Docker/Render without this step).")
        return 1

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
    )

    # 1) bucket reachable + token authorized
    try:
        client.head_bucket(Bucket=bucket)
        print(f" bucket '{bucket}' reachable - token has access")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404 or code in ("NoSuchBucket", "404"):
            print(f"\nFAIL: bucket '{bucket}' does not exist (create it in the dashboard).")
        elif status == 403 or code in ("AccessDenied", "403"):
            print("\nFAIL: token cannot access this bucket (wrong key, or the token")
            print("      is scoped to a different bucket).")
        else:
            print(f"\nFAIL: head_bucket -> {code or status}: {exc}")
        return 1
    except Exception as exc:  # network / signature problems
        print(f"\nFAIL: could not authenticate to R2: {exc}")
        return 1

    # 2) upload / read / delete a tiny test object
    key = f"__r2_check__/{uuid.uuid4().hex}.txt"
    payload = b"ai-teaching-assistant r2 check"
    try:
        client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="text/plain")
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if body != payload:
            print("\nFAIL: round-trip mismatch (read != written).")
            return 1
        client.delete_object(Bucket=bucket, Key=key)
        print(" upload/read/delete round-trip OK")
    except Exception as exc:
        print(f"\nFAIL: round-trip -> {exc}")
        return 1

    print("-" * 60)
    print("SUCCESS - R2 is connected. New uploads are stored in bucket")
    print(f"'{bucket}' (10 GB free, no egress cost) instead of the database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
