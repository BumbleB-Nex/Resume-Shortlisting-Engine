"""
Create data/jd/Sample_JD.pdf — a realistic Junior Full Stack Developer
Intern JD for the fictional TechNova Solutions, mirroring the hackathon
brief. Replace with the official Sample_JD.pdf when it is provided.

Run:  python scripts/make_sample_jd.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import JD_DIR  # noqa: E402

JD_TEXT = """TechNova Solutions
Junior Full Stack Developer Intern

Location: Bengaluru (Hybrid) | Duration: 6 months | Stipend: INR 25,000 / month

About TechNova Solutions
TechNova Solutions builds SaaS products for small and medium businesses. Our
engineering team ships web applications used by thousands of customers every day.

About the Role
We are looking for a Junior Full Stack Developer Intern to join our product
engineering team. You will work alongside senior engineers to design, build and
ship features across the stack, from responsive user interfaces to backend APIs
and databases.

Responsibilities
- Build responsive, accessible user interfaces using modern JavaScript frameworks
- Develop and maintain RESTful backend services and integrate them with the frontend
- Design database schemas and write efficient queries
- Write unit tests and participate in code reviews
- Collaborate with designers and product managers in an agile team
- Debug, troubleshoot and improve the performance of existing features

Required Skills
- Strong understanding of JavaScript (ES6+), HTML and CSS
- Experience with React or a similar frontend framework
- Experience building backend services with Node.js
- Understanding of REST APIs and JSON
- Working knowledge of SQL databases such as PostgreSQL or MySQL
- Familiarity with Git and GitHub workflows
- Good problem-solving and communication skills

Preferred Skills
- Experience with TypeScript
- Exposure to MongoDB or other NoSQL databases
- Familiarity with Docker and basic CI/CD pipelines
- Experience deploying applications to AWS or another cloud platform
- Knowledge of unit testing frameworks such as Jest
- Personal projects or open-source contributions demonstrating full-stack work

Eligibility
- Currently pursuing a Bachelor's degree in Computer Science, IT or a related field
- Available for a 6-month internship starting January 2027

What We Offer
- Mentorship from senior engineers
- Opportunity to convert to a full-time role
- Flexible hybrid working
"""


def main() -> None:
    JD_DIR.mkdir(parents=True, exist_ok=True)
    out = JD_DIR / "Sample_JD.pdf"
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 545, 790)
    remaining = JD_TEXT
    while remaining:
        overflow = page.insert_textbox(rect, remaining, fontsize=10.5, fontname="helv", lineheight=1.25)
        if overflow >= 0:
            break
        # crude split: move roughly half the text to the next page
        lines = remaining.split("\n")
        cut = len(lines) // 2
        page.insert_textbox(rect, "\n".join(lines[:cut]), fontsize=10.5, fontname="helv", lineheight=1.25)
        remaining = "\n".join(lines[cut:])
        page = doc.new_page()
    doc.save(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
