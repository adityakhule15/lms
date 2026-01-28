from rest_framework import viewsets, status, generics, mixins, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from django.db.models import Q, Count, Avg, Case, When, IntegerField, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from django.template.loader import render_to_string
import uuid
import json
from datetime import datetime

from .models import *
from .serializers import *

# Custom Permissions
class IsInstructor(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_instructor()

class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_student()

class IsCourseInstructorOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.instructor == request.user

# Authentication Views
class UserRegistrationView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    authentication_classes = []
    permission_classes = []
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Course Views
class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'category', 'instructor__username']
    ordering_fields = ['created_at', 'price', 'duration_hours', 'average_rating']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CourseCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return CourseUpdateSerializer
        elif self.action == 'retrieve':
            return CourseDetailSerializer
        return CourseSerializer
    
    def perform_create(self, serializer):
        if not self.request.user.is_instructor():
            raise PermissionDenied("Only instructors can create courses")
        serializer.save(instructor=self.request.user)
    
    def get_queryset(self):
        user = self.request.user
        if user.is_instructor():
            return Course.objects.filter(instructor=user)
        elif user.is_student():
            # Show all published courses for students
            return Course.objects.filter(is_published=True)
        return Course.objects.none()
    
    def retrieve(self, request, *args, **kwargs):
        """
        Get single course with enrollment status and progress
        """
        instance = self.get_object()
        user = request.user
        
        # Get enrollment status if user is a student
        is_enrolled = False
        enrollment = None
        progress_percentage = 0
        completed_lessons = 0
        certificate = None
        
        if user.is_student():
            enrollment = Enrollment.objects.filter(
                student=user,
                course=instance
            ).first()
            
            if enrollment:
                is_enrolled = True
                total_lessons = instance.total_lessons()
                completed_lessons = LessonProgress.objects.filter(
                    enrollment=enrollment,
                    completed=True
                ).count()
                
                if total_lessons > 0:
                    progress_percentage = round((completed_lessons / total_lessons) * 100, 2)
                
                # Check for certificate
                certificate = Certificate.objects.filter(
                    student=user,
                    course=instance
                ).first()
        
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # Add enrollment information
        data['is_enrolled'] = is_enrolled
        data['enrollment'] = EnrollmentSerializer(enrollment).data if enrollment else None
        data['progress'] = {
            'completed_lessons': completed_lessons,
            'total_lessons': instance.total_lessons(),
            'percentage': progress_percentage,
            'is_completed': enrollment.completed if enrollment else False
        }
        data['certificate'] = CertificateSerializer(certificate).data if certificate else None
        
        # Add detailed lesson information with progress
        lessons = instance.lessons.all().order_by('order')
        lesson_details = []
        for lesson in lessons:
            lesson_progress = LessonProgress.objects.filter(
                student=user,
                lesson=lesson,
                enrollment=enrollment
            ).first()
            
            # Check if lesson has quiz
            has_quiz = Quiz.objects.filter(lesson=lesson).exists()
            quiz_completed = False
            if has_quiz:
                quiz = Quiz.objects.filter(lesson=lesson).first()
                quiz_completed = QuizAttempt.objects.filter(
                    student=user,
                    quiz=quiz,
                    passed=True
                ).exists()
            
            lesson_details.append({
                'id': lesson.id,
                'title': lesson.title,
                'description': lesson.description,
                'content_type': lesson.content_type,
                'content': lesson.content,
                'video_url': lesson.video_url,
                'order': lesson.order,
                'duration_minutes': lesson.duration_minutes,
                'has_quiz': has_quiz,
                'quiz_completed': quiz_completed,
                'progress': {
                    'completed': lesson_progress.completed if lesson_progress else False,
                    'completed_at': lesson_progress.completed_at if lesson_progress else None,
                    'last_accessed': lesson_progress.last_accessed if lesson_progress else None
                }
            })
        
        data['lessons_with_progress'] = lesson_details
        
        return Response(data)
    
    @action(detail=False, methods=['get'])
    def enrolled_courses(self, request):
        """Get courses where student is enrolled"""
        if not request.user.is_student():
            raise PermissionDenied("Only students can view enrolled courses")
        
        enrollments = Enrollment.objects.filter(student=request.user)
        courses_data = []
        
        for enrollment in enrollments:
            course = enrollment.course
            total_lessons = course.total_lessons()
            completed_lessons = LessonProgress.objects.filter(
                enrollment=enrollment,
                completed=True
            ).count()
            
            progress_percentage = 0
            if total_lessons > 0:
                progress_percentage = round((completed_lessons / total_lessons) * 100, 2)
            
            course_data = CourseSerializer(course).data
            course_data['progress'] = {
                'completed_lessons': completed_lessons,
                'total_lessons': total_lessons,
                'percentage': progress_percentage,
                'is_completed': enrollment.completed
            }
            course_data['enrollment_date'] = enrollment.enrolled_at
            course_data['last_accessed'] = LessonProgress.objects.filter(
                enrollment=enrollment
            ).order_by('-last_accessed').first().last_accessed if LessonProgress.objects.filter(enrollment=enrollment).exists() else None
            
            courses_data.append(course_data)
        
        return Response(courses_data)
    
    @action(detail=False, methods=['get'])
    def available_courses(self, request):
        """Get courses available for enrollment (not enrolled yet)"""
        if not request.user.is_student():
            raise PermissionDenied("Only students can view available courses")
        
        enrolled_courses = Enrollment.objects.filter(student=request.user).values_list('course_id', flat=True)
        courses = Course.objects.filter(is_published=True).exclude(id__in=enrolled_courses)
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        """Enroll in a course"""
        if not request.user.is_student():
            raise PermissionDenied("Only students can enroll in courses")
        
        course = self.get_object()
        
        # Check if already enrolled
        if Enrollment.objects.filter(student=request.user, course=course).exists():
            enrollment = Enrollment.objects.get(student=request.user, course=course)
            return Response({
                'message': 'Already enrolled in this course',
                'enrollment': EnrollmentSerializer(enrollment).data
            }, status=status.HTTP_200_OK)
        
        # Check if course is published
        if not course.is_published:
            return Response({
                'error': 'This course is not available for enrollment'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create enrollment
        enrollment = Enrollment.objects.create(
            student=request.user,
            course=course
        )
        
        # Create lesson progress entries for all lessons
        lessons = course.lessons.all()
        for lesson in lessons:
            LessonProgress.objects.create(
                student=request.user,
                lesson=lesson,
                enrollment=enrollment
            )
        
        return Response({
            'message': 'Successfully enrolled in the course',
            'enrollment': EnrollmentSerializer(enrollment).data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def unenroll(self, request, pk=None):
        """Unenroll from a course"""
        if not request.user.is_student():
            raise PermissionDenied("Only students can unenroll from courses")
        
        course = self.get_object()
        
        try:
            enrollment = Enrollment.objects.get(student=request.user, course=course)
            
            # Delete related progress and attempts
            LessonProgress.objects.filter(enrollment=enrollment).delete()
            QuizAttempt.objects.filter(enrollment=enrollment).delete()
            Certificate.objects.filter(enrollment=enrollment).delete()
            
            enrollment.delete()
            
            return Response({
                'message': 'Successfully unenrolled from the course'
            })
            
        except Enrollment.DoesNotExist:
            return Response({
                'error': 'You are not enrolled in this course'
            }, status=status.HTTP_400_BAD_REQUEST)

# Lesson Views
class LessonViewSet(viewsets.ModelViewSet):
    serializer_class = LessonSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_instructor():
            return Lesson.objects.filter(course__instructor=user)
        elif user.is_student():
            enrolled_courses = Enrollment.objects.filter(student=user).values_list('course_id', flat=True)
            return Lesson.objects.filter(course_id__in=enrolled_courses)
        
        return Lesson.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LessonDetailSerializer
        return LessonSerializer
    
    def retrieve(self, request, *args, **kwargs):
        """
        Get single lesson with progress and quiz information
        """
        instance = self.get_object()
        user = request.user
        
        # Check if student is enrolled in the course
        enrollment = Enrollment.objects.filter(
            student=user,
            course=instance.course
        ).first()
        
        if user.is_student() and not enrollment:
            raise PermissionDenied("You are not enrolled in this course")
        
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # Add progress information for students
        if user.is_student():
            progress = LessonProgress.objects.filter(
                student=user,
                lesson=instance,
                enrollment=enrollment
            ).first()
            
            data['progress'] = {
                'completed': progress.completed if progress else False,
                'completed_at': progress.completed_at if progress else None,
                'last_accessed': progress.last_accessed if progress else None
            }
            
            # Update last accessed time
            if progress:
                progress.last_accessed = timezone.now()
                progress.save()
            else:
                LessonProgress.objects.create(
                    student=user,
                    lesson=instance,
                    enrollment=enrollment,
                    last_accessed=timezone.now()
                )
            
            # Add quiz information
            quiz = Quiz.objects.filter(lesson=instance, is_active=True).first()
            if quiz:
                data['quiz'] = {
                    'id': quiz.id,
                    'title': quiz.title,
                    'description': quiz.description,
                    'passing_score': quiz.passing_score,
                    'time_limit_minutes': quiz.time_limit_minutes,
                    'total_questions': quiz.questions.count(),
                    'attempts_taken': QuizAttempt.objects.filter(
                        student=user,
                        quiz=quiz
                    ).count(),
                    'max_attempts': quiz.max_attempts,
                    'best_score': QuizAttempt.objects.filter(
                        student=user,
                        quiz=quiz
                    ).order_by('-score').first().score if QuizAttempt.objects.filter(student=user, quiz=quiz).exists() else None
                }
        
        return Response(data)
    
    def perform_create(self, serializer):
        if not self.request.user.is_instructor():
            raise PermissionDenied("Only instructors can create lessons")
        
        course = serializer.validated_data['course']
        if course.instructor != self.request.user:
            raise ValidationError("You can only add lessons to your own courses")
        
        # Set order if not provided
        if 'order' not in serializer.validated_data:
            last_lesson = Lesson.objects.filter(course=course).order_by('-order').first()
            serializer.validated_data['order'] = last_lesson.order + 1 if last_lesson else 1
        
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def mark_complete(self, request, pk=None):
        """Mark a lesson as completed"""
        lesson = self.get_object()
        
        # Check if student is enrolled in the course
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=lesson.course
        ).first()
        
        if not enrollment:
            raise PermissionDenied("You are not enrolled in this course")
        
        # Check if lesson has quiz that needs to be completed first
        quiz = Quiz.objects.filter(lesson=lesson, is_active=True).first()
        if quiz and quiz.questions.exists():
            # Check if quiz is passed
            quiz_passed = QuizAttempt.objects.filter(
                student=request.user,
                quiz=quiz,
                passed=True
            ).exists()
            
            if not quiz_passed:
                return Response({
                    'error': 'You must pass the quiz before marking this lesson as complete'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update or create lesson progress
        progress, created = LessonProgress.objects.update_or_create(
            student=request.user,
            lesson=lesson,
            enrollment=enrollment,
            defaults={
                'completed': True, 
                'completed_at': timezone.now(),
                'last_accessed': timezone.now()
            }
        )
        
        # Check if all lessons are completed
        self._check_course_completion(enrollment)
        
        return Response(LessonProgressSerializer(progress).data)
    
    def _check_course_completion(self, enrollment):
        """Check if all lessons in a course are completed"""
        course = enrollment.course
        total_lessons = course.total_lessons()
        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()
        
        if total_lessons == completed_lessons and total_lessons > 0:
            enrollment.completed = True
            enrollment.completed_at = timezone.now()
            enrollment.save()
            
            # Generate certificate if not already exists
            self._generate_certificate(enrollment)
    
    def _generate_certificate(self, enrollment):
        """Generate certificate for completed course"""
        if not Certificate.objects.filter(enrollment=enrollment).exists():
            certificate_id = f"CERT-{uuid.uuid4().hex[:12].upper()}"
            
            Certificate.objects.create(
                student=enrollment.student,
                course=enrollment.course,
                enrollment=enrollment,
                certificate_id=certificate_id,
                issued_at=timezone.now()
            )

# Enrollment Views
class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.is_student():
            return Enrollment.objects.filter(student=self.request.user)
        elif self.request.user.is_instructor():
            return Enrollment.objects.filter(course__instructor=self.request.user)
        return Enrollment.objects.none()
    
    def retrieve(self, request, *args, **kwargs):
        """
        Get single enrollment with detailed progress
        """
        instance = self.get_object()
        
        # Check permissions
        if not (instance.student == request.user or instance.course.instructor == request.user):
            raise PermissionDenied("You don't have permission to view this enrollment")
        
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # Add detailed progress information
        progress = LessonProgress.objects.filter(enrollment=instance)
        data['lesson_progress'] = LessonProgressSerializer(progress, many=True).data
        
        # Add quiz attempts
        quiz_attempts = QuizAttempt.objects.filter(enrollment=instance)
        data['quiz_attempts'] = QuizAttemptSerializer(quiz_attempts, many=True).data
        
        # Add certificate if exists
        certificate = Certificate.objects.filter(enrollment=instance).first()
        data['certificate'] = CertificateSerializer(certificate).data if certificate else None
        
        # Calculate progress statistics
        total_lessons = instance.course.total_lessons()
        completed_lessons = progress.filter(completed=True).count()
        
        data['progress_stats'] = {
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'percentage': round((completed_lessons / total_lessons) * 100, 2) if total_lessons > 0 else 0,
            'time_spent': self._calculate_time_spent(instance)
        }
        
        return Response(data)
    
    def _calculate_time_spent(self, enrollment):
        """Calculate total time spent on course"""
        progress_entries = LessonProgress.objects.filter(enrollment=enrollment)
        total_minutes = 0
        
        for progress in progress_entries:
            if progress.lesson.duration_minutes:
                total_minutes += progress.lesson.duration_minutes
        
        return {
            'total_minutes': total_minutes,
            'hours': total_minutes // 60,
            'minutes': total_minutes % 60
        }
    
    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """Get detailed progress for an enrollment"""
        enrollment = self.get_object()
        
        # Check permissions
        if not (enrollment.student == request.user or enrollment.course.instructor == request.user):
            raise PermissionDenied("You don't have permission to view this enrollment")
        
        progress = LessonProgress.objects.filter(enrollment=enrollment)
        serializer = LessonProgressSerializer(progress, many=True)
        
        return Response({
            'enrollment': EnrollmentSerializer(enrollment).data,
            'lesson_progress': serializer.data
        })
    
    @action(detail=True, methods=['get'])
    def certificate(self, request, pk=None):
        """Get certificate for enrollment"""
        enrollment = self.get_object()
        
        # Check permissions
        if not (enrollment.student == request.user or enrollment.course.instructor == request.user):
            raise PermissionDenied("You don't have permission to view this certificate")
        
        certificate = get_object_or_404(Certificate, enrollment=enrollment)
        serializer = CertificateSerializer(certificate)
        
        return Response(serializer.data)

# Progress Views
class CourseProgressViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def retrieve(self, request, pk=None):
        """
        Get detailed progress for a specific course
        """
        try:
            course = Course.objects.get(id=pk)
            
            # Check if user is enrolled (for students) or instructor
            enrollment = None
            is_enrolled = False
            
            if request.user.is_student():
                enrollment = Enrollment.objects.filter(
                    student=request.user,
                    course=course
                ).first()
                is_enrolled = enrollment is not None
            elif request.user.is_instructor() and course.instructor != request.user:
                raise PermissionDenied("You are not the instructor of this course")
            
            # Get total lessons in course
            total_lessons = course.total_lessons()
            
            # Get completed lessons
            completed_lessons = 0
            if enrollment:
                completed_lessons = LessonProgress.objects.filter(
                    enrollment=enrollment,
                    completed=True
                ).count()
            
            # Calculate progress percentage
            progress_percentage = 0
            if total_lessons > 0:
                progress_percentage = round((completed_lessons / total_lessons) * 100, 2)
            
            # Get all lessons with their completion status
            lessons = course.lessons.all().order_by('order')
            lesson_progress = []
            
            for lesson in lessons:
                progress = None
                if enrollment:
                    progress = LessonProgress.objects.filter(
                        student=request.user,
                        lesson=lesson,
                        enrollment=enrollment
                    ).first()
                
                # Check if lesson has quiz
                quiz = Quiz.objects.filter(lesson=lesson, is_active=True).first()
                quiz_status = None
                if quiz:
                    quiz_attempts = QuizAttempt.objects.filter(
                        student=request.user,
                        quiz=quiz
                    ) if enrollment else QuizAttempt.objects.none()
                    
                    best_attempt = quiz_attempts.order_by('-score').first()
                    passed = quiz_attempts.filter(passed=True).exists()
                    
                    quiz_status = {
                        'has_quiz': True,
                        'quiz_id': quiz.id,
                        'total_attempts': quiz_attempts.count(),
                        'best_score': best_attempt.score if best_attempt else None,
                        'passed': passed,
                        'required_passing_score': quiz.passing_score
                    }
                
                lesson_progress.append({
                    'lesson_id': lesson.id,
                    'lesson_title': lesson.title,
                    'content_type': lesson.content_type,
                    'order': lesson.order,
                    'duration_minutes': lesson.duration_minutes,
                    'has_quiz': quiz is not None,
                    'quiz_status': quiz_status,
                    'progress': {
                        'completed': progress.completed if progress else False,
                        'completed_at': progress.completed_at if progress else None,
                        'last_accessed': progress.last_accessed if progress else None
                    }
                })
            
            # Check if there's a certificate for this course
            certificate = None
            if enrollment:
                certificate = Certificate.objects.filter(
                    student=request.user,
                    course=course
                ).first()
            
            response_data = {
                'course': {
                    'id': course.id,
                    'title': course.title,
                    'description': course.description,
                    'instructor': {
                        'id': course.instructor.id,
                        'username': course.instructor.username,
                        'first_name': course.instructor.first_name,
                        'last_name': course.instructor.last_name
                    },
                    'total_lessons': total_lessons
                },
                'enrollment': {
                    'exists': is_enrolled,
                    'data': EnrollmentSerializer(enrollment).data if enrollment else None
                },
                'progress_summary': {
                    'total_lessons': total_lessons,
                    'completed_lessons': completed_lessons,
                    'progress_percentage': progress_percentage,
                    'remaining_lessons': total_lessons - completed_lessons,
                    'course_completed': enrollment.completed if enrollment else False
                },
                'lesson_progress': lesson_progress,
                'certificate': {
                    'exists': certificate is not None,
                    'data': CertificateSerializer(certificate).data if certificate else None
                }
            }
            
            return Response(response_data)
            
        except Course.DoesNotExist:
            return Response({
                'error': 'Course not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def overall(self, request):
        """
        Get overall progress across all enrolled courses
        """
        if not request.user.is_student():
            raise PermissionDenied("Only students can view overall progress")
        
        # Get all enrollments for the student
        enrollments = Enrollment.objects.filter(student=request.user)
        
        overall_progress = []
        total_courses = enrollments.count()
        completed_courses = 0
        total_progress_percentage = 0
        
        for enrollment in enrollments:
            total_lessons = enrollment.course.total_lessons()
            completed_lessons = LessonProgress.objects.filter(
                enrollment=enrollment,
                completed=True
            ).count()
            
            progress_percentage = 0
            if total_lessons > 0:
                progress_percentage = round((completed_lessons / total_lessons) * 100, 2)
            
            if enrollment.completed:
                completed_courses += 1
            
            total_progress_percentage += progress_percentage
            
            # Get certificate if exists
            certificate = Certificate.objects.filter(enrollment=enrollment).first()
            
            overall_progress.append({
                'course_id': enrollment.course.id,
                'course_title': enrollment.course.title,
                'course_description': enrollment.course.description[:100] + '...' if enrollment.course.description and len(enrollment.course.description) > 100 else enrollment.course.description,
                'enrollment_id': enrollment.id,
                'total_lessons': total_lessons,
                'completed_lessons': completed_lessons,
                'progress_percentage': progress_percentage,
                'course_completed': enrollment.completed,
                'enrolled_at': enrollment.enrolled_at,
                'last_activity': LessonProgress.objects.filter(
                    enrollment=enrollment
                ).order_by('-last_accessed').first().last_accessed if LessonProgress.objects.filter(enrollment=enrollment).exists() else None,
                'certificate': CertificateSerializer(certificate).data if certificate else None
            })
        
        # Calculate average progress
        average_progress = round(total_progress_percentage / total_courses, 2) if total_courses > 0 else 0
        
        return Response({
            'student': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'full_name': request.user.get_full_name()
            },
            'summary': {
                'total_courses': total_courses,
                'completed_courses': completed_courses,
                'in_progress_courses': total_courses - completed_courses,
                'average_progress': average_progress,
                'total_certificates': Certificate.objects.filter(student=request.user).count()
            },
            'course_progress': overall_progress
        })

class StudentProgressReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsInstructor]
    
    def list(self, request):
        """
        Get progress for all students in instructor's courses
        """
        # Get all students' progress in instructor's courses
        courses = Course.objects.filter(instructor=request.user)
        
        course_reports = []
        for course in courses:
            enrollments = course.enrollments.all()
            
            student_progress = []
            for enrollment in enrollments:
                total_lessons = course.total_lessons()
                completed_lessons = LessonProgress.objects.filter(
                    enrollment=enrollment,
                    completed=True
                ).count()
                
                progress_percentage = 0
                if total_lessons > 0:
                    progress_percentage = round((completed_lessons / total_lessons) * 100, 2)
                
                # Get quiz performance
                quiz_attempts = QuizAttempt.objects.filter(enrollment=enrollment)
                avg_quiz_score = quiz_attempts.aggregate(Avg('score'))['score__avg'] or 0
                
                # Get last activity
                last_activity = LessonProgress.objects.filter(
                    enrollment=enrollment
                ).order_by('-last_accessed').first()
                
                student_progress.append({
                    'student_id': enrollment.student.id,
                    'student_name': f"{enrollment.student.first_name} {enrollment.student.last_name}",
                    'username': enrollment.student.username,
                    'email': enrollment.student.email,
                    'enrollment_date': enrollment.enrolled_at,
                    'completed_lessons': completed_lessons,
                    'progress_percentage': progress_percentage,
                    'course_completed': enrollment.completed,
                    'avg_quiz_score': round(avg_quiz_score, 2),
                    'total_quiz_attempts': quiz_attempts.count(),
                    'last_activity': last_activity.last_accessed if last_activity else None,
                    'time_spent': self._calculate_time_spent(enrollment)
                })
            
            # Calculate course statistics
            total_students = enrollments.count()
            completed_students = enrollments.filter(completed=True).count()
            avg_progress = 0
            if student_progress:
                avg_progress = round(sum([s['progress_percentage'] for s in student_progress]) / len(student_progress), 2)
            
            # Calculate average quiz score for course
            all_quiz_attempts = QuizAttempt.objects.filter(
                enrollment__course=course
            )
            avg_course_quiz_score = all_quiz_attempts.aggregate(Avg('score'))['score__avg'] or 0
            
            course_reports.append({
                'course_id': course.id,
                'course_title': course.title,
                'total_students': total_students,
                'completed_students': completed_students,
                'completion_rate': round((completed_students / total_students) * 100, 2) if total_students > 0 else 0,
                'average_progress': avg_progress,
                'average_quiz_score': round(avg_course_quiz_score, 2),
                'student_progress': student_progress
            })
        
        return Response({
            'instructor': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email
            },
            'course_reports': course_reports,
            'summary': {
                'total_courses': courses.count(),
                'total_students': Enrollment.objects.filter(course__instructor=request.user).values('student').distinct().count(),
                'total_enrollments': Enrollment.objects.filter(course__instructor=request.user).count(),
                'total_certificates': Certificate.objects.filter(course__instructor=request.user).count()
            }
        })
    
    def retrieve(self, request, pk=None):
        """
        Get specific student's progress
        """
        # Get specific student's progress
        student = get_object_or_404(User, id=pk, role='student')
        
        # Get enrollments in instructor's courses
        enrollments = Enrollment.objects.filter(
            student=student,
            course__instructor=request.user
        )
        
        student_progress = []
        for enrollment in enrollments:
            total_lessons = enrollment.course.total_lessons()
            completed_lessons = LessonProgress.objects.filter(
                enrollment=enrollment,
                completed=True
            ).count()
            
            progress_percentage = 0
            if total_lessons > 0:
                progress_percentage = round((completed_lessons / total_lessons) * 100, 2)
            
            # Get quiz attempts for this course
            quiz_attempts = QuizAttempt.objects.filter(enrollment=enrollment)
            quiz_details = []
            for attempt in quiz_attempts:
                quiz_details.append({
                    'quiz_title': attempt.quiz.title,
                    'score': attempt.score,
                    'passed': attempt.passed,
                    'completed_at': attempt.completed_at
                })
            
            # Get last activity
            last_activity = LessonProgress.objects.filter(
                enrollment=enrollment
            ).order_by('-last_accessed').first()
            
            # Check for certificate
            certificate = Certificate.objects.filter(enrollment=enrollment).first()
            
            student_progress.append({
                'course_id': enrollment.course.id,
                'course_title': enrollment.course.title,
                'enrollment_date': enrollment.enrolled_at,
                'total_lessons': total_lessons,
                'completed_lessons': completed_lessons,
                'progress_percentage': progress_percentage,
                'course_completed': enrollment.completed,
                'completion_date': enrollment.completed_at if enrollment.completed else None,
                'quiz_attempts': quiz_details,
                'last_activity': last_activity.last_accessed if last_activity else None,
                'certificate': CertificateSerializer(certificate).data if certificate else None
            })
        
        return Response({
            'student': {
                'id': student.id,
                'username': student.username,
                'email': student.email,
                'first_name': student.first_name,
                'last_name': student.last_name,
                'date_joined': student.date_joined
            },
            'progress_by_course': student_progress,
            'summary': {
                'total_courses': enrollments.count(),
                'completed_courses': enrollments.filter(completed=True).count(),
                'in_progress_courses': enrollments.filter(completed=False).count(),
                'total_certificates': Certificate.objects.filter(student=student, course__instructor=request.user).count()
            }
        })
    
    def _calculate_time_spent(self, enrollment):
        """Calculate time spent on course"""
        progress_entries = LessonProgress.objects.filter(enrollment=enrollment)
        total_minutes = 0
        
        for progress in progress_entries:
            if progress.lesson.duration_minutes:
                total_minutes += progress.lesson.duration_minutes
        
        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        return f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

class LessonProgressViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def reset(self, request, pk=None):
        """
        Reset completion status for a lesson
        """
        try:
            lesson = Lesson.objects.get(id=pk)
            
            # Check if student is enrolled
            enrollment = Enrollment.objects.filter(
                student=request.user,
                course=lesson.course
            ).first()
            
            if not enrollment:
                raise PermissionDenied("You are not enrolled in this course")
            
            progress = LessonProgress.objects.get(
                student=request.user,
                lesson=lesson,
                enrollment=enrollment
            )
            
            # Reset the progress
            progress.completed = False
            progress.completed_at = None
            progress.save()
            
            # Update enrollment completion status if needed
            if enrollment.completed:
                # Check if all lessons are still completed
                total_lessons = enrollment.course.total_lessons()
                completed_lessons = LessonProgress.objects.filter(
                    enrollment=enrollment,
                    completed=True
                ).count()
                
                if completed_lessons < total_lessons:
                    enrollment.completed = False
                    enrollment.completed_at = None
                    enrollment.save()
                    
                    # Delete certificate if exists
                    Certificate.objects.filter(
                        student=request.user,
                        course=enrollment.course
                    ).delete()
            
            return Response({
                'message': 'Lesson progress reset successfully',
                'lesson_id': pk,
                'lesson_title': lesson.title,
                'completed': False,
                'enrollment': {
                    'course_completed': enrollment.completed,
                    'progress': {
                        'completed_lessons': LessonProgress.objects.filter(enrollment=enrollment, completed=True).count(),
                        'total_lessons': enrollment.course.total_lessons()
                    }
                }
            })
            
        except Lesson.DoesNotExist:
            return Response({
                'error': 'Lesson not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except LessonProgress.DoesNotExist:
            return Response({
                'error': 'Lesson progress not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def details(self, request, pk=None):
        """
        Get detailed progress for a specific lesson
        """
        try:
            lesson = Lesson.objects.get(id=pk)
            
            # Check if student is enrolled
            enrollment = Enrollment.objects.filter(
                student=request.user,
                course=lesson.course
            ).first()
            
            if not enrollment:
                raise PermissionDenied("You are not enrolled in this course")
            
            progress = LessonProgress.objects.filter(
                student=request.user,
                lesson=lesson,
                enrollment=enrollment
            ).first()
            
            # Get quiz information if exists
            quiz = Quiz.objects.filter(lesson=lesson, is_active=True).first()
            quiz_info = None
            if quiz:
                attempts = QuizAttempt.objects.filter(
                    student=request.user,
                    quiz=quiz
                )
                quiz_info = {
                    'quiz_id': quiz.id,
                    'title': quiz.title,
                    'passing_score': quiz.passing_score,
                    'max_attempts': quiz.max_attempts,
                    'attempts': QuizAttemptSerializer(attempts, many=True).data,
                    'best_score': attempts.order_by('-score').first().score if attempts.exists() else None,
                    'passed': attempts.filter(passed=True).exists()
                }
            
            return Response({
                'lesson': {
                    'id': lesson.id,
                    'title': lesson.title,
                    'course': {
                        'id': lesson.course.id,
                        'title': lesson.course.title
                    }
                },
                'progress': LessonProgressSerializer(progress).data if progress else None,
                'quiz': quiz_info,
                'can_mark_complete': quiz_info['passed'] if quiz_info else True
            })
            
        except Lesson.DoesNotExist:
            return Response({
                'error': 'Lesson not found'
            }, status=status.HTTP_404_NOT_FOUND)

# Dashboard Views
class InstructorDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsInstructor]
    
    def get(self, request):
        # Get instructor's courses
        courses = Course.objects.filter(instructor=request.user)
        
        # Course statistics
        course_stats = []
        for course in courses:
            total_students = course.enrollments.count()
            completed_enrollments = course.enrollments.filter(completed=True).count()
            
            # Calculate average progress
            enrollments = course.enrollments.all()
            avg_progress = 0
            if enrollments.exists():
                total_progress = 0
                for enrollment in enrollments:
                    total_lessons = course.total_lessons()
                    if total_lessons > 0:
                        completed_lessons = LessonProgress.objects.filter(
                            enrollment=enrollment,
                            completed=True
                        ).count()
                        total_progress += (completed_lessons / total_lessons) * 100
                avg_progress = round(total_progress / enrollments.count(), 2)
            
            
            course_stats.append({
                'course_id': course.id,
                'course_title': course.title,
                'total_students': total_students,
                'completed_students': completed_enrollments,
                'average_progress': avg_progress,
                'total_lessons': course.total_lessons(),
                'total_revenue': course.enrollments.count() * course.price if course.price else 0
            })
        
        # Overall statistics
        total_courses = courses.count()
        total_students = Enrollment.objects.filter(
            course__instructor=request.user
        ).values('student').distinct().count()
        
        # Recent enrollments (last 7 days)
        week_ago = timezone.now() - timezone.timedelta(days=7)
        recent_enrollments = Enrollment.objects.filter(
            course__instructor=request.user,
            enrolled_at__gte=week_ago
        ).count()
        
        # Recent completions (last 7 days)
        recent_completions = Enrollment.objects.filter(
            course__instructor=request.user,
            completed_at__gte=week_ago
        ).count()
        
        return Response({
            'instructor': UserSerializer(request.user).data,
            'overall_stats': {
                'total_courses': total_courses,
                'total_students': total_students,
                'total_enrollments': Enrollment.objects.filter(
                    course__instructor=request.user
                ).count(),
                'recent_enrollments': recent_enrollments,
                'recent_completions': recent_completions,
                'total_revenue': sum(course.enrollments.count() * course.price for course in courses if course.price)
            },
            'course_statistics': course_stats,
            'recent_activity': self._get_recent_activity(request.user)
        })
    
    def _get_recent_activity(self, instructor):
        """Get recent student activity in instructor's courses"""
        # Get recent lesson completions
        recent_completions = LessonProgress.objects.filter(
            lesson__course__instructor=instructor,
            completed_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).select_related('student', 'lesson', 'lesson__course').order_by('-completed_at')[:10]
        
        activity = []
        for completion in recent_completions:
            activity.append({
                'student': completion.student.username,
                'student_name': completion.student.get_full_name(),
                'course': completion.lesson.course.title,
                'lesson': completion.lesson.title,
                'completed_at': completion.completed_at,
                'type': 'lesson_completion'
            })
        
        # Get recent quiz attempts
        recent_quizzes = QuizAttempt.objects.filter(
            quiz__lesson__course__instructor=instructor,
            completed_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).select_related('student', 'quiz', 'quiz__lesson', 'quiz__lesson__course').order_by('-completed_at')[:10]
        
        for attempt in recent_quizzes:
            activity.append({
                'student': attempt.student.username,
                'student_name': attempt.student.get_full_name(),
                'course': attempt.quiz.lesson.course.title,
                'quiz': attempt.quiz.title,
                'score': attempt.score,
                'passed': attempt.passed,
                'completed_at': attempt.completed_at,
                'type': 'quiz_attempt'
            })
        
        # Sort by date
        activity.sort(key=lambda x: x['completed_at'], reverse=True)
        
        return activity[:15]  # Return top 15 activities

class StudentDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]
    
    def get(self, request):
        # Get student's enrollments
        enrollments = Enrollment.objects.filter(student=request.user)
        
        # Serialize enrollments with progress
        enrollments_data = []
        for enrollment in enrollments:
            total_lessons = enrollment.course.total_lessons()
            completed_lessons = LessonProgress.objects.filter(
                enrollment=enrollment,
                completed=True
            ).count()
            
            progress_percentage = 0
            if total_lessons > 0:
                progress_percentage = round((completed_lessons / total_lessons) * 100, 2)
            
            enrollment_data = EnrollmentSerializer(enrollment).data
            enrollment_data['progress'] = {
                'completed_lessons': completed_lessons,
                'total_lessons': total_lessons,
                'percentage': progress_percentage
            }
            
            # Add next lesson to complete
            if not enrollment.completed:
                next_lesson = LessonProgress.objects.filter(
                    enrollment=enrollment,
                    completed=False
                ).select_related('lesson').order_by('lesson__order').first()
                
                if next_lesson:
                    enrollment_data['next_lesson'] = {
                        'id': next_lesson.lesson.id,
                        'title': next_lesson.lesson.title,
                        'order': next_lesson.lesson.order
                    }
            
            enrollments_data.append(enrollment_data)
        
        # Recent activity
        recent_progress = LessonProgress.objects.filter(
            student=request.user
        ).select_related('lesson', 'lesson__course').order_by('-last_accessed')[:10]
        
        # Recent quiz attempts
        recent_quiz_attempts = QuizAttempt.objects.filter(
            student=request.user
        ).select_related('quiz', 'quiz__lesson', 'quiz__lesson__course').order_by('-completed_at')[:5]
        
        # Certificates
        certificates = Certificate.objects.filter(student=request.user)
        
        # Upcoming deadlines (quizzes with attempts left)
        upcoming_quizzes = []
        for enrollment in enrollments:
            if not enrollment.completed:
                # Find lessons with quizzes that are not passed yet
                lessons_with_quizzes = Lesson.objects.filter(
                    course=enrollment.course,
                    quiz__is_active=True
                ).distinct()
                
                for lesson in lessons_with_quizzes:
                    quiz = Quiz.objects.filter(lesson=lesson, is_active=True).first()
                    if quiz:
                        attempts = QuizAttempt.objects.filter(
                            student=request.user,
                            quiz=quiz
                        ).count()
                        
                        if attempts < quiz.max_attempts or not QuizAttempt.objects.filter(
                            student=request.user,
                            quiz=quiz,
                            passed=True
                        ).exists():
                            upcoming_quizzes.append({
                                'quiz_id': quiz.id,
                                'title': quiz.title,
                                'course': lesson.course.title,
                                'lesson': lesson.title,
                                'max_attempts': quiz.max_attempts,
                                'attempts_used': attempts,
                                'passing_score': quiz.passing_score
                            })
        
        return Response({
            'student': UserSerializer(request.user).data,
            'enrollments': enrollments_data,
            'recent_activity': LessonProgressSerializer(recent_progress, many=True).data,
            'recent_quiz_attempts': QuizAttemptSerializer(recent_quiz_attempts, many=True).data,
            'certificates': CertificateSerializer(certificates, many=True).data,
            'upcoming_quizzes': upcoming_quizzes,
            'stats': {
                'total_courses': enrollments.count(),
                'completed_courses': enrollments.filter(completed=True).count(),
                'in_progress_courses': enrollments.filter(completed=False).count(),
                'total_lessons_completed': LessonProgress.objects.filter(student=request.user, completed=True).count(),
                'total_quiz_attempts': QuizAttempt.objects.filter(student=request.user).count(),
                'quiz_pass_rate': self._calculate_quiz_pass_rate(request.user)
            }
        })
    
    def _calculate_quiz_pass_rate(self, student):
        """Calculate student's quiz pass rate"""
        quiz_attempts = QuizAttempt.objects.filter(student=student)
        if not quiz_attempts.exists():
            return 0
        
        passed_attempts = quiz_attempts.filter(passed=True).count()
        return round((passed_attempts / quiz_attempts.count()) * 100, 2)

# Quiz Views
class QuizViewSet(viewsets.ModelViewSet):
    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.is_instructor():
            return Quiz.objects.filter(lesson__course__instructor=self.request.user)
        elif self.request.user.is_student():
            enrolled_courses = Enrollment.objects.filter(
                student=self.request.user
            ).values_list('course_id', flat=True)
            return Quiz.objects.filter(lesson__course_id__in=enrolled_courses, is_active=True)
        return Quiz.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'retrieve' and self.request.user.is_student():
            return QuizDetailSerializer
        return QuizSerializer
    
    def retrieve(self, request, *args, **kwargs):
        """
        Get quiz details with appropriate permissions
        """
        instance = self.get_object()
        
        if request.user.is_student():
            # Check if student is enrolled in the course
            enrollment = Enrollment.objects.filter(
                student=request.user,
                course=instance.lesson.course
            ).first()
            
            if not enrollment:
                raise PermissionDenied("You are not enrolled in this course")
            
            # Check max attempts
            attempts = QuizAttempt.objects.filter(
                student=request.user,
                quiz=instance
            ).count()
            
            if attempts >= instance.max_attempts:
                return Response({
                    'error': 'Maximum attempts reached for this quiz',
                    'quiz': QuizSerializer(instance).data,
                    'attempts': attempts,
                    'max_attempts': instance.max_attempts,
                    'best_score': QuizAttempt.objects.filter(
                        student=request.user,
                        quiz=instance
                    ).order_by('-score').first().score if attempts > 0 else None
                })
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def perform_create(self, serializer):
        if not self.request.user.is_instructor():
            raise PermissionDenied("Only instructors can create quizzes")
        
        lesson = serializer.validated_data['lesson']
        if lesson.course.instructor != self.request.user:
            raise ValidationError("You can only add quizzes to your own courses")
        serializer.save()

class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated, IsInstructor]
    
    def get_queryset(self):
        return Question.objects.filter(quiz__lesson__course__instructor=self.request.user)
    
    def perform_create(self, serializer):
        quiz = serializer.validated_data['quiz']
        if quiz.lesson.course.instructor != self.request.user:
            raise ValidationError("You can only add questions to your own quizzes")
        serializer.save()

class QuizAttemptViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsStudent]
    
    def create(self, request, quiz_id=None):
        """Submit a quiz attempt"""
        quiz = get_object_or_404(Quiz, id=quiz_id, is_active=True)
        
        # Check if student is enrolled
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=quiz.lesson.course
        ).first()
        
        if not enrollment:
            raise PermissionDenied("You are not enrolled in this course")
        
        # Check max attempts
        attempts = QuizAttempt.objects.filter(
            student=request.user,
            quiz=quiz
        ).count()
        
        if attempts >= quiz.max_attempts:
            best_attempt = QuizAttempt.objects.filter(
                student=request.user,
                quiz=quiz
            ).order_by('-score').first()
            
            return Response({
                'error': 'Maximum attempts reached for this quiz',
                'attempts': attempts,
                'max_attempts': quiz.max_attempts,
                'best_score': best_attempt.score if best_attempt else None,
                'passed': best_attempt.passed if best_attempt else False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = SubmitQuizSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Calculate score
        questions = quiz.questions.all()
        total_score = 0
        max_score = sum(q.points for q in questions)
        
        # Store detailed results
        detailed_results = []
        
        for answer in serializer.validated_data['answers']:
            question_id = answer.get('question_id')
            user_answer = answer.get('answer')
            
            question = questions.filter(id=question_id).first()
            if question:
                is_correct = question.correct_answer.lower() == str(user_answer).lower()
                if is_correct:
                    total_score += question.points
                
                detailed_results.append({
                    'question_id': question_id,
                    'question_text': question.question_text,
                    'user_answer': user_answer,
                    'correct_answer': question.correct_answer,
                    'is_correct': is_correct,
                    'points': question.points if is_correct else 0,
                    'explanation': question.explanation
                })
        
        # Calculate percentage
        percentage = round((total_score / max_score) * 100, 2) if max_score > 0 else 0
        passed = percentage >= quiz.passing_score
        
        # Create quiz attempt
        attempt = QuizAttempt.objects.create(
            student=request.user,
            quiz=quiz,
            enrollment=enrollment,
            score=percentage,
            passed=passed,
            completed_at=timezone.now(),
            detailed_results=detailed_results
        )
        
        # If quiz is passed, mark the lesson as completed
        if passed:
            lesson_progress, created = LessonProgress.objects.update_or_create(
                student=request.user,
                lesson=quiz.lesson,
                enrollment=enrollment,
                defaults={'completed': True, 'completed_at': timezone.now()}
            )
            
            # Check if all lessons are completed
            self._check_course_completion(enrollment)
        
        return Response({
            'attempt_id': attempt.id,
            'score': percentage,
            'passed': passed,
            'total_questions': questions.count(),
            'correct_answers': total_score,
            'max_score': max_score,
            'attempt_number': attempts + 1,
            'remaining_attempts': quiz.max_attempts - (attempts + 1),
            'detailed_results': detailed_results
        }, status=status.HTTP_201_CREATED)
    
    def _check_course_completion(self, enrollment):
        """Check if all lessons in course are completed"""
        course = enrollment.course
        total_lessons = course.total_lessons()
        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()
        
        if total_lessons == completed_lessons and total_lessons > 0:
            enrollment.completed = True
            enrollment.completed_at = timezone.now()
            enrollment.save()
            
            # Generate certificate
            self._generate_certificate(enrollment)
    
    def _generate_certificate(self, enrollment):
        """Generate certificate for completed course"""
        if not Certificate.objects.filter(enrollment=enrollment).exists():
            certificate_id = f"CERT-{uuid.uuid4().hex[:12].upper()}"
            
            Certificate.objects.create(
                student=enrollment.student,
                course=enrollment.course,
                enrollment=enrollment,
                certificate_id=certificate_id,
                issued_at=timezone.now()
            )
    
    @action(detail=False, methods=['get'], url_path='quiz/(?P<quiz_id>\d+)/history')
    def quiz_attempt_history(self, request, quiz_id=None):
        """Get attempt history for a specific quiz"""
        quiz = get_object_or_404(Quiz, id=quiz_id)
        
        # Check if student is enrolled
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=quiz.lesson.course
        ).first()
        
        if not enrollment:
            raise PermissionDenied("You are not enrolled in this course")
        
        attempts = QuizAttempt.objects.filter(
            student=request.user,
            quiz=quiz
        ).order_by('-completed_at')
        
        return Response({
            'quiz': {
                'id': quiz.id,
                'title': quiz.title,
                'passing_score': quiz.passing_score,
                'max_attempts': quiz.max_attempts
            },
            'attempts': QuizAttemptSerializer(attempts, many=True).data,
            'statistics': {
                'total_attempts': attempts.count(),
                'best_score': attempts.aggregate(Max('score'))['score__max'] or 0,
                'average_score': attempts.aggregate(Avg('score'))['score__avg'] or 0,
                'pass_count': attempts.filter(passed=True).count()
            }
        })

# Certificate Views
class CertificateViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get all certificates for current user"""
        if request.user.is_student():
            certificates = Certificate.objects.filter(student=request.user)
        elif request.user.is_instructor():
            certificates = Certificate.objects.filter(course__instructor=request.user)
        else:
            certificates = Certificate.objects.none()
        
        serializer = CertificateSerializer(certificates, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None):
        """Get specific certificate"""
        certificate = get_object_or_404(Certificate, id=pk)
        
        # Check permissions
        if not (certificate.student == request.user or certificate.course.instructor == request.user):
            raise PermissionDenied("You don't have permission to view this certificate")
        
        serializer = CertificateSerializer(certificate)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download certificate as PDF"""
        certificate = get_object_or_404(Certificate, id=pk)
        
        # Check permissions
        if not (certificate.student == request.user or certificate.course.instructor == request.user):
            raise PermissionDenied("You don't have permission to download this certificate")
        
        # Generate PDF (simplified version - in production, use a proper PDF library)
        html_content = render_to_string('certificate_template.html', {
            'certificate': certificate,
            'student': certificate.student,
            'course': certificate.course,
            'issue_date': certificate.issued_at.strftime('%B %d, %Y'),
            'certificate_id': certificate.certificate_id
        })
        
        # For now, return JSON with download link
        # In production, generate actual PDF using reportlab or similar
        return Response({
            'certificate_id': certificate.certificate_id,
            'download_url': f"/api/certificates/{certificate.id}/pdf/",
            'preview_html': html_content,
            'message': 'PDF generation would be implemented with a proper PDF library'
        })
    
    @action(detail=True, methods=['get'], permission_classes=[])
    def verify(self, request, certificate_id=None):
        """Verify a certificate by ID (public endpoint)"""
        if certificate_id:
            certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
            
            return Response({
                'certificate_id': certificate.certificate_id,
                'valid': True,
                'verification_date': timezone.now(),
                'student': {
                    'id': certificate.student.id,
                    'name': certificate.student.get_full_name(),
                    'email': certificate.student.email
                },
                'course': {
                    'id': certificate.course.id,
                    'title': certificate.course.title,
                    'description': certificate.course.description,
                    'category': certificate.course.category,
                    'duration_hours': certificate.course.duration_hours
                },
                'instructor': {
                    'id': certificate.course.instructor.id,
                    'name': certificate.course.instructor.get_full_name()
                },
                'issued_at': certificate.issued_at,
                'enrollment': {
                    'enrolled_at': certificate.enrollment.enrolled_at,
                    'completed_at': certificate.enrollment.completed_at
                }
            })
        
        # If no certificate_id provided, check by student and course
        student_id = request.query_params.get('student_id')
        course_id = request.query_params.get('course_id')
        
        if student_id and course_id:
            certificate = get_object_or_404(
                Certificate, 
                student_id=student_id, 
                course_id=course_id
            )
            
            return Response({
                'certificate_id': certificate.certificate_id,
                'valid': True,
                'student': certificate.student.get_full_name(),
                'course': certificate.course.title,
                'issued_at': certificate.issued_at
            })
        
        return Response({
            'error': 'Please provide certificate_id or student_id and course_id'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsStudent])
    def regenerate(self, request):
        """Regenerate certificate for a completed course"""
        course_id = request.data.get('course_id')
        
        if not course_id:
            return Response({
                'error': 'course_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if student is enrolled and completed the course
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course_id=course_id,
            completed=True
        ).first()
        
        if not enrollment:
            return Response({
                'error': 'Course not completed or not enrolled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Delete existing certificate
        Certificate.objects.filter(enrollment=enrollment).delete()
        
        # Generate new certificate
        certificate_id = f"CERT-{uuid.uuid4().hex[:12].upper()}"
        certificate = Certificate.objects.create(
            student=request.user,
            course=enrollment.course,
            enrollment=enrollment,
            certificate_id=certificate_id,
            issued_at=timezone.now()
        )
        
        return Response({
            'message': 'Certificate regenerated successfully',
            'certificate': CertificateSerializer(certificate).data
        }, status=status.HTTP_201_CREATED)

# Additional API Views
class CourseAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsInstructor]
    
    def get(self, request, course_id):
        """Get detailed analytics for a course"""
        course = get_object_or_404(Course, id=course_id, instructor=request.user)
        
        enrollments = course.enrollments.all()
        
        # Progress distribution
        progress_distribution = {
            '0-25%': 0,
            '26-50%': 0,
            '51-75%': 0,
            '76-99%': 0,
            '100%': 0
        }
        
        # Quiz performance
        quiz_performance = []
        quizzes = Quiz.objects.filter(lesson__course=course)
        
        for quiz in quizzes:
            attempts = QuizAttempt.objects.filter(quiz=quiz)
            avg_score = attempts.aggregate(Avg('score'))['score__avg'] or 0
            pass_rate = (attempts.filter(passed=True).count() / attempts.count() * 100) if attempts.exists() else 0
            
            quiz_performance.append({
                'quiz_id': quiz.id,
                'title': quiz.title,
                'total_attempts': attempts.count(),
                'average_score': round(avg_score, 2),
                'pass_rate': round(pass_rate, 2),
                'passing_score': quiz.passing_score
            })
        
        # Student engagement
        active_students = 0
        for enrollment in enrollments:
            # Calculate progress
            total_lessons = course.total_lessons()
            completed_lessons = LessonProgress.objects.filter(
                enrollment=enrollment,
                completed=True
            ).count()
            
            progress = (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0
            
            # Categorize progress
            if progress == 100:
                progress_distribution['100%'] += 1
            elif progress >= 76:
                progress_distribution['76-99%'] += 1
            elif progress >= 51:
                progress_distribution['51-75%'] += 1
            elif progress >= 26:
                progress_distribution['26-50%'] += 1
            else:
                progress_distribution['0-25%'] += 1
            
            # Check if active (accessed in last 7 days)
            recent_activity = LessonProgress.objects.filter(
                enrollment=enrollment,
                last_accessed__gte=timezone.now() - timezone.timedelta(days=7)
            ).exists()
            
            if recent_activity:
                active_students += 1
        
        # Time spent analysis
        total_time_spent = 0
        for enrollment in enrollments:
            progress_entries = LessonProgress.objects.filter(enrollment=enrollment)
            for progress in progress_entries:
                if progress.lesson.duration_minutes:
                    total_time_spent += progress.lesson.duration_minutes
        
        avg_time_spent = total_time_spent / enrollments.count() if enrollments.exists() else 0
        
        return Response({
            'course': {
                'id': course.id,
                'title': course.title,
                'total_students': enrollments.count(),
                'completion_rate': round((enrollments.filter(completed=True).count() / enrollments.count() * 100), 2) if enrollments.exists() else 0
            },
            'progress_distribution': progress_distribution,
            'engagement': {
                'active_students': active_students,
                'inactive_students': enrollments.count() - active_students,
                'activity_rate': round((active_students / enrollments.count() * 100), 2) if enrollments.exists() else 0
            },
            'time_analysis': {
                'total_time_spent_hours': round(total_time_spent / 60, 2),
                'average_time_spent_hours': round(avg_time_spent / 60, 2),
                'average_time_per_lesson_minutes': round(avg_time_spent / course.total_lessons(), 2) if course.total_lessons() > 0 else 0
            },
            'quiz_performance': quiz_performance,
            'recent_completions': enrollments.filter(
                completed_at__gte=timezone.now() - timezone.timedelta(days=30)
            ).count()
        })

class StudentActivityView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get student's recent activity across all courses"""
        if request.user.is_student():
            # Get all activities (lesson progress and quiz attempts)
            activities = []
            
            # Lesson activities
            lesson_activities = LessonProgress.objects.filter(
                student=request.user
            ).select_related('lesson', 'lesson__course').order_by('-last_accessed')[:50]
            
            for activity in lesson_activities:
                activities.append({
                    'type': 'lesson',
                    'action': 'completed' if activity.completed else 'accessed',
                    'course': activity.lesson.course.title,
                    'lesson': activity.lesson.title,
                    'timestamp': activity.completed_at if activity.completed else activity.last_accessed,
                    'details': {
                        'completed': activity.completed,
                        'duration_minutes': activity.lesson.duration_minutes
                    }
                })
            
            # Quiz activities
            quiz_activities = QuizAttempt.objects.filter(
                student=request.user
            ).select_related('quiz', 'quiz__lesson', 'quiz__lesson__course').order_by('-completed_at')[:50]
            
            for activity in quiz_activities:
                activities.append({
                    'type': 'quiz',
                    'action': 'attempted',
                    'course': activity.quiz.lesson.course.title,
                    'quiz': activity.quiz.title,
                    'timestamp': activity.completed_at,
                    'details': {
                        'score': activity.score,
                        'passed': activity.passed,
                        'total_questions': activity.quiz.questions.count()
                    }
                })
            
            # Sort by timestamp
            activities.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # Group by date
            grouped_activities = {}
            for activity in activities[:30]:  # Limit to 30 most recent
                date_str = activity['timestamp'].strftime('%Y-%m-%d')
                if date_str not in grouped_activities:
                    grouped_activities[date_str] = []
                grouped_activities[date_str].append(activity)
            
            return Response({
                'student': UserSerializer(request.user).data,
                'total_activities': len(activities),
                'activities_by_date': grouped_activities,
                'recent_activities': activities[:10]  # Top 10 most recent
            })
        
        elif request.user.is_instructor():
            # For instructors, show recent student activity in their courses
            courses = Course.objects.filter(instructor=request.user)
            
            recent_activity = []
            for course in courses:
                # Recent lesson completions
                recent_lessons = LessonProgress.objects.filter(
                    lesson__course=course,
                    completed_at__gte=timezone.now() - timezone.timedelta(days=7)
                ).select_related('student', 'lesson').order_by('-completed_at')[:10]
                
                for activity in recent_lessons:
                    recent_activity.append({
                        'type': 'lesson_completion',
                        'course': course.title,
                        'student': activity.student.username,
                        'student_name': activity.student.get_full_name(),
                        'lesson': activity.lesson.title,
                        'timestamp': activity.completed_at
                    })
                
                # Recent quiz attempts
                recent_quizzes = QuizAttempt.objects.filter(
                    quiz__lesson__course=course,
                    completed_at__gte=timezone.now() - timezone.timedelta(days=7)
                ).select_related('student', 'quiz').order_by('-completed_at')[:10]
                
                for activity in recent_quizzes:
                    recent_activity.append({
                        'type': 'quiz_attempt',
                        'course': course.title,
                        'student': activity.student.username,
                        'student_name': activity.student.get_full_name(),
                        'quiz': activity.quiz.title,
                        'score': activity.score,
                        'passed': activity.passed,
                        'timestamp': activity.completed_at
                    })
            
            # Sort by timestamp
            recent_activity.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return Response({
                'instructor': UserSerializer(request.user).data,
                'recent_activity': recent_activity[:20],  # Top 20 most recent
                'activity_count': len(recent_activity)
            })
        
        return Response({
            'error': 'Unauthorized'
        }, status=status.HTTP_403_FORBIDDEN)