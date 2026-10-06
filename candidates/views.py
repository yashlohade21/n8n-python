import logging
import os
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Candidate, Education, Experience, Skill
from .serializers import CandidateSerializer, CandidateUploadSerializer
from .services.file_handler import extract_text
from .services.cv_parser import parse_cv
from .services.linkedin_parser import fetch_linkedin_public, parse_linkedin_with_gemini, compare_profiles

logger = logging.getLogger(__name__)


@api_view(['POST'])
def upload_cv(request):
    serializer = CandidateUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    uploaded_file = serializer.validated_data['file']
    source_email = serializer.validated_data.get('source_email', '')

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ('.pdf', '.docx', '.doc'):
        return Response(
            {'error': 'Unsupported file type. Please upload a PDF or DOCX file.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    candidate = Candidate(source_email=source_email)
    candidate.resume_file.save(uploaded_file.name, uploaded_file, save=True)

    try:
        file_path = candidate.resume_file.path
        raw_text = extract_text(file_path)
        candidate.raw_text = raw_text
        candidate.save()

        parsed = parse_cv(raw_text)

        candidate.full_name = parsed.get('full_name', '') or 'Unknown'
        candidate.email = parsed.get('email', '')
        candidate.phone = parsed.get('phone', '')
        candidate.linkedin_url = parsed.get('linkedin_url', '')
        candidate.summary = parsed.get('summary', '')
        candidate.location = parsed.get('location', '')
        candidate.current_title = parsed.get('current_title', '')
        candidate.current_company = parsed.get('current_company', '')
        candidate.save()

        for skill_data in parsed.get('skills', []):
            if skill_data.get('name'):
                Skill.objects.create(
                    candidate=candidate,
                    name=skill_data['name'],
                    proficiency_level=skill_data.get('proficiency', ''),
                )

        for edu_data in parsed.get('education', []):
            if edu_data.get('institution'):
                Education.objects.create(
                    candidate=candidate,
                    institution=edu_data['institution'],
                    degree=edu_data.get('degree', ''),
                    field_of_study=edu_data.get('field', ''),
                    start_date=edu_data.get('start', ''),
                    end_date=edu_data.get('end', ''),
                )

        for exp_data in parsed.get('experience', []):
            if exp_data.get('company'):
                Experience.objects.create(
                    candidate=candidate,
                    company=exp_data['company'],
                    title=exp_data.get('title', ''),
                    description=exp_data.get('description', ''),
                    start_date=exp_data.get('start', ''),
                    end_date=exp_data.get('end', ''),
                )

        # LinkedIn comparison
        linkedin_data = {}
        comparison = {'overall_match': 0, 'fields': {}, 'available': False}
        linkedin_text_input = serializer.validated_data.get('linkedin_text', '')

        def _enrich_from_linkedin(text_data):
            nonlocal linkedin_data, comparison
            linkedin_data = parse_linkedin_with_gemini(text_data)
            if linkedin_data:
                comparison = compare_profiles(parsed, linkedin_data)
                candidate.linkedin_enriched = True
                candidate.linkedin_headline = linkedin_data.get('headline', '')
                candidate.linkedin_summary = linkedin_data.get('summary', '')
                candidate.linkedin_connections = linkedin_data.get('connections', '')
                from django.utils import timezone
                candidate.linkedin_enriched_at = timezone.now()
                candidate.save()

        if linkedin_text_input:
            try:
                _enrich_from_linkedin(linkedin_text_input)
            except Exception as e:
                logger.warning("LinkedIn text parsing failed: %s", e)
        elif candidate.linkedin_url:
            try:
                page_text = fetch_linkedin_public(candidate.linkedin_url)
                # If original URL failed, try with hyphens between name parts
                if not page_text and '/in/' in candidate.linkedin_url:
                    import re as _re
                    slug = candidate.linkedin_url.split('/in/')[-1].strip('/')
                    # Try adding hyphens: yashlohade -> yash-lohade
                    name = parsed.get('full_name', '').strip().lower()
                    if name:
                        hyphenated_slug = '-'.join(name.split())
                        if hyphenated_slug != slug:
                            alt_url = candidate.linkedin_url.replace(f'/in/{slug}', f'/in/{hyphenated_slug}')
                            logger.info("Trying alternate LinkedIn URL: %s", alt_url)
                            page_text = fetch_linkedin_public(alt_url)
                            if page_text:
                                candidate.linkedin_url = alt_url
                                candidate.save()
                if page_text:
                    _enrich_from_linkedin(page_text)
            except Exception as e:
                logger.warning("LinkedIn comparison failed: %s", e)

        candidate.comparison_data = comparison
        candidate.save()

        candidate.refresh_from_db()
        result = CandidateSerializer(candidate).data
        result['resume_parsed'] = parsed
        result['linkedin_parsed'] = linkedin_data
        result['comparison'] = comparison

        return Response(result, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error("CV processing failed: %s", e)
        if not candidate.full_name:
            candidate.full_name = f"Parse Error - {uploaded_file.name}"
            candidate.save()
        return Response(
            {'error': str(e), 'candidate_id': candidate.id},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


@api_view(['GET'])
def health_check(request):
    try:
        count = Candidate.objects.count()
        return Response({'status': 'ok', 'candidates': count})
    except Exception as e:
        return Response({'status': 'error', 'error': str(e)}, status=500)


class CandidateViewSet(viewsets.ModelViewSet):
    queryset = Candidate.objects.prefetch_related('education', 'experience', 'skills').all()
    serializer_class = CandidateSerializer
