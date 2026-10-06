"""
Email Poller - Checks Gmail for CV attachments and sends them to n8n webhook.
Run: python email_poller.py
"""
import imaplib
import email
import time
import os
import requests
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv('GMAIL_USER', '')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '60'))  # seconds
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/cv-upload')
DJANGO_UPLOAD_URL = os.getenv('DJANGO_UPLOAD_URL', 'http://localhost:8000/api/candidates/upload/')

# Set to True to send directly to Django (skip n8n)
DIRECT_TO_DJANGO = os.getenv('DIRECT_TO_DJANGO', 'true').lower() == 'true'


def get_filename(part):
    filename = part.get_filename()
    if filename:
        decoded, charset = decode_header(filename)[0]
        if isinstance(decoded, bytes):
            return decoded.decode(charset or 'utf-8')
        return decoded
    return None


def is_cv_file(filename):
    if not filename:
        return False
    ext = filename.lower().rsplit('.', 1)[-1]
    return ext in ('pdf', 'docx', 'doc')


def process_email(msg, msg_id):
    subject = str(decode_header(msg['Subject'])[0][0] or '')
    if isinstance(subject, bytes):
        subject = subject.decode('utf-8', errors='ignore')

    from_addr = msg['From'] or ''
    print(f"  Subject: {subject}")
    print(f"  From: {from_addr}")

    cv_found = False
    for part in msg.walk():
        filename = get_filename(part)
        if not is_cv_file(filename):
            continue

        print(f"  CV found: {filename}")
        file_data = part.get_payload(decode=True)

        if DIRECT_TO_DJANGO:
            # Send directly to Django API
            try:
                resp = requests.post(
                    DJANGO_UPLOAD_URL,
                    files={'file': (filename, file_data)},
                    data={'source_email': from_addr},
                    timeout=120,
                )
                if resp.status_code in (200, 201):
                    result = resp.json()
                    name = result.get('full_name', 'Unknown')
                    linkedin = result.get('linkedin_enriched', False)
                    match = result.get('comparison', {}).get('overall_match', 0)
                    print(f"  -> Candidate: {name} | LinkedIn: {linkedin} | Match: {match}%")
                else:
                    print(f"  -> Django error {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                print(f"  -> Django request failed: {e}")
        else:
            # Send to n8n webhook
            try:
                resp = requests.post(
                    N8N_WEBHOOK_URL,
                    files={'file': (filename, file_data)},
                    data={'source_email': from_addr, 'subject': subject},
                    timeout=120,
                )
                print(f"  -> n8n response: {resp.status_code}")
            except Exception as e:
                print(f"  -> n8n webhook failed: {e}")

        cv_found = True

    if not cv_found:
        print("  No CV attachment found, skipping")

    return cv_found


def poll_inbox():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("ERROR: Set GMAIL_USER and GMAIL_APP_PASSWORD in .env")
        return

    print(f"\nConnecting to Gmail ({GMAIL_USER})...")
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select('INBOX')

        # Search for unseen emails
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            print("No new emails")
            mail.logout()
            return

        msg_ids = messages[0].split()
        if not msg_ids:
            print("No unread emails")
            mail.logout()
            return

        print(f"Found {len(msg_ids)} unread email(s)")

        for msg_id in msg_ids:
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            print(f"\nProcessing email #{msg_id.decode()}:")
            processed = process_email(msg, msg_id)

            if processed:
                # Mark as read
                mail.store(msg_id, '+FLAGS', '\\Seen')
                print("  Marked as read")

        mail.logout()
        print("\nDone polling")

    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}")
        print("Check: GMAIL_USER, GMAIL_APP_PASSWORD, and that IMAP is enabled in Gmail settings")
    except Exception as e:
        print(f"Error: {e}")


def main():
    mode = "Django directly" if DIRECT_TO_DJANGO else f"n8n webhook ({N8N_WEBHOOK_URL})"
    print(f"=== CV Email Poller ===")
    print(f"Gmail: {GMAIL_USER}")
    print(f"Mode: {mode}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print("Press Ctrl+C to stop\n")

    while True:
        try:
            poll_inbox()
        except KeyboardInterrupt:
            print("\nStopped")
            break
        except Exception as e:
            print(f"Error: {e}")

        print(f"\nWaiting {POLL_INTERVAL}s...")
        try:
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\nStopped")
            break


if __name__ == '__main__':
    main()
