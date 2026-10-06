from rest_framework import serializers
from .models import Candidate, Education, Experience, Skill


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = ['id', 'institution', 'degree', 'field_of_study', 'start_date', 'end_date']


class ExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experience
        fields = ['id', 'company', 'title', 'description', 'start_date', 'end_date']


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ['id', 'name', 'proficiency_level']


class CandidateSerializer(serializers.ModelSerializer):
    education = EducationSerializer(many=True, read_only=True)
    experience = ExperienceSerializer(many=True, read_only=True)
    skills = SkillSerializer(many=True, read_only=True)

    class Meta:
        model = Candidate
        fields = [
            'id', 'full_name', 'email', 'phone', 'linkedin_url',
            'summary', 'location', 'current_title', 'current_company',
            'resume_file', 'linkedin_headline', 'linkedin_summary',
            'linkedin_connections', 'linkedin_enriched', 'linkedin_enriched_at',
            'comparison_data',
            'source_email', 'created_at', 'updated_at',
            'education', 'experience', 'skills',
        ]
        read_only_fields = ['created_at', 'updated_at']


class CandidateUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    source_email = serializers.CharField(required=False, default='')
    linkedin_text = serializers.CharField(required=False, default='')
