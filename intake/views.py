import json
import calendar as cal_module
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import FoodEntry, Friendship, ProductEntryRequest, ProductList, QuickAddProduct


def _parse_decimal(raw):
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except Exception:
        return None


def _day_summary(user, day):
    entries = FoodEntry.objects.filter(user=user, date=day)
    kcal = sum(e.total_kcal for e in entries)
    protein = sum(e.total_protein for e in entries)
    return kcal, protein


def _accepted_friendships(user):
    return Friendship.objects.filter(
        Q(sender=user) | Q(recipient=user),
        status=Friendship.STATUS_ACCEPTED,
    ).select_related('sender', 'recipient')


def _friends(user):
    return [
        friendship.recipient if friendship.sender_id == user.id else friendship.sender
        for friendship in _accepted_friendships(user)
    ]


def _are_friends(first, second):
    return Friendship.objects.filter(
        Q(sender=first, recipient=second) | Q(sender=second, recipient=first),
        status=Friendship.STATUS_ACCEPTED,
    ).exists()


# ── Home ──────────────────────────────────────────────────────────────────────

@login_required
def home(request):
    today = date.today()
    profile = request.user.profile
    kcal_total, protein_total = _day_summary(request.user, today)

    kcal_pct = min(round(kcal_total / profile.kcal_goal * 100) if profile.kcal_goal else 0, 100)
    protein_pct = min(round(protein_total / profile.protein_goal * 100) if profile.protein_goal else 0, 100)

    today_entries = FoodEntry.objects.filter(user=request.user, date=today)
    quick_entries = today_entries.filter(source=FoodEntry.SOURCE_QUICK)
    lists = ProductList.objects.filter(owner=request.user).annotate(product_count=Count('products'))

    return render(request, 'intake/home.html', {
        'today': today,
        'kcal_total': kcal_total,
        'protein_total': protein_total,
        'kcal_goal': profile.kcal_goal,
        'protein_goal': profile.protein_goal,
        'kcal_pct': kcal_pct,
        'protein_pct': protein_pct,
        'quick_entries': quick_entries,
        'lists': lists,
        'friends': _friends(request.user),
    })


# ── Nutrient Detail ───────────────────────────────────────────────────────────

@login_required
def detail(request, nutrient):
    if nutrient not in ('calories', 'protein'):
        return redirect('home')

    today = date.today()
    profile = request.user.profile
    kcal_total, protein_total = _day_summary(request.user, today)

    if nutrient == 'calories':
        total = kcal_total
        goal = profile.kcal_goal
        color = 'orange'
        unit = 'kcal'
    else:
        total = protein_total
        goal = profile.protein_goal
        color = 'blue'
        unit = 'g'

    pct = min(round(total / goal * 100) if goal else 0, 100)
    circ = 263.9
    dash_offset = round(circ - (pct / 100) * circ, 2)
    entries = FoodEntry.objects.filter(user=request.user, date=today)

    return render(request, 'intake/detail.html', {
        'nutrient': nutrient,
        'total': total,
        'goal': goal,
        'pct': pct,
        'dash_offset': dash_offset,
        'color': color,
        'unit': unit,
        'entries': entries,
        'today': today,
    })


# ── Set Goal ──────────────────────────────────────────────────────────────────

@login_required
@require_POST
def set_goal(request, nutrient):
    if nutrient not in ('calories', 'protein'):
        return redirect('home')
    profile = request.user.profile
    try:
        value = int(request.POST.get('goal', 0))
        if value > 0:
            if nutrient == 'calories':
                profile.kcal_goal = value
            else:
                profile.protein_goal = value
            profile.save()
    except (ValueError, TypeError):
        pass
    return redirect('detail', nutrient=nutrient)


# ── Add Meal (2-step) ─────────────────────────────────────────────────────────

@login_required
def add_meal(request, target_date=None):
    if target_date is None:
        target_date = date.today()

    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip() or 'Meal'
            kcal_per_100g = Decimal(request.POST.get('kcal_per_100g', '0'))
            protein_per_100g = Decimal(request.POST.get('protein_per_100g', '0'))
            weight_g = Decimal(request.POST.get('weight_g', '0'))
            entry_date_str = request.POST.get('entry_date', str(target_date))
            entry_date = date.fromisoformat(entry_date_str)

            FoodEntry.objects.create(
                user=request.user,
                date=entry_date,
                name=name,
                kcal_per_100g=kcal_per_100g,
                protein_per_100g=protein_per_100g,
                weight_g=weight_g,
                source=FoodEntry.SOURCE_MANUAL,
            )

            if str(entry_date) == str(date.today()):
                return redirect('home')
            return redirect('calendar_day', day=str(entry_date))
        except (ValueError, TypeError):
            pass

    return render(request, 'intake/add_meal.html', {
        'target_date': target_date,
        'today': date.today(),
    })


