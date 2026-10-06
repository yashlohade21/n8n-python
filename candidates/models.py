from django.db import models


class Candidate(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    linkedin_url = models.URLField(blank=True, default='')
    summary = models.TextField(blank=True, default='')
    location = models.CharField(max_length=255, blank=True, default='')
    current_title = models.CharField(max_length=255, blank=True, default='')
    current_company = models.CharField(max_length=255, blank=True, default='')

    resume_file = models.FileField(upload_to='cvs/', blank=True)
    raw_text = models.TextField(blank=True, default='')

    linkedin_headline = models.CharField(max_length=500, blank=True, default='')
    linkedin_summary = models.TextField(blank=True, default='')
    linkedin_connections = models.CharField(max_length=50, blank=True, default='')
    linkedin_enriched = models.BooleanField(default=False)
    linkedin_enriched_at = models.DateTimeField(null=True, blank=True)

    comparison_data = models.JSONField(blank=True, null=True, default=None)

    source_email = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name


class Education(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='education')
    institution = models.CharField(max_length=255)
    degree = models.CharField(max_length=255, blank=True, default='')
    field_of_study = models.CharField(max_length=255, blank=True, default='')
    start_date = models.CharField(max_length=50, blank=True, default='')
    end_date = models.CharField(max_length=50, blank=True, default='')

    def __str__(self):
        return f"{self.degree} - {self.institution}"


class Experience(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='experience')
    company = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    start_date = models.CharField(max_length=50, blank=True, default='')
    end_date = models.CharField(max_length=50, blank=True, default='')

    def __str__(self):
        return f"{self.title} at {self.company}"


class Skill(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='skills')
    name = models.CharField(max_length=100)
    proficiency_level = models.CharField(max_length=50, blank=True, default='')

    def __str__(self):
        return self.name
