from batid.exceptions import PlotUnknown
from batid.models import Building, Plot
from django.contrib.gis.db.models.functions import Area, Intersection
from django.db.models import Case, F, Func, When
from django.db.models.lookups import Exact


def get_buildings_on_plot(plot_id: str):
    try:
        plot = Plot.objects.get(id=plot_id)
    except Plot.DoesNotExist:
        raise PlotUnknown(f"plot id {plot_id} is unknown to the RNB")

    bdg_qs = (
        Building.objects.filter(is_active=True)
        .filter(shape__intersects=plot.shape)
        .annotate(
            bdg_cover_ratio=Case(
                When(
                    Exact(
                        Func(F("shape"), function="ST_AREA"),
                        0,
                    ),
                    then=1.0,
                ),
                default=Area(Intersection("shape", plot.shape)) / Area("shape"),
            )
        )
        .order_by("-bdg_cover_ratio", "rnb_id")
    )
    return bdg_qs