# ── Product Lists ────────────────────────────────────────────────────────────

@login_required
def product_lists(request):
    lists = ProductList.objects.filter(owner=request.user).annotate(product_count=Count('products'))
    return render(request, 'intake/product_lists.html', {
        'lists': lists,
    })


@login_required
@require_POST
def product_list_create(request):
    name = request.POST.get('name', '').strip()
    is_public = request.POST.get('is_public') == 'on'
    if name:
        plist = ProductList.objects.create(owner=request.user, name=name, is_public=is_public)
        return redirect('product_list_detail', pk=plist.pk)
    return redirect('product_lists')


@login_required
def product_list_detail(request, pk):
    plist = get_object_or_404(ProductList, pk=pk, owner=request.user)
    today = date.today()
    q = request.GET.get('q', '').strip()
    products = plist.products.all()
    if q:
        products = products.filter(name__icontains=q)
    products = list(products)
    for product in products:
        first = product.name[:1].upper()
        product.initial = first if first.isalpha() else '#'
    available_initials = {product.initial for product in products}
    return render(request, 'intake/product_list_detail.html', {
        'plist': plist,
        'products': products,
        'q': q,
        'alphabet': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        'available_initials': available_initials,
        'friends': _friends(request.user),
        'other_lists': ProductList.objects.filter(owner=request.user).exclude(pk=plist.pk),
        'today': today,
    })


@login_required
@require_POST
def product_list_rename(request, pk):
    plist = get_object_or_404(ProductList, pk=pk, owner=request.user)
    name = request.POST.get('name', '').strip()
    if name:
        plist.name = name
        plist.save()
    return redirect('product_list_detail', pk=pk)


@login_required
@require_POST
def product_list_toggle_public(request, pk):
    plist = get_object_or_404(ProductList, pk=pk, owner=request.user)
    plist.is_public = not plist.is_public
    plist.save()
    return redirect('product_list_detail', pk=pk)


@login_required
@require_POST
def product_list_delete(request, pk):
    plist = get_object_or_404(ProductList, pk=pk, owner=request.user)
    plist.delete()
    return redirect('product_lists')


@login_required
def public_lists(request):
    q = request.GET.get('q', '').strip()
    lists = (
        ProductList.objects
        .filter(is_public=True)
        .exclude(owner=request.user)
        .annotate(product_count=Count('products'))
        .select_related('owner')
    )
    if q:
        lists = lists.filter(owner__username__icontains=q)
    return render(request, 'intake/public_lists.html', {'lists': lists, 'q': q})


@login_required
@require_POST
def product_list_clone(request, pk):
    source = get_object_or_404(ProductList, pk=pk, is_public=True)
    clone = ProductList.objects.create(owner=request.user, name=source.name, is_public=False)
    for p in source.products.all():
        QuickAddProduct.objects.create(
            product_list=clone,
            name=p.name,
            kcal_per_100g=p.kcal_per_100g,
            protein_per_100g=p.protein_per_100g,
            default_weight_g=p.default_weight_g,
        )
    return redirect('product_list_detail', pk=clone.pk)


# ── Products within a list ───────────────────────────────────────────────────

@login_required
@require_POST
def quick_add_product_create(request, pk):
    plist = get_object_or_404(ProductList, pk=pk, owner=request.user)
    name = request.POST.get('name', '').strip()
    kcal_per_100g = _parse_decimal(request.POST.get('kcal_per_100g')) or Decimal('0')
    protein_per_100g = _parse_decimal(request.POST.get('protein_per_100g')) or Decimal('0')
    default_weight_g = _parse_decimal(request.POST.get('default_weight_g'))

    if name:
        QuickAddProduct.objects.create(
            product_list=plist,
            name=name,
            kcal_per_100g=kcal_per_100g,
            protein_per_100g=protein_per_100g,
            default_weight_g=default_weight_g,
        )
    return redirect('product_list_detail', pk=pk)


