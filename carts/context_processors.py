from carts.views import _cart_id
from .models import CartItem, Cart

def counter(request):
    cart_count = 0
    if 'admin' in request.path:
        return {}
    else:
        try:
            cart = Cart.objects.filter(cart_id=_cart_id(request))
            cart_item = CartItem.objects.all().filter(cart=cart[:1])
            for cart_items in cart_item:
                cart_count = cart_items.quantity
        except Cart.DoesNotExist:
            cart_count = 0
            
    return dict(cart_count=cart_count)