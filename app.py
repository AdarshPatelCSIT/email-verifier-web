from flask import Flask, render_template, request, send_file
import csv
import os
import smtplib
import dns.resolver
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from validate_email_address import validate_email
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"
OUTPUT_FILE = os.path.join(OUTPUT_FOLDER, "emails_output.csv")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

MAX_THREADS = 10
FROM_ADDRESS = "check@example.com"

# Utility Functions
def is_valid_format(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def is_private_domain(domain):
    public_domains = [
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "aol.com", "icloud.com", "live.com", "msn.com", "protonmail.com"
    ]
    return domain.lower() not in public_domains

def get_mx_records(domain):
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=10)
        return sorted([(r.preference, str(r.exchange)) for r in answers], key=lambda x: x[0])
    except Exception:
        return None

def smtp_check(email, mx_records):
    for _, mx in mx_records:
        try:
            server = smtplib.SMTP(mx, timeout=10)
            server.helo("example.com")
            server.mail(FROM_ADDRESS)
            code, _ = server.rcpt(email)
            server.quit()
            if code in (250, 251):
                return "ACTIVE"
        except Exception:
            continue
    return "NOT ACTIVE"

def verify_email(email):
    email = email.strip()
    if not is_valid_format(email):
        return {"email": email, "status": "NOT ACTIVE"}
    if not validate_email(email, verify=False):
        return {"email": email, "status": "NOT ACTIVE"}

    domain = email.split("@")[-1]
    if not is_private_domain(domain):
        return {"email": email, "status": "NOT ACTIVE"}

    mx_records = get_mx_records(domain)
    if not mx_records:
        return {"email": email, "status": "NOT ACTIVE"}

    status = smtp_check(email, mx_records)
    return {"email": email, "status": status}

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename.endswith(".csv"):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            emails = []
            with open(filepath, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                if "email" not in reader.fieldnames:
                    return render_template("index.html", error="CSV must have an 'email' header column.")
                emails = [row["email"].strip() for row in reader]

            results = []
            with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                futures = [executor.submit(verify_email, email) for email in emails]
                for future in as_completed(futures):
                    results.append(future.result())

            with open(OUTPUT_FILE, "w", newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=["email", "status"])
                writer.writeheader()
                writer.writerows(results)

            return send_file(OUTPUT_FILE, as_attachment=True)

        return render_template("index.html", error="Please upload a valid CSV file.")
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