@login_required
@require_POST
def quick_add_product_edit(request, pk):
    product = get_object_or_404(QuickAddProduct, pk=pk, product_list__owner=request.user)
    name = request.POST.get('name', '').strip()
    kcal_per_100g = _parse_decimal(request.POST.get('kcal_per_100g'))
    protein_per_100g = _parse_decimal(request.POST.get('protein_per_100g'))
    default_weight_g = _parse_decimal(request.POST.get('default_weight_g'))

    if name and kcal_per_100g is not None and protein_per_100g is not None:
        product.name = name
        product.kcal_per_100g = kcal_per_100g
        product.protein_per_100g = protein_per_100g
        product.default_weight_g = default_weight_g
        product.save()
    return redirect('product_list_detail', pk=product.product_list_id)


@login_required
@require_POST
def quick_add_product_delete(request, pk):
    product = get_object_or_404(QuickAddProduct, pk=pk, product_list__owner=request.user)
    list_pk = product.product_list_id
    product.delete()
    return redirect('product_list_detail', pk=list_pk)


@login_required
@require_POST
@transaction.atomic
def quick_add_use(request, pk):
    product = get_object_or_404(QuickAddProduct, pk=pk, product_list__owner=request.user)
    weight_g = _parse_decimal(request.POST.get('weight_g')) or product.default_weight_g
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    added = False

    date_param = request.GET.get('date') or request.POST.get('date')
    try:
        entry_date = date.fromisoformat(date_param) if date_param else date.today()
    except ValueError:
        entry_date = date.today()

    if weight_g and weight_g > 0:
        FoodEntry.objects.create(
            user=request.user,
            date=entry_date,
            name=product.name,
            kcal_per_100g=product.kcal_per_100g,
            protein_per_100g=product.protein_per_100g,
            weight_g=weight_g,
            source=FoodEntry.SOURCE_QUICK,
        )
        added = True

        recipient_id = request.POST.get('recipient')
        if recipient_id:
            recipient = User.objects.filter(pk=recipient_id).first()
            if recipient and _are_friends(request.user, recipient):
                ProductEntryRequest.objects.create(
                    sender=request.user,
                    recipient=recipient,
                    product=product,
                    product_name=product.name,
                    kcal_per_100g=product.kcal_per_100g,
                    protein_per_100g=product.protein_per_100g,
                    weight_g=weight_g,
                    date=entry_date,
                )
                if not is_ajax:
                    messages.success(request, f'Added for you and sent to {recipient.username} for approval.')

    if is_ajax:
        return JsonResponse({'ok': added}, status=200 if added else 400)

    if str(entry_date) != str(date.today()):
        return redirect('calendar_day', day=str(entry_date))
    return redirect('product_list_detail', pk=product.product_list_id)


@login_required
@require_POST
def quick_add_product_copy(request, pk):
    product = get_object_or_404(QuickAddProduct, pk=pk, product_list__owner=request.user)
    target = get_object_or_404(ProductList, pk=request.POST.get('target_list'), owner=request.user)
    if target.pk == product.product_list_id:
        messages.error(request, 'Choose another list.')
        return redirect('product_list_detail', pk=product.product_list_id)

    QuickAddProduct.objects.create(
        product_list=target,
        name=product.name,
        kcal_per_100g=product.kcal_per_100g,
        protein_per_100g=product.protein_per_100g,
        default_weight_g=product.default_weight_g,
    )
    messages.success(request, f'Copied {product.name} to {target.name}.')
    return redirect('product_list_detail', pk=product.product_list_id)


@login_required
@require_POST
def product_request_create(request, pk):
    product = get_object_or_404(QuickAddProduct, pk=pk, product_list__owner=request.user)
    recipient = get_object_or_404(User, pk=request.POST.get('recipient'))
    weight_g = _parse_decimal(request.POST.get('weight_g')) or product.default_weight_g
    try:
        entry_date = date.fromisoformat(request.POST.get('date') or str(date.today()))
    except ValueError:
        entry_date = date.today()

    if not _are_friends(request.user, recipient):
        messages.error(request, 'You can only send products to accepted friends.')
    elif not weight_g or weight_g <= 0:
        messages.error(request, 'Enter a valid product weight.')
    else:
        ProductEntryRequest.objects.create(
            sender=request.user,
            recipient=recipient,
            product=product,
            product_name=product.name,
            kcal_per_100g=product.kcal_per_100g,
            protein_per_100g=product.protein_per_100g,
            weight_g=weight_g,
            date=entry_date,
        )
        messages.success(request, f'Sent to {recipient.username} for approval.')
    return redirect('product_list_detail', pk=product.product_list_id)


