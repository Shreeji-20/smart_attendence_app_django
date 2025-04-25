from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count, Avg, F, ExpressionWrapper, DateTimeField
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models.functions import ExtractHour, ExtractMinute
from .models import Attendance, LeaveRequest, Profile, Notification
from collections import defaultdict
import json
from django.http import JsonResponse
from .face_recognition import FaceRecognizer
import os
import numpy as np
from django.db.models import Max
from django.utils.timezone import localtime
import pytz
from django.contrib.admin.views.decorators import staff_member_required

# Initialize face recognizer
face_recognizer = FaceRecognizer()

def create_notification(user, notification_type, title, message, link=None):
    """Helper function to create notifications"""
    Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link
    )

def index(request):
    return render(request, "attendance/index.html")  # Ensure index.html is in the correct template folder



def login_view(request):
    if request.user.is_authenticated:  
        return redirect("home")  # Redirect logged-in users to home

    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("home")  # Redirect to home after login
        else:
            messages.error(request, "Invalid username or password!")

    return render(request, "attendance/login.html")


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from .models import Attendance
from django.db.models import Count

@login_required
def home(request):
    user = request.user
    today = timezone.now().date()

    # Fetch attendance data for the logged-in user
    attendance_data = Attendance.objects.filter(user=user)

    # 1. Monthly Attendance Trends
    monthly_attendance = (
        attendance_data
        .values('date__month')
        .annotate(total=Count('id'))
        .order_by('date__month')
    )

    # 2. Weekly Attendance Patterns - Updated to show Monday through Saturday
    weekly_attendance = (
        attendance_data
        .exclude(date__week_day=7)  # Exclude Sunday (week_day=7)
        .values('date__week_day')
        .annotate(count=Count('id'))
        .order_by('date__week_day')
    )
    
    # Convert weekly attendance to a list of counts in order of days
    weekly_counts = [0] * 6  # Initialize with zeros for Monday to Saturday
    
    # Add historical attendance
    for item in weekly_attendance:
        # Convert 1-7 (Monday-Sunday) to 0-5 (Monday-Saturday)
        day_index = item['date__week_day'] - 1
        weekly_counts[day_index] = item['count']
    
    # Add today's attendance if exists (excluding Sunday)
    today_attendance = attendance_data.filter(date=today).count()
    today_weekday = today.weekday()  # 0-6 (Monday-Sunday)
    if today_weekday != 6:  # Only add if not Sunday
        weekly_counts[today_weekday] += today_attendance

    # Update the days list to match the correct order
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    # 3. Daily Check-in/Check-out Times (calculated in Python)
    daily_times = []
    date_attendance = defaultdict(lambda: {'check_in_times': [], 'check_out_times': []})
    
    # Get last 30 days of attendance
    thirty_days_ago = today - timedelta(days=30)
    recent_attendance = attendance_data.filter(
        date__gte=thirty_days_ago,
        date__isnull=False
    ).order_by('date')
    
    for attendance in recent_attendance:
        if attendance.date and attendance.check_in_time:
            date_attendance[attendance.date]['check_in_times'].append(attendance.check_in_time)
        if attendance.date and attendance.check_out_time:
            date_attendance[attendance.date]['check_out_times'].append(attendance.check_out_time)
    
    for date, times in date_attendance.items():
        try:
            avg_check_in = None
            avg_check_out = None
            
            if times['check_in_times']:
                total_minutes = sum((t.hour * 60 + t.minute) for t in times['check_in_times'])
                avg_minutes = total_minutes / len(times['check_in_times'])
                avg_check_in = datetime.combine(date, datetime.min.time()) + timedelta(minutes=avg_minutes)
            
            if times['check_out_times']:
                total_minutes = sum((t.hour * 60 + t.minute) for t in times['check_out_times'])
                avg_minutes = total_minutes / len(times['check_out_times'])
                avg_check_out = datetime.combine(date, datetime.min.time()) + timedelta(minutes=avg_minutes)
            
            daily_times.append({
                'date': date.strftime('%Y-%m-%d') if date else None,
                'avg_check_in': avg_check_in.strftime('%Y-%m-%d %H:%M:%S') if avg_check_in else None,
                'avg_check_out': avg_check_out.strftime('%Y-%m-%d %H:%M:%S') if avg_check_out else None
            })
        except (AttributeError, TypeError):
            continue
    
    # 4. Department Attendance
    try:
        dept_attendance = list(
            attendance_data
            .filter(date__isnull=False)
            .values('user__profile__department')
            .annotate(
                total=Count('id'),
                percentage=Count('id') * 100.0 / attendance_data.filter(date__isnull=False).count() if attendance_data.exists() else 0
            )
            .exclude(user__profile__department__isnull=True)
        )
    except Exception:
        dept_attendance = []
    
    # 5. Leave Statistics
    leave_stats = (
        LeaveRequest.objects
        .filter(user=user)
        .values('leave_type')
        .annotate(count=Count('id'))
    )

    # 6. Late Arrivals Count
    late_arrivals_count = attendance_data.filter(
        check_in_time__hour__gte=8,
        check_in_time__minute__gte=10
    ).count()
    
    context = {
        'user': user,
        'monthly_attendance': list(monthly_attendance),
        'weekly_attendance': weekly_counts,
        'daily_times': json.dumps(daily_times),
        'dept_attendance': json.dumps(dept_attendance),
        'leave_stats': list(leave_stats),
        'late_arrivals_count': late_arrivals_count,
        'months': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
        'days': days  # Use the updated days list
    }
    
    return render(request, 'attendance/home.html', context)


