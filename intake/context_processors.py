from .models import Friendship, ProductEntryRequest


def notification_count(request):
    if not request.user.is_authenticated:
        return {'notification_count': 0}
    return {
        'notification_count': (
            Friendship.objects.filter(
                recipient=request.user,
                status=Friendship.STATUS_PENDING,
            ).count()
            + ProductEntryRequest.objects.filter(
                recipient=request.user,
                status=ProductEntryRequest.STATUS_PENDING,
            ).count()
        )
    }
