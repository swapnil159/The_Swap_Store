from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.utils import timezone
from django.shortcuts import redirect
from .forms import CheckoutForm, CouponForm
from .models import Item, OrderItem, Order, BillingAddress, Payment, Coupon

import stripe
stripe.api_key = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"


# Create your views here.

class HomeView(ListView):
    model = Item
    paginate_by = 10
    template_name = "home-page.html"

class OrderSummaryView(LoginRequiredMixin, View):
    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user,ordered=False)
            context = {
                'object' : order
            }
            return render(self.request, 'order_summary.html', context)
        except ObjectDoesNotExist:
            messages.warning(self.request, "You do not have an active order")
            return redirect("/")

class ItemDetailView(DetailView):
    model = Item
    template_name = "product-page.html"

class CheckoutView(View):

    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            form = CheckoutForm()
            context = {
                'form' : form,
                'couponform' : CouponForm(),
                'order' : order,
                'DISPLAY_COUPON_FORM' : True
            }
            return render(self.request, "checkout-page.html", context)
        except ObjectDoesNotExist:
            messages.info(request, "You do not have an active order")
            return redirect("core:checkout")
        
    
    def post(self, *args, **kwargs):
        form = CheckoutForm(self.request.POST or None)
        try:
            order = Order.objects.get(user=self.request.user,ordered=False)
            if form.is_valid():
                street_address = form.cleaned_data.get('street_address')
                apartment_address = form.cleaned_data.get('apartment_address')
                country = form.cleaned_data.get('country')
                zip = form.cleaned_data.get('zip')
                # TODO : add functionalities
                #same_shipping_address = form.cleaned_data.get('same_shipping_address')
                #save_info = form.cleaned_data.get('save_info')
                payment_option = form.cleaned_data.get('payment_option')
                billing_address = BillingAddress(
                    user = self.request.user,
                    street_address = street_address,
                    apartment_address = apartment_address,
                    country = country,
                    zip = zip
                )
                billing_address.save()
                order.billing_address = billing_address
                order.save()
                
                if payment_option == 'S':
                    return redirect('core:payment', payment_option="stripe")
                elif payment_option=='P':
                    return redirect('core:payment', payment_option="paypal")
                else:
                    messages.warning(self.request, "Invalid payment option selected.")
                    return redirect('core:checkout')
        except ObjectDoesNotExist:
            messages.warning(self.request, "You do not have an active order")
            return redirect("core:order-summary")

def products(request):
    context = {
        "items" : Item.objects.all()
    }
    return render(request, "product-page.html", context)

class PaymentView(View):
    def get(self, *args, **kwargs):
        order=Order.objects.get(user=self.request.user, ordered=False)
        if order.billing_address:
            context = {
                'order' : order,
                'DISPLAY_COUPON_FORM' : False
            }
            return render(self.request, 'payment.html', context)
        else:
            messages.warning(self.request, "You do not have a billing address")
            return redirect("core:checkout")

    def post(self, *args, **kwargs):
        order=Order.objects.get(user=self.request.user, ordered=False)
        token = self.request.POST.get('stripeToken')
        amount=int(order.get_total_amount() * 100)


        try:
            charge = stripe.Charge.create(
                amount=amount,  #cents
                currency="usd",
                source=token,
            )

            #create the payment
            payment = Payment()
            payment.stripe_charge_id = charge['id']
            payment.user = self.request.user
            payment.amount = order.get_total_amount()
            payment.save()

            #assign the payment to order
            order_items = order.items.all()
            order_items.update(ordered=True)
            for item in order_items:
                item.save()

            order.ordered = True
            order.payment = payment
            order.save()

            messages.success(self.request, "Your order was successful.")
            return redirect("/")

        except stripe.error.CardError as e:
            # Since it's a decline, stripe.error.CardError will be caught
            messages.warning(self.request, f"{e.error.message}")
            return redirect("/")
        except stripe.error.RateLimitError as e:
            # Too many requests made to the API too quickly
            messages.warning(self.request, "Rate limit error")
            return redirect("/")
        except stripe.error.InvalidRequestError as e:
            # Invalid parameters were supplied to Stripe's API
            messages.warning(self.request, "Invalid parameters")
            return redirect("/")
        except stripe.error.AuthenticationError as e:
            # Authentication with Stripe's API failed
            # (maybe you changed API keys recently)
            messages.warning(self.request, "Not authenticated")
            return redirect("/")
        except stripe.error.APIConnectionError as e:
            # Network communication with Stripe failed
            messages.warning(self.request, "API connection error")
            return redirect("/")
        except stripe.error.StripeError as e:
            # Display a very generic error to the user, and maybe send
            # yourself an email
            messages.warning(self.request, "Something went wrong. You have not been charged. Please try again")
            return redirect("/")
        except Exception as e:
            # Send us an email
            messages.warning(self.request, "There was a serious error. We have been notified")
            return redirect("/")



@login_required
def add_to_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_item, created = OrderItem.objects.get_or_create(
        item=item,
        user = request.user,
        ordered=False
    )
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # Check if ordered item exists in order
        if order.items.filter(item__slug=item.slug).exists():
            order_item.quantity += 1
            order_item.save()
            messages.info(request, "The quantity of this item was updated")
            return redirect("core:order-summary")
        else:
            messages.info(request, "This item was added to your cart")
            order.items.add(order_item)
            return redirect("core:order-summary")
    else:
        ordered_date = timezone.now()
        order = Order.objects.create(user=request.user, ordered_date=ordered_date)
        order.items.add(order_item)
        messages.info(request, "This item was added to your cart")
        return redirect("core:order-summary")


@login_required
def remove_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # Check if ordered item exists in order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user = request.user,
                ordered=False
            )[0]
            order.items.remove(order_item)
            order_item.delete()
            messages.info(request, "This item was removed from your cart")
            return redirect("core:order-summary")
        else:
            messages.info(request, "Your cart does not contain this item")
            return redirect("core:product", slug=slug)
    else:
        messages.info(request, "You have no active order")
        return redirect("core:product", slug=slug)

@login_required
def remove_single_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # Check if ordered item exists in order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user = request.user,
                ordered=False
            )[0]

            if order_item.quantity > 1:
                order_item.quantity -= 1
                order_item.save()
            else:
                order.items.remove(order_item)
                order_item.delete()
            messages.info(request, "This item was updated in your cart")
            return redirect("core:order-summary")
        else:
            messages.info(request, "Your cart does not contain this item")
            return redirect("core:product", slug=slug)
    else:
        messages.info(request, "You have no active order")
        return redirect("core:product", slug=slug)


def get_coupon(request, code):
    try:
        coupon = Coupon.objects.get(code=code)
        return coupon
    except ObjectDoesNotExist:
        messages.info(request, "This coupon does not exist")
        return redirect("core:checkout")

class AddCouponView(View):
    def post(self, *args, **kwargs):
        form = CouponForm(request.POST or None)
        if form.is_valid():
            try:
                code = form.cleaned_data.get('code')
                order = Order.objects.get(user=request.user, ordered=False)
                order.coupon = get_coupon(request, code)
                order.save()
                messages.success(request, "Coupon successfully added")
                return redirect("core:checkout")
            except ObjectDoesNotExist:
                messages.info(request, "You do not have an active order")
                return redirect("core:checkout")