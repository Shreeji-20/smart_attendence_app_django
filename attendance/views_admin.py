from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator
from .models import User, Attendance, Profile, LeaveRequest, Notification, Settings
import json
from django.core.serializers.json import DjangoJSONEncoder

def is_admin(user):
    return user.is_authenticated and user.is_staff

def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, 'You must be logged in as an admin to access this page.')
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            return redirect('admin_dashboard')
        else:
            messages.error(request, 'Invalid credentials or insufficient permissions')
    
    return render(request, 'custom_admin/login.html')

@user_passes_test(is_admin)
def admin_logout(request):
    logout(request)
    return redirect('admin_login')

@user_passes_test(is_admin)
def admin_dashboard(request):
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)

    # Basic stats
    context = {
        'total_users': User.objects.filter(is_staff=False).count(),
        'today_attendance': Attendance.objects.filter(date=today).count(),
        'active_sessions': Attendance.objects.filter(date=today, check_out_time__isnull=True).count(),
        'pending_leaves': LeaveRequest.objects.filter(status='Pending').count(),
    }

    # Department-wise attendance stats for the last 7 days
    dept_attendance = {}
    for dept_code, dept_name in Profile.DEPARTMENT_CHOICES:
        dept_stats = Attendance.objects.filter(
            date__gte=seven_days_ago,
            user__profile__department=dept_code
        ).values('status').annotate(
            count=Count('id')
        )
        present_count = sum(s['count'] for s in dept_stats if s['status'] in ['Present', 'Late'])
        total_possible = User.objects.filter(profile__department=dept_code).count() * 7
        attendance_rate = (present_count / total_possible * 100) if total_possible > 0 else 0
        dept_attendance[dept_name] = round(attendance_rate, 1)

    context['dept_attendance_labels'] = json.dumps(list(dept_attendance.keys()))
    context['dept_attendance_data'] = json.dumps(list(dept_attendance.values()))

    # Weekly leave trends
    weekly_leaves = LeaveRequest.objects.filter(
        start_date__gte=seven_days_ago
    ).values('start_date').annotate(
        approved=Count('id', filter=Q(status='Approved')),
        pending=Count('id', filter=Q(status='Pending')),
        rejected=Count('id', filter=Q(status='Rejected'))
    ).order_by('start_date')

    context['weekly_leave_dates'] = json.dumps([l['start_date'].strftime('%Y-%m-%d') for l in weekly_leaves])
    context['weekly_leave_approved'] = json.dumps([l['approved'] for l in weekly_leaves])
    context['weekly_leave_pending'] = json.dumps([l['pending'] for l in weekly_leaves])
    context['weekly_leave_rejected'] = json.dumps([l['rejected'] for l in weekly_leaves])

    # Department-wise stats
    total_users = User.objects.filter(is_staff=False).count()
    department_stats = Profile.objects.values('department').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Calculate percentages for each department
    for dept in department_stats:
        if total_users > 0:
            dept['percentage'] = round((dept['count'] / total_users) * 100)
        else:
            dept['percentage'] = 0
    
    context['department_stats'] = list(department_stats)

    # Attendance trends (last 7 days) with detailed user data
    attendance_data = Attendance.objects.filter(
        date__gte=seven_days_ago
    ).values('date').annotate(
        count=Count('id'),
        on_time=Count('id', filter=Q(status='Present')),
        late=Count('id', filter=Q(status='Late'))
    ).order_by('date')

    # Get detailed attendance records for each day
    detailed_attendance = {}
    for date in [seven_days_ago + timedelta(days=x) for x in range(8)]:
        date_records = Attendance.objects.filter(date=date).select_related('user', 'user__profile').values(
            'user__username',
            'user__first_name',
            'user__last_name',
            'user__profile__enrollment_number',
            'user__profile__department',
            'check_in_time',
            'status'
        )
        # Convert datetime objects to strings
        records_list = list(date_records)
        for record in records_list:
            if record['check_in_time']:
                record['check_in_time'] = record['check_in_time'].isoformat()
        detailed_attendance[date.strftime('%Y-%m-%d')] = records_list

    context['attendance_dates'] = json.dumps([data['date'].strftime('%Y-%m-%d') for data in attendance_data])
    context['attendance_counts'] = json.dumps([data['count'] for data in attendance_data])
    context['on_time_counts'] = json.dumps([data['on_time'] for data in attendance_data])
    context['late_counts'] = json.dumps([data['late'] for data in attendance_data])
    context['detailed_attendance'] = json.dumps(detailed_attendance)

    # User distribution with detailed lists
    active_users = User.objects.filter(last_login__gte=thirty_days_ago).select_related('profile')
    inactive_users = User.objects.filter(Q(last_login__lt=thirty_days_ago) | Q(last_login__isnull=True)).select_related('profile')
    new_users = User.objects.filter(date_joined__gte=thirty_days_ago).select_related('profile')

    def serialize_users(users):
        user_list = list(users.values('username', 'first_name', 'last_name', 'email', 'profile__department', 'last_login', 'date_joined'))
        for user in user_list:
            if user.get('last_login'):
                user['last_login'] = user['last_login'].isoformat()
            if user.get('date_joined'):
                user['date_joined'] = user['date_joined'].isoformat()
        return user_list

    context['user_distribution'] = json.dumps([active_users.count(), inactive_users.count(), new_users.count()])
    context['detailed_users'] = json.dumps({
        'active': serialize_users(active_users),
        'inactive': serialize_users(inactive_users),
        'new': serialize_users(new_users)
    })

    # Leave distribution with detailed records
    leave_stats = LeaveRequest.objects.values('leave_type').annotate(
        count=Count('id'),
        approved=Count('id', filter=Q(status='Approved')),
        rejected=Count('id', filter=Q(status='Rejected')),
        pending=Count('id', filter=Q(status='Pending'))
    )

    detailed_leaves = {}
    for leave_type in LeaveRequest.objects.values_list('leave_type', flat=True).distinct():
        leave_records = LeaveRequest.objects.filter(leave_type=leave_type).select_related('user').values(
            'user__username',
            'user__first_name',
            'user__last_name',
            'start_date',
            'end_date',
            'reason',
            'status'
        )
        # Convert datetime objects to strings
        records_list = list(leave_records)
        for record in records_list:
            record['start_date'] = record['start_date'].isoformat()
            record['end_date'] = record['end_date'].isoformat()
        detailed_leaves[leave_type] = records_list

    context['leave_types'] = json.dumps([stat['leave_type'] for stat in leave_stats])
    context['leave_counts'] = json.dumps([{
        'approved': stat['approved'],
        'rejected': stat['rejected'],
        'pending': stat['pending']
    } for stat in leave_stats])
    context['detailed_leaves'] = json.dumps(detailed_leaves)

    # Hourly attendance distribution with user details
    hourly_stats = Attendance.objects.filter(
        date__gte=seven_days_ago
    ).values('check_in_time__hour').annotate(
        count=Count('id')
    ).order_by('check_in_time__hour')
    
    detailed_hourly = {}
    for hour in range(24):
        hour_records = Attendance.objects.filter(
            date__gte=seven_days_ago,
            check_in_time__hour=hour
        ).select_related('user').values(
            'user__username',
            'user__first_name',
            'user__last_name',
            'date',
            'check_in_time',
            'status'
        )
        # Convert datetime objects to strings
        records_list = list(hour_records)
        for record in records_list:
            record['date'] = record['date'].isoformat()
            if record['check_in_time']:
                record['check_in_time'] = record['check_in_time'].isoformat()
        detailed_hourly[f"{hour:02d}:00"] = records_list

    context['hourly_labels'] = json.dumps([f"{stat['check_in_time__hour']:02d}:00" for stat in hourly_stats])
    context['hourly_counts'] = json.dumps([stat['count'] for stat in hourly_stats])
    context['detailed_hourly'] = json.dumps(detailed_hourly)

    # Recent activities
    context['recent_activities'] = Notification.objects.all().order_by('-created_at')[:5]
    context['recent_leaves'] = LeaveRequest.objects.all().order_by('-start_date')[:5]

    return render(request, 'custom_admin/dashboard.html', context)

