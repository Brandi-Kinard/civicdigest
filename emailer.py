"""
emailer.py — CivicDigest video delivery notification
Sends the completed broadcast video link to a subscriber via SendGrid.

Environment variables:
    SENDGRID_API_KEY   — your SendGrid API key
    SENDGRID_FROM      — verified sender email (your Gmail)
"""

import os
import requests

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDGRID_FROM    = os.environ.get("SENDGRID_FROM", os.environ.get("SENDGRID_SENDER", ""))


def send_video_notification(to_email: str, city: str, video_url: str) -> bool:
    """
    Send a video-ready notification email.
    Returns True on success, False on failure.
    """
    if not SENDGRID_API_KEY:
        print("[emailer] No SENDGRID_API_KEY — skipping email")
        return False

    subject = f"Your CivicDigest broadcast for {city} is ready"

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#0A0A1E;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0A0A1E;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="padding:0 0 24px 0;">
              <span style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:32px;font-weight:900;color:#F4F4F0;letter-spacing:0.04em;">
                CIVIC<span style="color:#C41E3A;">DIGEST</span>
              </span>
            </td>
          </tr>

          <!-- Red rule -->
          <tr>
            <td style="height:3px;background:#C41E3A;padding:0 0 32px 0;"></td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px 0 24px 0;">
              <p style="margin:0 0 8px 0;font-size:11px;letter-spacing:0.2em;color:#C41E3A;text-transform:uppercase;font-family:monospace;">
                // Your broadcast is ready
              </p>
              <h1 style="margin:0 0 16px 0;font-size:28px;font-weight:700;color:#F4F4F0;line-height:1.2;">
                {city} City Council Report
              </h1>
              <p style="margin:0 0 32px 0;font-size:15px;color:#8A8A9A;line-height:1.6;">
                Your AI-generated broadcast video is ready. Click below to watch the full report.
              </p>

              <!-- CTA button -->
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background:#C41E3A;">
                    <a href="{video_url}"
                       style="display:inline-block;padding:16px 32px;font-family:monospace;font-size:12px;font-weight:500;letter-spacing:0.15em;text-transform:uppercase;color:#ffffff;text-decoration:none;">
                      Watch Broadcast
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="height:1px;background:rgba(255,255,255,0.08);padding:0 0 24px 0;"></td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 0 0 0;">
              <p style="margin:0;font-family:monospace;font-size:10px;color:#8A8A9A;line-height:1.6;letter-spacing:0.05em;">
                This summary is AI-generated from publicly available city council records and may contain errors or omissions.
                It is not a substitute for official meeting minutes.<br><br>
                CivicDigest — Local Government Intelligence
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    plain = f"""Your CivicDigest broadcast for {city} is ready.

Watch it here: {video_url}

---
This summary is AI-generated from publicly available city council records and may contain errors or omissions. It is not a substitute for official meeting minutes.

CivicDigest — Local Government Intelligence
"""

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": SENDGRID_FROM, "name": "CivicDigest"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain},
            {"type": "text/html",  "value": html},
        ]
    }

    try:
        r = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=15
        )
        if r.status_code in (200, 202):
            print(f"[emailer] ✅ Sent to {to_email}")
            return True
        else:
            print(f"[emailer] ❌ Failed {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[emailer] ❌ Exception: {e}")
        return False


if __name__ == "__main__":
    # Quick test — run: python emailer.py
    import sys
    to = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SENDGRID_FROM", "")
    if not to:
        print("Usage: python emailer.py recipient@email.com")
        sys.exit(1)
    ok = send_video_notification(to, "Chicago", "https://example.com/test_video.mp4")
    print("Result:", "SUCCESS" if ok else "FAILED")
