"""
Integration test with REAL Gemini API - no mocks.
Tests: PDF creation → text extraction → Gemini parsing → DB storage → API response.
"""
import os
import sys
import tempfile

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('GEMINI_API_KEY', os.getenv('GEMINI_API_KEY', ''))

# Configure Django with SQLite in-memory
import django
from django.conf import settings
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        INSTALLED_APPS=[
            'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
            'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
            'rest_framework', 'candidates',
        ],
        ROOT_URLCONF='cv_recruiter.urls',
        MIDDLEWARE=[
            'django.middleware.security.SecurityMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        ],
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [],
            'APP_DIRS': True, 'OPTIONS': {'context_processors': [
                'django.template.context_processors.request', 'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ]},
        }],
        REST_FRAMEWORK={'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination', 'PAGE_SIZE': 20},
        SECRET_KEY='test-secret-key-for-testing',
        ALLOWED_HOSTS=['*'],
        GEMINI_API_KEY=os.environ['GEMINI_API_KEY'],
        LINKEDIN_EMAIL='', LINKEDIN_PASSWORD='',
        MEDIA_URL='media/', MEDIA_ROOT=tempfile.mkdtemp(),
        STATIC_URL='static/', DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
    )
django.setup()

# Create tables
from django.core.management import call_command
call_command('migrate', '--run-syncdb', verbosity=0)

from django.test.utils import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from candidates.models import Candidate, Education, Experience, Skill
from candidates.services.file_handler import extract_text
from candidates.services.cv_parser import parse_cv

import fitz  # PyMuPDF


SAMPLE_CV_TEXT = """YASH LOHADE
Software Developer

Contact: yashlohade2502@gmail.com | +91 9403320356
LinkedIn: https://linkedin.com/in/yashlohade
Location: Hyderabad, India

SUMMARY
Passionate full-stack developer with 1+ year of experience building scalable web applications
using Java, Spring Boot, Python, Django, React, and cloud services (AWS). Strong problem-solving
skills with expertise in REST APIs, microservices, and database design.

EXPERIENCE
Software Developer | Win Information Technology | Aug 2025 - Present
- Developed RESTful APIs using Spring Boot and Python FastAPI
- Built responsive frontends with React and Next.js
- Implemented CI/CD pipelines with Docker and AWS
- Worked with PostgreSQL and MongoDB databases

EDUCATION
B.Tech in Computer Science | XYZ Engineering College | 2019 - 2023
- CGPA: 8.5/10
- Relevant coursework: Data Structures, Algorithms, DBMS, OS, Computer Networks

SKILLS
Programming: Python, Java, JavaScript, TypeScript, SQL
Frameworks: Django, Spring Boot, React, FastAPI, Node.js
Tools: Docker, Git, AWS, PostgreSQL, MongoDB, Redis
"""


