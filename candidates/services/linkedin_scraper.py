import logging
from django.conf import settings
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


def _get_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        'user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def scrape_linkedin_profile(linkedin_url: str) -> dict:
    """
    Scrape public LinkedIn profile data.
    Returns dict with headline, summary, etc. or empty dict on failure.
    Note: LinkedIn aggressively blocks scraping. This works best for
    public profiles without login walls.
    """
    if not linkedin_url:
        return {}

    driver = None
    try:
        driver = _get_driver()
        driver.get(linkedin_url)

        wait = WebDriverWait(driver, 10)

        data = {
            'linkedin_headline': '',
            'linkedin_summary': '',
            'linkedin_connections': '',
            'linkedin_enriched': True,
            'linkedin_enriched_at': timezone.now(),
        }

        # Try to extract headline
        try:
            headline_el = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.top-card-layout__headline'))
            )
            data['linkedin_headline'] = headline_el.text.strip()
        except Exception:
            logger.debug("Could not extract LinkedIn headline")

        # Try to extract summary/about
        try:
            about_section = driver.find_element(
                By.CSS_SELECTOR, 'section.summary .core-section-container__content'
            )
            data['linkedin_summary'] = about_section.text.strip()
        except Exception:
            logger.debug("Could not extract LinkedIn summary")

        # Try to extract connections
        try:
            connections_el = driver.find_element(
                By.CSS_SELECTOR, '.top-card-layout__connections'
            )
            data['linkedin_connections'] = connections_el.text.strip()
        except Exception:
            logger.debug("Could not extract LinkedIn connections")

        return data

    except Exception as e:
        logger.warning("LinkedIn scraping failed for %s: %s", linkedin_url, e)
        return {}

    finally:
        if driver:
            driver.quit()


def enrich_candidate(candidate):
    """Enrich a candidate model instance with LinkedIn data."""
    if not candidate.linkedin_url:
        return False

    data = scrape_linkedin_profile(candidate.linkedin_url)
    if not data:
        return False

    for key, value in data.items():
        setattr(candidate, key, value)
    candidate.save()
    return True