@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.filter(is_staff=False).select_related('profile').order_by('-date_joined')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(profile__enrollment_number__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(users, 10)  # Show 10 users per page
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)

    context = {
        'users': users_page,
        'search_query': search_query,
        'departments': Profile.DEPARTMENT_CHOICES,
        'sections': Profile.SECTION_CHOICES
    }
    
    return render(request, 'custom_admin/users.html', context)

@user_passes_test(is_admin)
def admin_attendance(request):
    # Get filter parameters
    date_filter = request.GET.get('date')
    department_filter = request.GET.get('department')
    status_filter = request.GET.get('status')

    # Base queryset
    attendance_records = Attendance.objects.all().select_related('user', 'user__profile')

    # Apply filters
    if date_filter:
        attendance_records = attendance_records.filter(date=date_filter)
    if department_filter:
        attendance_records = attendance_records.filter(user__profile__department=department_filter)
    if status_filter:
        attendance_records = attendance_records.filter(status=status_filter)

    # Pagination
    paginator = Paginator(attendance_records.order_by('-date', '-check_in_time'), 20)
    page_number = request.GET.get('page')
    attendance_page = paginator.get_page(page_number)

    context = {
        'attendance_records': attendance_page,
        'departments': Profile.DEPARTMENT_CHOICES,
        'date_filter': date_filter,
        'department_filter': department_filter,
        'status_filter': status_filter
    }

    return render(request, 'custom_admin/attendance.html', context)

