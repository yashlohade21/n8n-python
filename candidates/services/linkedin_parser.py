import json
import logging
import re
import time
from django.conf import settings
from groq import Groq

logger = logging.getLogger(__name__)

LINKEDIN_PARSE_PROMPT = """You are given raw text scraped from a LinkedIn public profile page.
Extract structured information and return ONLY valid JSON (no markdown fences):

{
  "full_name": "",
  "headline": "",
  "location": "",
  "summary": "",
  "current_title": "",
  "current_company": "",
  "skills": ["skill1", "skill2"],
  "education": [{"institution": "", "degree": "", "field": "", "start": "", "end": ""}],
  "experience": [{"company": "", "title": "", "description": "", "start": "", "end": ""}],
  "connections": ""
}

Rules:
- Extract everything available. Use empty string "" for missing fields.
- For skills, return just the names as strings.
- Return ONLY the JSON object.

LinkedIn profile text:
"""


def _fetch_via_cdp(url: str) -> str:
    """Fetch LinkedIn page via Chrome DevTools Protocol (connects to running Chrome on port 9222)."""
    import requests as req
    import websocket

    target_id = None
    try:
        # Create a new tab with the LinkedIn URL
        resp = req.put(f'http://127.0.0.1:9222/json/new?{url}', timeout=5)
        target = resp.json()
        target_id = target.get('id')
        ws_url = target.get('webSocketDebuggerUrl')

        if not ws_url:
            return ""

        time.sleep(6)  # Wait for page load + JS rendering

        ws = websocket.create_connection(ws_url, timeout=15)

        # Get page text via JS
        ws.send(json.dumps({
            'id': 1, 'method': 'Runtime.evaluate',
            'params': {'expression': 'document.body.innerText'}
        }))
        result = json.loads(ws.recv())

        ws.close()

        # Close the tab to avoid accumulating targets
        if target_id:
            try:
                req.get(f'http://127.0.0.1:9222/json/close/{target_id}', timeout=3)
            except Exception:
                pass

        text = result.get('result', {}).get('result', {}).get('value', '')
        text = re.sub(r'\s+', ' ', text).strip()

        # Check for login wall
        if len(text) < 500 and ('Join LinkedIn' in text or 'Agree & Join' in text):
            return ""
        if "This page doesn" in text:
            return ""

        return text[:15000]

    except Exception as e:
        logger.debug("CDP fetch failed: %s", e)
        # Clean up tab on error
        if target_id:
            try:
                import requests as req2
                req2.get(f'http://127.0.0.1:9222/json/close/{target_id}', timeout=3)
            except Exception:
                pass
        return ""


def _fetch_via_selenium(url: str) -> str:
    """Fallback: fetch via headless Selenium."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            driver.get(url)
            time.sleep(4)
            text = driver.find_element("tag name", "body").text
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) < 500 and 'Join LinkedIn' in text:
                return ""
            return text[:15000]
        finally:
            driver.quit()

    except Exception as e:
        logger.debug("Selenium fetch failed: %s", e)
        return ""


def fetch_linkedin_public(url: str) -> str:
    """Fetch LinkedIn profile text. Tries CDP first (uses logged-in Chrome), then Selenium."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    url = url.replace("://linkedin.com", "://www.linkedin.com")

    # Try CDP first (Chrome MCP with LinkedIn session)
    text = _fetch_via_cdp(url)
    if text:
        logger.info("LinkedIn fetched via CDP (%d chars)", len(text))
        return text

    # Fallback to Selenium
    text = _fetch_via_selenium(url)
    if text:
        logger.info("LinkedIn fetched via Selenium (%d chars)", len(text))
        return text

    return ""


def parse_linkedin_with_gemini(profile_text: str) -> dict:
    """Parse LinkedIn profile text using Groq LLM."""
    if not profile_text or not settings.GROQ_API_KEY:
        return {}

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model='openai/gpt-oss-120b',
        messages=[{'role': 'user', 'content': LINKEDIN_PARSE_PROMPT + profile_text}],
        temperature=0.1,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content.strip()

    if raw.startswith('```'):
        raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
    if raw.endswith('```'):
        raw = raw[:-3]
    if raw.startswith('json'):
        raw = raw[4:]
    if '<think>' in raw:
        raw = raw.split('</think>')[-1].strip()
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Failed to parse LinkedIn Groq response: %s", raw[:500])
        return {}


