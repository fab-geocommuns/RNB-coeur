import factory
from batid.models import Building, Address
from batid.services.rnb_id import generate_rnb_id


class BuildingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Building

    source = "bdtopo"
    rnb_id = generate_rnb_id()


class AddressAutransFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    id = factory.Faker("uuid4")
    source = "BAN"
    city_name = "Autrans-Méaudre en Vercors"
    city_zipcode = "38112"
