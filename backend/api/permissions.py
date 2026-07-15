from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or getattr(getattr(user, 'profile', None), 'role', None) == 'admin')
        )


class IsStudentRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and not user.is_staff
            and getattr(getattr(user, 'profile', None), 'role', None) == 'student'
        )