def create_pdf_from_text(text):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def main():
    print("=" * 60)
    print("END-TO-END TEST WITH REAL GEMINI API")
    print("=" * 60)

    # --- Step 1: Create test PDF ---
    print("\n[1/5] Creating test PDF...")
    pdf_bytes = create_pdf_from_text(SAMPLE_CV_TEXT)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(pdf_bytes)
        pdf_path = f.name
    print(f"  ✓ PDF created ({len(pdf_bytes)} bytes)")

    # --- Step 2: Extract text ---
    print("\n[2/5] Extracting text from PDF...")
    raw_text = extract_text(pdf_path)
    os.unlink(pdf_path)
    assert 'YASH LOHADE' in raw_text, "Name not found in extracted text"
    assert 'yashlohade2502@gmail.com' in raw_text, "Email not found"
    print(f"  ✓ Extracted {len(raw_text)} characters")
    print(f"  Preview: {raw_text[:100]}...")

    # --- Step 3: Parse with REAL Gemini API ---
    print("\n[3/5] Sending to Gemini API for parsing...")
    from django.conf import settings
    settings.GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

    try:
        parsed = parse_cv(raw_text)
    except Exception as e:
        print(f"  ✗ Gemini API call failed: {e}")
        return False

    print(f"  ✓ Gemini returned structured data")
    print(f"    Name:     {parsed.get('full_name')}")
    print(f"    Email:    {parsed.get('email')}")
    print(f"    Phone:    {parsed.get('phone')}")
    print(f"    LinkedIn: {parsed.get('linkedin_url')}")
    print(f"    Title:    {parsed.get('current_title')}")
    print(f"    Company:  {parsed.get('current_company')}")
    print(f"    Location: {parsed.get('location')}")
    print(f"    Skills:   {[s['name'] for s in parsed.get('skills', [])]}")
    print(f"    Edu:      {[e['institution'] for e in parsed.get('education', [])]}")
    print(f"    Exp:      {[e['company'] for e in parsed.get('experience', [])]}")

    # Validate key fields
    assert parsed.get('full_name'), "full_name is empty"
    assert parsed.get('email'), "email is empty"
    assert len(parsed.get('skills', [])) > 0, "no skills parsed"
    print("  ✓ All key fields validated")

    # --- Step 4: Test full API upload with real Gemini ---
    print("\n[4/5] Testing API upload endpoint (real Gemini)...")
    media_tmp = tempfile.mkdtemp()

    from django.test.utils import override_settings
    with override_settings(MEDIA_ROOT=media_tmp):
        from unittest.mock import patch
        # Only mock LinkedIn scraper (no Chrome available), Gemini is REAL
        with patch('candidates.views.enrich_candidate', return_value=False):
            client = APIClient()
            pdf_bytes = create_pdf_from_text(SAMPLE_CV_TEXT)
            upload_file = SimpleUploadedFile('yash_resume.pdf', pdf_bytes, content_type='application/pdf')

            response = client.post(
                '/api/candidates/upload/',
                {'file': upload_file, 'source_email': 'recruiter@company.com'},
                format='multipart',
            )

    if response.status_code == 201:
        data = response.json()
        print(f"  ✓ Upload successful (HTTP 201)")
        print(f"    Candidate ID: {data['id']}")
        print(f"    Name:         {data['full_name']}")
        print(f"    Email:        {data['email']}")
        print(f"    Title:        {data['current_title']}")
        print(f"    Skills:       {len(data['skills'])} skills stored")
        print(f"    Education:    {len(data['education'])} records")
        print(f"    Experience:   {len(data['experience'])} records")
    else:
        print(f"  ✗ Upload failed (HTTP {response.status_code})")
        print(f"    Response: {response.json()}")
        return False

    # --- Step 5: Verify DB records ---
    print("\n[5/5] Verifying database records...")
    candidate = Candidate.objects.get(id=data['id'])
    skills = Skill.objects.filter(candidate=candidate)
    education = Education.objects.filter(candidate=candidate)
    experience = Experience.objects.filter(candidate=candidate)

    print(f"  ✓ Candidate: {candidate.full_name} ({candidate.email})")
    print(f"  ✓ Skills ({skills.count()}): {', '.join(s.name for s in skills)}")
    print(f"  ✓ Education ({education.count()}): {', '.join(e.institution for e in education)}")
    print(f"  ✓ Experience ({experience.count()}): {', '.join(e.company for e in experience)}")
    print(f"  ✓ Resume file saved: {bool(candidate.resume_file)}")
    print(f"  ✓ Raw text stored: {len(candidate.raw_text)} chars")
    print(f"  ✓ Source email: {candidate.source_email}")

    # Test CRUD
    print("\n[BONUS] Testing CRUD endpoints...")
    client = APIClient()

    # List
    r = client.get('/api/candidates/')
    assert r.status_code == 200
    print(f"  ✓ GET /api/candidates/ → {r.json()['count']} candidates")

    # Detail
    r = client.get(f'/api/candidates/{candidate.id}/')
    assert r.status_code == 200
    print(f"  ✓ GET /api/candidates/{candidate.id}/ → {r.json()['full_name']}")

    # Update
    r = client.patch(f'/api/candidates/{candidate.id}/', {'current_title': 'Senior Developer'}, format='json')
    assert r.status_code == 200
    print(f"  ✓ PATCH → title updated to '{r.json()['current_title']}'")

    # Delete
    r = client.delete(f'/api/candidates/{candidate.id}/')
    assert r.status_code == 204
    assert Candidate.objects.count() == 0
    print(f"  ✓ DELETE → candidate removed")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED — END-TO-END PIPELINE WORKING")
    print("=" * 60)
    return True


if __name__ == '__main__':
    main()