def register_view(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        password1 = request.POST["password1"]
        password2 = request.POST["password2"]
        enrollment_number = request.POST["enrollment_number"]
        department = request.POST["department"]
        semester = request.POST["semester"]
        section = request.POST["section"]
        phone_number = request.POST["phone_number"]
        address = request.POST["address"]

        if password1 == password2:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already taken.")
            elif User.objects.filter(email=email).exists():
                messages.error(request, "Email already registered.")
            elif Profile.objects.filter(enrollment_number=enrollment_number).exists():
                messages.error(request, "Enrollment number already registered.")
            else:
                # Create user
                user = User.objects.create_user(username=username, email=email, password=password1)
                
                # Update profile
                profile = Profile.objects.get(user=user)
                profile.enrollment_number = enrollment_number
                profile.department = department
                profile.semester = semester
                profile.section = section
                profile.phone_number = phone_number
                profile.address = address
                profile.save()
                
                messages.success(request, "Registration successful! Please log in.")
                return redirect("login")
        else:
            messages.error(request, "Passwords do not match.")

    # Get department choices for the template
    department_choices = Profile.DEPARTMENT_CHOICES
    return render(request, "attendance/register.html", {'department_choices': department_choices})

@login_required(login_url="login")
def home_view(request):
    return render(request, "attendance/home.html")

@login_required
def calendar_view(request):
    user = request.user
    attendance_data = Attendance.objects.filter(user=user)
    
    # Get attendance data for the calendar
    calendar_events = []
    for attendance in attendance_data:
        if attendance.date:  # Check if date exists
            event = {
                'title': 'Present',  # Default title
                'start': attendance.date.strftime('%Y-%m-%d'),  # Required by FullCalendar
                'allDay': True,  # Full day event
                'backgroundColor': '#4e73df',  # Default color
                'borderColor': '#4e73df',
                'extendedProps': {
                    'check_in': attendance.check_in_time.strftime('%I:%M %p') if attendance.check_in_time else 'Not marked',
                    'check_out': attendance.check_out_time.strftime('%I:%M %p') if attendance.check_out_time else 'Not marked',
                }
            }
            calendar_events.append(event)
    
    return render(request, 'attendance/calendar.html', {
        'calendar_events': json.dumps(calendar_events)
    })

@login_required
def notification_view(request):
    notifications = Notification.objects.filter(user=request.user)
    unread_count = notifications.filter(is_read=False).count()
    
    if request.method == 'POST' and request.POST.get('action') == 'mark_all_read':
        notifications.update(is_read=True)
        return JsonResponse({'success': True})
    
    context = {
        'notifications': notifications,
        'unread_count': unread_count
    }
    return render(request, 'attendance/notification.html', context)

@login_required
def mark_notification_read(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.is_read = True
        notification.save()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Notification not found'}, status=404)

def leave_view(request):
    if request.method == "POST":
        leave_type = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason')

        # Validate leave type
        if not leave_type or leave_type not in dict(LeaveRequest.LEAVE_CHOICES):
            messages.error(request, "Please select a valid leave type.")
            return redirect('leave')

        leave_request = LeaveRequest.objects.create(
            user=request.user,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status='Pending'  # Explicitly set status
        )

        create_notification(
            request.user,
            'leave',
            'Leave Request Submitted',
            f'Your {leave_type} request from {start_date} to {end_date} has been submitted.',
            f'/leave/{leave_request.id}/details/'
        )

        messages.success(request, "Your leave request has been submitted!")
        return redirect('leave')

    user_leaves = LeaveRequest.objects.filter(user=request.user).order_by('-start_date')
    leave_choices = LeaveRequest.LEAVE_CHOICES
    return render(request, 'attendance/leave.html', {
        'leaves': user_leaves,
        'leave_choices': leave_choices
    })

@login_required
def mark_attendance(request):
    user = request.user
    ist = pytz.timezone('Asia/Kolkata')
    today = localtime(timezone.now(), ist)
    
    if request.method == "POST":
        try:
            if not os.path.exists(os.path.join(face_recognizer.faces_dir, f'user_{user.id}.jpg')):
                return JsonResponse({
                    'success': False,
                    'message': 'Please train your face first before marking attendance.'
                })
            
            image_data = request.POST.get('image_data')
            action = request.POST.get('action')
            
            if not image_data:
                return JsonResponse({
                    'success': False,
                    'message': 'No image data provided'
                })
            
            result = face_recognizer.predict(image_data, user.id)
            
            if not result['success']:
                return JsonResponse({
                    'success': False,
                    'message': result['message']
                })
            
            attendance, created = Attendance.objects.get_or_create(
                user=user,
                date=today.date(),
                defaults={'check_in_time': today.time()}
            )
            
            if not created:
                if not attendance.check_out_time:
                    attendance.check_out_time = today.time()
                    attendance.save()
                    create_notification(
                        user,
                        'attendance',
                        'Check-out Recorded',
                        f'You have checked out at {today.strftime("%I:%M %p")} IST',
                        '/calendar/'
                    )
                    return JsonResponse({
                        'success': True,
                        'message': f'Check-out time recorded successfully at {today.strftime("%I:%M %p")} IST!'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'You have already checked out for today.'
                    })
            else:
                create_notification(
                    user,
                    'attendance',
                    'Check-in Recorded',
                    f'You have checked in at {today.strftime("%I:%M %p")} IST',
                    '/calendar/'
                )
                return JsonResponse({
                    'success': True,
                    'message': f'Check-in time recorded successfully at {today.strftime("%I:%M %p")} IST!'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error processing attendance: {str(e)}'
            })
    
    today_attendance = Attendance.objects.filter(
        user=user,
        date=today.date()
    ).first()
    
    has_face_data = os.path.exists(os.path.join(face_recognizer.faces_dir, f'user_{user.id}.jpg'))
    
    context = {
        'today_attendance': today_attendance,
        'can_check_in': not today_attendance or not today_attendance.check_in_time,
        'can_check_out': today_attendance and today_attendance.check_in_time and not today_attendance.check_out_time,
        'has_face_data': has_face_data
    }
    
    return render(request, 'attendance/mark_attendance.html', context)

@login_required
def train_face_recognition(request):
    if request.method == "POST":
        try:
            # Get the image data from the request
            image_data = request.POST.get('image_data')
            
            if not image_data:
                return JsonResponse({
                    'success': False,
                    'message': 'No image data provided'
                })
            
            # Preprocess the image
            gray = face_recognizer.preprocess_image(image_data)
            if gray is None:
                return JsonResponse({
                    'success': False,
                    'message': 'Error preprocessing image'
                })
            
            # Detect and extract face
            face, error = face_recognizer.detect_face(gray)
            if face is None:
                return JsonResponse({
                    'success': False,
                    'message': error
                })
            
            # Train the model with the user's ID
            if face_recognizer.train(face, request.user.id):
                return JsonResponse({
                    'success': True,
                    'message': 'Face recognition training completed successfully!'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Error training face recognition'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error processing training: {str(e)}'
            })
    
    # For GET requests, show the training form
    context = {
        'has_face_data': os.path.exists(os.path.join(face_recognizer.faces_dir, f'user_{request.user.id}.jpg'))
    }
    return render(request, 'attendance/train_face.html', context)

@staff_member_required
def approve_leave(request, leave_id):
    try:
        leave_request = LeaveRequest.objects.get(id=leave_id)
        if leave_request.status == 'Pending':
            leave_request.status = 'Approved'
            leave_request.save()
            
            # Create notification for the student
            Notification.objects.create(
                user=leave_request.user,
                notification_type='leave',
                title='Leave Request Approved',
                message=f'Your leave request from {leave_request.start_date} to {leave_request.end_date} has been approved.',
                link='/leave/'
            )
            messages.success(request, 'Leave request has been approved successfully.')
        else:
            messages.warning(request, 'This leave request has already been processed.')
    except LeaveRequest.DoesNotExist:
        messages.error(request, 'Leave request not found.')
    except Exception as e:
        messages.error(request, f'An error occurred: {str(e)}')
    return redirect('admin:attendance_leaverequest_changelist')

@staff_member_required
def reject_leave(request, leave_id):
    try:
        leave_request = LeaveRequest.objects.get(id=leave_id)
        if leave_request.status == 'Pending':
            leave_request.status = 'Rejected'
            leave_request.save()
            
            # Create notification for the student
            Notification.objects.create(
                user=leave_request.user,
                notification_type='leave',
                title='Leave Request Rejected',
                message=f'Your leave request from {leave_request.start_date} to {leave_request.end_date} has been rejected.',
                link='/leave/'
            )
            messages.success(request, 'Leave request has been rejected successfully.')
        else:
            messages.warning(request, 'This leave request has already been processed.')
    except LeaveRequest.DoesNotExist:
        messages.error(request, 'Leave request not found.')
    except Exception as e:
        messages.error(request, f'An error occurred: {str(e)}')
    return redirect('admin:attendance_leaverequest_changelist')

@login_required
def leave_details(request, leave_id):
    try:
        leave_request = LeaveRequest.objects.get(id=leave_id, user=request.user)
        context = {
            'leave_request': leave_request,
            'status_color': {
                'Pending': 'warning',
                'Approved': 'success',
                'Rejected': 'danger'
            }.get(leave_request.status, 'secondary')
        }
        return render(request, 'attendance/leave_details.html', context)
    except LeaveRequest.DoesNotExist:
        messages.error(request, "Leave request not found.")
        return redirect('notification')

