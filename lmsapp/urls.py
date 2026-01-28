from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'courses', views.CourseViewSet, basename='course')
router.register(r'lessons', views.LessonViewSet, basename='lesson')
router.register(r'enrollments', views.EnrollmentViewSet, basename='enrollment')
router.register(r'course-progress', views.CourseProgressViewSet, basename='course-progress')
router.register(r'student-progress-reports', views.StudentProgressReportViewSet, basename='student-progress-report')
router.register(r'lesson-progress', views.LessonProgressViewSet, basename='lesson-progress')
router.register(r'quizzes', views.QuizViewSet, basename='quiz')
router.register(r'questions', views.QuestionViewSet, basename='question')
router.register(r'quiz-attempts', views.QuizAttemptViewSet, basename='quiz-attempt')
router.register(r'certificates', views.CertificateViewSet, basename='certificate')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', views.UserRegistrationView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('dashboard/instructor/', views.InstructorDashboardView.as_view(), name='instructor-dashboard'),
    path('dashboard/student/', views.StudentDashboardView.as_view(), name='student-dashboard'),
    
    # Specific endpoints
    path('quizzes/<int:quiz_id>/attempt/', views.QuizAttemptViewSet.as_view({'post': 'create'}), name='quiz-attempt'),
    path('quiz-attempts/quiz/<int:quiz_id>/history/', views.QuizAttemptViewSet.as_view({'get': 'quiz_attempt_history'}), name='quiz-attempt-history'),
    
    # Certificate endpoints
    path('certificates/verify/<str:certificate_id>/', views.CertificateViewSet.as_view({'get': 'verify'}), name='verify-certificate'),
    path('certificates/regenerate/', views.CertificateViewSet.as_view({'post': 'regenerate'}), name='regenerate-certificate'),
    
    # Analytics and activity
    path('courses/<int:course_id>/analytics/', views.CourseAnalyticsView.as_view(), name='course-analytics'),
    path('activity/', views.StudentActivityView.as_view(), name='student-activity'),
]