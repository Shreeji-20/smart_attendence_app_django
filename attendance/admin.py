from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Profile, Attendance, LeaveRequest, Notification
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'

class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_department', 'get_section')
    list_select_related = ('profile',)

    def get_department(self, instance):
        return instance.profile.department
    get_department.short_description = 'Department'

    def get_section(self, instance):
        return instance.profile.section
    get_section.short_description = 'Section'

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super(CustomUserAdmin, self).get_inline_instances(request, obj)

class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'check_in_time', 'check_out_time', 'status')
    list_filter = ('date', 'status', 'user__profile__department', 'user__profile__section')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    date_hierarchy = 'date'
    ordering = ('-date', '-check_in_time')

class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_leave_type', 'start_date', 'end_date', 'status', 'approval_actions')
    list_filter = ('status', 'leave_type', 'start_date', 'end_date')
    search_fields = ('user__username', 'reason', 'leave_type')
    date_hierarchy = 'start_date'
    ordering = ('-start_date',)
    actions = ['approve_selected_requests', 'reject_selected_requests']

    def get_leave_type(self, obj):
        if not obj.leave_type:
            return "Not Specified"
        return obj.leave_type
    get_leave_type.short_description = 'Leave Type'
    get_leave_type.admin_order_field = 'leave_type'

    def approval_actions(self, obj):
        if obj.status == 'Pending':
            approve_url = reverse('admin_approve_leave', args=[obj.id])
            reject_url = reverse('admin_reject_leave', args=[obj.id])
            return format_html(
                '<div class="submit-row">'
                '<a href="{}" class="button" style="background: #28a745; color: white; padding: 5px 10px; '
                'border-radius: 4px; text-decoration: none; margin-right: 5px;">Approve</a>'
                '<a href="{}" class="button" style="background: #dc3545; color: white; padding: 5px 10px; '
                'border-radius: 4px; text-decoration: none;">Reject</a>'
                '</div>',
                approve_url,
                reject_url
            )
        return mark_safe(f'<span style="color: {self._get_status_color(obj.status)};">{obj.status}</span>')

    def _get_status_color(self, status):
        colors = {
            'Approved': '#28a745',
            'Rejected': '#dc3545',
            'Pending': '#ffc107'
        }
        return colors.get(status, 'black')

    approval_actions.short_description = 'Actions'
    approval_actions.allow_tags = True

    def approve_selected_requests(self, request, queryset):
        for leave_request in queryset:
            if leave_request.status == 'Pending':
                leave_request.status = 'Approved'
                leave_request.save()
                # Create notification for the student
                Notification.objects.create(
                    user=leave_request.user,
                    notification_type='leave',
                    title='Leave Request Approved',
                    message=f'Your leave request from {leave_request.start_date} to {leave_request.end_date} has been approved.',
                    link=f'/leave/{leave_request.id}/details/'
                )
        self.message_user(request, f"{queryset.count()} leave requests were approved.")
    approve_selected_requests.short_description = "Approve selected leave requests"

    def reject_selected_requests(self, request, queryset):
        for leave_request in queryset:
            if leave_request.status == 'Pending':
                leave_request.status = 'Rejected'
                leave_request.save()
                # Create notification for the student
                Notification.objects.create(
                    user=leave_request.user,
                    notification_type='leave',
                    title='Leave Request Rejected',
                    message=f'Your leave request from {leave_request.start_date} to {leave_request.end_date} has been rejected.',
                    link=f'/leave/{leave_request.id}/details/'
                )
        self.message_user(request, f"{queryset.count()} leave requests were rejected.")
    reject_selected_requests.short_description = "Reject selected leave requests"

class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'created_at', 'is_read')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

# Unregister the default User admin and register our custom admin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Attendance, AttendanceAdmin)
admin.site.register(LeaveRequest, LeaveRequestAdmin)
admin.site.register(Notification, NotificationAdmin)
