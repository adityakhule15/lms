# 🎓 Learning Management System (LMS)

A **Django REST Framework–based Learning Management System** with **JWT authentication**, **student progress tracking**, **quizzes**, and **certificate generation**. This project implements complete instructor and student workflows with dashboards and analytics.

---

## 📌 Problem Statement

Build a minimal yet scalable **Learning Management System** where:

* Instructors can create courses and lessons
* Students can enroll, complete lessons, and track progress
* Progress is calculated accurately per course
* Dashboards provide insights for both instructors and students

---

## 🎯 Key Features

### 👨‍🏫 Instructor Features

* Create & manage courses
* Add **video** or **text** lessons
* Create quizzes with questions & correct answers
* View **student progress dashboard**
* Track **class-level progress statistics** (enrollments, completion %)

### 👨‍🎓 Student Features

* Browse available courses
* Enroll in courses
* View lesson lists
* Mark lessons as completed
* Attempt quizzes
* Track course-wise progress percentage
* Earn **certificate of completion**
* View personal dashboard

### 📊 Progress & Analytics

* Accurate lesson-based completion tracking
* Automatic course completion percentage
* Instructor overview of student performance

### 🌟 Optional / Implemented Enhancements

* Quizzes per course
* Certificate generation on course completion (PDF)
* JWT-based secure authentication

---

## 🛠 Tech Stack

### Backend

* **Python 3.x**
* **Django**
* **Django REST Framework (DRF)**
* **Simple JWT** for authentication

### Database

* SQLite (development)
* PostgreSQL (production-ready)

### Frontend (API Ready)

* Can be integrated with **React / Next.js**

---

## 🔐 Authentication

* JWT (Access & Refresh Tokens)
* Role-based access:

  * Instructor
  * Student

---

## 📡 API Endpoints

### 🔑 Authentication

* `POST /api/register/` – User registration
* `POST /api/login/` – User login

---

### 📚 Courses

* `GET /api/courses/` – List all courses
* `POST /api/courses/` – Create course (Instructor only)
* `GET /api/courses/{id}/` – Course details
* `PUT /api/courses/{id}/` – Update course
* `DELETE /api/courses/{id}/` – Delete course
* `POST /api/courses/{id}/enroll/` – Enroll in course
* `GET /api/courses/enrolled_courses/` – Student enrolled courses
* `GET /api/courses/available_courses/` – Courses not enrolled

---

### 📖 Lessons

* `GET /api/lessons/` – List lessons
* `POST /api/lessons/` – Create lesson (Instructor only)
* `POST /api/lessons/{id}/mark_complete/` – Mark lesson completed

---

### 🧪 Quizzes

* `POST /api/quizzes/{id}/attempt/` – Submit quiz answers

---

### 📊 Dashboards

* `GET /api/instructor-dashboard/` – Instructor dashboard
* `GET /api/student-dashboard/` – Student dashboard

---

## 🧾 Certificate Generation

* Certificate is automatically generated once:

  * All lessons are completed
  * Quiz (if applicable) is passed
* Downloadable PDF certificate

---

## ⚙️ Setup Instructions

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/adityakhule15/lms.git
cd lms
```

### 2️⃣ Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Apply Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5️⃣ Create Superuser

```bash
python manage.py createsuperuser
```

### 6️⃣ Run Development Server

```bash
python manage.py runserver
```

Server will start at:

```
http://127.0.0.1:8000/
```

---

## 📦 requirements.txt

```txt
Django>=4.2
 djangorestframework
 djangorestframework-simplejwt
 python-decouple
 Pillow
 reportlab
```

---

## 📁 Project Structure (Simplified)

```
lms/
├── accounts/        # Authentication & roles
├── courses/         # Courses & lessons
├── quizzes/         # Quiz & attempts
├── progress/        # Lesson completion & tracking
├── certificates/    # Certificate generation
├── lms/             # Project settings
└── manage.py
```

---

## 🚀 Deployment

* Ready for deployment on:

  * Render
  * Railway
  * AWS EC2
  * DigitalOcean

Use PostgreSQL and environment variables for production.

---

## ✅ Deliverables Covered

* ✔ Course creation & lesson workflow
* ✔ Enrollment & completion tracking
* ✔ Instructor & student dashboards
* ✔ Certificates of completion
* ✔ GitHub repository & README

---

## 👨‍💻 Author

**Aditya Sanjayrao Khule**
Python / Django Developer
📍 Maharashtra, India

GitHub: [https://github.com/adityakhule15](https://github.com/adityakhule15)

---

## 📜 License

This project is licensed under the MIT License.
