from flask import Flask, render_template, request, send_file
import csv
import os
import smtplib
import dns.resolver
import re
import socket
from validate_email_address import validate_email
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"
OUTPUT_FILE = os.path.join(OUTPUT_FOLDER, "emails_output.csv")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def is_valid_format(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def get_mx_records(domain):
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        return sorted([(r.preference, str(r.exchange)) for r in answers], key=lambda x: x[0])
    except Exception:
        return None

def check_smtp(email, mx_records):
    from_address = "check@example.com"
    for _, mx in mx_records:
        try:
            server = smtplib.SMTP(timeout=10)
            server.connect(mx)
            server.helo("example.com")
            server.mail(from_address)
            code, _ = server.rcpt(email)
            server.quit()
            if code in (250, 251):
                return True
        except Exception:
            continue
    return False

def check_email(email):
    if not is_valid_format(email):
        return "NOT ACTIVE"
    if not validate_email(email, verify=False):
        return "NOT ACTIVE"
    domain = email.split('@')[1]
    mx_records = get_mx_records(domain)
    if not mx_records:
        return "NOT ACTIVE"
    return "ACTIVE" if check_smtp(email, mx_records) else "NOT ACTIVE"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename.endswith(".csv"):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            results = []
            with open(filepath, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                if "email" not in reader.fieldnames:
                    return render_template("index.html", error="CSV must have an 'email' header column.")

                for row in reader:
                    email = row['email'].strip()
                    status = check_email(email)
                    results.append({"email": email, "status": status})

            with open(OUTPUT_FILE, "w", newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=["email", "status"])
                writer.writeheader()
                writer.writerows(results)

            return send_file(OUTPUT_FILE, as_attachment=True)

        return render_template("index.html", error="Please upload a valid CSV file.")
    return render_template("index.html")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

