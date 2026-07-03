import json
import calendar as cal_module
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import FoodEntry, ProductList, QuickAddProduct


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
    today = date.today()
    lists = ProductList.objects.filter(owner=request.user).annotate(product_count=Count('products'))
    recent = FoodEntry.objects.filter(user=request.user, date=today, source=FoodEntry.SOURCE_QUICK)
    return render(request, 'intake/product_lists.html', {
        'lists': lists,
        'recent': recent,
        'today': today,
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
    products = plist.products.all()
    recent = FoodEntry.objects.filter(user=request.user, date=today, source=FoodEntry.SOURCE_QUICK)
    return render(request, 'intake/product_list_detail.html', {
        'plist': plist,
        'products': products,
        'recent': recent,
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
def quick_add_use(request, pk):
    product = get_object_or_404(QuickAddProduct, pk=pk, product_list__owner=request.user)
    weight_g = _parse_decimal(request.POST.get('weight_g')) or product.default_weight_g

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

    if str(entry_date) != str(date.today()):
        return redirect('calendar_day', day=str(entry_date))
    return redirect('product_list_detail', pk=product.product_list_id)


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
        try:
            kcal_goal = int(request.POST.get('kcal_goal', profile.kcal_goal))
            protein_goal = int(request.POST.get('protein_goal', profile.protein_goal))
            if kcal_goal > 0:
                profile.kcal_goal = kcal_goal
            if protein_goal > 0:
                profile.protein_goal = protein_goal
            profile.save()
        except (ValueError, TypeError):
            pass
        return redirect('settings')
    return render(request, 'intake/settings.html', {'profile': profile})
