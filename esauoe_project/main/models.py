from django.db import models
from django.utils import timezone


class ESAMember(models.Model):
    full_name = models.CharField(max_length=200)
    admission_number = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=100)
    admission_year = models.IntegerField()
    graduation_year = models.IntegerField()
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    mpesa_number = models.CharField(max_length=15)
    batch_number = models.CharField(max_length=50, unique=True)
    membership_date = models.DateTimeField(default=timezone.now)
    payment_status = models.BooleanField(default=False)
    transaction_id = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.full_name} - {self.batch_number}"