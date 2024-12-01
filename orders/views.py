import datetime
import os
from django.shortcuts import redirect, render

from carts.models import CartItem
from orders.forms import OrderForm
from orders.models import Order, OrderProduct, Payment

# email
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage


import requests
import json


from store.models import Product
# Create your views here.

        
def payments(request):
    return render(request, 'orders/payments.html')

def place_order(request, total=0, quantity=0):
    current_user = request.user
    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()
    
    
    if cart_count <= 0:
        return redirect('store')
    
    grand_total = 0
    tax = 0
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity
    tax = (2 * total)/100
    grand_total = total + tax   
    
    
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            data= Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.address_line_1 = form.cleaned_data['address_line_1']
            data.address_line_2 = form.cleaned_data['address_line_2']
            data.state = form.cleaned_data['state']
            data.city = form.cleaned_data['city']
            data.country = form.cleaned_data['country']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get('REMOTE_ADDR')
            data.save()
            
            #generate order number
            yr = int(datetime.date.today().strftime('%Y'))
            dt = int(datetime.date.today().strftime('%d'))
            mt = int(datetime.date.today().strftime('%m'))
            d = datetime.date(yr,mt,dt)
            current_date = d.strftime("%Y%d%m")
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()
            
            order = Order.objects.get(user=current_user, is_ordered=False, order_number=order_number)
            context = {
                'order': order,
                'cart_items': cart_items,
                'total': total,
                'tax': tax,
                'grand_total': grand_total
            }
            return render(request, 'orders/payments.html', context) 
        else:
            return redirect('checkout')
        
def initiate_payment(request):
    url = "https://a.khalti.com/api/v2/epayment/initiate/"
    
    KHALTI_API_KEY = os.getenv('KHALTI_SECRET_KEY')
    print(KHALTI_API_KEY)
    return_url = request.POST.get('return_url')
    purchase_order_id = request.POST.get('purchase_order_id')
    amount = request.POST.get('amount')
    amount = float(amount)
    amount = int(amount * 100)
    user = request.user
    
    print(return_url, purchase_order_id, amount)
    
    payload = json.dumps({
        "return_url": "http://127.0.0.1:8000/" + return_url ,
        "website_url": "http://127.0.0.1:8000/",
        "amount": "100000",
        "purchase_order_id": purchase_order_id,
        "purchase_order_name": "test",
        "customer_info": {
        "name": user.first_name + " " + user.last_name,
        "email": user.email,
        "phone": user.phone_number
        }
    })
    headers = {
        'Authorization':  f'key {KHALTI_API_KEY}',
        'Content-Type': 'application/json',
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    new_res = json.loads(response.text)
    print(new_res)
    return redirect(new_res['payment_url'])
        
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import render
import requests
import json

def verify_payment(request):
    url = "https://a.khalti.com/api/v2/epayment/lookup/"
    
    KHALTI_API_KEY = os.getenv('KHALTI_SECRET_KEY')

    purchase_order_id = request.GET.get('purchase_order_id')  # Ensure this parameter is present
    pidx = request.GET.get('pidx')

    headers = {
        'Authorization':  f'key {KHALTI_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = json.dumps({'pidx': pidx})

    try:
        # Make the API request to check payment status
        response = requests.post(url, headers=headers, data=payload)
        new_res = response.json()  # Get the response as JSON

        status = new_res.get('status', None)
        # Handle the order processing logic
        order = Order.objects.get(user=request.user, order_number=purchase_order_id)

        if order.is_ordered:
            # Order is already completed, display the confirmation page
            ordered_products = OrderProduct.objects.filter(order_id=order.id)
            subtotal = sum(item.product_price * item.quantity for item in ordered_products)
            payment = Payment.objects.get(payment_id=new_res['transaction_id'])
            context = {
                'order': order,
                'orderProduct': ordered_products,
                'payment': payment,
                'subtotal': subtotal,
            }
            return render(request, 'orders/order_complete.html', context)
        else:
            # Process payment and move cart items to Order Product table
            amount_paid = int(new_res['total_amount'] / 100)  # Convert from paise to rupees
            payment = Payment(
                user=request.user,
                payment_id=new_res['transaction_id'],
                payment_method="Khalti",
                amount_paid=amount_paid,
                status=status,
            )
            payment.save()

            order.payment = payment
            order.is_ordered = True
            order.save()

            # Move cart items to Order Product table and update stock
            cart_items = CartItem.objects.filter(user=request.user)
            for item in cart_items:
                orderproduct = OrderProduct(
                    order_id=order.id,
                    payment=payment,
                    user_id=request.user.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    product_price=item.product.price,
                    ordered=True
                )
                orderproduct.save()

                # Handle variations of products in the cart
                cart_item = CartItem.objects.get(id=item.id)
                product_variation = cart_item.variation.all()
                orderproduct.variations.set(product_variation)
                orderproduct.save()

                # Reduce product stock
                product = Product.objects.get(id=item.product_id)
                product.stock -= item.quantity
                product.save()

            # Clear the cart
            CartItem.objects.filter(user=request.user).delete()

            # Send order confirmation email
            mail_subject = "Thank You For Your Order"
            message = render_to_string('orders/order_received_email.html', {'user': request.user, 'order': order})
            to_mail = request.user.email
            send_email = EmailMessage(mail_subject, message, to=[to_mail])
            send_email.send()

            # Calculate subtotal
            ordered_products = OrderProduct.objects.filter(order_id=order.id)
            subtotal = sum(item.product_price * item.quantity for item in ordered_products)

            # Prepare context and render the order completion page
            context = {
                'order': order,
                'orderProduct': ordered_products,
                'payment': payment,
                'subtotal': subtotal,
            }
            return render(request, 'orders/order_complete.html', context)

    except requests.exceptions.RequestException as e:
        # Handle API request errors
        return render(request, 'orders/order_failure.html', {'message': f"Error processing payment: {str(e)}"})
    except ObjectDoesNotExist:
        # Handle cases where order or payment is not found
        return render(request, 'orders/order_failure.html', {'message': 'Order or payment not found.'})
    except Exception as e:
        # Catch any other unexpected errors
        return render(request, 'orders/order_failure.html', {'message': f"An unexpected error occurred: {str(e)}"})

def order_complete(request):
    return render(request, 'orders/order_complete.html')

    