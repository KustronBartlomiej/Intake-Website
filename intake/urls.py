from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('detail/<str:nutrient>/', views.detail, name='detail'),
    path('detail/<str:nutrient>/goal/', views.set_goal, name='set_goal'),
    path('detail/<str:nutrient>/entries/', views.entry_list, name='entry_list'),
    path('add/', views.add_meal, name='add_meal'),
    path('add/<str:target_date>/', views.add_meal, name='add_meal_date'),
    path('quick-add/', views.quick_add, name='quick_add'),
    path('quick-add/product/create/', views.quick_add_product_create, name='product_create'),
    path('quick-add/product/<int:pk>/delete/', views.quick_add_product_delete, name='product_delete'),
    path('quick-add/product/<int:pk>/use/', views.quick_add_use, name='quick_add_use'),
    path('entries/<int:pk>/delete/', views.entry_delete, name='entry_delete'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/<str:day>/', views.calendar_day, name='calendar_day'),
    path('settings/', views.settings_view, name='settings'),
]
