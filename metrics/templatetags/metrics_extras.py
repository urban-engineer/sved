from django import template


register = template.Library()


@register.simple_tag
def size_comparison(source_file_size: int, compressed_file_size: int) -> float:
    return round(float(compressed_file_size) / float(source_file_size) * 100, 2)


@register.filter
def round_metric(metric: float) -> float:
    return round(metric, 2)


@register.filter
def score_to_color_psnr(score: float) -> str:
    if score > 45:
        return "table-warning"
    elif score < 35:
        return "table-danger"
    else:
        return "table-success"

@register.filter
def score_to_color_ms_ssim(score: float) -> str:
    if score > .99:
        return "table-success"
    elif score >= 0.88:
        return "table-warning"
    else:
        return "table-danger"