def compare_profiles(resume_data: dict, linkedin_data: dict) -> dict:
    """Compare resume vs LinkedIn profile and return match analysis."""
    if not linkedin_data:
        return {"overall_match": 0, "fields": {}, "available": False}

    fields = {}

    # Name match
    r_name = (resume_data.get('full_name') or '').strip().lower()
    l_name = (linkedin_data.get('full_name') or '').strip().lower()
    if r_name and l_name:
        r_parts = set(r_name.split())
        l_parts = set(l_name.split())
        overlap = r_parts & l_parts
        score = len(overlap) / max(len(r_parts), len(l_parts)) * 100 if overlap else 0
        fields['name'] = {
            'resume': resume_data.get('full_name', ''),
            'linkedin': linkedin_data.get('full_name', ''),
            'match': round(score),
            'status': 'match' if score >= 80 else 'partial' if score > 0 else 'mismatch',
        }
    else:
        fields['name'] = {
            'resume': resume_data.get('full_name', ''),
            'linkedin': linkedin_data.get('full_name', ''),
            'match': 0, 'status': 'missing',
        }

    # Title match
    r_title = (resume_data.get('current_title') or '').strip().lower()
    l_title = (linkedin_data.get('current_title') or linkedin_data.get('headline') or '').strip().lower()
    if r_title and l_title:
        r_words = set(r_title.split())
        l_words = set(l_title.split())
        overlap = r_words & l_words
        score = len(overlap) / max(len(r_words), len(l_words), 1) * 100
        fields['title'] = {
            'resume': resume_data.get('current_title', ''),
            'linkedin': linkedin_data.get('current_title') or linkedin_data.get('headline', ''),
            'match': round(score), 'status': 'match' if score >= 70 else 'partial' if score > 0 else 'mismatch',
        }
    else:
        fields['title'] = {
            'resume': resume_data.get('current_title', ''),
            'linkedin': linkedin_data.get('current_title') or linkedin_data.get('headline', ''),
            'match': 0, 'status': 'missing',
        }

    # Company match
    r_company = (resume_data.get('current_company') or '').strip().lower()
    l_company = (linkedin_data.get('current_company') or '').strip().lower()
    if r_company and l_company:
        score = 100 if r_company == l_company else (
            80 if r_company in l_company or l_company in r_company else 0)
        fields['company'] = {
            'resume': resume_data.get('current_company', ''),
            'linkedin': linkedin_data.get('current_company', ''),
            'match': score, 'status': 'match' if score >= 80 else 'partial' if score > 0 else 'mismatch',
        }
    else:
        fields['company'] = {
            'resume': resume_data.get('current_company', ''),
            'linkedin': linkedin_data.get('current_company', ''),
            'match': 0, 'status': 'missing',
        }

    # Location match
    r_loc = (resume_data.get('location') or '').strip().lower()
    l_loc = (linkedin_data.get('location') or '').strip().lower()
    if r_loc and l_loc:
        r_parts = set(re.split(r'[,\s]+', r_loc))
        l_parts = set(re.split(r'[,\s]+', l_loc))
        overlap = r_parts & l_parts
        score = len(overlap) / max(len(r_parts), len(l_parts), 1) * 100
        fields['location'] = {
            'resume': resume_data.get('location', ''),
            'linkedin': linkedin_data.get('location', ''),
            'match': round(score), 'status': 'match' if score >= 50 else 'partial' if score > 0 else 'mismatch',
        }
    else:
        fields['location'] = {
            'resume': resume_data.get('location', ''),
            'linkedin': linkedin_data.get('location', ''),
            'match': 0, 'status': 'missing',
        }

    # Skills match
    r_skills = set(s.get('name', '').lower() if isinstance(s, dict) else s.lower()
                   for s in resume_data.get('skills', []) if s)
    l_skills = set(s.lower() if isinstance(s, str) else (s.get('name', '').lower() if isinstance(s, dict) else '')
                   for s in linkedin_data.get('skills', []) if s)
    if r_skills and l_skills:
        common = r_skills & l_skills
        only_resume = r_skills - l_skills
        only_linkedin = l_skills - r_skills
        score = len(common) / max(len(r_skills | l_skills), 1) * 100
        fields['skills'] = {
            'resume': sorted(r_skills), 'linkedin': sorted(l_skills),
            'common': sorted(common), 'only_resume': sorted(only_resume),
            'only_linkedin': sorted(only_linkedin),
            'match': round(score), 'status': 'match' if score >= 60 else 'partial' if score > 0 else 'mismatch',
        }
    else:
        fields['skills'] = {
            'resume': sorted(r_skills), 'linkedin': sorted(l_skills),
            'common': [], 'only_resume': sorted(r_skills), 'only_linkedin': sorted(l_skills),
            'match': 0, 'status': 'missing',
        }

    # Experience match
    r_exps = set((e.get('company', '') or '').lower() for e in resume_data.get('experience', []) if e.get('company'))
    l_exps = set((e.get('company', '') or '').lower() for e in linkedin_data.get('experience', []) if e.get('company'))
    if r_exps and l_exps:
        common_exp = r_exps & l_exps
        score = len(common_exp) / max(len(r_exps | l_exps), 1) * 100
        fields['experience'] = {
            'resume': sorted(r_exps), 'linkedin': sorted(l_exps), 'common': sorted(common_exp),
            'match': round(score), 'status': 'match' if score >= 60 else 'partial' if score > 0 else 'mismatch',
        }
    else:
        fields['experience'] = {
            'resume': sorted(r_exps), 'linkedin': sorted(l_exps), 'common': [],
            'match': 0, 'status': 'missing',
        }

    # Education match
    r_edu = set((e.get('institution', '') or '').lower() for e in resume_data.get('education', []) if e.get('institution'))
    l_edu = set((e.get('institution', '') or '').lower() for e in linkedin_data.get('education', []) if e.get('institution'))
    if r_edu and l_edu:
        common_edu = r_edu & l_edu
        score = len(common_edu) / max(len(r_edu | l_edu), 1) * 100
        fields['education'] = {
            'resume': sorted(r_edu), 'linkedin': sorted(l_edu), 'common': sorted(common_edu),
            'match': round(score), 'status': 'match' if score >= 50 else 'partial' if score > 0 else 'mismatch',
        }
    else:
        fields['education'] = {
            'resume': sorted(r_edu), 'linkedin': sorted(l_edu), 'common': [],
            'match': 0, 'status': 'missing',
        }

    # Overall match (weighted)
    weights = {'name': 15, 'title': 20, 'company': 15, 'location': 5, 'skills': 25, 'experience': 10, 'education': 10}
    total_weight = sum(weights.values())
    weighted_score = sum(fields[k]['match'] * weights[k] for k in weights if k in fields)
    overall = round(weighted_score / total_weight)

    return {'overall_match': overall, 'fields': fields, 'available': True}
