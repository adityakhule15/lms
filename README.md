# Learning Management System (LMS)

A Django-based Learning Management System with student progress tracking, course management, and JWT authentication.

## Features

### Instructor Features
- Create and manage courses
- Add video/text lessons to courses
- Create quizzes with questions
- View student progress dashboard
- Track class-level progress statistics

### Student Features
- Browse available courses
- Enroll in courses
- View lesson lists
- Mark lessons as completed
- Take quizzes
- Track course progress
- Earn certificates upon completion
- View personal dashboard

### Admin Features
- User management
- Course management
- System monitoring

## API Endpoints

### Authentication
- `POST /api/register/` - User registration
- `POST /api/login/` - User login

### Courses
- `GET /api/courses/` - List all courses
- `POST /api/courses/` - Create new course (instructor only)
- `GET /api/courses/{id}/` - Get course details
- `PUT /api/courses/{id}/` - Update course
- `DELETE /api/courses/{id}/` - Delete course
- `POST /api/courses/{id}/enroll/` - Enroll in course
- `GET /api/courses/enrolled_courses/` - Get enrolled courses
- `GET /api/courses/available_courses/` - Get available courses

### Lessons
- `GET /api/lessons/` - List lessons
- `POST /api/lessons/` - Create lesson (instructor only)
- `POST /api/lessons/{id}/mark_complete/` - Mark lesson as completed

### Dashboard
- `GET /api/instructor-dashboard/` - Instructor dashboard
- `GET /api/student-dashboard/` - Student dashboard

### Quizzes
- `POST /api/quizzes/{id}/attempt/` - Submit quiz answers

## Setup Instructions

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt