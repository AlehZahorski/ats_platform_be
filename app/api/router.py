from fastapi import APIRouter

from app.modules.admins.router import router as admin_auth_router
from app.modules.admins.usage_router import router as admin_usage_router
from app.modules.applications.router import router as applications_router
from app.modules.articles.admin_router import router as admin_articles_router
from app.modules.articles.company_router import router as company_articles_router
from app.modules.articles.public_router import router as articles_public_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.automation.router import router as automation_router
from app.modules.candidates.router import router as candidates_router
from app.modules.companies.public_router import router as companies_public_router
from app.modules.companies.router import router as companies_router
from app.modules.consents.router import router as gdpr_router
from app.modules.email_templates.router import router as email_templates_router
from app.modules.forms.router import router as forms_router
from app.modules.interviews.router import router as interviews_router
from app.modules.jobs.router import router as jobs_router
from app.modules.llm_usage.router import router as llm_usage_router
from app.modules.notes.router import router as notes_router
from app.modules.organizer.router import router as organizer_router
from app.modules.partners.admin_router import router as admin_partners_router
from app.modules.partners.public_router import router as presentation_public_router
from app.modules.pipeline.router import router as pipeline_router
from app.modules.reports.router import router as reports_router
from app.modules.reviews.router import router as reviews_router
from app.modules.tags.router import router as tags_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(companies_router, prefix="/company", tags=["Company"])
api_router.include_router(companies_public_router, prefix="/companies", tags=["Companies (public)"])
api_router.include_router(articles_public_router, prefix="/articles", tags=["Articles (public)"])
api_router.include_router(admin_auth_router, prefix="/admin/auth", tags=["Admin auth"])
api_router.include_router(admin_articles_router, prefix="/admin/articles", tags=["Admin: Articles"])
api_router.include_router(admin_usage_router, prefix="/admin/usage", tags=["Admin: Usage"])
api_router.include_router(admin_partners_router, prefix="/admin/partners", tags=["Admin: Partners"])
api_router.include_router(
    presentation_public_router, prefix="/presentation", tags=["Presentation (public)"]
)
api_router.include_router(
    company_articles_router, prefix="/company/articles", tags=["Company: Articles"]
)
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(forms_router, prefix="/forms", tags=["Forms"])
api_router.include_router(applications_router, prefix="/applications", tags=["Applications"])
api_router.include_router(pipeline_router, prefix="/pipeline", tags=["Pipeline"])
api_router.include_router(notes_router, prefix="/notes", tags=["Notes"])
api_router.include_router(tags_router, prefix="/tags", tags=["Tags"])
api_router.include_router(audit_router, prefix="/audit", tags=["Audit"])
api_router.include_router(
    email_templates_router, prefix="/email-templates", tags=["Email Templates"]
)
api_router.include_router(automation_router, prefix="/automations", tags=["Automations"])
api_router.include_router(interviews_router, prefix="/interviews", tags=["Interviews"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(organizer_router, prefix="/organizer", tags=["Organizer"])
api_router.include_router(candidates_router, prefix="/candidates", tags=["Candidates"])
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(gdpr_router, prefix="/gdpr", tags=["GDPR"])
api_router.include_router(reviews_router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(llm_usage_router, prefix="/llm-usage", tags=["LLM Usage"])