@login_required
@admin_required
def admin_settings(request):
    settings = Settings.get_settings()
    
    if request.method == 'POST':
        # Update settings
        settings.working_hours_start = request.POST.get('working_hours_start')
        settings.working_hours_end = request.POST.get('working_hours_end')
        settings.allow_late_checkin = request.POST.get('allow_late_checkin') == 'on'
        settings.late_threshold = int(request.POST.get('late_threshold', 15))
        settings.send_notifications = request.POST.get('send_notifications') == 'on'
        settings.max_leaves = int(request.POST.get('max_leaves', 2))
        settings.leave_notice_days = int(request.POST.get('leave_notice_days', 1))
        settings.save()
        
        messages.success(request, 'Settings updated successfully!')
        return redirect('admin_settings')
    
    context = {
        'settings': settings,
    }
    return render(request, 'custom_admin/settings.html', context)

@user_passes_test(is_admin)
def toggle_user_status(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = not user.is_active
    user.save()
    
    status = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f'User {user.username} has been {status}')
    return redirect('admin_users')

@user_passes_test(is_admin)
def admin_leave_management(request):
    # Get filter parameters
    status_filter = request.GET.get('status')
    leave_type_filter = request.GET.get('leave_type')
    search_query = request.GET.get('search', '')

    # Base queryset
    leave_requests = LeaveRequest.objects.all().select_related('user', 'user__profile').order_by('-start_date')

    # Apply filters
    if status_filter:
        leave_requests = leave_requests.filter(status=status_filter)
    if leave_type_filter:
        leave_requests = leave_requests.filter(leave_type=leave_type_filter)
    if search_query:
        leave_requests = leave_requests.filter(
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__profile__department__icontains=search_query) |
            Q(leave_type__icontains=search_query)
        )

    # Add duration field
    for leave in leave_requests:
        leave.duration = (leave.end_date - leave.start_date).days + 1

    # Pagination
    paginator = Paginator(leave_requests, 10)  # Show 10 requests per page
    page_number = request.GET.get('page')
    leave_page = paginator.get_page(page_number)

    context = {
        'leave_requests': leave_page,
        'leave_types': LeaveRequest.LEAVE_CHOICES,
        'status_filter': status_filter,
        'leave_type_filter': leave_type_filter,
        'search_query': search_query,
    }
    
    return render(request, 'custom_admin/leave_management.html', context)

@user_passes_test(is_admin)
def handle_leave_request(request, leave_id):
    if request.method != 'POST':
        return redirect('admin_leave_management')

    leave_request = get_object_or_404(LeaveRequest, id=leave_id)
    action = request.POST.get('action')

    if action == 'approve':
        leave_request.status = 'Approved'
        message = f'Leave request approved for {leave_request.user.get_full_name()}'
    elif action == 'reject':
        leave_request.status = 'Rejected'
        message = f'Leave request rejected for {leave_request.user.get_full_name()}'
    else:
        messages.error(request, 'Invalid action')
        return redirect('admin_leave_management')

    leave_request.save()

    # Create notification for the user
    Notification.objects.create(
        user=leave_request.user,
        notification_type='leave',
        title=f'Leave Request {leave_request.status}',
        message=f'Your {leave_request.leave_type} request from {leave_request.start_date} to {leave_request.end_date} has been {leave_request.status.lower()}.',
        link='/leave-requests/'  # Adjust this based on your URL structure
    )

    messages.success(request, message)
    return redirect('admin_leave_management') 