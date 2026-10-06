from django.contrib import admin
from .models import Candidate, Education, Experience, Skill


class EducationInline(admin.TabularInline):
    model = Education
    extra = 0


class ExperienceInline(admin.TabularInline):
    model = Experience
    extra = 0


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 0


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'current_title', 'current_company',
                    'linkedin_enriched', 'source_email', 'created_at']
    list_filter = ['linkedin_enriched', 'created_at']
    search_fields = ['full_name', 'email', 'current_title', 'skills__name']
    readonly_fields = ['created_at', 'updated_at', 'raw_text']
    inlines = [SkillInline, ExperienceInline, EducationInline]

    fieldsets = (
        ('Personal Info', {
            'fields': ('full_name', 'email', 'phone', 'location', 'summary')
        }),
        ('Professional', {
            'fields': ('current_title', 'current_company', 'linkedin_url')
        }),
        ('LinkedIn Enrichment', {
            'fields': ('linkedin_headline', 'linkedin_summary',
                       'linkedin_connections', 'linkedin_enriched', 'linkedin_enriched_at'),
            'classes': ('collapse',),
        }),
        ('Source', {
            'fields': ('resume_file', 'source_email', 'raw_text', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'institution', 'degree', 'field_of_study']


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'company', 'title', 'start_date', 'end_date']


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'name', 'proficiency_level']
    list_filter = ['proficiency_level']
    search_fields = ['name']