@login_required
@require_POST
def entry_request_create(request, pk):
    entry = get_object_or_404(FoodEntry, pk=pk, user=request.user)
    recipient = get_object_or_404(User, pk=request.POST.get('recipient'))

    if not _are_friends(request.user, recipient):
        messages.error(request, 'You can only send products to accepted friends.')
    else:
        ProductEntryRequest.objects.create(
            sender=request.user,
            recipient=recipient,
            product_name=entry.name,
            kcal_per_100g=entry.kcal_per_100g,
            protein_per_100g=entry.protein_per_100g,
            weight_g=entry.weight_g,
            date=entry.date,
        )
        messages.success(request, f'Sent to {recipient.username} for approval.')

    next_url = request.POST.get('next')
    return redirect(next_url or 'home')


@login_required
@require_POST
def entry_repeat(request, pk):
    entry = get_object_or_404(FoodEntry, pk=pk, user=request.user)
    FoodEntry.objects.create(
        user=request.user,
        date=entry.date,
        name=entry.name,
        kcal_per_100g=entry.kcal_per_100g,
        protein_per_100g=entry.protein_per_100g,
        weight_g=entry.weight_g,
        source=entry.source,
    )
    messages.success(request, f'Added {entry.name} again.')
    next_url = request.POST.get('next')
    return redirect(next_url or 'home')


# ── Friends and notifications ────────────────────────────────────────────────

@login_required
@require_POST
def friend_request_create(request):
    username = request.POST.get('username', '').strip()
    recipient = User.objects.filter(username__iexact=username, is_active=True).first()
    if not recipient:
        messages.error(request, 'No active user with that username was found.')
    elif recipient == request.user:
        messages.error(request, 'You cannot add yourself as a friend.')
    elif Friendship.objects.filter(
        Q(sender=request.user, recipient=recipient) | Q(sender=recipient, recipient=request.user)
    ).exists():
        messages.error(request, 'A friendship or invitation already exists for this user.')
    else:
        Friendship.objects.create(sender=request.user, recipient=recipient)
        messages.success(request, f'Friend invitation sent to {recipient.username}.')
    return redirect('settings')


@login_required
@require_POST
def friend_request_respond(request, pk, action):
    friendship = get_object_or_404(
        Friendship,
        pk=pk,
        recipient=request.user,
        status=Friendship.STATUS_PENDING,
    )
    if action == 'accept':
        friendship.status = Friendship.STATUS_ACCEPTED
        friendship.responded_at = timezone.now()
        friendship.save(update_fields=['status', 'responded_at'])
        messages.success(request, f'You and {friendship.sender.username} are now friends.')
    elif action == 'decline':
        friendship.delete()
    return redirect('notifications')


@login_required
@require_POST
def friend_remove(request, pk):
    friendship = get_object_or_404(
        Friendship.objects.filter(Q(sender=request.user) | Q(recipient=request.user)),
        pk=pk,
        status=Friendship.STATUS_ACCEPTED,
    )
    friendship.delete()
    messages.success(request, 'Friend removed.')
    return redirect('settings')


@login_required
def notifications(request):
    friend_requests = Friendship.objects.filter(
        recipient=request.user,
        status=Friendship.STATUS_PENDING,
    ).select_related('sender')
    product_requests = ProductEntryRequest.objects.filter(
        recipient=request.user,
        status=ProductEntryRequest.STATUS_PENDING,
    ).select_related('sender')
    recent_responses = ProductEntryRequest.objects.filter(
        sender=request.user,
    ).exclude(status=ProductEntryRequest.STATUS_PENDING).select_related('recipient')[:10]
    return render(request, 'intake/notifications.html', {
        'friend_requests': friend_requests,
        'product_requests': product_requests,
        'recent_responses': recent_responses,
    })


@login_required
@require_POST
@transaction.atomic
def product_request_respond(request, pk, action):
    product_request = get_object_or_404(
        ProductEntryRequest.objects.select_for_update(),
        pk=pk,
        recipient=request.user,
        status=ProductEntryRequest.STATUS_PENDING,
    )
    if action == 'accept':
        entry = FoodEntry.objects.create(
            user=request.user,
            date=product_request.date,
            name=product_request.product_name,
            kcal_per_100g=product_request.kcal_per_100g,
            protein_per_100g=product_request.protein_per_100g,
            weight_g=product_request.weight_g,
            source=FoodEntry.SOURCE_QUICK,
        )
        product_request.status = ProductEntryRequest.STATUS_ACCEPTED
        product_request.created_entry = entry
        messages.success(request, f'{product_request.product_name} was added to your daily intake.')
    elif action == 'decline':
        product_request.status = ProductEntryRequest.STATUS_DECLINED
    else:
        return redirect('notifications')
    product_request.responded_at = timezone.now()
    product_request.save(update_fields=['status', 'created_entry', 'responded_at'])
    return redirect('notifications')


