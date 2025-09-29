from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth import login


def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.is_superuser or user.is_staff:
                return redirect('all_groups_admin')
            elif hasattr(user, 'role') and user.role == 'teacher':
                return redirect('teacher_home')
            elif hasattr(user, 'role') and user.role == 'student':
                return redirect('student_home')
            else:
                messages.error(request, "Roli aniqlanmadi", extra_tags='login_message')
        else:
            messages.error(request, "Login yoki parol noto‘g‘ri", extra_tags='login_message')

    return render(request, 'main/login.html')
