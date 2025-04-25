from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views, views_admin

urlpatterns = [
    path("", views.index, name="index"),  # Show index.html as the first page
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("home/", views.home, name="home"),  # Ensure this view exists
    path("calendar/", views.calendar_view, name="calendar"),
    path("notification/", views.notification_view, name="notification"),
    path("mark-notification-read/<int:notification_id>/", views.mark_notification_read, name="mark_notification_read"),
    path("leave/", views.leave_view, name="leave"),
    path("leave/<int:leave_id>/details/", views.leave_details, name="leave_details"),
    path("mark_attendance/", views.mark_attendance, name="mark_attendance"),
    path("train_face/", views.train_face_recognition, name="train_face_recognition"),
    # Admin actions for leave requests
    path("leave-request/<int:leave_id>/approve/", views.approve_leave, name="admin_approve_leave"),
    path("leave-request/<int:leave_id>/reject/", views.reject_leave, name="admin_reject_leave"),
    # Custom Admin URLs
    path('custom-admin/login/', views_admin.admin_login, name='admin_login'),
    path('custom-admin/logout/', views_admin.admin_logout, name='admin_logout'),
    path('custom-admin/dashboard/', views_admin.admin_dashboard, name='admin_dashboard'),
    path('custom-admin/users/', views_admin.admin_users, name='admin_users'),
    path('custom-admin/attendance/', views_admin.admin_attendance, name='admin_attendance'),
    path('custom-admin/settings/', views_admin.admin_settings, name='admin_settings'),
    path('custom-admin/leave-management/', views_admin.admin_leave_management, name='admin_leave_management'),
    path('custom-admin/user/<int:user_id>/toggle-status/', views_admin.toggle_user_status, name='toggle_user_status'),
    path('custom-admin/leave/<int:leave_id>/handle/', views_admin.handle_leave_request, name='handle_leave_request'),
]
