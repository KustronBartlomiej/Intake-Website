from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User


@admin.action(description='Approve selected users')
def approve_users(modeladmin, request, queryset):
    queryset.update(is_active=True)


class ApprovalUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ('is_active',)
    actions = [approve_users]


admin.site.unregister(User)
admin.site.register(User, ApprovalUserAdmin)
