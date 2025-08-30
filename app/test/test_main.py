# from fastapi.testclient import TestClient
# import pytest
# from app.main import app

# client = TestClient(app)

# def test_health_check():
#     response = client.get("/health")
#     assert response.status_code == 200
#     assert response.json() == {"status": "healthy"}

# def test_upload_document():
#     with open("test_document.pdf", "rb") as f:
#         response = client.post("/upload", files={"file": ("test.pdf", f, "application/pdf")})
#     assert response.status_code == 200

# def test_chat():
#     response = client.post("/chat", json={"message": "What is this document about?", "session_id": "test"})
#     assert response.status_code == 200


import smtplib
from email.mime.text import MIMEText

SMTP_HOST = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = "mddanish867@gmail.com"   # your Brevo login email
SMTP_PASS = "xkeysib-..."             # your Brevo SMTP key
FROM_EMAIL = "paperbrain <mddanish867@gmail.com>"
TO_EMAIL = "mddanish867@gmail.com"

msg = MIMEText("Test email from Paperbrain via Brevo SMTP.")
msg["Subject"] = "SMTP Test"
msg["From"] = FROM_EMAIL
msg["To"] = TO_EMAIL

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
    server.set_debuglevel(1)
    server.ehlo()
    server.starttls()
    server.login(SMTP_USER, SMTP_PASS)
    server.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())

print("✅ Test email sent successfully")
