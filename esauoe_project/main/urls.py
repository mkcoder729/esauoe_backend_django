from django.urls import path
from . import views

urlpatterns = [
    # Main pages
    path('', views.index, name='index'),
    path('wie/', views.wie, name='wie'),
    path('news/', views.news, name='news'),

    # Member registration and payment APIs
    path('api/register-member/', views.register_member, name='register_member'),
    path('api/initiate-payment/', views.initiate_mpesa_payment, name='initiate_payment'),
    path('api/mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),
    path('api/update-payment-status/', views.update_payment_status, name='update_payment_status'),
    path('api/send-confirmation-email/', views.send_confirmation_email_api, name='send_confirmation_email'),

    # PDF generation
    path('membership-pdf/<int:member_id>/', views.generate_membership_pdf, name='membership_pdf'),

    # Admin and data APIs
    path('api/members-data/', views.get_members_data, name='members_data'),
    path('api/simulate-payment/', views.simulate_payment_success, name='simulate_payment'),
]