# ── Delete Entry ──────────────────────────────────────────────────────────────

@login_required
@require_POST
def entry_delete(request, pk):
    entry = get_object_or_404(FoodEntry, pk=pk, user=request.user)
    entry_date = entry.date
    entry.delete()
    referer = request.POST.get('next', '')
    if referer:
        return redirect(referer)
    if str(entry_date) == str(date.today()):
        return redirect('home')
    return redirect('calendar_day', day=str(entry_date))


# ── Entry List ────────────────────────────────────────────────────────────────

@login_required
def entry_list(request, nutrient):
    if nutrient not in ('calories', 'protein'):
        return redirect('home')
    today = date.today()
    entries = FoodEntry.objects.filter(user=request.user, date=today)
    return render(request, 'intake/entry_list.html', {
        'entries': entries,
        'nutrient': nutrient,
        'today': today,
    })


# ── Calendar ──────────────────────────────────────────────────────────────────

@login_required
def calendar_view(request):
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # Clamp
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    # All days with entries this month
    first_day = date(year, month, 1)
    last_day = date(year, month, cal_module.monthrange(year, month)[1])

    entries_this_month = FoodEntry.objects.filter(
        user=request.user,
        date__gte=first_day,
        date__lte=last_day,
    ).values('date', 'kcal_per_100g', 'protein_per_100g', 'weight_g')

    day_data = {}
    for e in entries_this_month:
        d = e['date']
        kcal = float(e['kcal_per_100g']) * float(e['weight_g']) / 100
        prot = float(e['protein_per_100g']) * float(e['weight_g']) / 100
        if d not in day_data:
            day_data[d] = {'kcal': 0, 'protein': 0}
        day_data[d]['kcal'] += kcal
        day_data[d]['protein'] += prot

    # Round
    for d in day_data:
        day_data[d]['kcal'] = round(day_data[d]['kcal'], 1)
        day_data[d]['protein'] = round(day_data[d]['protein'], 1)

    # Build calendar weeks
    cal = cal_module.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render(request, 'intake/calendar.html', {
        'year': year,
        'month': month,
        'month_name': cal_module.month_name[month],
        'weeks': weeks,
        'day_data': day_data,
        'today': today,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
    })


@login_required
def calendar_day(request, day):
    try:
        target = date.fromisoformat(day)
    except ValueError:
        return redirect('calendar')

    profile = request.user.profile
    entries = FoodEntry.objects.filter(user=request.user, date=target)
    kcal_total = sum(e.total_kcal for e in entries)
    protein_total = sum(e.total_protein for e in entries)
    kcal_pct = min(round(kcal_total / profile.kcal_goal * 100) if profile.kcal_goal else 0, 100)
    protein_pct = min(round(protein_total / profile.protein_goal * 100) if profile.protein_goal else 0, 100)
    products = QuickAddProduct.objects.filter(product_list__owner=request.user)

    return render(request, 'intake/calendar_day.html', {
        'target': target,
        'today': date.today(),
        'entries': entries,
        'kcal_total': kcal_total,
        'protein_total': protein_total,
        'kcal_goal': profile.kcal_goal,
        'protein_goal': profile.protein_goal,
        'kcal_pct': kcal_pct,
        'protein_pct': protein_pct,
        'products': products,
    })


# ── Settings ──────────────────────────────────────────────────────────────────

@login_required
def settings_view(request):
    profile = request.user.profile
    if request.method == 'POST':
        if request.POST.get('setting_type') == 'appearance':
            profile.dark_mode = request.POST.get('dark_mode') == 'on'
            profile.save(update_fields=['dark_mode'])
        else:
            try:
                kcal_goal = int(request.POST.get('kcal_goal', profile.kcal_goal))
                protein_goal = int(request.POST.get('protein_goal', profile.protein_goal))
                if kcal_goal > 0:
                    profile.kcal_goal = kcal_goal
                if protein_goal > 0:
                    profile.protein_goal = protein_goal
                profile.save(update_fields=['kcal_goal', 'protein_goal'])
            except (ValueError, TypeError):
                pass
        return redirect('settings')
    friendships = _accepted_friendships(request.user)
    outgoing_requests = Friendship.objects.filter(
        sender=request.user,
        status=Friendship.STATUS_PENDING,
    ).select_related('recipient')
    return render(request, 'intake/settings.html', {
        'profile': profile,
        'friendships': friendships,
        'outgoing_requests': outgoing_requests,
    })
