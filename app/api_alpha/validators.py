from rest_framework import serializers

from batid.models import Building


def ads_validate_rnbid(rnb_id):

    if not Building.objects.filter(rnb_id=rnb_id).exists():
        raise serializers.ValidationError(f"L'ID-RNB \"{rnb_id}\" n'existe pas.")


def bdg_is_active(rnb_id: str):

    bdg = Building.objects.filter(rnb_id=rnb_id).first()

    if bdg is None:
        raise serializers.ValidationError(f"L'ID-RNB \"{rnb_id}\" n'existe pas.")

    if not bdg.is_active:
        raise serializers.ValidationError(f"L'ID-RNB \"{rnb_id}\" n'est pas actif.")


class BdgInADSValidator:
    def __call__(self, value):

        rnb_id = value.get("rnb_id", None)
        shape = value.get("shape", None)

        if rnb_id is None and shape is None:
            raise serializers.ValidationError("Soit 'rnb_id' soit 'shape' est requis.")

        if rnb_id is not None and shape is not None:
            raise serializers.ValidationError(
                "Vous ne pouvez pas fournir à la fois un 'rnb_id' et une forme, vous devez supprimer la forme."
            )


class ADSValidator:
    def __call__(self, data):
        self.validate_bdg_once(data)
        self.validate_has_bdg(data)

    def validate_has_bdg(self, data):
        if data.get("buildings_operations") is None:
            raise serializers.ValidationError(
                {"buildings_operations": "Ce champ est requis."}
            )
        if len(data["buildings_operations"]) == 0:
            raise serializers.ValidationError(
                {"buildings_operations": "Au moins un bâtiment est requis."}
            )

    def validate_bdg_once(self, data):
        if data.get("buildings_operations") is None:
            return

        rnb_ids = [
            op["rnb_id"]
            for op in data["buildings_operations"]
            if "rnb_id" in op and op["rnb_id"] is not None
        ]
        if len(rnb_ids) != len(set(rnb_ids)):
            raise serializers.ValidationError(
                {
                    "buildings_operations": "Un identifiant RNB ne peut être présent qu'une seule fois dans un ADS."
                }
            )
