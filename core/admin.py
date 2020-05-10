from django.contrib import admin
from .models import Order, Item, OrderItem, Payment, BillingAddress

# Register your models here.
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Item)
admin.site.register(BillingAddress)
admin.site.register(Payment)
