from django import template
from datetime import timedelta
register = template.Library()

@register.filter
def minutes_to_hours_minutes(minutes):
    try:
        total_minutes = int(minutes)
    except (ValueError, TypeError):
        return minutes  # Return original value if it's not a valid integer
        
    hours = total_minutes // 60
    remaining_minutes = total_minutes % 60
    
    if hours > 0:
        if remaining_minutes == 0:
            return f"{hours}h"
        return f"{hours}h {remaining_minutes}m"
    return f"{int(minutes)}m"

@register.filter
def rounddelta(delta:timedelta, to=1):
    delta = timedelta(seconds=round(delta.total_seconds(), to))
    return delta