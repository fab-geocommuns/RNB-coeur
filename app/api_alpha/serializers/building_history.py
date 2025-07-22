from rest_framework import serializers
from api_alpha.serializers.serializers import RNBIdField, ExtIdSerializer
from batid.utils.misc import ext_ids_equal


class PlainAddressSerializer(serializers.Serializer):
    """
    Serializer for address data, used in the BuildingWithHistorySerializer.
    It is not a ModelSerializer, but a plain Serializer.
    The fields must be a copy of the AddressSerializer fields.
    """

    id = serializers.CharField()
    source = serializers.CharField()
    street_number = serializers.CharField()
    street_rep = serializers.CharField()
    street = serializers.CharField()
    city_name = serializers.CharField()
    city_zipcode = serializers.CharField()
    city_insee_code = serializers.CharField()


class BuildingEventSerializer(serializers.Serializer):
    def to_representation(self, instance):

        instance_copy = instance.copy()

        if (
            instance_copy["type"] == "update"
            and "previous_version" in instance_copy["details"]
            and "current_version" in instance_copy["details"]
        ):

            updated_fields = []

            previous = instance_copy["details"]["previous_version"]
            current = instance_copy["details"]["current_version"]

            if previous.get("status") != current.get("status"):
                updated_fields.append("status")

            if previous.get("shape") != current.get("shape"):
                updated_fields.append("shape")

            if not ext_ids_equal(previous.get("ext_ids"), current.get("ext_ids")):
                updated_fields.append("ext_ids")

            prev_addresses = previous.get("addresses_id")
            curr_addresses = current.get("addresses_id")

            if (
                prev_addresses
                and curr_addresses
                and set(prev_addresses) != set(curr_addresses)
            ):
                updated_fields.append("addresses")

            instance_copy["details"]["updated_fields"] = updated_fields

            # remove the previous_version and current_version fields
            del instance_copy["details"]["previous_version"]
            del instance_copy["details"]["current_version"]

        elif (
            instance_copy["type"] == "merge"
            and instance_copy["details"].get("merge_role") == "parent"
        ):
            instance_copy["details"]["updated_fields"] = ["is_active"]
        elif (
            instance_copy["type"] == "split"
            and instance_copy["details"].get("split_role") == "parent"
        ):
            instance_copy["details"]["updated_fields"] = ["is_active"]

        return instance_copy


class BuildingHistorySerializer(serializers.Serializer):
    rnb_id = RNBIdField()
    is_active = serializers.BooleanField()
    shape = serializers.JSONField()
    status = serializers.CharField()
    event = BuildingEventSerializer()
    ext_ids = ExtIdSerializer(many=True)
    updated_at = serializers.DateTimeField()
    addresses = PlainAddressSerializer(many=True, read_only=True)
