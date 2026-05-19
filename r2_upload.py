"""
r2_upload.py
Uploads a local file to Cloudflare R2 and returns a stable public URL.
Used by broadcast.py to replace the ngrok audio tunnel.

Environment variables required (add to .env or ~/.zshrc):
    R2_ACCOUNT_ID       — your Cloudflare account ID (32-char hex)
    R2_ACCESS_KEY_ID    — R2 API token access key ID
    R2_SECRET_ACCESS_KEY — R2 API token secret
    R2_BUCKET_NAME      — bucket name (civicdigest-audio)
    R2_PUBLIC_URL       — public bucket URL (https://pub-XXXX.r2.dev)
"""

import os
import boto3
from botocore.config import Config
from pathlib import Path


def get_r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_audio(local_path: str, object_key: str = None) -> str:
    """
    Upload a file to R2. Returns the public URL.

    Args:
        local_path: absolute or relative path to the file on disk
        object_key: the filename/key in the bucket (defaults to the file's basename)

    Returns:
        Public URL string, e.g. https://pub-XXXX.r2.dev/civicdigest_chicago_1234.mp3
    """
    local_path = Path(local_path)

    if not local_path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")

    if object_key is None:
        object_key = local_path.name

    bucket = os.environ["R2_BUCKET_NAME"]
    public_base = os.environ["R2_PUBLIC_URL"].rstrip("/")

    client = get_r2_client()

    # Detect content type
    suffix = local_path.suffix.lower()
    content_type_map = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".mp4": "video/mp4",
        ".png": "image/png",
        ".jpg": "image/jpeg",
    }
    content_type = content_type_map.get(suffix, "application/octet-stream")

    print(f"[R2] Uploading {local_path.name} → {bucket}/{object_key}")

    client.upload_file(
        Filename=str(local_path),
        Bucket=bucket,
        Key=object_key,
        ExtraArgs={"ContentType": content_type},
    )

    public_url = f"{public_base}/{object_key}"
    print(f"[R2] Upload complete → {public_url}")
    return public_url


def delete_object(object_key: str) -> None:
    """Optional cleanup — delete an object from the bucket after use."""
    bucket = os.environ["R2_BUCKET_NAME"]
    client = get_r2_client()
    client.delete_object(Bucket=bucket, Key=object_key)
    print(f"[R2] Deleted {object_key} from {bucket}")


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import tempfile

    # If a file path is passed as an argument, upload it.
    # Otherwise, create a tiny test file and upload that.
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    else:
        # Create a small test file
        tmp = tempfile.NamedTemporaryFile(
            suffix=".mp3", prefix="civicdigest_test_", delete=False
        )
        tmp.write(b"\xff\xfb\x90\x00" * 100)  # fake MP3 header bytes
        tmp.close()
        test_file = tmp.name
        print(f"[R2] Created test file: {test_file}")

    try:
        url = upload_audio(test_file)
        print(f"\n✅ SUCCESS\nPublic URL: {url}")
        print("\nPaste that URL in your browser — you should get a file download.")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        raise
