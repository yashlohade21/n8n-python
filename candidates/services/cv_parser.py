import json
import logging
from groq import Groq
from django.conf import settings

logger = logging.getLogger(__name__)

PARSE_PROMPT = """You are a CV/resume parser. Extract structured information from the following resume text.
Return ONLY valid JSON (no markdown fences) with this exact structure:

{
  "full_name": "",
  "email": "",
  "phone": "",
  "linkedin_url": "",
  "summary": "",
  "location": "",
  "current_title": "",
  "current_company": "",
  "skills": [{"name": "", "proficiency": ""}],
  "education": [{"institution": "", "degree": "", "field": "", "start": "", "end": ""}],
  "experience": [{"company": "", "title": "", "description": "", "start": "", "end": ""}]
}

Rules:
- Extract all available information. Use empty string "" for missing fields.
- For skills proficiency, use: beginner, intermediate, advanced, or expert.
- For dates, use the format as found in the CV (e.g. "Jan 2023", "2023", "Present").
- linkedin_url should be the full URL if found (e.g. https://linkedin.com/in/username or https://www.linkedin.com/in/username). Look for patterns like "linkedin.com/in/..." anywhere in the text. Always return the complete URL with https://.
- Return ONLY the JSON object, no other text.

Resume text:
"""


def parse_cv(text: str) -> dict:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not configured")

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model='openai/gpt-oss-120b',
        messages=[{'role': 'user', 'content': PARSE_PROMPT + text}],
        temperature=0.1,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
    if raw.endswith('```'):
        raw = raw[:-3]
    if raw.startswith('json'):
        raw = raw[4:]
    # Strip thinking tags if present
    if '<think>' in raw:
        raw = raw.split('</think>')[-1].strip()
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Failed to parse Groq response: %s", raw[:500])
        raise ValueError("LLM returned invalid JSON")
