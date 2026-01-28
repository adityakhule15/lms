from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import *

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'bio', 'phone']
        read_only_fields = ['id']

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name', 'role']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields don't match."})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if not user:
            raise serializers.ValidationError('Invalid credentials')
        return {'user': user}

class CourseSerializer(serializers.ModelSerializer):
    instructor = UserSerializer(read_only=True)
    total_lessons = serializers.SerializerMethodField()
    total_students = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()
    
    
    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'instructor', 'thumbnail', 
                 'created_at', 'total_lessons', 'total_students', 'is_published', 'category', 'level', 'duration_hours', 'price', 'is_enrolled']
    
    def get_total_lessons(self, obj):
        return Lesson.objects.filter(
                course=obj
            ).count()
    
    def get_total_students(self, obj):
        return Enrollment.objects.filter(
                course=obj
            ).count()

    def get_is_enrolled(self, obj):
        # Get the request from context
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Check if user is enrolled in this course
            return Enrollment.objects.filter(
                student=request.user,
                course=obj
            ).exists()
        return False
    
class CourseCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['title', 'description', 'thumbnail', 'is_published',
                  'category', 'level', 'duration_hours', 'price']

class CourseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['title', 'description', 'thumbnail', 'is_published',
                  'category', 'level', 'duration_hours', 'price']
        extra_kwargs = {
            'title': {'required': False},
            'description': {'required': False},
            'category': {'required': False},
            'level': {'required': False},
            'duration_hours': {'required': False},
            'price': {'required': False},
            'is_published': {'required': False},
            'thumbnail': {'required': False}
        }

class LessonSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    
    class Meta:
        model = Lesson
        fields = '__all__'

class EnrollmentSerializer(serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    course = CourseSerializer(read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = ['id', 'student', 'course', 'enrolled_at', 'completed', 
                 'completed_at', 'progress_percentage']
    
    def get_progress_percentage(self, obj):
        total_lessons = obj.course.total_lessons()
        if total_lessons == 0:
            return 0
        completed_lessons = LessonProgress.objects.filter(
            enrollment=obj, 
            completed=True
        ).count()
        return round((completed_lessons / total_lessons) * 100)

class LessonProgressSerializer(serializers.ModelSerializer):
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    course_title = serializers.CharField(source='lesson.course.title', read_only=True)
    
    class Meta:
        model = LessonProgress
        fields = ['id', 'lesson', 'lesson_title', 'course_title', 'completed', 
                 'completed_at', 'last_accessed']

class QuizSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quiz
        fields = ['id', 'lesson', 'title', 'description', 'passing_score']

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'quiz', 'question_type', 'question_text', 
                 'options', 'correct_answer', 'points', 'order']

class QuizAttemptSerializer(serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    
    class Meta:
        model = QuizAttempt
        fields = ['id', 'student', 'quiz', 'quiz_title', 'score', 
                 'passed', 'started_at', 'completed_at']

class SubmitQuizSerializer(serializers.Serializer):
    answers = serializers.ListField(
        child=serializers.DictField()
    )

class CertificateSerializer(serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    course = CourseSerializer(read_only=True)
    
    class Meta:
        model = Certificate
        fields = ['id', 'student', 'course', 'certificate_id', 
                 'issued_at', 'pdf_file']

class StudentProgressSerializer(serializers.ModelSerializer):
    course = CourseSerializer()
    progress_percentage = serializers.SerializerMethodField()
    completed_lessons = serializers.SerializerMethodField()
    total_lessons = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = ['course', 'enrolled_at', 'completed', 'progress_percentage', 
                 'completed_lessons', 'total_lessons']
    
    def get_progress_percentage(self, obj):
        total_lessons = obj.course.total_lessons()
        if total_lessons == 0:
            return 0
        completed_lessons = LessonProgress.objects.filter(
            enrollment=obj, 
            completed=True
        ).count()
        return round((completed_lessons / total_lessons) * 100)
    
    def get_completed_lessons(self, obj):
        return LessonProgress.objects.filter(enrollment=obj, completed=True).count()
    
    def get_total_lessons(self, obj):
        return obj.course.total_lessons()
    

class CourseProgressSerializer(serializers.Serializer):
    enrollment_id = serializers.IntegerField()
    course_id = serializers.IntegerField()
    course_title = serializers.CharField()
    total_lessons = serializers.IntegerField()
    completed_lessons = serializers.IntegerField()
    progress_percentage = serializers.FloatField()
    is_completed = serializers.BooleanField()
    enrolled_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    
class LessonProgressDetailSerializer(serializers.ModelSerializer):
    lesson = LessonSerializer(read_only=True)
    
    class Meta:
        model = LessonProgress
        fields = ['lesson', 'completed', 'completed_at', 'last_accessed']

from rest_framework import serializers
from .models import *

# Add these serializers to your existing serializers.py

class CourseDetailSerializer(serializers.ModelSerializer):
    instructor = UserSerializer(read_only=True)
    total_lessons = serializers.IntegerField(read_only=True)
    total_students = serializers.SerializerMethodField()
    average_rating = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Course
        fields = '__all__'
        read_only_fields = ['instructor', 'created_at', 'updated_at']
    
    def get_total_students(self, obj):
        return Enrollment.objects.filter(
                course=obj
            ).count()

class LessonDetailSerializer(serializers.ModelSerializer):
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all())
    has_quiz = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Lesson
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class QuizDetailSerializer(serializers.ModelSerializer):
    lesson = serializers.StringRelatedField()
    course = serializers.SerializerMethodField()
    total_questions = serializers.IntegerField(read_only=True)
    attempts_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = Quiz
        fields = '__all__'
    
    def get_course(self, obj):
        return {
            'id': obj.lesson.course.id,
            'title': obj.lesson.course.title
        }
    
    def get_attempts_remaining(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            attempts = QuizAttempt.objects.filter(
                student=request.user,
                quiz=obj
            ).count()
            return max(0, obj.max_attempts - attempts)
        return obj.max_attempts

class StudentProgressSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    last_accessed = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = ['id', 'course_title', 'enrolled_at', 'completed', 'completed_at', 
                 'progress_percentage', 'last_accessed']
    
    def get_progress_percentage(self, obj):
        total_lessons = obj.course.total_lessons()
        completed_lessons = LessonProgress.objects.filter(
            enrollment=obj,
            completed=True
        ).count()
        
        if total_lessons > 0:
            return round((completed_lessons / total_lessons) * 100, 2)
        return 0
    
    def get_last_accessed(self, obj):
        last_progress = LessonProgress.objects.filter(
            enrollment=obj
        ).order_by('-last_accessed').first()
        
        return last_progress.last_accessed if last_progress else None
    
    